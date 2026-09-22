"""
Agent Dispatcher — Two-Stage Routing.

Resolve um problema arquitetural fundamental: o `claude-agent-sdk` carrega
TODOS os 14 agentes (~80K tokens) no system prompt do Supervisor a cada
chamada, mesmo que apenas 2-3 sejam relevantes para a query do usuário.

Esse padrão "tolerável" no Claude Sonnet (cache agressivo + throughput alto)
quebra com modelos como Kimi K2.6: prompts gigantes travam o endpoint.

Solução: chamada leve **antes** do Supervisor que recebe apenas nomes +
descrições dos agentes (~3K tokens) e devolve a lista de 1-5 agentes
relevantes. O Supervisor então é construído carregando APENAS esses agentes
(reduz prompt de ~100K para ~25-30K tokens).

Custo: ~$0.0001 por dispatch (chamada minúscula).
Economia: 3-4x menos tokens, processa em qualquer modelo, ~80% mais barato
no Sonnet também.

Política de fallback baseada em confidence:
  - >0.80  → usa apenas selected (máxima economia)
  - 0.60-0.80 → adiciona `data-quality-steward` + `governance-auditor`
                como vizinhos comuns (segurança razoável)
  - <0.60  → expande para todos os 14 agentes (fallback seguro)

Uso:
    from data_agents.agents.dispatcher import select_agents, apply_fallback_policy
    from data_agents.agents.loader import preload_registry

    available = preload_registry()
    selected, confidence, reason = await select_agents(query, available)
    final_agents = apply_fallback_policy(selected, confidence, available)
    options = build_supervisor_options(agent_names=final_agents)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

from data_agents.config.settings import settings

if TYPE_CHECKING:
    from data_agents.agents.loader import AgentMeta

logger = logging.getLogger("data_agents.dispatcher")

# ─── Constantes ──────────────────────────────────────────────────────────────

#: Agentes "vizinhos comuns" — adicionados quando confidence está em zona média.
#: data-quality e governance são úteis em quase qualquer projeto de dados,
#: então quando o dispatcher está incerto, é razoável incluí-los preventivamente.
_NEIGHBOR_AGENTS = ["data-quality-steward", "governance-auditor"]

#: Agentes que NUNCA devem ser delegados pelo Supervisor (são chamados via
#: caminhos especiais ou não fazem sentido no contexto multi-agente).
_NEVER_DELEGATED = {"geral"}

#: Limite máximo de chars do prompt que vai pro dispatcher (evita truncar
#: queries longas no log + protege custo).
_MAX_QUERY_CHARS = 2000

#: Limite máximo de chars da descrição de cada agente injetada no prompt.
_MAX_AGENT_DESC_CHARS = 240

_DISPATCHER_SYSTEM_PROMPT = """Você é um router de agentes especialistas em engenharia de dados.

Recebe uma query do usuário e a lista de agentes disponíveis. Devolve quais agentes são relevantes para o trabalho.

REGRAS DE SAÍDA:
- Retorne APENAS JSON válido, sem markdown, sem explicação fora do JSON.
- Formato exato:
  {"agents": ["nome1", "nome2"], "confidence": 0.95, "reason": "explicação curta"}
- "agents": 1 a 5 nomes de agentes do catálogo (use o nome exato como aparece).
- "confidence": float 0.0-1.0 indicando o quão certo você está da escolha.
- "reason": ≤20 palavras explicando por que esses agentes.

REGRAS DE ROTEAMENTO:
- Query sobre Databricks (Spark, Delta, Unity Catalog, Genie, jobs) → agentes Databricks, NÃO Fabric.
- Query sobre Microsoft Fabric (Lakehouse, Power BI, Direct Lake, Eventhouse) → agentes Fabric, NÃO Databricks.
- Query sobre migração de banco relacional → migration-expert + agente da plataforma destino.
- Query sobre qualidade de dados → data-quality-steward.
- Query sobre governança/PII/LGPD → governance-auditor.
- Query sobre planejamento amplo de projeto → 2-4 agentes relevantes (não tudo).
- Query ambígua ou multi-domínio → confidence ≤0.7 e mais agentes.
- NUNCA inclua o agente "geral" — ele é caminho separado.

