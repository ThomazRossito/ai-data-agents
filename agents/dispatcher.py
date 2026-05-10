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
    from agents.dispatcher import select_agents, apply_fallback_policy
    from agents.loader import preload_registry

    available = preload_registry()
    selected, confidence, reason = await select_agents(query, available)
    final_agents = apply_fallback_policy(selected, confidence, available)
    options = build_supervisor_options(agent_names=final_agents)
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

from config.settings import settings

if TYPE_CHECKING:
    from agents.loader import AgentMeta

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

    payload = json.dumps(
        {
            "model": settings.default_model,
            "max_tokens": 256,
            "system": _DISPATCHER_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_msg}],
        }
    ).encode("utf-8")

    base = (settings.anthropic_base_url or "https://api.anthropic.com").rstrip("/")
    url = f"{base}/v1/messages"

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "User-Agent": "data-agents-api/1.0 dispatcher",
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
        logger.warning(f"Dispatcher HTTP {e.code}: {e.reason} — fallback para todos os agentes")
        return _all_delegatable(available), 0.0, f"http_error:{e.code}"
    except (urllib.error.URLError, TimeoutError) as e:
        logger.warning(f"Dispatcher network error: {e} — fallback para todos os agentes")
        return _all_delegatable(available), 0.0, f"network_error:{type(e).__name__}"
    except Exception as e:
        logger.error(f"Dispatcher unexpected error: {e}", exc_info=True)
        return _all_delegatable(available), 0.0, f"unexpected:{type(e).__name__}"

    # Parse da resposta
    try:
        text = data["content"][0]["text"].strip()
    except (KeyError, IndexError, TypeError):
        logger.warning(f"Dispatcher response sem content válido: {data}")
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
        logger.warning(
            f"Dispatcher retornou nenhum agente válido (raw={raw_agents}) — fallback"
        )
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


# ─── Helpers internos ────────────────────────────────────────────────────────


def _all_delegatable(available: dict[str, "AgentMeta"]) -> list[str]:
    """Retorna todos os nomes de agentes do registry, exceto os never-delegated."""
    return [n for n in available if n not in _NEVER_DELEGATED]
