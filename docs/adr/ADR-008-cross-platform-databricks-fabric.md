# ADR-008: Cross-platform coverage of Databricks AND Fabric

> **Status**: Accepted
> **Date**: 2026-05-22
> **Deciders**: @ThomazRossito
> **Tags**: scope, product, positioning

## Context

The competing landscape of agentic data-engineering tooling specializes:

- `databricks-solutions/ai-dev-kit` — Databricks-only (deep + official).
- `luanmorenommaciel/agentspec` — agent framework with strong Databricks coverage, less Fabric.
- `databricks-forge` — Databricks-only SaaS for Unity Catalog discovery.

The Brazilian data engineering market (where the maintainer operates) is heterogeneous: many enterprises run **both** Databricks (Azure or AWS) and Microsoft Fabric, often migrating between them, often comparing them for new workloads. A specialist tool for either side answers half the question.

A choice presented itself early in the project:

1. **Specialize in Databricks** — be the best Databricks agent system, accepting that Fabric users go elsewhere.
2. **Specialize in Fabric** — be the best Fabric agent system, accepting that Databricks users go elsewhere.
3. **Cover both** — be the only system that does cross-platform comparison, migration, and side-by-side architecture work.

Each path has different costs:

- Specialization (1) or (2) means deeper integration, more MCPs per platform, more time per skill — at the cost of leaving half the market unserved.
- Cross-platform coverage means broader but shallower coverage — at the cost of being "second best" in any single platform unless effort is high enough to be first-best in both.

## Decision

**Cover both Databricks and Microsoft Fabric as first-class platforms.** Optimize for cross-platform workflows (migrations, comparisons, dual-platform pipelines) as a deliberate differentiator.

Concretely:

- Two flagship engineering agents — `databricks-engineer` (T1) and `fabric-engineer` (T1) — receive equivalent depth and MCP coverage.
- Both platforms have multiple specialized MCPs (Databricks: official + Genie + Migration source; Fabric: community + official + SQL Analytics + Semantic + RTI + Notebook + OneLake + Ontology).
- `migration-expert` (T1) is platform-agnostic; uses `migration_source` MCP (SQL Server, PostgreSQL) and targets either `databricks` or `fabric` MCPs.
- Cross-cutting agents (`data-quality-steward`, `governance-auditor`, `data-contracts-engineer`, `data-mesh-architect`) are platform-agnostic and explicitly mention both Databricks + Fabric tools in their `mcp_servers`.
- The Supervisor enforces "Platform Isolation" rule (cache_prefix.md table): when the user mentions a platform, use only that platform's tools — never silently fall back to the other.
- Slash commands are platform-tagged: `/sql`, `/spark`, `/pipeline`, `/cdc`, `/diagnose`, `/genie`, `/dashboard` route to `databricks-engineer`; `/fabric`, `/semantic`, `/schema`, `/finops`, `/medallion`, `/catalog` route to `fabric-engineer`.

## Consequences

### Positive
- **Unique market position.** No competing project ships first-class support for both Databricks and Fabric. This is the principal differentiator vs `ai-dev-kit` and `agentspec`.
- **Migration value.** The single most expensive cross-platform workflow — migrating between platforms or co-running both — is covered end-to-end.
- **Re-use of cross-cutting agents.** Data quality, governance, contracts, and mesh agents work uniformly across both platforms.
- **Avoids vendor lock-in messaging.** "I picked the wrong platform" is a recoverable position, not a re-platform.

### Negative
- **Higher MCP surface area.** 8 custom MCPs split between platforms vs ~3-4 if specialized.
- **More agents to maintain.** `databricks-engineer` and `fabric-engineer` each have rich frontmatter, KB domains, and skill domains.
- **Harder to compete on depth.** A 100%-Databricks team using `ai-dev-kit` may find it deeper for their specific need.
- **More credentials in `.env`.** Users need Databricks token AND Azure SP AND Fabric workspace IDs — even if they only intend to use one.
- **Documentation overhead.** Every feature, KB, ADR needs to mention "applies to both" or specify which platform.

### Neutral / unknown
- **Adding a third platform** (Snowflake? Iceberg-on-S3? Big Query?) is now an obvious follow-up question. ADR-XXX TBD if/when that happens.
- **Quality drift.** Whether maintaining parity between Databricks and Fabric capabilities over time is sustainable for a small team. The Phase-3 lint will at least surface gaps.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| Databricks-only | Deeper niche; compete head-to-head with `ai-dev-kit` | Half the market unserved; no migration story | Loses the only unique value |
| Fabric-only | Less crowded niche | Smaller market; Microsoft tooling is still maturing | Cross-platform value > single-platform niche |
| "Databricks first, Fabric eventually" | Defers the cost | In practice means Fabric never gets done; partial-Fabric is worse than no-Fabric | Half measures |
| Generic platform abstraction layer | Idealistic | Heavyweight; doesn't match either platform's idioms; agents lose precision | Abstractions over Databricks-Fabric never end up as nice as they sound |

## References

- `agents/registry/databricks-engineer.md`, `agents/registry/fabric-engineer.md` — parity in tier and capability.
- `agents/registry/migration-expert.md` — explicit cross-platform agent.
- `agents/cache_prefix.md` — "Platform Isolation" rule injected into all agents.
- `config/commands.yaml` — platform-tagged slash commands.
- `kb/migration/`, `kb/databricks/`, `kb/fabric/` — domain-isolated KB structure.
- `PRODUCT.md` — explicit ICP / JTBD targeting cross-platform teams.
