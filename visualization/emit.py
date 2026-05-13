"""
visualization/emit.py — Emissor manual de eventos JSONL pra viz.

Comandos que **furam o Supervisor** (`/party`, `/geral`, `/analyze-project`)
não passam pelos hooks (`audit_hook`, `workflow_tracker`, `session_logger`),
então não alimentam `logs/audit.jsonl`, `logs/workflows.jsonl`, `logs/sessions.jsonl`
— os arquivos que o tailer da viz fica observando.

Resultado: a cena 3D ficava muda durante esses comandos.

Este módulo expõe uma API pequena pra emitir os mesmos eventos
**diretamente nos JSONLs**, sem depender do SDK ou de hooks. A viz consome
exatamente o mesmo schema que `event_translator.py` já entende.

Uso típico — DOMA Party Mode:

    from visualization.emit import (
        emit_dispatcher_decision,
        emit_delegation,
        emit_tool_call,
        emit_session_end,
    )

    emit_dispatcher_decision(selected=agent_names, session_id=sid, reason="party")
    for name in agent_names:
        emit_delegation(agent=name, session_id=sid, workflow="party_mode",
                        prompt_preview=query)
    results = await asyncio.gather(*tasks)
    for name, _, _ in results:
        emit_tool_call(agent=name, tool="party.respond", session_id=sid)
    emit_session_end(session_id=sid, cost_usd=total, turns=len(results), duration_s=dt)

Falhas em I/O do JSONL nunca propagam — a viz é cosmética, não pode quebrar
a query do usuário se logs/ estiver read-only ou o disco cheio.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("data_agents.visualization.emit")

# Mesmo caminho usado por hooks/audit_hook.py — não centralize aqui pra evitar
# import circular com config; logs/ é sempre relativo à raiz do repo.
LOGS_DIR = Path(__file__).parent.parent / "logs"
AUDIT_LOG = LOGS_DIR / "audit.jsonl"
WORKFLOWS_LOG = LOGS_DIR / "workflows.jsonl"


def _now_iso() -> str:
    """ISO-8601 UTC com sufixo Z — formato que o resto do sistema usa."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write(path: Path, record: dict[str, Any]) -> None:
    """
    Grava um registro JSON-line. Nunca propaga exceção — viz é cosmética.

    Cria diretório `logs/` se faltar (idempotente).
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        record.setdefault("timestamp", _now_iso())
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:  # noqa: BLE001 — viz nunca pode quebrar a query
        logger.warning("falha emitindo viz event: %s", exc)


# ─── API pública ─────────────────────────────────────────────────────────────


def emit_dispatcher_decision(
    selected: list[str],
    session_id: str | None,
    reason: str = "manual",
    confidence: float = 1.0,
) -> None:
    """
    Anuncia à viz qual conjunto de agentes vai responder à query.
    Frontend renderiza isso como "rack selecionado" antes do trabalho começar.

    Args:
        selected:    nomes canônicos dos agentes (kebab-case, do registry)
        session_id:  ID da sessão CLI/UI; pode ser None se não houver
        reason:      contexto livre (ex: "party_full", "analyze_databricks")
        confidence:  0.0–1.0; sempre 1.0 pra emissão manual
    """
    _write(
        AUDIT_LOG,
        {
            "event": "dispatcher_decision",
            "session_id": session_id,
            "selected": list(selected),
            "agent_names": list(selected),  # alias usado por algumas variantes
            "confidence": confidence,
            "reason": reason,
            "fallback_applied": False,
        },
    )


def emit_delegation(
    agent: str,
    session_id: str | None,
    workflow: str = "manual",
    prompt_preview: str = "",
) -> None:
    """
    Indica à viz que um agente específico começou a trabalhar agora.
    Frontend acende o rack/cabeça/halo do agente.

    Args:
        agent:           nome canônico (kebab-case)
        session_id:      ID da sessão
        workflow:        rótulo lógico do fluxo ("party_mode", "geral", "analyze")
        prompt_preview:  primeiros caracteres da query (truncado a 160)
    """
    _write(
        WORKFLOWS_LOG,
        {
            "event": "workflow_step",
            "session_id": session_id,
            "agent": agent,
            "workflow": workflow,
            "tool_use_id": f"{workflow}_{agent}",
            "prompt_preview": (prompt_preview or "")[:160],
        },
    )


def emit_tool_call(
    agent: str,
    tool: str,
    session_id: str | None,
    platform: str | None = None,
    has_error: bool = False,
) -> None:
    """
    Marca um "pulso" no agente — frontend usa isso pra reforçar atividade
    e empurrar pacotes pelos cabos da fibra. Usado ao final de cada agente
    do Party Mode pra sinalizar que terminou.

    Args:
        agent:      nome canônico
        tool:       rótulo livre da ação ("party.respond", "geral.respond")
        session_id: ID da sessão
        platform:   "databricks" | "fabric" | "memory" | ...
        has_error:  True se a resposta veio com erro
    """
    _write(
        AUDIT_LOG,
        {
            "event": "tool_call",
            "session_id": session_id,
            "agent_name": agent,
            "tool_name": tool,
            "platform": platform,
            "operation_type": "manual_emit",
            "has_error": has_error,
            "result_type": "text",
            "tool_use_id": f"manual_{agent}_{tool}",
        },
    )


def emit_session_end(
    session_id: str | None,
    cost_usd: float,
    turns: int,
    duration_s: float,
    session_type: str = "manual",
) -> None:
    """
    Sinaliza fim da sessão à viz. Frontend mostra overlay de encerramento
    e zera contadores.

    Args:
        session_id:    ID da sessão
        cost_usd:      custo total acumulado em USD
        turns:         número de "voltas" (ex: agentes consultados)
        duration_s:    duração total em segundos
        session_type:  "party" | "geral" | "analyze" | etc.
    """
    _write(
        AUDIT_LOG,
        {
            "event": "session_end",
            "session_id": session_id,
            "cost_usd": float(cost_usd),
            "turns": int(turns),
            "duration_s": float(duration_s),
            "session_type": session_type,
        },
    )
