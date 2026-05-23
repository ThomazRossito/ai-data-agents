# ADR-004: Tier system (T0/T1/T2/T3) for budget and effort

> **Status**: Accepted
> **Date**: 2026-05-22
> **Deciders**: @ThomazRossito
> **Tags**: cost, agent-design, performance

## Context

Different agents have different cognitive demands:

- Answering "what is a Bronze layer?" is conceptual and doesn't need 25 tool turns.
- Planning a SQL Server → Databricks migration with 100 tables genuinely needs many turns of discovery, planning, validation.
- Generating a star schema for Gold layer is somewhere in between.

A uniform `max_turns` setting wastes resources:

- Too low → complex agents fail before finishing.
- Too high → simple agents loop unnecessarily, multiplying cost.

Likewise for "effort" — the model's internal reasoning depth. Conceptual Q&A benefits from `low` effort (fast, cheap). Migration assessment benefits from `high` effort (slower, more reliable).

Pre-Kimi K2.6, this could have been solved by routing tier to model choice (Haiku/Sonnet/Opus). Post-Kimi K2.6 (single model line — see ADR-001), the differentiation has to happen via parameters on the same model.

## Decision

**Introduce a four-tier classification** for agents. The tier determines `max_turns` and `effort` parameters; the model is always `kimi-k2.6`.

| Tier | Profile | `max_turns` | `effort` |
|---|---|---|---|
| **T0** | Conversational, zero MCP, no tool use | 3 | low |
| **T1** | Engineering core: complex pipelines, migrations, cross-platform | 20 | high |
| **T2** | Specialized analysis: quality, governance, semantic, contracts, mesh | 12 | medium |
| **T3** | Conversational with limited tools: intake, briefing | 5 | low |

Defaults live in `config/settings.py::tier_turns_map` and `tier_effort_map`. Each agent declares `tier:` in its frontmatter. The loader applies the tier defaults unless the agent overrides via frontmatter (`max_turns:` or `effort:` fields).

Distribution (as of v2.3.0):
- T0: 1 (`geral`)
- T1: 5 (`databricks-engineer`, `databricks-ai`, `fabric-engineer`, `migration-expert`, `python-expert`)
- T2: 8 (`data-quality-steward`, `governance-auditor`, `dbt-expert`, `fabric-rti`, `fabric-ontology`, `data-contracts-engineer`, `data-mesh-architect`, `azure-cost-calculator`)
- T3: 1 (`business-analyst`)

Overrides in v2.3.0:
- `databricks-engineer`, `fabric-engineer`, `migration-expert` use `max_turns: 25` (override from T1's 20).
- `databricks-ai` uses `max_turns: 20` (matches T1 default; explicit for clarity).
- `migration-expert` uses `effort: high` (matches T1 default; explicit).

## Consequences

### Positive
- Cost predictability per agent type. The supervisor cannot accidentally run a T0 agent for 25 turns.
- New agents pick a tier and inherit sensible defaults — onboarding faster.
- Tier maps live in `.env` and `Settings`; can be tuned without code change.

### Negative
- Adds one more concept (tier) to learn when reading the registry.
- "Tier" naming overloads English ("tier 1 support" vs "tier 1 engineering core") — readers must look up the definitions.
- Some agents straddle tiers (e.g., `dbt-expert` could be T1 or T2). The classification is partly judgment.

### Neutral / unknown
- The numeric values (20/12/5/3 turns) are seeded by intuition, not measured. Real-world telemetry could refine them post-v3.
- Adding a T1.5 or T2.5 may eventually become necessary; current rule is "if you want a new tier, propose an ADR".

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| Single global `max_turns` | Simple | Either too low for T1 or too high for T0 | Optimizes neither end |
| Per-agent `max_turns` only (no tier) | Maximum flexibility | Every new agent has to think from scratch; drift over time | Tier provides a sensible default |
| Tier = model choice (e.g., T0→Haiku, T1→Opus) | Cleaner separation | Doesn't work with single-model Kimi K2.6 line (ADR-001) | Incompatible with chosen provider |
| Continuous "complexity score" 0–100 | More gradient | Harder to reason about; no clear thresholds | Discrete tiers are easier to maintain |

## References

- `config/settings.py::tier_turns_map`, `tier_effort_map`.
- `agents/loader.py::load_agent` — applies tier defaults with frontmatter override.
- `agents/registry/*.md` — each declares `tier:`.
- `.env.example` — `TIER_TURNS_MAP`, `TIER_EFFORT_MAP` for runtime override.
