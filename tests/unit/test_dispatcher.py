"""
Testes para agents/dispatcher.py — Two-Stage Routing.

Cobre:
  - apply_fallback_policy: lógica determinística de seleção por confidence
  - format_dispatcher_log: formatação amigável da mensagem
  - select_agents: chamada async ao endpoint (mockada via urlopen)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from data_agents.agents.dispatcher import (
    _NEIGHBOR_AGENTS,
    _NEVER_DELEGATED,
    apply_fallback_policy,
    format_dispatcher_log,
    select_agents,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_meta(name: str, tier: str = "T1", description: str = "Stub agent.") -> MagicMock:
    """Cria um AgentMeta mock com os campos mínimos usados pelo dispatcher."""
    m = MagicMock()
    m.name = name
    m.tier = tier
    m.description = description
    return m


def _make_available(*names: str) -> dict:
    """Cria um dict de AgentMeta mocks pelos nomes passados."""
    defaults = {
        "databricks-engineer": "Especialista Databricks (SQL, Spark, Delta).",
        "databricks-ai": "Especialista IA/streaming Databricks (RAG, Vector Search).",
        "fabric-engineer": "Especialista Microsoft Fabric (Lakehouse, OneLake).",
        "fabric-rti": "Especialista Fabric Real-Time Intelligence (KQL).",
        "data-quality-steward": "Qualidade de dados (validações, drift).",
        "governance-auditor": "Governança (LGPD, RLS, OLS, linhagem).",
        "migration-expert": "Migração SQL Server/PostgreSQL para lakehouses.",
        "python-expert": "Python puro (pacotes, APIs, CLIs).",
        "dbt-expert": "dbt Core (models, testes, snapshots).",
        "geral": "Conversacional, zero MCP.",
    }
    return {name: _make_meta(name, "T1", defaults.get(name, "Stub.")) for name in names}


# ─── apply_fallback_policy ───────────────────────────────────────────────────


class TestApplyFallbackPolicy:
    """Verifica a política de fallback baseada em confidence."""

    def test_high_confidence_returns_selected_unchanged(self):
        available = _make_available(
            "databricks-engineer", "fabric-engineer", "data-quality-steward"
        )
        result = apply_fallback_policy(["databricks-engineer"], 0.95, available)
        assert result == ["databricks-engineer"]

    def test_high_confidence_dedupes_selected(self):
        """Se selected vier com duplicatas, remove (preservando ordem)."""
        available = _make_available("databricks-engineer", "fabric-engineer")
        result = apply_fallback_policy(
            ["databricks-engineer", "databricks-engineer", "fabric-engineer"],
            0.90,
            available,
        )
        assert result == ["databricks-engineer", "fabric-engineer"]

    def test_medium_confidence_adds_neighbors(self):
        """Confiança média (0.6-0.8) adiciona vizinhos comuns."""
        available = _make_available(
            "databricks-engineer", "data-quality-steward", "governance-auditor"
        )
        result = apply_fallback_policy(["databricks-engineer"], 0.70, available)
        assert "databricks-engineer" in result
        for neighbor in _NEIGHBOR_AGENTS:
            if neighbor in available:
                assert neighbor in result

    def test_medium_confidence_no_dup_when_neighbor_already_selected(self):
        """Se vizinho já está em selected, não duplica."""
        available = _make_available("databricks-engineer", "data-quality-steward")
        result = apply_fallback_policy(
            ["databricks-engineer", "data-quality-steward"], 0.65, available
        )
        # data-quality-steward aparece só uma vez
        assert result.count("data-quality-steward") == 1

    def test_low_confidence_returns_all_delegatable(self):
        """Confiança baixa (<0.6) expande pra todos os agentes."""
        available = _make_available(
            "databricks-engineer", "fabric-engineer", "data-quality-steward", "geral"
        )
        result = apply_fallback_policy(["databricks-engineer"], 0.40, available)
        # Deve incluir todos exceto "geral" (never_delegated)
        assert "databricks-engineer" in result
        assert "fabric-engineer" in result
        assert "data-quality-steward" in result
        assert "geral" not in result

    def test_zero_confidence_means_all_delegatable(self):
        """Confidence 0.0 (erro de network) → fallback total."""
        available = _make_available("databricks-engineer", "fabric-engineer")
        result = apply_fallback_policy([], 0.0, available)
        assert sorted(result) == ["databricks-engineer", "fabric-engineer"]

    def test_neighbor_only_added_when_present_in_available(self):
        """Se vizinho não existe no registry disponível, não é adicionado."""
        # Available NÃO inclui data-quality-steward nem governance-auditor
        available = _make_available("databricks-engineer", "fabric-engineer")
        result = apply_fallback_policy(["databricks-engineer"], 0.70, available)
        assert "data-quality-steward" not in result
        assert "governance-auditor" not in result
        assert "databricks-engineer" in result


# ─── format_dispatcher_log ───────────────────────────────────────────────────


class TestFormatDispatcherLog:
    """Verifica a formatação amigável do log do dispatcher."""

    def test_basic_format(self):
        out = format_dispatcher_log(
            selected=["databricks-engineer"],
            final=["databricks-engineer"],
            confidence=0.90,
            reason="query Databricks",
            total_available=14,
        )
        assert "🎯 Dispatcher" in out
        assert "databricks-engineer" in out
        assert "90%" in out
        assert "1/14" in out
        assert "query Databricks" in out

    def test_format_with_fallback_extras(self):
        """Quando final tem mais que selected, mostra o '+N fallback'."""
        out = format_dispatcher_log(
            selected=["databricks-engineer"],
            final=["databricks-engineer", "data-quality-steward", "governance-auditor"],
            confidence=0.65,
            reason="possível impacto governança",
            total_available=14,
        )
        assert "+2 fallback" in out
        assert "65%" in out

    def test_format_without_reason(self):
        """Reason vazia: não aparece no output."""
        out = format_dispatcher_log(
            selected=["fabric-engineer"],
            final=["fabric-engineer"],
            confidence=0.85,
            reason="",
            total_available=15,
        )
        assert "fabric-engineer" in out
        assert "85%" in out
        assert "1/15" in out


# ─── select_agents (chamada async) ──────────────────────────────────────────


class TestSelectAgents:
    """Verifica a chamada HTTP ao endpoint (mockada)."""

    def _mock_response(self, payload_dict: dict):
        """Cria um mock urlopen que retorna o JSON dado."""
        body = json.dumps(payload_dict).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @pytest.mark.asyncio
    async def test_selects_databricks_for_databricks_query(self):
        """Mock simulando dispatcher escolhendo databricks-engineer."""
        available = _make_available(
            "databricks-engineer", "fabric-engineer", "data-quality-steward", "geral"
        )
        mock_api = self._mock_response(
            {
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "agents": ["databricks-engineer"],
                                "confidence": 0.92,
                                "reason": "query menciona Spark e Delta",
                            }
                        )
                    }
                ]
            }
        )
        with patch("urllib.request.urlopen", return_value=mock_api):
            agents, conf, reason = await select_agents(
                "crie pipeline Bronze no Databricks", available
            )
        assert agents == ["databricks-engineer"]
        assert conf == pytest.approx(0.92)
        assert "Spark" in reason or "Delta" in reason

    @pytest.mark.asyncio
    async def test_filters_invalid_agent_names(self):
        """Se modelo retornar nome que não está no registry, é filtrado."""
        available = _make_available("databricks-engineer", "fabric-engineer")
        mock_api = self._mock_response(
            {
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "agents": [
                                    "databricks-engineer",
                                    "agent-fantasma",
                                    "fabric-engineer",
                                ],
                                "confidence": 0.85,
                                "reason": "ok",
                            }
                        )
                    }
                ]
            }
        )
        with patch("urllib.request.urlopen", return_value=mock_api):
            agents, _, _ = await select_agents("query", available)
        assert "agent-fantasma" not in agents
        assert "databricks-engineer" in agents
        assert "fabric-engineer" in agents

    @pytest.mark.asyncio
    async def test_filters_geral_never_delegated(self):
        """O agente 'geral' nunca é delegado, mesmo se modelo escolher."""
        available = _make_available("databricks-engineer", "geral")
        mock_api = self._mock_response(
            {
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "agents": ["geral", "databricks-engineer"],
                                "confidence": 0.90,
                                "reason": "ok",
                            }
                        )
                    }
                ]
            }
        )
        with patch("urllib.request.urlopen", return_value=mock_api):
            agents, _, _ = await select_agents("query", available)
        assert "geral" not in agents
        assert "databricks-engineer" in agents

    @pytest.mark.asyncio
    async def test_fallback_on_invalid_json(self):
        """Modelo retorna texto não-JSON: fallback retorna todos os agentes."""
        available = _make_available("databricks-engineer", "fabric-engineer", "geral")
        mock_api = self._mock_response({"content": [{"text": "isso aqui não é JSON nenhum"}]})
        with patch("urllib.request.urlopen", return_value=mock_api):
            agents, conf, reason = await select_agents("query", available)
        # Fallback inclui todos exceto geral
        assert sorted(agents) == ["databricks-engineer", "fabric-engineer"]
        assert conf == 0.0
        assert "invalid_json" in reason

    @pytest.mark.asyncio
    async def test_fallback_on_empty_selection(self):
        """Modelo retorna agents=[] (lista vazia): fallback."""
        available = _make_available("databricks-engineer", "geral")
        mock_api = self._mock_response(
            {"content": [{"text": json.dumps({"agents": [], "confidence": 0.5, "reason": "ok"})}]}
        )
        with patch("urllib.request.urlopen", return_value=mock_api):
            agents, conf, reason = await select_agents("query", available)
        assert agents == ["databricks-engineer"]  # geral filtrado
        assert conf == 0.0
        assert "empty_selection" in reason

    @pytest.mark.asyncio
    async def test_fallback_on_http_error(self):
        """Falha HTTP retorna fallback safe (todos os agentes, conf=0)."""
        import urllib.error

        available = _make_available("databricks-engineer", "fabric-engineer", "geral")

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                url="http://x", code=500, msg="error", hdrs=None, fp=None
            ),
        ):
            agents, conf, reason = await select_agents("query", available)
        assert sorted(agents) == ["databricks-engineer", "fabric-engineer"]
        assert conf == 0.0
        assert "http_error:500" in reason

    @pytest.mark.asyncio
    async def test_http_error_loga_o_corpo_da_resposta(self, caplog):
        """Eval 2026-09-15: 12× 'HTTP 400: Bad Request' contra a Anthropic e
        nenhuma pista de QUAL campo foi rejeitado. O corpo tem que ir ao log."""
        import io
        import logging
        import urllib.error

        available = _make_available("databricks-engineer", "geral")
        corpo = (
            b'{"type":"error","error":{"type":"invalid_request_error",'
            b'"message":"campo X nao e aceito"}}'
        )
        err = urllib.error.HTTPError(
            url="http://x", code=400, msg="Bad Request", hdrs=None, fp=io.BytesIO(corpo)
        )
        with caplog.at_level(logging.WARNING, logger="data_agents.dispatcher"):
            with patch("urllib.request.urlopen", side_effect=err):
                _, _, reason = await select_agents("query", available)
        assert "http_error:400" in reason
        assert "invalid_request_error" in caplog.text
        assert "campo X nao e aceito" in caplog.text

    def test_corpo_do_erro_e_truncado_e_sem_chave(self):
        import io
        import urllib.error

        from data_agents.agents.dispatcher import _HTTP_ERROR_BODY_MAX, _http_error_body

        longo = ("x" * 1000 + " sk-abcdefghijklmnop \n quebra").encode()
        err = urllib.error.HTTPError(
            url="http://x", code=400, msg="b", hdrs=None, fp=io.BytesIO(longo)
        )
        body = _http_error_body(err)
        assert len(body) <= _HTTP_ERROR_BODY_MAX
        assert "\n" not in body

        curto = b"erro com sk-abcdefghijklmnop dentro"
        err2 = urllib.error.HTTPError(
            url="http://x", code=400, msg="b", hdrs=None, fp=io.BytesIO(curto)
        )
        assert "sk-abcdefghijklmnop" not in _http_error_body(err2)
        assert "sk-a…" in _http_error_body(
            urllib.error.HTTPError(
                url="http://x", code=400, msg="b", hdrs=None, fp=io.BytesIO(curto)
            )
        )

    def test_corpo_do_erro_sem_fp_nao_estoura(self):
        import urllib.error

        from data_agents.agents.dispatcher import _http_error_body

        err = urllib.error.HTTPError(url="http://x", code=500, msg="b", hdrs=None, fp=None)
        assert _http_error_body(err) == ""

    @pytest.mark.asyncio
    async def test_handles_markdown_fenced_response(self):
        """Modelo às vezes envolve JSON em ```json ... ```; deve parsear OK."""
        available = _make_available("databricks-engineer")
        fenced = (
            "```json\n"
            + json.dumps({"agents": ["databricks-engineer"], "confidence": 0.9, "reason": "ok"})
            + "\n```"
        )
        mock_api = self._mock_response({"content": [{"text": fenced}]})
        with patch("urllib.request.urlopen", return_value=mock_api):
            agents, conf, _ = await select_agents("query", available)
        assert agents == ["databricks-engineer"]
        assert conf == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_clamps_confidence_to_valid_range(self):
        """Confidence acima de 1.0 ou abaixo de 0.0 é clampada para [0,1]."""
        available = _make_available("databricks-engineer")
        mock_api = self._mock_response(
            {
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "agents": ["databricks-engineer"],
                                "confidence": 1.5,  # fora do range
                                "reason": "ok",
                            }
                        )
                    }
                ]
            }
        )
        with patch("urllib.request.urlopen", return_value=mock_api):
            _, conf, _ = await select_agents("query", available)
        assert conf == 1.0  # clampado


# ─── Constantes (sanity check) ───────────────────────────────────────────────


class TestConstants:
    """Sanity dos constants módulo-level — protege contra mudanças acidentais."""

    def test_geral_in_never_delegated(self):
        assert "geral" in _NEVER_DELEGATED

    def test_neighbor_agents_are_quality_and_governance(self):
        assert "data-quality-steward" in _NEIGHBOR_AGENTS
        assert "governance-auditor" in _NEIGHBOR_AGENTS


# ─── Regressão: bloco `thinking` quebrava o dispatcher (auditoria 2026-09-13) ──


class TestDispatcherThinkingBlocks:
    """
    O dispatcher falhava em TODA query, silenciosamente.

    O Kimi K2.6 raciocina por padrão. Numa execução real observada, a resposta
    veio com `content = [{"type": "thinking", ...}]`, `stop_reason = max_tokens`
    e `thinking_tokens = 255` de um orçamento de 256 — o modelo gastou tudo
    pensando e nunca emitiu o texto. O parse antigo fazia `content[0]["text"]`,
    levantava KeyError e caía no fallback que carrega TODOS os agentes,
    anulando o two-stage routing (o prompt voltava de ~25K para ~80K).

    Correção em duas frentes: `thinking=disabled` no payload (causa) e varredura
    dos blocos procurando o de texto (robustez).
    """

    def _mock_response(self, payload_dict: dict):
        body = json.dumps(payload_dict).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @pytest.mark.asyncio
    async def test_skips_thinking_block_and_finds_text(self):
        """Com thinking + text, deve achar o texto — não parar no content[0]."""
        available = _make_available("databricks-engineer", "fabric-engineer", "geral")
        mock_api = self._mock_response(
            {
                "content": [
                    {"type": "thinking", "thinking": "O usuário perguntou sobre catálogos..."},
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "agents": ["databricks-engineer"],
                                "confidence": 0.95,
                                "reason": "Unity Catalog",
                            }
                        ),
                    },
                ]
            }
        )
        with patch("urllib.request.urlopen", return_value=mock_api):
            agents, conf, reason = await select_agents("liste os catálogos", available)

        assert agents == ["databricks-engineer"], (
            "o bloco thinking veio primeiro e o parse deve puxar o bloco de texto"
        )
        assert conf == pytest.approx(0.95)

    @pytest.mark.asyncio
    async def test_only_thinking_block_falls_back_cleanly(self):
        """Cenário real observado: só thinking, sem texto. Fallback, sem exceção."""
        available = _make_available("databricks-engineer", "fabric-engineer", "geral")
        mock_api = self._mock_response(
            {
                "content": [{"type": "thinking", "thinking": "raciocinando..."}],
                "stop_reason": "max_tokens",
                "usage": {"output_tokens": 256, "output_tokens_details": {"thinking_tokens": 255}},
            }
        )
        with patch("urllib.request.urlopen", return_value=mock_api):
            agents, conf, reason = await select_agents("liste os catálogos", available)

        assert reason == "no_content"
        assert conf == 0.0
        assert len(agents) > 1, "fallback deve carregar os agentes delegáveis"

    def test_payload_disables_thinking_and_is_deterministic(self):
        """
        A causa raiz: sem `thinking=disabled`, o modelo gasta o orçamento
        pensando. E `temperature: 0` torna o roteamento reprodutível.
        """
        import inspect

        from data_agents.agents import dispatcher

        src = inspect.getsource(dispatcher.select_agents)
        assert '"thinking": {"type": "disabled"}' in src, (
            "o payload do dispatcher deve desabilitar thinking explicitamente"
        )
        assert '"temperature": 0' in src, "roteamento deve ser determinístico"
