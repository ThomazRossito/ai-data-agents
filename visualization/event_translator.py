"""
Event Translator — converte entradas raw dos JSONLs no schema visual.

O frontend Three.js consome um stream homogêneo com 4 tipos de evento:

  - delegation         : Supervisor → sub-agente foi acionado
                         (do workflows.jsonl)
  - tool_call          : um agente fez uma tool call
                         (do audit.jsonl, filtra os que importam visualmente)
  - dispatcher_decision: o dispatcher selecionou N agentes pra essa query
                         (do audit.jsonl OU log dedicado quando existir)
  - session_end        : sessão encerrou, com custo/turns finais
                         (do audit.jsonl evento `session_end`)

Schema final (frontend espera exatamente esses campos):
    {
      "type": "delegation" | "tool_call" | "dispatcher_decision" | "session_end",
      "ts":   ISO-8601 string,
      "session_id": str | null,
      "agent": str | null,        # nome canônico (data-agents-api registry)
      "tool": str | null,         # nome MCP ou ferramenta
      "platform": str | null,     # "databricks" | "fabric" | ... | null
      "metadata": dict             # campos extras (custo, ids, etc.)
    }

Nomes de agente normalizam pro formato do registry (kebab-case lowercase):
    "Python Expert"       → "python-expert"
    "Data Quality Steward" → "data-quality-steward"
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("data_agents.visualization.translator")

# Conjunto canônico de agentes do registry. Eventos com agentes fora dessa lista
# são logados mas passam (resiliente a novos agentes).
KNOWN_AGENTS = {
    "databricks-engineer",
    "databricks-ai",
    "fabric-engineer",
    "fabric-rti",
    "fabric-ontology",
    "migration-expert",
    "python-expert",
    "dbt-expert",
    "data-quality-steward",
    "governance-auditor",
    "data-contracts-engineer",
    "data-mesh-architect",
    "business-analyst",
    "geral",
}


def normalize_agent_name(raw: str | None) -> str | None:
    """
    Normaliza nomes de agente vindos dos logs pro padrão do registry.

    Exemplos:
        "Python Expert"        → "python-expert"
        "Data Quality Steward" → "data-quality-steward"
        "databricks-engineer"  → "databricks-engineer" (já canônico)
        "Supervisor"           → "supervisor" (passa, frontend trata especial)
        None                   → None
    """
    if not raw:
        return None
    # Já está em kebab-case
    if "-" in raw and raw.islower():
        return raw
    # "Python Expert" / "Data Quality Steward" / etc.
    return re.sub(r"\s+", "-", raw.strip().lower())


def _platform_from_tool(tool_name: str | None) -> str | None:
    """Infere plataforma do nome da tool MCP."""
    if not tool_name:
        return None
    if tool_name.startswith("mcp__databricks_genie__"):
        return "databricks"
    if tool_name.startswith("mcp__databricks__"):
        return "databricks"
    if tool_name.startswith("mcp__fabric_rti__"):
        return "fabric"
    if tool_name.startswith("mcp__fabric_sql__"):
        return "fabric"
    if tool_name.startswith("mcp__fabric"):
        return "fabric"
    if tool_name.startswith("mcp__migration_source__"):
        return "migration"
    if tool_name.startswith("mcp__postgres__"):
        return "postgres"
    if tool_name.startswith("mcp__context7__"):
        return "docs"
    if tool_name.startswith("mcp__memory_mcp__"):
        return "memory"
    if tool_name.startswith("mcp__github__"):
        return "github"
    if tool_name.startswith("mcp__tavily__") or tool_name.startswith("mcp__firecrawl__"):
        return "web"
    return None


# ─── Tradução por origem ─────────────────────────────────────────────────────


def translate_workflow_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    """
    workflows.jsonl emite `workflow_step` quando o Supervisor delega pra um
    sub-agente. Cada entrada vira UM evento de `delegation`.
    """
    if raw.get("event") != "workflow_step":
        return None
    agent = normalize_agent_name(raw.get("agent"))
    if not agent:
        return None
    return {
        "type": "delegation",
        "ts": raw.get("timestamp"),
        "session_id": raw.get("session_id"),
        "agent": agent,
        "tool": None,
        "platform": None,
        "metadata": {
            "workflow": raw.get("workflow"),
            "tool_use_id": raw.get("tool_use_id"),
            "prompt_preview": (raw.get("prompt_preview") or "")[:160],
        },
    }


# Tools que o frontend ignora (ruído visual)
_NOISE_TOOLS = {
    "Todowrite",
    "TodoWrite",
    "ExitPlanMode",
}


def translate_audit_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    """
    audit.jsonl tem várias variantes de evento. Filtra pro essencial:

      - event="tool_call" + tool_name relevante → tool_call visual
      - event="agent_delegated"                → delegation (alternativo)
      - event="dispatcher_decision"            → dispatcher_decision
      - event="session_end"                    → session_end
    """
    event = raw.get("event")

    if event == "dispatcher_decision":
        selected = raw.get("selected") or raw.get("agent_names") or []
        return {
            "type": "dispatcher_decision",
            "ts": raw.get("timestamp"),
            "session_id": raw.get("session_id"),
            "agent": None,
            "tool": None,
            "platform": None,
            "metadata": {
                "selected": [normalize_agent_name(n) for n in selected if n],
                "confidence": raw.get("confidence", 0.0),
                "reason": raw.get("reason", ""),
                "fallback_applied": raw.get("fallback_applied", False),
            },
        }

    if event == "session_end":
        return {
            "type": "session_end",
            "ts": raw.get("timestamp"),
            "session_id": raw.get("session_id"),
            "agent": None,
            "tool": None,
            "platform": None,
            "metadata": {
                "cost_usd": raw.get("cost_usd", 0.0),
                "turns": raw.get("turns", 0),
                "duration_s": raw.get("duration_s", 0.0),
            },
        }

    if event == "agent_delegated":
        # Variante alternativa de delegação registrada no audit
        agent = normalize_agent_name(raw.get("agent_name") or raw.get("agent"))
        if not agent:
            return None
        return {
            "type": "delegation",
            "ts": raw.get("timestamp"),
            "session_id": raw.get("session_id"),
            "agent": agent,
            "tool": None,
            "platform": None,
            "metadata": {"tool_use_id": raw.get("tool_use_id")},
        }

    if event == "tool_call":
        tool_name = raw.get("tool_name")
        if not tool_name or tool_name in _NOISE_TOOLS:
            return None
        agent = normalize_agent_name(raw.get("agent_name"))
        platform = raw.get("platform") or _platform_from_tool(tool_name)
        return {
            "type": "tool_call",
            "ts": raw.get("timestamp"),
            "session_id": raw.get("session_id"),
            "agent": agent,
            "tool": tool_name,
            "platform": platform,
            "metadata": {
                "operation_type": raw.get("operation_type"),
                "has_error": raw.get("has_error", False),
                "result_type": raw.get("result_type"),
                "tool_use_id": raw.get("tool_use_id"),
            },
        }

    return None


def translate_session_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    """
    sessions.jsonl: cada linha é o resumo final de uma sessão concluída.
    Não tem campo `event` — toda entrada é tratada como `session_end`.
    """
    if "total_cost_usd" not in raw and "num_turns" not in raw:
        return None
    return {
        "type": "session_end",
        "ts": raw.get("timestamp"),
        "session_id": raw.get("session_id"),
        "agent": None,
        "tool": None,
        "platform": None,
        "metadata": {
            "cost_usd": raw.get("total_cost_usd", 0.0),
            "turns": raw.get("num_turns", 0),
            "duration_s": raw.get("duration_s", 0.0),
            "session_type": raw.get("session_type", ""),
        },
    }


def translate(raw: dict[str, Any], source: str) -> dict[str, Any] | None:
    """
    Despacha pro tradutor certo conforme a fonte (`audit`, `workflow`, `session`).
    Retorna o evento visual ou None se deve ser filtrado.
    """
    if source == "workflow":
        return translate_workflow_event(raw)
    if source == "audit":
        return translate_audit_event(raw)
    if source == "session":
        return translate_session_event(raw)
    logger.debug(f"fonte desconhecida: {source}")
    return None
