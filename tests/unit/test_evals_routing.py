"""
Testes de `data_agents/evals/routing.py` — o eval de roteamento.

Duas frentes, ambas OFFLINE (o eval de verdade fala com a API e roda por
`make eval-routing`, fora do CI, que não guarda credenciais):

  - TestDatasetLint: o dataset cita agentes que existem de fato no registry.
    Sem isto, um agente renomeado transformaria o eval em falso negativo
    silencioso — reprovaria por nome errado, não por roteamento ruim.

  - TestScoreCase / TestSummarize: o scoring tem dente. O teste que importa é
    `test_fallback_completo_reprova_todos_os_casos`: se ele algum dia passar,
    o eval inteiro perdeu o sentido, porque o bug de 2026-09-13 (fallback
    carregando os 24 agentes em toda query) voltaria a marcar 100%.
"""

from __future__ import annotations

import pytest

from data_agents.evals.routing import (
    DEFAULT_MAX_AGENTS,
    RoutingCase,
    RoutingResult,
    is_fallback_reason,
    load_cases,
    score_case,
    summarize,
)


@pytest.fixture(scope="module")
def cases() -> list[RoutingCase]:
    return load_cases()


@pytest.fixture(scope="module")
def registry_names() -> set[str]:
    from data_agents.agents.loader import preload_registry

    return set(preload_registry())


# ─── Lint do dataset contra o registry real ──────────────────────────────────


class TestDatasetLint:
    def test_dataset_carrega(self, cases: list[RoutingCase]) -> None:
        assert len(cases) >= 20, (
            f"dataset pequeno demais ({len(cases)} casos) — com poucos casos um "
            "único acerto/erro move a accuracy mais que o gate de 90% tolera"
        )

    def test_todo_agente_citado_existe_no_registry(
        self, cases: list[RoutingCase], registry_names: set[str]
    ) -> None:
        problemas = []
        for case in cases:
            fantasmas = sorted(case.mentioned_agents - registry_names)
            if fantasmas:
                problemas.append(f"{case.id}: {fantasmas}")
        assert not problemas, (
            "casos citam agentes que não existem em data_agents/agents/registry/ "
            "— renomeação de agente sem atualizar o dataset:\n" + "\n".join(problemas)
        )

    def test_geral_nunca_e_esperado(self, cases: list[RoutingCase]) -> None:
        """`geral` está em _NEVER_DELEGATED — esperá-lo seria expectativa impossível."""
        ofensores = [c.id for c in cases if "geral" in set(c.expect_any) | set(c.expect_all)]
        assert not ofensores, (
            f"casos esperam o agente 'geral', que o dispatcher filtra por contrato "
            f"(_NEVER_DELEGATED): {ofensores}"
        )

    def test_todo_caso_tem_criterio(self, cases: list[RoutingCase]) -> None:
        """Caso sem expectativa e sem teto apertado não mede nada."""
        vazios = [
            c.id
            for c in cases
            if not c.expect_any
            and not c.expect_all
            and not c.forbid
            and c.max_agents >= DEFAULT_MAX_AGENTS * 2
        ]
        assert not vazios, f"casos sem critério de aprovação (aprovariam sempre): {vazios}"

    def test_expectativa_e_proibicao_nao_se_contradizem(self, cases: list[RoutingCase]) -> None:
        conflitos = []
        for case in cases:
            esperados = set(case.expect_any) | set(case.expect_all)
            colisao = sorted(esperados & set(case.forbid))
            if colisao:
                conflitos.append(f"{case.id}: {colisao}")
        assert not conflitos, "caso espera e proíbe o mesmo agente:\n" + "\n".join(conflitos)


# ─── Scoring ─────────────────────────────────────────────────────────────────


def _case(**kwargs) -> RoutingCase:
    base = {"id": "t", "prompt": "p"}
    base.update(kwargs)
    return RoutingCase(**base)


class TestScoreCase:
    def test_selecao_correta_e_estreita_passa(self) -> None:
        case = _case(expect_any=["databricks-engineer"], forbid=["fabric-engineer"])
        passed, failures = score_case(case, ["databricks-engineer"])
        assert passed
        assert failures == []

    def test_expect_any_aceita_qualquer_um(self) -> None:
        case = _case(expect_any=["sqlserver-to-databricks", "migration-expert"])
        assert score_case(case, ["migration-expert"])[0]
        assert score_case(case, ["sqlserver-to-databricks"])[0]

    def test_expect_any_nao_atendido_reprova(self) -> None:
        case = _case(expect_any=["data-quality-steward"])
        passed, failures = score_case(case, ["databricks-engineer"])
        assert not passed
        assert "expect_any" in failures[0]

    def test_expect_all_parcial_reprova(self) -> None:
        case = _case(expect_all=["databricks-engineer", "data-quality-steward"])
        passed, failures = score_case(case, ["databricks-engineer"])
        assert not passed
        assert "data-quality-steward" in failures[0]

    def test_forbid_reprova_mesmo_com_expect_atendido(self) -> None:
        """S6 em forma de teste: acertar o steward não perdoa arrastar engenharia junto."""
        case = _case(expect_any=["data-quality-steward"], forbid=["databricks-engineer"])
        passed, failures = score_case(case, ["data-quality-steward", "databricks-engineer"])
        assert not passed
        assert "proibido" in failures[0]

    def test_selecao_larga_reprova(self) -> None:
        case = _case(expect_any=["databricks-engineer"], max_agents=3)
        selected = ["databricks-engineer", "a", "b", "c"]
        passed, failures = score_case(case, selected)
        assert not passed
        assert "larga demais" in failures[0]

    def test_caso_so_de_largura_passa_quando_estreito(self) -> None:
        case = _case(max_agents=5)
        assert score_case(case, ["a", "b", "c"])[0]

    def test_fallback_completo_reprova_todos_os_casos(
        self, cases: list[RoutingCase], registry_names: set[str]
    ) -> None:
        """O teste que dá razão de existir ao eval.

        Simula exatamente o bug de 2026-09-13: `select_agents` cai no fallback e
        devolve TODOS os agentes delegáveis. Todo caso do dataset tem que
        reprovar — se algum passar, o eval marcaria o roteamento como saudável
        justamente quando ele está morto.
        """
        todos = sorted(registry_names - {"geral"})
        assert len(todos) > DEFAULT_MAX_AGENTS, "registry pequeno demais para o cenário"

        sobreviventes = [c.id for c in cases if score_case(c, todos)[0]]
        assert not sobreviventes, (
            "estes casos APROVARIAM com o fallback carregando o registry inteiro — "
            f"o eval estaria cego ao bug que motivou sua criação: {sobreviventes}"
        )


