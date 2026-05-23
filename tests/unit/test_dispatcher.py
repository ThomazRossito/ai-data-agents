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
