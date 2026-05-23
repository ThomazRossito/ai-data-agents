# ADR-005: Constitution (S1–S7) as single source of truth for invariants

> **Status**: Accepted
> **Date**: 2026-05-22
> **Deciders**: @ThomazRossito
> **Tags**: governance, prompt-engineering, invariants

## Context

A multi-agent system needs **invariants** — rules that hold across all agents, all sessions, all tools. Examples:

- "The Supervisor never executes SQL directly."
- "Tokens and credentials never appear in agent output."
- "Operations that delete production data require explicit confirmation."
- "Cross-platform requests (Databricks ↔ Fabric) must route to the right agent for each side."

Without a single document of record, these invariants live in three problematic places:

1. **Distributed across agent prompts** — each agent re-states "you should never X" with subtle drift in wording. A new agent author may forget a rule entirely.
2. **Buried in code (hooks)** — only enforceable at runtime, not visible to agents during planning.
3. **In the developer's head** — invisible to LLM and to new contributors.

A change to an invariant in one place doesn't propagate. The system slowly violates rules nobody can remember anymore.

## Decision

**Maintain a single Constitution document** at `kb/constitution.md` with **inviolable rules** numbered S1–S7 (and architecture rules SS1–SS4 for Star Schema, plus Medallion rules per layer).

Each rule:

- Has a stable identifier (`S1`, `S2`, ...).
- Has a one-line statement that is testable.
- Is referenced by ID from the Supervisor system prompt, from each agent that needs to enforce it, and from hooks.

The seven Supervisor rules:

| ID | Rule |
|---|---|
| **S1** | The Supervisor NEVER generates SQL, Python, or Spark code directly. Always delegate. |
| **S2** | The Supervisor NEVER accesses MCP servers directly. MCP is the specialists' jurisdiction. |
| **S3** | KB-First: consult relevant Knowledge Base BEFORE planning any task. |
| **S4** | Present the plan to the user BEFORE initiating multi-agent delegation (with S4-AUTO exception). |
| **S5** | NEVER expose tokens, passwords, secrets, or credentials to the user or in artifacts. |
| **S6** | Quality tasks → `data-quality-steward`. Governance tasks → `governance-auditor`. Never to engineering agents. |
| **S7** | ALWAYS run the Clarity Checkpoint (5-dimension rubric) before planning complex tasks; below 3/5 requires `AskUserQuestion`. |

Plus S4-AUTO sub-rule (S4 relaxation for read-only / single-agent / low-cost when `S4_AUTONOMOUS_MODE=true`), and SS1–SS4 for Star Schema validation in Gold layer.

The Constitution is:

- **Read** by the Supervisor at the start of complex sessions (instructed in `SUPERVISOR_SYSTEM_PROMPT`).
- **Referenced by ID** from agent registry markdown when an agent needs to enforce a rule.
- **Enforced** at hook level for S1/S2 (security hook blocks destructive SQL), S5 (audit hook masks secrets), and partially S6 (no current automated enforcement; trusted to Supervisor).

## Consequences

### Positive
- Changes to invariants happen in **one file**. Diff is obvious to reviewers.
- New agents inherit the Constitution by reference — no copy-paste rules in 15 prompts.
- Auditors / contributors have one document to read to understand the system's "non-negotiables".
- Stable IDs (`S1`...`S7`) survive rewording — a hook can still say "violation of S5" even if S5's wording is improved.

### Negative
- Constitution must be **kept short** — if it grows past ~10 rules, the LLM may stop respecting them all. Discipline required.
- Some rules are unenforced (S6, S7) and rely on Supervisor compliance. Drift possible.
- A rule update requires updating cross-references in: agent prompts, hooks, this ADR, and possibly the README — the Lint of Phase 3 will help.

### Neutral / unknown
- Future automated enforcement: could a "Constitution lint" hook parse outputs and flag violations? Researched but not implemented in v2.x.
- The Constitution may need ADR-XXX revisions over time as new rules emerge; existing rule IDs stay stable.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| Embed rules in each agent's prompt | Always present in context | Drift across 15 agents; hard to update consistently | Defeats the goal |
| Codify rules in Python guards only | Deterministic enforcement | Invisible to LLM during planning — model violates blindly | Hooks complement Constitution, not replace |
| YAML rules consumed by linter | Structured, lintable | Loses the prose nuance ("inviolable", "always", "never") that LLMs respect | Markdown wins for LLM consumption |
| One-time onboarding doc | Familiar | Not consulted at runtime by the model | Defeats the goal |

## References

- `kb/constitution.md` — the Constitution itself.
- `agents/prompts/supervisor_prompt.py::SUPERVISOR_SYSTEM_PROMPT` — references Constitution by `Read("kb/constitution.md")`.
- `hooks/security_hook.py` — enforces S1/S2 partially via DDL/SQL pattern blocks.
- `hooks/audit_hook.py::_sanitize_command` — enforces S5 by masking credential-shaped flags in logs.
- Inspired by "Spec Kit" Constitutional Foundation (https://github.com/github/spec-kit).
