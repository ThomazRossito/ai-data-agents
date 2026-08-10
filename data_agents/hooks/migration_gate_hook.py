"""
Hook de enforcement do gate de migração (Constituição §2.2 / Supervisor Step 0.6(A)).

Problema que resolve
--------------------
O Supervisor pode ALUCINAR "Aprovação recebida" e, no MESMO turno do usuário, delegar
uma 2ª vez ao especialista de migração para GERAR código — pulando o gate de aprovação
humana. O prompt sozinho é "texto mole": já foi observado o modelo atravessá-lo
(sessão SSAS BRF, 2026-07-26). Este hook torna o gate um freio de verdade.

Regra
-----
Máximo de UMA delegação a especialista de migração por turno do usuário. A 1ª produz o
SPEC/plano; a 2ª (que seria o GENERATE sem aprovação) é BLOQUEADA.

Fluxo correto forçado:
  turno 1 (usuário pede migração) → 1 delegação (SPEC) → Supervisor PARA e pede aprovação.
  turno 2 (usuário aprova)        → 1 delegação (GENERATE) → permitida.

Reset por turno
---------------
`reset_migration_gate()` é chamado no INÍCIO de cada mensagem do usuário
(chainlit `on_message` / loop do CLI). Sem o reset, a delegação de GENERATE legítima
do turno 2 seria contada como "2ª" e bloqueada por engano.

Escopo: os hooks rodam in-process, no mesmo processo da UI/CLI. O uso é local e
single-session, então um contador de processo único (resetado por turno) é suficiente
e correto.
"""

import logging
from typing import Any

logger = logging.getLogger("data_agents.hooks.migration_gate")

# Especialistas cuja jurisdição é migração high-stakes (Step 0.6(A)).
MIGRATION_AGENTS: frozenset[str] = frozenset(
    {
        "ssas-to-databricks",
        "ssis-to-databricks",
        "migration-expert",
        "sqlserver-to-databricks",
        "hadoop-to-databricks",
        "teradata-to-databricks",
    }
)

# Contador de delegações a especialistas de migração no turno atual do usuário.
# Resetado por `reset_migration_gate()` no início de cada turno.
_delegation_count: dict[str, int] = {"n": 0}


def reset_migration_gate() -> None:
    """Zera o contador de delegações de migração.

    DEVE ser chamado no INÍCIO de cada turno do usuário (antes de `client.query`),
    para que a delegação de GENERATE do turno seguinte (pós-aprovação) não seja
    bloqueada como se fosse a 2ª do mesmo turno.
    """
    _delegation_count["n"] = 0


def _extract_agent_name(tool_input: dict[str, Any]) -> str:
    """Nome do sub-agente do tool `Agent` (mesma ordem de campos do workflow.tracker)."""
    return (
        tool_input.get("subagent_type")
        or tool_input.get("agent_name")
        or tool_input.get("name")
        or tool_input.get("agent")
        or ""
    )


def _deny(reason: str) -> dict[str, Any]:
    """Resposta PreToolUse que bloqueia a tool e devolve o motivo ao modelo."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


async def enforce_migration_gate(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
) -> dict[str, Any]:
    """PreToolUse (matcher="Agent") — impõe o gate de aprovação de migração.

    Permite a 1ª delegação a um especialista de migração no turno (que produz o SPEC).
    BLOQUEIA a 2ª+ no mesmo turno — que seria o GENERATE sem aprovação humana explícita.
    Não interfere em delegações a agentes não-migração.
    """
    if not input_data or not isinstance(input_data, dict):
        return {}
    if input_data.get("tool_name") != "Agent":
        return {}

    agent = _extract_agent_name(input_data.get("tool_input", {}) or {})
    if agent not in MIGRATION_AGENTS:
        return {}

    _delegation_count["n"] += 1

    if _delegation_count["n"] >= 2:
        logger.info(
            "Gate de migração: 2ª delegação a '%s' bloqueada no mesmo turno (Step 0.6A).",
            agent,
        )
        return _deny(
            "Gate S0.6(A) — PARE. Já houve uma delegação de migração neste turno (o SPEC). "
            "NÃO gere código agora e NÃO delegue de novo. Apresente o SPEC ao usuário "
            "(resumo curto + caminho do arquivo) e peça aprovação explícita. O GENERATE só pode "
            "rodar em um NOVO turno, depois que o usuário responder 'sim'. Nunca assuma aprovação."
        )

    return {}
