# Hooks

Hooks intercept every tool call before (PreToolUse) and after (PostToolUse) execution. They are **SDK-enforced** — there is no flag the LLM can set to skip them.

## The 11 hooks

| Hook | Type | Purpose |
|---|---|---|
| `security_hook::block_destructive_commands` | PreToolUse (Bash) | Blocks 22 patterns: `rm -rf`, `DROP TABLE`, `git reset --hard`, `cat .env`, etc. |
| `security_hook::check_sql_cost` | PreToolUse (any) | Detects `SELECT *` without WHERE/LIMIT in any tool |
| `workflow_tracker::pre_track_workflow_events` | PreToolUse | Emits `agent_start` / `tool_call` events for live UI feedback |
| `memory_hook::pre_track_lesson_timing` | PreToolUse | Marks `t0` for slow-op detection |
| `audit_hook::audit_tool_usage` | PostToolUse | Writes JSONL entry: timestamp, tool_name, tool_use_id, session_id, agent_name, has_error, error_category, platform, optional ledger HMAC signature |
| `cost_guard_hook::log_cost_generating_operations` | PostToolUse | Classifies HIGH/MEDIUM/LOW, alerts after 5 HIGH ops |
| `workflow_tracker::track_workflow_events` | PostToolUse | Tracks delegations, Clarity Checkpoint scores, progress callbacks |
| `memory_hook::capture_session_context` | PostToolUse | Accumulates session facts; flushed at session_end |
| `context_budget_hook::track_context_budget` | PostToolUse | WARN at 80% / ERROR at 95% of context window |
| `output_compressor_hook::compress_tool_output` | PostToolUse | Truncates verbose outputs before they reach the model |
| `session_lifecycle::on_session_start/end` | lifecycle | Inject memories at start; flush config snapshot + memories at end |

The full list with execution order lives in `data_agents/agents/supervisor.py::build_supervisor_options`.

## Why hooks instead of middleware

[ADR-006](../reference/adrs.md) discusses the alternatives. TL;DR:

- **Middleware around the LLM call**: easy to bypass (LLM can refuse to execute), single point of failure.
- **Tool wrapping**: requires re-implementing every MCP tool with the same signature; brittle when SDK adds new tools.
- **Hooks (chosen)**: SDK runs them around `tool_use` events regardless of which tool. New tools get hook coverage for free.

## Order of execution

PreToolUse runs in the order registered:

```
security.block_destructive_commands  →  (only for Bash)
security.check_sql_cost              →  (all tools)
workflow_tracker.pre_track           →  (all tools, emits events)
memory_hook.pre_track_lesson_timing  →  (all tools, marks t0)
                                        ↓
                                  TOOL EXECUTES
                                        ↓
PostToolUse runs in reverse-registration order:
output_compressor.compress           →  (truncate verbose output)
context_budget.track                 →  (count tokens, warn/error)
memory_hook.capture_session_context  →  (accumulate facts)
workflow_tracker.track               →  (emit progress event)
cost_guard.log_cost                  →  (classify + alert if 5 HIGH)
audit_hook.audit_tool_usage          →  (JSONL append + ledger sign)
```

If any PreToolUse raises, the tool does NOT execute.

## Anti-patterns

1. **Don't add LLM calls inside a hook**. Hooks run per tool — if you call Haiku inside `audit_tool_usage`, you 10x the cost. Use the memory layer's deferred summarizer instead.
2. **Don't make hooks stateful across processes**. Hooks live in the SDK process; if your CLI spawns workers, hook state doesn't share.
3. **Don't catch exceptions in audit_tool_usage**. If audit fails, you want to know — don't silently swallow. Log to stderr but re-raise.

## See also

- [`data_agents/hooks/`](https://github.com/ThomazRossito/ai-data-agents/tree/refactor/v3.0/data_agents/hooks) — source
- [`tests/unit/test_hooks.py`](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/tests/unit/test_hooks.py) — 22 security patterns + audit + cost guard tests
- [`tests/unit/test_structured_logging.py`](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/tests/unit/test_structured_logging.py) — JSONL contract enforcement (Phase 10)
