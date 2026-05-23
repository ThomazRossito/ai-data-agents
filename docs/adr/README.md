# Architecture Decision Records (ADRs)

This directory holds ADRs documenting significant architectural and technology choices for `ai-data-agents`.

Each ADR is a short Markdown file. The format follows Michael Nygard's "Documenting Architecture Decisions" — Context, Decision, Consequences. See [`_template.md`](_template.md).

## When to write an ADR

Write an ADR when a decision:

- Is **irreversible** or expensive to reverse.
- Affects **multiple components** (the supervisor, the loader, hooks, MCPs together).
- Has **alternatives that were seriously considered** — the alternatives' "why not" matters as much as the chosen path.
- Will need to be **defended later** ("why don't we use X?").

Do **not** write an ADR for routine implementation choices, bug fixes, refactors with no external impact, or formatting preferences.

## How to write one

1. Copy `_template.md` to `ADR-NNN-short-title-with-hyphens.md` (next available number).
2. Fill `Status: Proposed`. Open a draft PR.
3. Discuss with reviewers. Update the ADR with their input.
4. Once merged, status becomes `Accepted`.
5. If a future ADR overrules this one, update its status to `Superseded by ADR-XXX` and link.

ADRs are append-only — never delete one. If a decision is reversed, write a new ADR explaining the reversal.

## Index

| # | Title | Status | Date |
|---|---|---|---|
| [001](ADR-001-moonshot-kimi-as-primary-model.md) | Moonshot Kimi K2.6 as the primary model (over Claude Sonnet) | Accepted | 2026-05-22 |
| [002](ADR-002-memory-three-layers.md) | Three-layer memory architecture (ShortTerm + LongTerm + Ledger) | Accepted | 2026-05-22 |
| [003](ADR-003-two-stage-routing.md) | Two-Stage Routing via lightweight dispatcher | Accepted | 2026-05-22 |
| [004](ADR-004-tier-system.md) | Tier system (T0/T1/T2/T3) for budget and effort control | Accepted | 2026-05-22 |
| [005](ADR-005-constitution-rules.md) | Constitution (S1–S7) as single source of truth for invariants | Accepted | 2026-05-22 |
| [006](ADR-006-hooks-vs-middleware.md) | Pre/PostToolUse hooks as the interception layer | Accepted | 2026-05-22 |
| [007](ADR-007-kb-as-markdown.md) | Knowledge Base stored as Markdown with YAML frontmatter | Accepted | 2026-05-22 |
| [008](ADR-008-cross-platform-databricks-fabric.md) | Cross-platform coverage of Databricks AND Fabric (not specialization) | Accepted | 2026-05-22 |
| [009](ADR-009-structural-lints.md) | Structural lints as CI gate against declarative drift | Accepted | 2026-05-22 |

---

*Future ADRs (planned)*: MkDocs choice, Plugin Claude Code adoption, OpenTelemetry vs JSONL, package rename, namespace layout.
