# Constitution (S1–S7)

The Constitution is a set of **7 inviolable rules** the Supervisor consults before any complex delegation. They are the single source of truth for architectural invariants — every agent prompt, every hook, every test traces back to a Constitution rule.

The full text lives in [`kb/constitution.md`](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/kb/constitution.md) (loaded into the Supervisor context at session start).

## The 7 rules

| ID | Rule | What enforces it |
|---|---|---|
| **S1** | Supervisor NEVER generates SQL/PySpark directly | Supervisor prompt explicitly forbids; no MCP in Supervisor's `allowed_tools` |
| **S2** | Supervisor NEVER accesses MCP directly | Same — Supervisor has only `Agent`, `Read`, `Write`, `Bash`, `Grep`, `Glob`, `AskUserQuestion` |
| **S3** | KB-First: consult `kb/` BEFORE planning any task | Per-agent KB-First Protocol section in registry files |
| **S4** | Present plan to user BEFORE multi-agent delegation (with `S4_AUTONOMOUS_MODE` opt-out for read-only / single-agent / low-cost) | `agents/prompts/supervisor_prompt.py` Step 2; `s4_decision` event logged |
| **S5** | NEVER expose tokens/secrets in artifacts or responses | `audit_hook.py::_sanitize_command`, `transcript_hook.py::_redact_secrets` |
| **S6** | Quality → `data-quality-steward`. Governance → `governance-auditor`. NEVER delegate governance to engineering agents. | Phase 5 escalation graph injects this as a whitelist into the Supervisor prompt |
| **S7** | Clarity Checkpoint (score ≥ 3/5) before complex tasks | `supervisor_prompt.py` Step 0.5; rubric in `kb/constitution.md` §3 |

## How rules become tests

S1 + S2 are tested via `tests/unit/test_supervisor.py` (Supervisor `allowed_tools` does not contain any MCP tool).

S6 is tested via `scripts/lint_registry.py::cross_check_escalation_targets` — every `escalation_rules.target` must reference an existing agent in the registry. Self-referencing targets are rejected.

S5 is partly tested by `tests/unit/test_structured_logging.py` (audit hook sanitizes command previews) and by `tests/unit/test_settings.py` (settings classify which env vars are secrets).

## How rules become hooks

S2 is hook-enforced at runtime: even if the Supervisor were tricked into calling an MCP tool directly, the SDK's `allowed_tools` list rejects the call before execution.

S5 has runtime enforcement in `data_agents/hooks/security_hook.py::block_destructive_commands` (22 patterns including `cat .env`, `printenv`, `env | grep KEY`).

## Why a Constitution

The temptation in multi-agent systems is to encode rules in the Supervisor prompt as natural-language reminders. That works ~80% of the time and fails subtly the other 20%.

The Constitution does three things differently:

1. **Numbered and versioned** — when you read `[S6]` in an agent definition, you know exactly which rule is in play. PRs can debate "should we relax S6?" without ambiguity.
2. **Multi-layered enforcement** — each rule is enforced at >1 layer (prompt + hook + test). If one layer fails, another catches.
3. **Lint-checkable** — `scripts/lint_registry.py` and `tests/unit/test_supervisor.py` provide automated guards against regression.

The Constitution evolves but **never silently**. Every change is an ADR (e.g. ADR-005 created S5, future ADR could amend with S8). The version is the git history.
