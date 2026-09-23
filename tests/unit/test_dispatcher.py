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
    async def test_fallback_on_http_error(self, monkeypatch):
        """Falha HTTP persistente retorna fallback safe (todos os agentes, conf=0).
        500 é transitório: tenta de novo antes de desistir (sem dormir no teste)."""
        import urllib.error

        from data_agents.agents import dispatcher as disp

        async def _nao_dorme(_s):
            return None

        monkeypatch.setattr(disp, "_sleep", _nao_dorme)
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

    def test_payload_disables_thinking(self):
        """
        A causa raiz do bug de 2026-09-13: sem `thinking=disabled`, o modelo
        gasta o orçamento pensando e nunca emite o JSON.

        (Este teste grepava o código-fonte e afirmava que `temperature: 0`
        "torna o roteamento reprodutível" — falso, medido em 2026-09-14: 10/25
        casos variam. Agora testa o comportamento do payload, não o texto.)
        """
        from data_agents.agents.dispatcher import build_dispatcher_payload

        for base in ("https://api.moonshot.ai/anthropic", "https://api.anthropic.com"):
            body = build_dispatcher_payload("q", "m", base)
            assert body["thinking"] == {"type": "disabled"}, base
            assert body["max_tokens"] >= 512, "orçamento folgado para modelos com thinking forçado"


# ─── build_dispatcher_payload (puro) ─────────────────────────────────────────


class TestBuildDispatcherPayload:
    """Eval 2026-09-15 contra o Sonnet 5: 24/24 `HTTP 400 — "temperature is
    deprecated for this model"`. O campo só pode ir para a Moonshot."""

    def test_anthropic_sem_temperature(self):
        from data_agents.agents.dispatcher import build_dispatcher_payload

        body = build_dispatcher_payload("q", "claude-sonnet-5", "https://api.anthropic.com")
        assert "temperature" not in body
        assert body["thinking"] == {"type": "disabled"}
        assert body["model"] == "claude-sonnet-5"
        assert body["messages"] == [{"role": "user", "content": "q"}]

    def test_moonshot_mantem_temperature_zero(self):
        """Baseline do eval-routing foi medido com temperature=0 — não mexer."""
        from data_agents.agents.dispatcher import build_dispatcher_payload

        body = build_dispatcher_payload("q", "kimi-k2.6", "https://api.moonshot.ai/anthropic")
        assert body["temperature"] == 0

    @pytest.mark.asyncio
    async def test_select_agents_usa_o_payload_sem_temperature_na_anthropic(self, monkeypatch):
        from data_agents.agents import dispatcher as disp

        monkeypatch.setattr(disp.settings, "anthropic_base_url", "https://api.anthropic.com")
        monkeypatch.setattr(disp.settings, "default_model", "claude-sonnet-5")
        available = _make_available("databricks-engineer", "geral")
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            resp = MagicMock()
            resp.read.return_value = json.dumps(
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "agents": ["databricks-engineer"],
                                    "confidence": 0.9,
                                    "reason": "x",
                                }
                            ),
                        }
                    ]
                }
            ).encode()
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            agents, conf, _ = await select_agents("query", available)
        assert "temperature" not in captured["body"]
        assert agents == ["databricks-engineer"] and conf == 0.9


# ─── O que o dispatcher ENXERGA (hotfix 2026-09-22) ─────────────────────────


class TestDescricaoVisivelAoDispatcher:
    """Caso real: "me fale sobre o Genie Ontology" → fabric-ontology (85%).

    O dispatcher lê só os primeiros `_MAX_AGENT_DESC_CHARS` de cada descrição.
    No databricks-engineer, "Genie" aparecia no char 322 — invisível. No
    fabric-ontology, "Ontolog" aparece no início. O roteador só tinha um casamento
    lexical possível, e era o errado. Estes testes travam a janela visível.
    """

    def _visivel(self, nome: str) -> str:
        from data_agents.agents.dispatcher import _MAX_AGENT_DESC_CHARS
        from data_agents.agents.loader import preload_registry

        desc = " ".join((preload_registry()[nome].description or "").split())
        return desc[:_MAX_AGENT_DESC_CHARS].lower()

    def test_databricks_engineer_mostra_a_familia_genie_na_janela(self):
        vis = self._visivel("databricks-engineer")
        for termo in ("genie", "genie ontology", "genie one", "genie agents", "databricks"):
            assert termo in vis, f"'{termo}' fora dos primeiros chars que o dispatcher lê"

    def test_fabric_ontology_mostra_fabric_na_janela(self):
        vis = self._visivel("fabric-ontology")
        assert "fabric" in vis and "ontolog" in vis

    def test_prompt_do_dispatcher_desambigua_ontology(self):
        from data_agents.agents.dispatcher import _DISPATCHER_SYSTEM_PROMPT as p

        assert "Genie Ontology" in p and "Fabric IQ Ontology" in p
        assert "não decide plataforma" in p.lower()

    def test_supervisor_proibe_substituir_entre_plataformas(self):
        from data_agents.agents.prompts.supervisor_prompt import SUPERVISOR_SYSTEM_PROMPT as p

        assert "Never substitute across platforms" in p
        assert "agent not found" in p

    def test_dataset_de_roteamento_cobre_o_caso(self):
        from data_agents.evals.routing import load_cases

        casos = {c.id: c for c in load_cases()}
        c = casos["genie-ontology-databricks"]
        assert "databricks-engineer" in c.expect_any
        assert "fabric-ontology" in c.forbid, (
            "o usuário foi explícito: fabric-ontology NÃO pode ser chamado"
        )


