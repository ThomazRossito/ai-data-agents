# Architecture Decision Records

Each ADR captures one architectural decision in [Michael Nygard's format](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions): **Context · Decision · Consequences**.

ADRs are append-only — they're never deleted. If a decision is reversed, write a new ADR explaining the reversal.

## Index

| # | Title | Status | Date |
|---|---|---|---|
| 001 | [Moonshot Kimi K2.6 as the primary model](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/docs/adr/ADR-001-moonshot-kimi-as-primary-model.md) | Accepted | 2026-05-22 |
| 002 | [Three-layer memory architecture (ShortTerm + LongTerm + Ledger)](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/docs/adr/ADR-002-memory-three-layers.md) | Accepted | 2026-05-22 |
| 003 | [Two-Stage Routing via lightweight dispatcher](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/docs/adr/ADR-003-two-stage-routing.md) | Accepted | 2026-05-22 |
| 004 | [Tier system (T0/T1/T2/T3) for budget and effort control](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/docs/adr/ADR-004-tier-system.md) | Accepted | 2026-05-22 |
| 005 | [Constitution (S1–S7) as single source of truth for invariants](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/docs/adr/ADR-005-constitution-rules.md) | Accepted | 2026-05-22 |
| 006 | [Pre/PostToolUse hooks as the interception layer](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/docs/adr/ADR-006-hooks-vs-middleware.md) | Accepted | 2026-05-22 |
| 007 | [Knowledge Base stored as Markdown with YAML frontmatter](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/docs/adr/ADR-007-kb-as-markdown.md) | Accepted | 2026-05-22 |
| 008 | [Cross-platform coverage of Databricks AND Fabric (not specialization)](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/docs/adr/ADR-008-cross-platform-databricks-fabric.md) | Accepted | 2026-05-22 |
| 009 | [Structural lints as CI gate against declarative drift](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/docs/adr/ADR-009-structural-lints.md) | Accepted | 2026-05-22 |
| 010 | [Docs site with MkDocs Material, deployed via GitHub Pages](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/docs/adr/ADR-010-docs-site-mkdocs-material.md) | Accepted | 2026-05-23 |

## Future / planned

- ADR-011 — Plugin Claude Code adoption (Phase 12, optional)
- ADR-012 — Package rename to `data-agents-databricks-fabric` (PyPI)
- ADR-013 — OpenTelemetry vs JSONL (re-evaluate post-v3.0.0)
- ADR-014 — mkdocstrings reopening for API reference

## Why ADRs

The temptation in a refactor as large as v3 is to write decisions into commit messages and call it documentation. ADRs solve two problems commit messages can't:

1. **Discovery** — someone joining the project a year later needs to find "why didn't we use Sphinx?" without spelunking git log.
2. **Reversal traceability** — when a decision is undone, an ADR-XYZ "Supersedes ADR-ABC" gives the historical context. Commit history rarely surfaces that.

If you're tempted to make a non-trivial structural decision (new dependency, new build step, new abstraction layer), write an ADR first. Decision-paralysis is reduced — the ADR template forces you to enumerate alternatives.
