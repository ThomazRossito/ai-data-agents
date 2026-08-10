#!/usr/bin/env python3
"""Smoke test REAL do loader de workflows declarativos contra o Kimi.

Roda um workflow mínimo (2 passos, agente `geral`, zero MCP) definido em YAML,
provando a cadeia end-to-end: YAML → loader → WorkflowRunner → Kimi → output
+ context chain (o passo 2 recebe o output do passo 1).

Custo: ~centavos (2 chamadas curtas ao `geral` / kimi-k2.6).
Requer: `.env` com ANTHROPIC_API_KEY (Moonshot) + rede até api.moonshot.ai.

Uso:
    python scripts/try_declarative_workflow.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from data_agents.commands.workflow import WorkflowRunner
from data_agents.workflow.declarative.loader import load_workflow, to_workflow_steps

_YAML = (
    Path(__file__).resolve().parent.parent
    / "data_agents"
    / "workflow"
    / "declarative"
    / "demo_smoke.yaml"
)


async def _main() -> None:
    parsed = load_workflow(_YAML)
    steps = to_workflow_steps(parsed)
    print(f"YAML '{parsed['wf_id']}' carregado: {len(steps)} steps declarativos.\n")

    runner = WorkflowRunner(wf_id=parsed["wf_id"], steps=steps)
    result = await runner.run(query="Smoke test do loader de workflows declarativos.")

    print(result.summary())
    print(f"\nsuccess={result.success}  custo_total=${result.total_cost_usd:.4f}")


if __name__ == "__main__":
    asyncio.run(_main())