# ─── Saldo/quota e erro transitório (2026-09-22) ─────────────────────────────


_QUOTA_BODY = (
    b'{"error":{"message":"Your account org-xyz <ak-abcdef123456> is suspended due to '
    b"insufficient balance, please recharge your account or check your plan and billing "
    b'details","type":"exceeded_current_quota_error"}}'
)


def _http_err(code: int, body: bytes = b"", headers: dict | None = None):
    import io
    import urllib.error
    from email.message import Message

    h = Message()
    for k, v in (headers or {}).items():
        h[k] = v
    return urllib.error.HTTPError(
        url="http://x", code=code, msg="err", hdrs=h, fp=io.BytesIO(body) if body else None
    )


def _ok_response():
    body = json.dumps(
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {"agents": ["databricks-engineer"], "confidence": 0.95, "reason": "ok"}
                    ),
                }
            ]
        }
    ).encode()
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestSaldoEErroTransitorio:
    """Caso real: Moonshot devolveu 429 exceeded_current_quota_error ("suspended due to
    insufficient balance"). O dispatcher tratou como qualquer erro, carregou os 24
    agentes e seguiu — pareceu regressão de roteamento. Sem saldo, o certo é parar."""

    @pytest.fixture(autouse=True)
    def _sem_dormir(self, monkeypatch):
        from data_agents.agents import dispatcher as disp

        self.esperas: list[float] = []

        async def _grava(s):
            self.esperas.append(s)

        monkeypatch.setattr(disp, "_sleep", _grava)

    @pytest.mark.parametrize(
        "code,body,esperado",
        [
            (429, _QUOTA_BODY.decode(), "quota"),
            (429, '{"error":{"type":"rate_limit_error","message":"slow down"}}', "transitorio"),
            (503, "", "transitorio"),
            (529, "", "transitorio"),
            (400, '{"error":{"type":"invalid_request_error"}}', "outro"),
            (401, "", "outro"),
        ],
    )
    def test_classifica(self, code, body, esperado):
        from data_agents.agents.dispatcher import classify_http_error

        assert classify_http_error(code, body) == esperado

    @pytest.mark.asyncio
    async def test_sem_saldo_para_na_hora_sem_fallback(self):
        from data_agents.config.exceptions import ProviderQuotaError

        chamadas = []

        def _urlopen(*a, **k):
            chamadas.append(1)
            raise _http_err(429, _QUOTA_BODY)

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            with pytest.raises(ProviderQuotaError) as exc:
                await select_agents("q", _make_available("databricks-engineer", "geral"))
        assert len(chamadas) == 1, "saldo zerado não melhora tentando de novo"
        assert self.esperas == []
        msg = str(exc.value)
        assert "saldo/quota" in msg and "exceeded_current_quota_error" in msg
        assert "ak-abcdef123456" not in msg and "org-xyz" not in msg, "identificador da conta vazou"

    @pytest.mark.asyncio
    async def test_429_de_rate_limit_tenta_de_novo_e_segue(self):
        respostas = [
            _http_err(429, b'{"error":{"type":"rate_limit_error"}}'),
            _ok_response(),
        ]

        def _urlopen(*a, **k):
            r = respostas.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            agents, conf, _ = await select_agents(
                "q", _make_available("databricks-engineer", "geral")
            )
        assert agents == ["databricks-engineer"] and conf == 0.95
        assert self.esperas == [2.0]

    @pytest.mark.asyncio
    async def test_retry_after_do_servidor_e_respeitado_com_teto(self):
        respostas = [
            _http_err(429, b"{}", {"Retry-After": "3"}),
            _http_err(429, b"{}", {"Retry-After": "120"}),
            _ok_response(),
        ]

        def _urlopen(*a, **k):
            r = respostas.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            await select_agents("q", _make_available("databricks-engineer", "geral"))
        assert self.esperas == [3.0, 10.0], "Retry-After honrado, mas nunca mais que 10s"

    @pytest.mark.asyncio
    async def test_transitorio_persistente_cai_no_fallback_depois_das_tentativas(self):
        chamadas = []

        def _urlopen(*a, **k):
            chamadas.append(1)
            raise _http_err(503)

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            agents, conf, reason = await select_agents(
                "q", _make_available("databricks-engineer", "fabric-engineer", "geral")
            )
        assert len(chamadas) == 3 and self.esperas == [2.0, 4.0]
        assert reason == "http_error:503" and conf == 0.0
        assert sorted(agents) == ["databricks-engineer", "fabric-engineer"]

    @pytest.mark.asyncio
    async def test_400_nao_tenta_de_novo(self):
        chamadas = []

        def _urlopen(*a, **k):
            chamadas.append(1)
            raise _http_err(400, b'{"error":{"type":"invalid_request_error"}}')

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            _, _, reason = await select_agents("q", _make_available("databricks-engineer", "geral"))
        assert len(chamadas) == 1 and reason == "http_error:400"

    def test_scrub_mascara_identificador_ak(self):
        from data_agents.agents.dispatcher import _SECRET_RE

        assert _SECRET_RE.sub("***", "conta <ak-faibitj3xufi11> ok") == "conta <***> ok"

    def test_cli_para_quando_nao_tem_saldo(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[2] / "data_agents/cli.py").read_text(
            encoding="utf-8"
        )
        assert "except ProviderQuotaError" in src