Sua escolha alimenta um Supervisor que carrega APENAS esses agentes na sessão. Quanto mais focado, mais barato e rápido."""


# ─── API pública ─────────────────────────────────────────────────────────────


async def select_agents(
    query: str,
    available: dict[str, "AgentMeta"],
    timeout_s: int = 30,
) -> tuple[list[str], float, str]:
    """
    Chama o dispatcher (Kimi K2.6 com prompt minúsculo) para escolher
    quais agentes carregar para a query.

    Args:
        query: Texto do prompt do usuário.
        available: Dict {nome: AgentMeta} dos agentes disponíveis no registry.
        timeout_s: Timeout da chamada HTTP. Default 30s (não deve demorar mais
            que isso para um prompt de ~3K tokens).

    Returns:
        Tupla (agent_names, confidence, reason):
          - agent_names: lista de nomes de agentes selecionados (filtrada para
            conter apenas nomes presentes em `available`)
          - confidence: float 0.0-1.0 (0.0 = fallback por erro)
          - reason: string explicativa para log/debug

    Em caso de erro de rede, JSON inválido ou nenhum agente válido retornado,
    cai em fallback retornando todos os agentes com confidence 0.0.
    """
    # Constrói lista compacta — só nome + tier + descrição truncada
    agents_lines = []
    for name in sorted(available):
        if name in _NEVER_DELEGATED:
            continue
        meta = available[name]
        desc = (meta.description or "")[:_MAX_AGENT_DESC_CHARS]
        agents_lines.append(f"- {name} (tier {meta.tier}): {desc}")
    agents_block = "\n".join(agents_lines)

    user_msg = (
        f"## Query do usuário\n{query[:_MAX_QUERY_CHARS]}\n\n"
        f"## Agentes disponíveis\n{agents_block}\n\n"
        "Retorne o JSON com a seleção."
    )

    # BUG CORRIGIDO (auditoria 2026-09-13) — o dispatcher falhava em TODA query.
    #
    # Sem `thinking` explícito, o Kimi K2.6 raciocina por padrão. Numa execução
    # real observada, a resposta veio assim:
    #
    #   content     = [{"type": "thinking", ...}]      <- só isso, sem bloco de texto
    #   stop_reason = "max_tokens"
    #   usage       = {"output_tokens": 256, "thinking_tokens": 255}
    #
    # Ou seja: o modelo gastou os 256 tokens PENSANDO e nunca emitiu a resposta.
    # O parse caía em "no_content", o fallback carregava TODOS os agentes, e o
    # two-stage routing — que existe justamente para manter o system prompt em
    # ~25K em vez de ~80K — era anulado silenciosamente (só um WARNING no log).
    #
    # Dois ajustes, um para a causa e outro para a robustez:
    #   1. thinking=disabled — isto é classificação barata, não precisa raciocínio.
    #   2. max_tokens folgado — se um modelo futuro exigir thinking sempre-ligado
    #      (K3, K2.7-Code), ainda sobra orçamento para o texto sair.
    #
    # `temperature: 0` reduz a variação, mas NÃO dá determinismo neste endpoint.
    #
    # CORREÇÃO (2026-09-14) — este comentário afirmava que temperature 0 tornava
    # o roteamento reprodutível ("a mesma pergunta seleciona os mesmos agentes
    # entre execuções"). Era suposição, não medição. Três rodadas do
    # `make eval-routing` com o dataset idêntico mostraram:
    #
    #   conjunto de agentes idêntico nos 3 runs : 15/25 casos
    #   conjunto variou                          : 10/25 casos
    #
    # A variação é sempre de MARGEM, nunca de núcleo: em 75/75 execuções de caso
    # o agente esperado apareceu. O que oscila é o acompanhante adjacente
    # (`fabric-rti` às vezes vem com `fabric-engineer`; `migracao-hadoop` trocou
    # `migration-expert` por `databricks-cost-calculator` num run). A confidence
    # também oscila: `ambiguo-plataforma-nova` deu 75% / 65% / 75%.
    #
    # Consequência prática: não trate o roteamento como cacheável por hash da
    # query, e não aperte o gate de routing_accuracy só porque uma rodada deu
    # 100% — o piso de ruído é real. Ver data_agents/evals/routing.py.
    base = (settings.anthropic_base_url or "https://api.anthropic.com").rstrip("/")
    url = f"{base}/v1/messages"
    payload = json.dumps(build_dispatcher_payload(user_msg, settings.default_model, base)).encode(
        "utf-8"
    )

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "User-Agent": "ai-data-agents/1.0 dispatcher",
        },
        method="POST",
    )

    # Roda HTTP em thread (urllib é síncrono, mas chamada é leve <30s)
    def _do_request():
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # nosec B310
            return json.loads(resp.read().decode("utf-8"))

    try:
        data = await asyncio.to_thread(_do_request)
    except urllib.error.HTTPError as e:
        # O corpo do erro é onde a API diz O QUE rejeitou. Sem ele, o eval de
        # 2026-09-15 registrou 12× "HTTP 400: Bad Request" contra a Anthropic e
        # ninguém soube qual campo do payload era o problema.
        body = _http_error_body(e)
        logger.warning(
            f"Dispatcher HTTP {e.code}: {e.reason} — fallback para todos os agentes"
            + (f" — corpo: {body}" if body else "")
        )
        return _all_delegatable(available), 0.0, f"http_error:{e.code}"
    except (urllib.error.URLError, TimeoutError) as e:
        logger.warning(f"Dispatcher network error: {e} — fallback para todos os agentes")
        return _all_delegatable(available), 0.0, f"network_error:{type(e).__name__}"
    except Exception as e:
        logger.error(f"Dispatcher unexpected error: {e}", exc_info=True)
        return _all_delegatable(available), 0.0, f"unexpected:{type(e).__name__}"

    # Parse da resposta — NUNCA assumir que content[0] é o bloco de texto.
    #
    # Modelos com raciocínio estendido devolvem um bloco `thinking` PRIMEIRO, e
    # `content[0]["text"]` levantava KeyError. Mesma classe do bug já corrigido
    # no extrator de tokens: varrer os blocos procurando `type == "text"`.
    # Aceita `type: "text"` e também blocos sem `type` (proxies compatíveis nem
    # sempre o emitem); pula `thinking` e qualquer outro tipo.
    text = ""
    for bloco in data.get("content") or []:
        if not isinstance(bloco, dict):
            continue
        if bloco.get("type") in (None, "text") and bloco.get("text"):
            text = str(bloco["text"]).strip()
            break

    if not text:
        # Diagnóstico acionável: sem isto, "no_content" não dizia POR QUE falhou.
        tipos = [b.get("type") for b in (data.get("content") or []) if isinstance(b, dict)]
        logger.warning(
            "Dispatcher sem bloco de texto — fallback para todos os agentes. "
            "blocos=%s stop_reason=%s usage=%s",
            tipos,
            data.get("stop_reason"),
            data.get("usage"),
        )
        return _all_delegatable(available), 0.0, "no_content"

    # Remove possíveis code fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"Dispatcher retornou JSON inválido: {text[:200]} — {e}")
        return _all_delegatable(available), 0.0, "invalid_json"

    raw_agents = parsed.get("agents", []) or []
    confidence_raw = parsed.get("confidence", 0.5)
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))  # clamp [0, 1]
    reason = str(parsed.get("reason", "")).strip()[:200]

    # Filtra: só nomes válidos no registry, e remove "geral" se aparecer
    selected = [
        n for n in raw_agents if isinstance(n, str) and n in available and n not in _NEVER_DELEGATED
    ]

    if not selected:
        logger.warning(f"Dispatcher retornou nenhum agente válido (raw={raw_agents}) — fallback")
        return _all_delegatable(available), 0.0, "empty_selection"

    logger.info(
        f"Dispatcher selecionou {len(selected)}/{len(available)} agentes: "
        f"{selected} (confidence={confidence:.0%}, reason={reason!r})"
    )
    return selected, confidence, reason


def apply_fallback_policy(
    selected: list[str],
    confidence: float,
    available: dict[str, "AgentMeta"],
) -> list[str]:
    """
    Aplica política de fallback baseada em confidence.

    - confidence >= 0.80  → retorna `selected` (sem mudanças)
    - confidence >= 0.60  → adiciona vizinhos comuns (data-quality, governance)
    - confidence <  0.60  → expande para todos os agentes do registry

    Args:
        selected: Agentes escolhidos pelo dispatcher.
        confidence: Score 0.0-1.0 retornado pelo dispatcher.
        available: Dict completo de agentes disponíveis.

    Returns:
        Lista final de nomes de agentes a carregar (preserva ordem, sem
        duplicatas).
    """
    if confidence >= 0.80:
        return list(dict.fromkeys(selected))

    if confidence >= 0.60:
        # Adiciona vizinhos comuns (preserva ordem, sem duplicatas)
        extras = [a for a in _NEIGHBOR_AGENTS if a in available]
        return list(dict.fromkeys(selected + extras))

    # Confiança baixa — fallback safe: carrega tudo
    return _all_delegatable(available)


def format_dispatcher_log(
    selected: list[str],
    final: list[str],
    confidence: float,
    reason: str,
    total_available: int,
) -> str:
    """
    Formata uma linha amigável com o resultado do dispatcher para mostrar
    ao usuário no terminal/UI.

    Args:
        selected: Agentes que o dispatcher escolheu originalmente.
        final: Agentes finais após apply_fallback_policy (pode ser maior).
        confidence: Score 0.0-1.0.
        reason: Razão curta dada pelo dispatcher.
        total_available: Total de agentes no registry (para mostrar X/Y).

    Returns:
        String formatada para exibição. Exemplo:
            "🎯 Dispatcher: databricks-engineer, data-quality-steward
             (conf=87% · 2/14 agentes · razão: query menciona Spark + validação)"
    """
    n_final = len(final)
    main_part = f"🎯 Dispatcher: {', '.join(final)}"
    suffix = f" (conf={confidence:.0%} · {n_final}/{total_available} agentes"
    extras = [a for a in final if a not in selected]
    if extras:
        suffix += f" · +{len(extras)} fallback"
    if reason:
        suffix += f" · {reason}"
    suffix += ")"
    return main_part + suffix


def build_dispatcher_payload(user_msg: str, model: str, base_url: str) -> dict:
    """Corpo da chamada do dispatcher. Puro — testável sem rede.

    `temperature` só vai para a Moonshot. Contra a Anthropic, os modelos da
    família Claude 5 rejeitam o campo com HTTP 400:

        {"type":"invalid_request_error","message":"`temperature` is deprecated for this model."}

    Foi isso que derrubou o dispatcher em 24/24 casos dos dois evals contra o
    Sonnet 5 (2026-09-15) — fallback para 24 agentes, prompt 4× maior, custo
    US$11,7 por rodada e pipeline incomparável. Na Moonshot o campo fica como
    estava: o baseline do `eval-routing` (100%/100%/100%, fallback 0%) foi
    medido com ele, e não há motivo para mexer no que está medido.
    """
    body: dict = {
        "model": model,
        "max_tokens": 512,
        "thinking": {"type": "disabled"},
        "system": _DISPATCHER_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_msg}],
    }
    if "moonshot" in base_url.lower():
        body["temperature"] = 0
    return body


# ─── Helpers internos ────────────────────────────────────────────────────────


def _all_delegatable(available: dict[str, "AgentMeta"]) -> list[str]:
    """Retorna todos os nomes de agentes do registry, exceto os never-delegated."""
    return [n for n in available if n not in _NEVER_DELEGATED]


_HTTP_ERROR_BODY_MAX = 400
_SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{6,}|dapi[a-f0-9]{8,}|tvly-[A-Za-z0-9_\-]{6,})")


def _http_error_body(e: urllib.error.HTTPError) -> str:
    """Corpo do erro HTTP, truncado e sem quebras de linha. Nunca levanta.

    Só o corpo da RESPOSTA é lido — a request (que carrega a chave no header)
    não entra. Se a API ecoar algo que pareça chave, `scrub` mascara.
    """
    try:
        raw = e.read()
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    except Exception:  # noqa: BLE001 — diagnóstico nunca derruba o fallback
        return ""
    text = " ".join(text.split())
    text = _SECRET_RE.sub(lambda m: m.group(0)[:4] + "…", text)
    return text[:_HTTP_ERROR_BODY_MAX]
