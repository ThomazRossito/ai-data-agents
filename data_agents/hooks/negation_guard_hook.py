"""
Negation guard — negação categórica sem busca web não passa como fato.

O CASO QUE MOTIVOU (2026-09-14/15, três rodadas da mesma pergunta)
--------------------------------------------------------------------
    "me fale sobre o Genie Ontology"

  1ª  geral (T0, sem tools)            → "Não existe um produto oficial chamado…"
  2ª  databricks-engineer, sem buscar  → hedge; citou o exemplo do prompt como fonte
  3ª  databricks-engineer, curl+llms   → "não é um produto ou feature do Databricks"

A terceira é a mais instrutiva: o agente VERIFICOU (baixou llms.txt e duas
páginas de Genie), não achou o termo e concluiu inexistência. Mas o termo não
está no llms.txt — é um conceito documentado em duas outras páginas
(uc-semantics, genie-one/chat#ontology). Ausência numa busca parcial virou
"não existe", com a autoridade de "após verificação na documentação oficial".

Três iterações de prompt (Supervisor, geral.md, cache_prefix.md) não mudaram o
padrão. Prompt é texto mole. Este hook é o freio.

O QUE FAZ
---------
PostToolUse em TODAS as tools (matcher vazio), dois deveres:

  1. Registrar se houve **busca web** no turno (`mcp__tavily__tavily-search`,
     `mcp__firecrawl__*search*`). Estado por turno, resetado por
     `reset_negation_guard()` — mesmo padrão do migration_gate_hook.

  2. Quando a tool é `Agent` (retorno de subagente): procurar **negação
     categórica de existência** no texto. Se achar e NÃO houve busca web no
     turno, injeta `additionalContext` para o Supervisor com instrução
     just-in-time: trate como "não encontrado nas fontes consultadas", não
     como fato; reformule; ofereça verificar. E grava um evento
     `unverified_negation` em logs/workflows.jsonl — vira métrica.

POR QUE additionalContext E NÃO updatedToolOutput
-------------------------------------------------
`updatedToolOutput` exige casar o schema de saída da tool; para `Agent` o
formato não é documentado e um mismatch é descartado em silêncio (o SDK mantém
o original). `additionalContext` é sempre aceito e chega ao modelo colado ao
resultado — instrução no ponto exato da decisão, não enterrada em 38K de prompt.

O QUE NÃO FAZ
-------------
Não julga se a feature existe. Não sabe. Só sabe que "não existe" foi dito sem
busca web, e que essa combinação errou três vezes em dois dias. Curl em duas
páginas NÃO conta como busca: foi exatamente o que falhou na 3ª rodada — o
índice não tinha o termo e as páginas certas não foram abertas.

LIMITE HONESTO
--------------
O Supervisor ainda pode ignorar a instrução. Mas agora (a) ela chega no momento
certo, (b) fica registrada, e (c) dá para medir quantas vezes o sistema afirmou
inexistência sem verificar — `unverified_negation_rate`, ao lado de
`fallback_rate`. Sem medição, nada disso é auditável.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("data_agents.hooks.negation_guard")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_WORKFLOWS_LOG = _PROJECT_ROOT / "logs" / "workflows.jsonl"

#: Tools que contam como VERIFICAÇÃO na web. Curl via Bash não entra: foi o
#: que falhou na 3ª rodada (índice sem o termo, páginas erradas abertas).
#: `WebSearch` é a busca built-in do Claude Code — no eval de 2026-09-15 foi
#: por ela que o Supervisor (e o general-purpose) verificaram em 5/12 casos;
#: sem contá-la, o guard puniria uma negação que FOI verificada. `WebFetch`
#: fica fora pelo mesmo motivo do curl: abrir uma página não é buscar.
_WEB_SEARCH_TOOLS: tuple[str, ...] = (
    "mcp__tavily__tavily-search",
    "mcp__tavily__tavily-extract",
    "mcp__firecrawl__firecrawl_search",
    "mcp__firecrawl__firecrawl_scrape",
    "WebSearch",
)

#: Negação categórica de existência — PT e EN. Casa a FORMA da afirmação, não o
#: assunto: o hook não sabe qual é o produto, só que alguém disse que não existe.
_NEGATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bn[aã]o\s+existe\b", re.IGNORECASE),
    re.compile(r"\bn[aã]o\s+[eé]\s+um[a]?\s+(produto|feature|recurso|funcionalidade|servi[cç]o)\b", re.IGNORECASE),
    re.compile(r"\bn[aã]o\s+h[aá]\s+(nenhum[a]?|um[a]?)\s+(produto|feature|recurso|funcionalidade)\b", re.IGNORECASE),
    re.compile(r"\bn[aã]o\s+[eé]\s+um\s+produto\s+real\b", re.IGNORECASE),
    re.compile(r"\bdoes\s+not\s+exist\b", re.IGNORECASE),
    re.compile(r"\bis\s+not\s+an?\s+(product|feature|real\s+product)\b", re.IGNORECASE),
    re.compile(r"\bthere\s+is\s+no\s+(such\s+)?(product|feature)\b", re.IGNORECASE),
)  # fmt: skip

#: Estado por turno: houve busca web? Resetado no início de cada mensagem do usuário.
_turn_state: dict[str, Any] = {"web_search": False, "web_search_tools": []}


def reset_negation_guard() -> None:
    """Zera o estado do turno. Chamar junto de `reset_migration_gate()`."""
    _turn_state["web_search"] = False
    _turn_state["web_search_tools"] = []


def _extract_text(input_data: dict[str, Any]) -> str:
    """Texto do retorno da tool, seja qual for a chave/forma que o SDK usou."""
    for key in ("tool_response", "tool_output", "output"):
        value = input_data.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            # {"content": [{"type": "text", "text": ...}, ...]} ou {"text": ...}
            if isinstance(value.get("text"), str):
                return value["text"]
            content = value.get("content")
            if isinstance(content, list):
                return "\n".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
        if isinstance(value, list):
            return "\n".join(
                str(b.get("text", "")) if isinstance(b, dict) else str(b) for b in value
            )
        return str(value)
    return ""


def find_negations(text: str) -> list[str]:
    """Trechos (±80 chars) em que o texto afirma inexistência. Vazio se não há."""
    achados: list[str] = []
    for pat in _NEGATION_PATTERNS:
        for m in pat.finditer(text):
            ini, fim = max(0, m.start() - 80), min(len(text), m.end() + 80)
            achados.append(text[ini:fim].replace("\n", " ").strip())
    return achados


def _log_event(agent: str, snippets: list[str], tool_use_id: str | None) -> None:
    try:
        _WORKFLOWS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_WORKFLOWS_LOG, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "event": "unverified_negation",
                        # Campos canônicos do LOGGING_CONTRACT (Phase 10) — permitem
                        # JOIN com audit.jsonl / sessions.jsonl / transcript.
                        "session_id": _session_id() or None,
                        "agent_name": agent,
                        "tool_use_id": tool_use_id,
                        "web_search_in_turn": False,
                        "snippets": snippets[:3],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except OSError as exc:  # pragma: no cover — log nunca derruba o hook
        logger.warning("negation_guard: falha ao gravar evento: %s", exc)


def _session_id() -> str:
    """Mesmo session_id que o audit_hook usa — fonte única, import tardio (evita ciclo)."""
    try:
        from data_agents.hooks import audit_hook

        return str(getattr(audit_hook, "_current_session_id", "") or "")
    except Exception:  # noqa: BLE001 — log nunca derruba o hook
        return ""


def _agent_name(tool_input: dict[str, Any]) -> str:
    return str(
        tool_input.get("subagent_type")
        or tool_input.get("agent_name")
        or tool_input.get("name")
        or "?"
    )


async def guard_unverified_negation(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
) -> dict[str, Any]:
    """PostToolUse (todas as tools).

    - tool de busca web → marca o turno como verificado.
    - `Agent` com negação categórica e turno NÃO verificado → additionalContext
      ao Supervisor + evento `unverified_negation`.
    """
    if not input_data or not isinstance(input_data, dict):
        return {}

    tool_name: str = input_data.get("tool_name", "") or ""

    if tool_name in _WEB_SEARCH_TOOLS:
        _turn_state["web_search"] = True
        _turn_state["web_search_tools"].append(tool_name)
        return {}

    if tool_name != "Agent":
        return {}

    texto = _extract_text(input_data)
    if not texto:
        return {}

    negacoes = find_negations(texto)
    if not negacoes:
        return {}

    if _turn_state["web_search"]:
        # Houve busca web neste turno — a negação pode estar fundamentada.
        # Não é papel deste hook julgar a qualidade da busca.
        return {}

    tool_input = input_data.get("tool_input", {}) or {}
    agente = _agent_name(tool_input if isinstance(tool_input, dict) else {})
    _log_event(agente, negacoes, tool_use_id)
    logger.warning(
        "negation_guard: '%s' afirmou inexistência sem busca web no turno — %d trecho(s)",
        agente,
        len(negacoes),
    )

    exemplo = negacoes[0][:160]
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "⚠️ NEGATION GUARD — o subagente afirmou que algo NÃO EXISTE, e nenhuma "
                "busca web (tavily/firecrawl) foi feita neste turno. Isto já produziu "
                "resposta falsa três vezes: ausência numa busca parcial NÃO é evidência de "
                "inexistência — o termo pode estar em página que não foi aberta, ou ser "
                "recente demais para o índice.\n"
                f"Trecho: «{exemplo}»\n"
                "AO SINTETIZAR, obrigatoriamente:\n"
                "1. NÃO repasse a negação. Reformule como: \"não encontrei '<termo>' nas "
                'fontes consultadas (<liste-as>)".\n'
                "2. Diga que pode ser feature recente ou nome usado só em parte da documentação.\n"
                "3. Ofereça verificar com busca web no termo exato antes de concluir.\n"
                "Se o usuário insistir numa resposta definitiva, delegue de novo pedindo "
                "explicitamente `tavily-search` com o termo entre aspas e domínio oficial."
            ),
        }
    }
