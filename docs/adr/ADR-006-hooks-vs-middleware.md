# ADR-006: Pre/PostToolUse hooks as the interception layer

> **Status**: Accepted
> **Date**: 2026-05-22
> **Deciders**: @ThomazRossito
> **Tags**: architecture, observability, integrity, agent-sdk

## Context

Every tool call the agents make needs to be observed and sometimes modified:

- **Security** — block destructive shell commands, block expensive SQL, mask secrets in logs.
- **Cost control** — classify operations (HIGH/MEDIUM/LOW), trigger alerts past thresholds.
- **Audit** — record every call with tamper-evident HMAC signature.
- **Memory capture** — extract session context from tool outputs without an LLM call.
- **Context budget** — track tokens accumulated against the 200K window, trigger compaction at 80%.
- **Output compression** — cap SQL row dumps, list outputs, file reads before they reach the LLM and burn tokens.

The `claude-agent-sdk` exposes `HookMatcher` for `PreToolUse` and `PostToolUse`. The alternative would be to wrap MCP servers manually, intercept the subprocess stdio, or build a custom proxy.

Each design choice has a trust and a coupling implication:

- **Wrap MCP servers** → couples the project to the MCP wire protocol; one wrapper per server type; one regression breaks everything.
- **Custom proxy** → highest control, highest complexity; effectively rewriting the SDK.
- **SDK hooks** → use what the SDK gives us; less control but less code.

## Decision

**Use the SDK's `PreToolUse` and `PostToolUse` hooks** as the single interception layer. All cross-cutting concerns implement the same `async def hook(input_data, tool_use_id, context) -> dict` signature and are registered in `agents/supervisor.py::build_supervisor_options`.

Layout:

- `hooks/security_hook.py` — `PreToolUse`. Two functions: `block_destructive_commands` (Bash-matcher), `check_sql_cost` (no matcher, intercepts all). Both return `{"hookSpecificOutput": {"permissionDecision": "deny", ...}}` to block.
- `hooks/audit_hook.py` — `PostToolUse`. `audit_tool_usage` writes one signed JSONL entry per call.
- `hooks/cost_guard_hook.py` — `PostToolUse`. Classifies HIGH/MEDIUM/LOW, alerts.
- `hooks/memory_hook.py` — `PostToolUse`. `capture_session_context` extracts facts; `pre_track_lesson_timing` (PreToolUse) records `t0`.
- `hooks/output_compressor_hook.py` (shim → `compression/hook.py`) — `PostToolUse`. Substitutes verbose outputs with compressed versions.
- `hooks/workflow_tracker.py` (shim → `workflow/tracker.py`) — Pre + PostToolUse. Tracks delegations and workflow steps.
- `hooks/context_budget_hook.py` — `PostToolUse`. Token accounting + auto-compaction trigger.
- `hooks/session_lifecycle.py` — `on_session_start` / `on_session_end`. Not SDK hooks per se, but called by entry points (`main.py`, `chainlit_app.py`).

Order matters: in `PostToolUse`, hooks run in registration order. `output_compressor_hook` is **last** so that `audit_hook` and `cost_guard_hook` observe the original, uncompressed output.

Hooks are **fail-safe**: any exception inside a hook is caught and logged; the tool call continues with the original output. A hook never blocks unless it explicitly denies.

## Consequences

### Positive
- The 11 hook concerns each live in a focused file. Adding a new cross-cutting concern (e.g., rate-limit-per-tool) means: write one function, register one `HookMatcher`.
- The `audit_hook` is the source of truth for `logs/audit.jsonl` — monitoring and visualization read it without re-instrumenting.
- The `output_compressor_hook` saves ~40-70% of tool output tokens on average (measured via `logs/compression.jsonl`).
- Hook fail-safe behavior means a buggy new hook can't break the conversation.

### Negative
- Hook execution order is implicit (registration order). Subtle bugs possible if order changes.
- Hooks can't easily communicate with each other — `_tool_start_times` (workflow tracker) and `_session_input_tokens` (context budget) use module globals.
- The shim pattern (`hooks/workflow_tracker.py` re-exports from `workflow/`) was needed during a previous refactor; it's a small wart.
- Coupling to the SDK's hook signature. If the SDK changes its hook API, every hook changes.

### Neutral / unknown
- Whether to consolidate the 11 hooks into fewer files. Argument for: simpler discovery. Argument against: each file is single-purpose and that's a virtue.
- Hook execution latency. Measured at ~0.5–2ms per hook per call; negligible today, may matter at very high tool-call rates.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| Wrap each MCP server with a proxy | Could enforce per-MCP rules deterministically | 1 wrapper per server; brittle to MCP wire updates | Too much code; the SDK already exposes hooks |
| Subclass/monkeypatch `ClaudeAgentOptions` | More control | Couples to SDK internals; fragile | Tighter coupling than registering a hook |
| Out-of-process audit (e.g., kernel/eBPF) | OS-level enforcement | Massive overkill; not portable | Wrong layer of abstraction |
| Inline checks in each agent prompt | Already done partially | Inconsistent enforcement; agents can ignore | Hooks complement prompts, not replace |

## References

- `hooks/` directory — implementation of all hooks.
- `agents/supervisor.py::build_supervisor_options` — registration of hooks in `ClaudeAgentOptions.hooks`.
- `compression/` and `workflow/` — extracted implementations behind the shims.
- `claude_agent_sdk.HookMatcher` — the SDK API used.
