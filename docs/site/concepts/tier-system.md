# Tier System

Every agent in the registry declares a `tier:` field. The tier controls **maxTurns** and **effort** at runtime, providing budget guardrails without rewriting agent code.

## The 4 tiers

| Tier | Default model | maxTurns | Effort | Used for |
|---|---|---|---|---|
| **T0** | `kimi-k2.6` | 3 | low | Conversational only, zero MCP — `geral` agent only |
| **T1** | `kimi-k2.6` | 20-25 | high | Engineering Core — complex multi-step (databricks-engineer, fabric-engineer, migration-expert, python-expert, databricks-ai) |
| **T2** | `kimi-k2.6` | 12 | medium | Specialized — quality, governance, semantics (data-quality-steward, governance-auditor, data-contracts-engineer, data-mesh-architect, dbt-expert, fabric-rti, fabric-ontology, azure-cost-calculator) |
| **T3** | `kimi-k2.6` | 5 | low | Conversational with limited tools — business-analyst (intake) |

The maps live in `Settings`:

```python
TIER_TURNS_MAP = {"T0": 3, "T1": 20, "T2": 12, "T3": 5}
TIER_EFFORT_MAP = {"T0": "low", "T1": "high", "T2": "medium", "T3": "low"}
TIER_MODEL_MAP = {"T0": "kimi-k2.6", "T1": "kimi-k2.6", "T2": "kimi-k2.6", "T3": "kimi-k2.6"}
```

All maps are env-configurable. For example, to route T0 to Haiku for an even cheaper conversational path:

```ini
# .env
TIER_MODEL_MAP='{"T0": "claude-haiku-4-5", "T1": "kimi-k2.6", "T2": "kimi-k2.6", "T3": "kimi-k2.6"}'
```

## Why tiers exist

Without tiers, every agent would inherit the same `max_turns` from `Settings.max_turns`. That means a quick conceptual question wastes 25 turns of budget, and a complex migration is capped at the same low number.

The tier system separates **agent intent** (declared once in registry) from **runtime budget** (configurable per environment).

## How an agent gets its tier

Agent definition (e.g. `data_agents/agents/registry/data-quality-steward.md`):

```yaml
---
name: data-quality-steward
description: ...
model: kimi-k2.6
tier: T2
tools: [Read, Grep, Glob, databricks_readonly, fabric_readonly, postgres_all]
---
```

`agents/loader.py::load_all_agents()` reads the tier and applies:

```python
agent.maxTurns = TIER_TURNS_MAP[tier]
agent.effort   = TIER_EFFORT_MAP[tier]
agent.model    = TIER_MODEL_MAP.get(tier, settings.default_model)
```

## DOMA Full (/plan) override

When the user runs `/plan <objective>`, the Supervisor activates **thinking mode** (`thinking={"type":"adaptive","effort":"high"}`) regardless of tier. This is for complex multi-step planning where the extended reasoning cost is justified. See `agents/supervisor.py::build_supervisor_options(enable_thinking=True)`.

## Validation

`scripts/lint_registry.py` validates that every agent declares a tier in `{T0, T1, T2, T3}`. Unknown tier → CI fails.

## See also

- [ADR-004](../reference/adrs.md) — tier system rationale
- `data_agents/config/settings.py::Settings::tier_*` — env config
- `data_agents/agents/loader.py::load_all_agents` — runtime application