class TestIsFallbackReason:
    @pytest.mark.parametrize(
        "reason",
        ["no_content", "invalid_json", "empty_selection"],
    )
    def test_razoes_exatas(self, reason: str) -> None:
        assert is_fallback_reason(reason)

    @pytest.mark.parametrize(
        "reason",
        ["http_error:429", "http_error:500", "network_error:URLError", "unexpected:KeyError"],
    )
    def test_razoes_com_sufixo(self, reason: str) -> None:
        assert is_fallback_reason(reason)

    def test_razao_de_decisao_real_nao_e_fallback(self) -> None:
        assert not is_fallback_reason("query menciona Spark e Unity Catalog")
        assert not is_fallback_reason("")

    def test_cobre_todos_os_returns_de_fallback_do_dispatcher(self) -> None:
        """Guarda contra drift: um novo caminho de fallback no dispatcher que
        este módulo não reconheça viraria fallback_rate subestimado."""
        import inspect

        from data_agents.agents import dispatcher

        fonte = inspect.getsource(dispatcher.select_agents)
        # Toda linha que devolve o fallback tem a forma:
        #   return _all_delegatable(available), 0.0, "<reason>"
        import re

        razoes = re.findall(r'_all_delegatable\(available\),\s*0\.0,\s*(?:f?")([^"{]*)', fonte)
        assert razoes, "não achei nenhum return de fallback — o padrão mudou?"
        nao_reconhecidas = [r for r in razoes if not is_fallback_reason(r)]
        assert not nao_reconhecidas, (
            f"o dispatcher devolve razões de fallback que routing.py não reconhece: "
            f"{nao_reconhecidas} — atualize _FALLBACK_REASONS/_FALLBACK_PREFIXES"
        )


class TestSummarize:
    def _result(self, passed: bool, fallback: bool, n_sel: int, n_final: int) -> RoutingResult:
        return RoutingResult(
            case_id="x",
            passed=passed,
            selected=["a"] * n_sel,
            final=["a"] * n_final,
            confidence=0.9,
            reason="r",
            used_fallback=fallback,
            failures=[],
        )

    def test_vazio_nao_divide_por_zero(self) -> None:
        m = summarize([])
        assert m["total"] == 0
        assert m["routing_accuracy"] == 0.0

    def test_metricas_basicas(self) -> None:
        m = summarize(
            [
                self._result(True, False, 2, 2),
                self._result(True, False, 1, 3),
                self._result(False, True, 24, 24),
                self._result(True, False, 1, 1),
            ]
        )
        assert m["total"] == 4
        assert m["passed"] == 3
        assert m["routing_accuracy"] == 0.75
        assert m["fallback_rate"] == 0.25
        assert m["avg_selected"] == 7.0
        assert m["avg_final"] == 7.5


# ─── Carga / validação do YAML ───────────────────────────────────────────────


class TestLoadCases:
    def _write(self, tmp_path, body: str):
        path = tmp_path / "cases.yaml"
        path.write_text(body, encoding="utf-8")
        return path

    def test_id_duplicado_levanta(self, tmp_path) -> None:
        path = self._write(
            tmp_path,
            "cases:\n  - id: a\n    prompt: x\n  - id: a\n    prompt: y\n",
        )
        with pytest.raises(ValueError, match="duplicado"):
            load_cases(path)

    def test_campo_obrigatorio_faltando_levanta(self, tmp_path) -> None:
        path = self._write(tmp_path, "cases:\n  - id: a\n")
        with pytest.raises(ValueError, match="prompt"):
            load_cases(path)

    def test_max_agents_invalido_levanta(self, tmp_path) -> None:
        path = self._write(tmp_path, "cases:\n  - id: a\n    prompt: x\n    max_agents: 0\n")
        with pytest.raises(ValueError, match="max_agents"):
            load_cases(path)

    def test_chave_cases_ausente_levanta(self, tmp_path) -> None:
        path = self._write(tmp_path, "queries: []\n")
        with pytest.raises(ValueError, match="cases"):
            load_cases(path)

    def test_defaults_aplicados(self, tmp_path) -> None:
        path = self._write(tmp_path, "cases:\n  - id: a\n    prompt: x\n")
        case = load_cases(path)[0]
        assert case.max_agents == DEFAULT_MAX_AGENTS
        assert case.expect_any == []
        assert case.forbid == []
