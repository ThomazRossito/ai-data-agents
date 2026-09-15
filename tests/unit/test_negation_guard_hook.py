"""
Testes do negation guard — o freio determinístico contra "não existe" sem busca.

Os textos de teste são os TRÊS retornos reais das três rodadas do caso Genie
Ontology (2026-09-14/15). Se o hook não pegar os três, não serve.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_agents.hooks import negation_guard_hook as ng
from data_agents.hooks.negation_guard_hook import (
    find_negations,
    guard_unverified_negation,
    reset_negation_guard,
)

# Os três retornos reais (trechos), na ordem em que aconteceram.
RODADA_1_GERAL = (
    'Não existe um produto oficial chamado "Genie Ontology". O que provavelmente '
    "aconteceu é uma junção de dois conceitos de plataformas diferentes."
)
RODADA_2_HEDGE = (
    "O Genie Ontology é uma feature real e recente da Databricks. Os detalhes técnicos "
    "exatos ainda não foram trazidos para a base de conhecimento do projeto."
)
RODADA_3_CURL = (
    'Após verificação na documentação oficial do Databricks: "Genie Ontology" não é um '
    'produto ou feature do Databricks. O termo "ontology" não aparece na documentação.'
)


@pytest.fixture(autouse=True)
def _estado_limpo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    reset_negation_guard()
    monkeypatch.setattr(ng, "_WORKFLOWS_LOG", tmp_path / "workflows.jsonl")
    yield
    reset_negation_guard()


def _agent_event(texto: str, agente: str = "databricks-engineer") -> dict:
    return {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": agente, "prompt": "..."},
        "tool_response": texto,
    }


class TestDeteccao:
    def test_rodada_1_geral(self) -> None:
        assert find_negations(RODADA_1_GERAL), "'Não existe um produto oficial' passou"

    def test_rodada_3_curl(self) -> None:
        assert find_negations(RODADA_3_CURL), "'não é um produto ou feature' passou"

    def test_rodada_2_hedge_nao_e_negacao(self) -> None:
        """Hedge honesto não pode disparar — senão o hook pune quem faz certo."""
        assert find_negations(RODADA_2_HEDGE) == []

    @pytest.mark.parametrize(
        "frase",
        [
            "Isso não existe na plataforma.",
            "Genie Ontology não é uma feature do Databricks.",
            "Não há nenhum produto com esse nome.",
            "não é um produto real",
            "This feature does not exist in Databricks.",
            "Genie Ontology is not a product.",
            "There is no such feature.",
        ],
    )
    def test_variantes_pt_en(self, frase: str) -> None:
        assert find_negations(frase)

    @pytest.mark.parametrize(
        "frase",
        [
            "Não encontrei esse termo nas fontes consultadas.",
            "Não localizei documentação específica; pode ser recente.",
            "A tabela não existe no schema silver — crie com CREATE TABLE.",  # ver nota abaixo
        ],
    )
    def test_frases_que_nao_sao_sobre_produto(self, frase: str) -> None:
        """Duas primeiras: hedge correto, não pode disparar.

        A terceira DISPARA — 'não existe' sobre uma tabela. É falso positivo
        aceito: o hook casa a forma, não o assunto, e o custo de um
        additionalContext a mais é muito menor que o de uma negação falsa
        sobre produto passar. Registrado aqui para ninguém 'consertar' e abrir
        o furo de volta.
        """
        if "tabela" in frase:
            assert find_negations(frase)
        else:
            assert find_negations(frase) == []

    def test_trecho_tem_contexto(self) -> None:
        trechos = find_negations(RODADA_1_GERAL)
        assert "Genie Ontology" in trechos[0]


class TestHookSemBusca:
    @pytest.mark.asyncio
    async def test_agent_com_negacao_sem_busca_injeta_contexto(self, tmp_path: Path) -> None:
        out = await guard_unverified_negation(_agent_event(RODADA_3_CURL), "t1", None)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
        assert "NEGATION GUARD" in ctx
        assert "NÃO repasse a negação" in ctx
        assert "tavily-search" in ctx
        assert "Genie Ontology" in ctx, "o trecho ofensor deve ir no contexto"

    @pytest.mark.asyncio
    async def test_grava_evento_medivel(self, tmp_path: Path) -> None:
        await guard_unverified_negation(_agent_event(RODADA_1_GERAL, "geral"), "t1", None)
        linhas = (tmp_path / "workflows.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(linhas) == 1
        ev = json.loads(linhas[0])
        assert ev["event"] == "unverified_negation"
        assert ev["agent_name"] == "geral"
        assert ev["tool_use_id"] == "t1"
        assert "session_id" in ev, "campo canônico do LOGGING_CONTRACT — permite JOIN com audit"
        assert ev["web_search_in_turn"] is False
        assert ev["snippets"]

    @pytest.mark.asyncio
    async def test_agent_sem_negacao_nao_faz_nada(self, tmp_path: Path) -> None:
        out = await guard_unverified_negation(_agent_event(RODADA_2_HEDGE), "t1", None)
        assert out == {}
        assert not (tmp_path / "workflows.jsonl").exists()


class TestHookComBusca:
    @pytest.mark.asyncio
    async def test_tavily_no_turno_libera_a_negacao(self, tmp_path: Path) -> None:
        """Com busca web feita, a negação pode estar fundamentada — o hook recua."""
        await guard_unverified_negation(
            {"tool_name": "mcp__tavily__tavily-search", "tool_input": {"query": "x"}}, "t0", None
        )
        out = await guard_unverified_negation(_agent_event(RODADA_3_CURL), "t1", None)
        assert out == {}
        assert not (tmp_path / "workflows.jsonl").exists()

    @pytest.mark.asyncio
    async def test_curl_via_bash_NAO_conta_como_busca(self, tmp_path: Path) -> None:
        """Foi exatamente o que falhou na 3ª rodada."""
        await guard_unverified_negation(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "curl https://docs.databricks.com/llms.txt"},
            },
            "t0",
            None,
        )
        out = await guard_unverified_negation(_agent_event(RODADA_3_CURL), "t1", None)
        assert out, "curl em duas páginas não é verificação — o hook tem que disparar"

    @pytest.mark.asyncio
    async def test_websearch_builtin_conta_como_busca(self, tmp_path: Path) -> None:
        """Eval 2026-09-15: Supervisor verificou via `WebSearch` (built-in do Claude
        Code) em 5/12 casos. Negação depois disso é verificada — o guard recua."""
        await guard_unverified_negation(
            {"tool_name": "WebSearch", "tool_input": {"query": "Genie Ontology"}}, "t0", None
        )
        assert await guard_unverified_negation(_agent_event(RODADA_3_CURL), "t1", None) == {}

    @pytest.mark.asyncio
    async def test_webfetch_NAO_conta_como_busca(self) -> None:
        """Abrir uma URL é o mesmo que curl: página errada vira 'não existe'."""
        await guard_unverified_negation(
            {"tool_name": "WebFetch", "tool_input": {"url": "https://docs.databricks.com"}},
            "t0",
            None,
        )
        assert await guard_unverified_negation(_agent_event(RODADA_3_CURL), "t1", None)

    @pytest.mark.asyncio
    async def test_context7_NAO_conta_como_busca(self) -> None:
        """context7 indexa bibliotecas, não produto — 2ª rodada."""
        await guard_unverified_negation(
            {"tool_name": "mcp__context7__resolve-library-id", "tool_input": {}}, "t0", None
        )
        assert await guard_unverified_negation(_agent_event(RODADA_1_GERAL), "t1", None)

    @pytest.mark.asyncio
    async def test_reset_zera_a_busca(self) -> None:
        await guard_unverified_negation(
            {"tool_name": "mcp__tavily__tavily-search", "tool_input": {}}, "t0", None
        )
        reset_negation_guard()
        assert await guard_unverified_negation(_agent_event(RODADA_1_GERAL), "t1", None), (
            "busca do turno anterior não pode valer para o turno seguinte"
        )


class TestExtracaoDeTexto:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "resposta",
        [
            RODADA_1_GERAL,
            {"text": RODADA_1_GERAL},
            {"content": [{"type": "text", "text": RODADA_1_GERAL}]},
            [{"type": "text", "text": RODADA_1_GERAL}],
        ],
        ids=["str", "dict-text", "dict-content", "list"],
    )
    async def test_formas_do_sdk(self, resposta) -> None:
        ev = {"tool_name": "Agent", "tool_input": {"subagent_type": "x"}, "tool_response": resposta}
        assert await guard_unverified_negation(ev, "t1", None)

    @pytest.mark.asyncio
    async def test_input_malformado_nao_estoura(self) -> None:
        assert await guard_unverified_negation(None, None, None) == {}
        assert await guard_unverified_negation({"tool_name": "Agent"}, None, None) == {}
        assert (
            await guard_unverified_negation(
                {"tool_name": "Agent", "tool_input": "não é dict", "tool_response": RODADA_1_GERAL},
                None,
                None,
            )
            != {}
        )
