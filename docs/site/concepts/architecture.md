# Architecture

This page links to the canonical architecture document, which lives in the repo as `docs/ARCHITECTURE.md`. It contains C4 levels 1+2 in Mermaid plus the full query lifecycle diagram.

→ [View ARCHITECTURE.md on GitHub](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/docs/ARCHITECTURE.md)

## TL;DR

```
User (CLI / Chainlit) → Supervisor (kimi-k2.6, no MCP)
                          ↓ Agent() tool call
                       Subagent (databricks-engineer / fabric-engineer / ...)
                          ↓ MCP tool call
                       MCP server (Databricks / Fabric / Genie / Pricing / ...)
                          ↓ HTTPS / TDS
                       External platform
```

Cross-cutting:

- **PreToolUse hooks** intercept every tool call (security, cost guard, SQL pattern check)
- **PostToolUse hooks** intercept results (audit JSONL, output compression, memory capture, context budget)
- **Memory layer** (ShortTerm SQLite + LongTerm FTS5 + HMAC ledger) provides session continuity

## Sub-decisions

The architecture is the outcome of multiple [ADRs](../reference/adrs.md):

- ADR-001 — Moonshot Kimi K2.6 as primary model (cost / latency)
- ADR-002 — Three-layer memory (vs naive RAG)
- ADR-003 — Two-Stage Routing (dispatcher reduces Supervisor prompt size)
- ADR-004 — Tier system (T0/T1/T2/T3 budget control)
- ADR-005 — Constitution S1–S7 (inviolable rules)
- ADR-006 — Hooks instead of middleware (SDK-enforced)
- ADR-007 — KB as Markdown with YAML frontmatter
- ADR-008 — Cross-platform Databricks + Fabric (not specialization)
- ADR-009 — Structural lints as CI gate
- ADR-010 — Docs site with MkDocs Material

## Why this works

1. **Separation of concerns** — Supervisor never touches MCP, hooks never touch LLM. Each layer has one job.
2. **Declarative agents** — adding an agent is one Markdown file in `data_agents/agents/registry/`. No Python code change.
3. **Constitution as protocol** — S1–S7 give the Supervisor a checklist to consult before delegating, instead of relying on prompt magic.
4. **Hook-level enforcement** — `block_destructive_commands` runs for every tool call, regardless of how the agent was tricked. The LLM can be wrong; the hook is deterministic.
5. **Memory is opt-in per layer** — ShortTerm (within session), LongTerm (across sessions), Ledger (audit chain). Each can be disabled independently via `.env`.
