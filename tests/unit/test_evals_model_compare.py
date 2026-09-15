"""
Testes offline do eval de comparação de modelos (data_agents/evals/model_compare.py).

Sem rede, sem SDK. Cobrem as funções puras que dão dente ao eval: carga e
validação do dataset, scoring por grupos OR, atribuição de tools a agentes
por janela de logs, sumário e a renderização do --compare.

Os fixtures de log reproduzem a 5ª rodada real do caso Genie Ontology
(2026-09-15 01:24–01:27): especialista fez Grep×3 e não buscou; o Supervisor
tentou `business-analyst` (fora do `agents=`, janela nunca fechou) e depois
`general-purpose`, que chamou firecrawl. Se a atribuição não reconstruir isso,
o eval não responde à pergunta que o motivou.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_agents.evals import model_compare as mc

_REPO = Path(__file__).resolve().parents[2]


# ─── Fixtures: a 5ª rodada, como os logs a gravaram ─────────────────────────


def _wf(ts: str, event: str, agent: str, **extra) -> dict:
    return {"timestamp": f"2026-09-15T01:{ts}+00:00", "event": event, "agent": agent, **extra}


def _audit(ts: str, tool: str) -> dict:
    return {"timestamp": f"2026-09-15T01:{ts}+00:00", "event": "tool_call", "tool_name": tool}


RODADA_5_WORKFLOWS = [
    _wf("24:24.000", "workflow_step", "Databricks Engineer", stage="started", tool_use_id="t1"),
    _wf("25:45.000", "agent_delegation", "Databricks Engineer", tool_use_id="t1"),
    _wf("25:45.100", "unverified_negation", "databricks-engineer"),
    _wf("26:16.000", "workflow_step", "Business Analyst", stage="started", tool_use_id="t2"),
    # t2 NUNCA fecha: business-analyst não estava no agents= → a chamada falhou.
    _wf("26:33.000", "workflow_step", "General Purpose", stage="started", tool_use_id="t3"),
    _wf("27:43.000", "agent_delegation", "General Purpose", tool_use_id="t3"),
]

RODADA_5_AUDIT = [
    _audit("24:51.000", "Grep"),
    _audit("24:52.000", "Grep"),
    _audit("25:09.000", "Grep"),
    _audit("25:45.000", "Agent"),
    _audit("26:58.000", "mcp__firecrawl__firecrawl_search"),
    _audit("26:58.500", "mcp__firecrawl__firecrawl_search"),
    _audit("27:08.000", "mcp__firecrawl__firecrawl_scrape"),
    _audit("27:09.000", "mcp__firecrawl__firecrawl_scrape"),
    _audit("27:18.000", "mcp__firecrawl__firecrawl_scrape"),
    _audit("27:43.000", "Agent"),
]


# ─── Dataset ─────────────────────────────────────────────────────────────────


class TestDataset:
    def test_carrega_o_dataset_real(self) -> None:
        cases = mc.load_cases()
        assert len(cases) >= 6
        assert {c.id for c in cases} >= {"genie-ontology", "managed-mcp-servers"}

    def test_todo_caso_tem_fonte_url_e_data(self) -> None:
        """Regra do arquivo: só entra fato verificado, com URL e data."""
        for c in mc.load_cases():
            assert c.fonte and all(u.startswith("http") for u in c.fonte), c.id
            assert c.verificado_em.startswith("2026-"), c.id
            assert c.must_include and all(isinstance(g, list) and g for g in c.must_include), c.id

    def test_agent_hint_existe_no_registry(self) -> None:
        registry = {p.stem for p in (_REPO / "data_agents/agents/registry").glob("*.md")}
        for c in mc.load_cases():
            if c.agent_hint:
                assert c.agent_hint in registry, f"{c.id}: agent_hint {c.agent_hint!r} não é agente"

    def test_rejeita_caso_sem_fonte(self, tmp_path: Path) -> None:
        p = tmp_path / "c.yaml"
        p.write_text(
            "cases:\n  - id: x\n    prompt: p\n    must_include: [[a]]\n    verificado_em: '2026-09-15'\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="fonte"):
            mc.load_cases(p)

    def test_rejeita_grupo_vazio(self, tmp_path: Path) -> None:
        p = tmp_path / "c.yaml"
        p.write_text(
            "cases:\n  - id: x\n    prompt: p\n    must_include: [[]]\n"
            "    fonte: [https://x]\n    verificado_em: '2026-09-15'\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="grupo inválido"):
            mc.load_cases(p)

    def test_grupo_como_string_vira_lista(self, tmp_path: Path) -> None:
        p = tmp_path / "c.yaml"
        p.write_text(
            "cases:\n  - id: x\n    prompt: p\n    must_include: [genie, [a, b]]\n"
            "    fonte: https://x\n    verificado_em: '2026-09-15'\n",
            encoding="utf-8",
        )
        (c,) = mc.load_cases(p)
        assert c.must_include == [["genie"], ["a", "b"]]
        assert c.fonte == ["https://x"]

    def test_rejeita_id_duplicado(self, tmp_path: Path) -> None:
        p = tmp_path / "c.yaml"
        item = "  - id: x\n    prompt: p\n    must_include: [[a]]\n    fonte: [https://x]\n    verificado_em: '2026-09-15'\n"
        p.write_text("cases:\n" + item + item, encoding="utf-8")
        with pytest.raises(ValueError, match="duplicado"):
            mc.load_cases(p)


# ─── Scoring ─────────────────────────────────────────────────────────────────


class TestScoreMustInclude:
    def test_grupos_or_case_insensitive(self) -> None:
        ok, missing = mc.score_must_include(
            "O Genie One usa a semântica do Unity Catalog.",
            [["genie one", "genie"], ["unity catalog"]],
        )
        assert ok and missing == []

    def test_grupo_faltando_reprova_e_aponta(self) -> None:
        ok, missing = mc.score_must_include("Genie é legal.", [["genie"], ["snippet", "inferid"]])
        assert not ok
        assert missing == [["snippet", "inferid"]]

    def test_rodada_5_passa_no_caso_genie_ontology(self) -> None:
        """A resposta da 5ª rodada (núcleo verificado na doc) tem que passar."""
        texto = (
            "camada de contexto unificada (unified context layer) que dá aos agentes Genie "
            "(Genie One, Genie Code) um mapa de negócio. Semântica do Unity Catalog — metric "
            "views, domains, pages. Contexto inferido — snippets extraídos automaticamente."
        )
        case = next(c for c in mc.load_cases() if c.id == "genie-ontology")
        ok, _ = mc.score_must_include(texto, case.must_include)
        assert ok

    def test_rodada_1_reprova_no_caso_genie_ontology(self) -> None:
        """A 1ª rodada ('não existe um produto oficial') falha nos grupos E dispara negação."""
        texto = (
            'Não existe um produto oficial chamado "Genie Ontology". O que provavelmente '
            "aconteceu é uma junção de dois conceitos de plataformas diferentes."
        )
        case = next(c for c in mc.load_cases() if c.id == "genie-ontology")
        ok, missing = mc.score_must_include(texto, case.must_include)
        assert not ok and len(missing) >= 1
        assert mc.find_negations(texto)


# ─── Atribuição de tools por agente ──────────────────────────────────────────


class TestAtribuicaoPorLogs:
    def test_reconstroi_a_rodada_5(self) -> None:
        by, attempted, completed = mc.attribute_tools_from_logs(RODADA_5_AUDIT, RODADA_5_WORKFLOWS)
        assert by["databricks-engineer"] == ["Grep", "Grep", "Grep"]
        assert by["general-purpose"] == [
            "mcp__firecrawl__firecrawl_search",
            "mcp__firecrawl__firecrawl_search",
            "mcp__firecrawl__firecrawl_scrape",
            "mcp__firecrawl__firecrawl_scrape",
            "mcp__firecrawl__firecrawl_scrape",
        ]
        assert "business-analyst" not in by, "delegação que falhou não pode receber tools"
        assert attempted == ["databricks-engineer", "business-analyst", "general-purpose"]
        assert completed == ["databricks-engineer", "general-purpose"]

    def test_quem_buscou_foi_general_purpose_nao_o_especialista(self) -> None:
        by, _, _ = mc.attribute_tools_from_logs(RODADA_5_AUDIT, RODADA_5_WORKFLOWS)
        web, who, tools = mc.web_search_summary(by)
        assert web is True
        assert who == ["general-purpose"]
        assert "databricks-engineer" not in who
        assert set(tools) == {
            "mcp__firecrawl__firecrawl_search",
            "mcp__firecrawl__firecrawl_scrape",
        }

    def test_tool_fora_de_janela_e_do_supervisor(self) -> None:
        audit = [_audit("00:01.000", "Read"), _audit("00:02.000", "Grep")]
        by, attempted, completed = mc.attribute_tools_from_logs(audit, [])
        assert by == {mc.SUPERVISOR: ["Read", "Grep"]}
        assert attempted == [] and completed == []

    def test_agent_do_supervisor_nao_conta_como_tool(self) -> None:
        by, _, _ = mc.attribute_tools_from_logs([_audit("00:01.000", "Agent")], [])
        assert by == {}

    def test_janela_reaberta_substitui_a_que_nao_fechou(self) -> None:
        wf = [
            _wf("00:00.000", "workflow_step", "Business Analyst", stage="started", tool_use_id="a"),
            _wf("00:10.000", "workflow_step", "General Purpose", stage="started", tool_use_id="b"),
        ]
        by, _, _ = mc.attribute_tools_from_logs([_audit("00:11.000", "WebFetch")], wf)
        assert by == {"general-purpose": ["WebFetch"]}

    def test_curl_e_context7_nao_sao_busca(self) -> None:
        """Mesmo critério do negation guard — foi o que enganou a 2ª e a 3ª rodadas."""
        web, who, _ = mc.web_search_summary(
            {"databricks-engineer": ["Bash", "mcp__context7__resolve-library-id", "Grep"]}
        )
        assert web is False and who == []

    def test_tavily_conta(self) -> None:
        web, who, tools = mc.web_search_summary(
            {"databricks-engineer": ["mcp__tavily__tavily-search"]}
        )
        assert web and who == ["databricks-engineer"] and tools == ["mcp__tavily__tavily-search"]


class TestMerge:
    def test_uniao_preserva_ordem_e_dedup(self) -> None:
        out = mc.merge_attribution(
            {"a": ["Grep", "Read"]}, {"a": ["Read", "Bash"], "b": ["mcp__tavily__tavily-search"]}
        )
        assert out == {"a": ["Grep", "Read", "Bash"], "b": ["mcp__tavily__tavily-search"]}


class TestSlug:
    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            ("Databricks Engineer", "databricks-engineer"),
            ("General Purpose", "general-purpose"),
            ("Ai Data Agents:Geral", "ai-data-agents:geral"),
            ("databricks-engineer", "databricks-engineer"),
            ("  Business  Analyst ", "business-analyst"),
        ],
    )
    def test_normaliza_display_name_do_tracker(self, entrada: str, esperado: str) -> None:
        assert mc.slug_agent(entrada) == esperado

    def test_agent_name_from_input(self) -> None:
        assert mc.agent_name_from_input({"subagent_type": "geral"}) == "geral"
        assert mc.agent_name_from_input({"name": "x"}) == "x"
        assert mc.agent_name_from_input("não é dict") == "?"
        assert mc.agent_name_from_input({}) == "?"


# ─── Sumário e --compare ─────────────────────────────────────────────────────


def _result(**over) -> mc.CaseResult:
    base = dict(
        case_id="genie-ontology", run=1, correct=True, missing_groups=[], negations=[],
        web_search=True, web_search_by=["general-purpose"],
        web_search_tools=["mcp__firecrawl__firecrawl_search"], specialist_searched=False,
        dispatched=["databricks-engineer"], dispatcher_confidence=0.95, dispatcher_reason="ok",
        delegations_attempted=["databricks-engineer", "business-analyst", "general-purpose"],
        delegations_completed=["databricks-engineer", "general-purpose"],
        off_dispatch_delegations=["business-analyst", "general-purpose"],
        unverified_negation_events=1, tools_by_agent_stream={}, tools_by_agent_log={},
        tools_used=["Grep"], response_chars=1200, response_preview="...", models_seen=["kimi-k2.6"],
        num_turns=4, duration_s=271.0, sdk_cost_usd=1.2, cost_usd=0.2287,
        cost_basis="tabela-moonshot:kimi-k2.6", input_tokens=100, output_tokens=50,
        cache_read_tokens=0, thinking='{"type": "disabled"}', error=None,
    )  # fmt: skip
    base.update(over)
    return mc.CaseResult(**base)


class TestSummarize:
    def test_vazio(self) -> None:
        s = mc.summarize([])
        assert s["total"] == 0 and s["accuracy"] == 0.0

    def test_rodada_5_como_caso_unico(self) -> None:
        s = mc.summarize([_result()])
        assert s["accuracy"] == 1.0
        assert s["web_search_rate"] == 1.0
        assert s["specialist_search_rate"] == 0.0, "acertou, mas NÃO foi o especialista"
        assert s["off_dispatch_rate"] == 1.0
        assert s["unverified_negation_rate"] == 1.0
        assert s["total_cost_usd"] == pytest.approx(0.2287)

    def test_mistura(self) -> None:
        s = mc.summarize(
            [
                _result(),
                _result(
                    case_id="x",
                    correct=False,
                    negations=["não existe"],
                    web_search=False,
                    web_search_by=[],
                    error=None,
                    cost_usd=0.1,
                ),  # fmt: skip
                _result(case_id="y", correct=False, error="timeout", cost_usd=0.0),
            ]
        )
        assert s["total"] == 3 and s["correct"] == 1
        assert s["accuracy"] == pytest.approx(1 / 3)
        assert s["negation_rate"] == pytest.approx(1 / 3)
        assert s["error_rate"] == pytest.approx(1 / 3)


class TestCompare:
    def _run(self, label: str, model: str, results: list[mc.CaseResult]) -> dict:
        from dataclasses import asdict

        return {
            "meta": {
                "label": label,
                "default_model": model,
                "endpoint_host": "api.moonshot.ai" if "kimi" in model else "api.anthropic.com",
                "thinking_config": '{"type": "disabled"}',
            },
            "summary": mc.summarize(results),
            "cases": [asdict(r) for r in results],
        }

    def test_render_mostra_as_duas_perguntas(self) -> None:
        a = self._run("kimi", "kimi-k2.6", [_result(), _result(case_id="managed-mcp-servers", correct=False, web_search=False, web_search_by=[])])  # fmt: skip
        b = self._run("anthropic", "claude-x", [_result(specialist_searched=True, web_search_by=["databricks-engineer"], off_dispatch_delegations=[]), _result(case_id="managed-mcp-servers", specialist_searched=True, web_search_by=["databricks-engineer"])])  # fmt: skip
        out = mc.render_comparison(a, b)
        assert "accuracy" in out and "specialist_search_rate" in out
        assert "genie-ontology" in out and "managed-mcp-servers" in out
        assert "general-purpose | databricks-engineer" in out
        assert "kimi-k2.6 @ api.moonshot.ai" in out and "claude-x @ api.anthropic.com" in out
        # A: 1/2 correto; B: 2/2
        assert "50%" in out and "100%" in out

    def test_repeticoes_agregam_por_caso(self) -> None:
        a = self._run("kimi", "kimi-k2.6", [_result(run=1), _result(run=2, correct=False)])
        b = self._run("b", "claude-x", [_result()])
        out = mc.render_comparison(a, b)
        assert "1/2" in out and "1/1" in out

    def test_persist_e_load_run_fecham_o_ciclo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mc, "EVALS_DIR", tmp_path)
        meta = {
            "label": "t",
            "default_model": "kimi-k2.6",
            "endpoint_host": "h",
            "thinking_config": "x",
        }
        path = mc.persist("kimi k2.6/teste", meta, [_result()])
        assert path.parent == tmp_path
        assert "kimi-k2.6-teste" in path.name, "label vira nome de arquivo seguro"
        data = mc._load_run(path)
        assert data["meta"]["label"] == "t"
        assert data["summary"]["accuracy"] == 1.0
        assert data["cases"][0]["web_search_by"] == ["general-purpose"]

    def test_load_run_rejeita_json_de_outro_eval(self, tmp_path: Path) -> None:
        p = tmp_path / "x.json"
        p.write_text(json.dumps({"type": "summary"}), encoding="utf-8")
        with pytest.raises(ValueError, match="sem chave"):
            mc._load_run(p)


class TestCLI:
    def test_compare_por_cli(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        monkeypatch.setattr(mc, "EVALS_DIR", tmp_path)
        meta = {"label": "a", "default_model": "m", "endpoint_host": "h", "thinking_config": "x"}
        pa = mc.persist("a", meta, [_result()])
        pb = mc.persist("b", {**meta, "label": "b"}, [_result(correct=False)])
        assert mc.main(["--compare", str(pa), str(pb)]) == 0
        out = capsys.readouterr().out
        assert "Comparação" in out and "accuracy" in out

    def test_id_inexistente_sai_2(self, capsys) -> None:
        assert mc.main(["--id", "nao-existe"]) == 2

    def test_repeat_invalido_sai_2(self) -> None:
        assert mc.main(["--repeat", "0", "--id", "genie-ontology"]) == 2


class TestFonteUnicaDeBuscaWeb:
    def test_mesmas_tools_do_negation_guard(self) -> None:
        """Se o hook mudar o que conta como busca, o eval segue junto — sem drift."""
        from data_agents.hooks import negation_guard_hook as ng

        assert mc.WEB_SEARCH_TOOLS == frozenset(ng._WEB_SEARCH_TOOLS)
        assert "mcp__tavily__tavily-search" in mc.WEB_SEARCH_TOOLS
        assert "Bash" not in mc.WEB_SEARCH_TOOLS and "WebFetch" not in mc.WEB_SEARCH_TOOLS
