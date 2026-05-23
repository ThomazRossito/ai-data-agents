# ADR-002: Three-layer memory architecture

> **Status**: Accepted
> **Date**: 2026-05-22
> **Deciders**: @ThomazRossito
> **Tags**: memory, persistence, integrity, cost

## Context

Multi-agent systems lose context across sessions. A naive single-store approach has three problems:

1. **Session vs persistent confusion.** Session-local facts ("the user is debugging the `silver_orders` pipeline right now") mix with persistent facts ("the team uses Auto Loader for Bronze ingestion"). Decay rules differ, retrieval relevance differs, and storage characteristics differ.
2. **Cost of retrieval.** If memory retrieval calls the LLM for every query, the cost dominates. A cache or an FTS-only index is needed.
3. **Audit integrity.** Memory captures derived from tool calls must be tamper-evident — a memory that an attacker (or hallucination) could mutate retroactively defeats the audit trail.

The system needs to capture session context for later sessions to benefit, but it must do so without an unaffordable retrieval cost and without compromising auditability.

## Decision

**Split memory into three layers**, each with its own data model and access pattern:

### Layer 1: ShortTermMemory (session buffer)
- **Storage**: SQLite + FTS5 + optional `fastembed` embeddings.
- **Path**: `memory/data/short_term__<project_id>.db`.
- **TTL**: 3 days. Entries expire automatically.
- **Lifecycle**: `on_session_start` → init + `expire_old_entries`. `capture_session_context` PostToolUse hook appends. `on_session_end` flushes to LongTerm.
- **Purpose**: Capture "what is happening right now" without writing the persistent log until flushed.

### Layer 2: LongTermMemory (persistent semantic index)
- **Storage**: SQLite FTS5 + optional `fastembed` embeddings.
- **Path**: `memory/data/long_term__<project_id>.db`.
- **TTL**: none. Decay by `MemoryType` (USER never decays, PROGRESS 7d, FEEDBACK 90d, LESSON_LEARNED 30d, PIPELINE_STATUS 14d, ARCHITECTURE never).
- **Lifecycle**: Populated by `compile_daily_logs` from MemoryStore (`.md` files). Searched by `MemoryManager.inject_context` with 60s in-memory cache. Single sync per session.
- **Purpose**: "What does the system know that is still relevant?" — injected into Supervisor system prompt.

### Layer 3: Ledger (HMAC-signed audit chain)
- **Storage**: `logs/audit.jsonl` (append-only) + per-session HMAC-SHA256 key.
- **Lifecycle**: `on_session_start` generates the session key. Every `audit_tool_usage` PostToolUse hook signs an entry with the key. `LEDGER_VERIFY_ON_LOAD` toggles read-time verification.
- **Purpose**: Tamper-evident audit. The agent's actions cannot be revised retroactively without breaking the chain.

The three layers communicate via well-defined sync points:

- ShortTerm → LongTerm: at `flush_session_memories` (session end).
- MemoryStore (`.md` files) → LongTerm: at `migrate_from_store` (lazy, once per session via `MemoryManager`).
- Ledger reads → audit dashboard, never written by user code.

## Consequences

### Positive
- Each layer optimizes for its access pattern. Retrieval cost stays low (FTS5 hits sub-millisecond).
- Decay rules per `MemoryType` mean stale PROGRESS memories don't pollute the prompt.
- Audit integrity is independent of the memory data model — Ledger could be moved to S3/Azure Blob without changing memory retrieval.
- Per-project isolation via `PROJECT_ID` suffix prevents cross-contamination when copying directories.

### Negative
- Three storage formats to maintain (SQLite x 2 + JSONL).
- `MemoryManager` façade hides complexity but reading the code requires understanding all three.
- The `.md`-based MemoryStore + SQLite FTS5 LongTerm + JSONL Ledger combination is unusual and requires docs (this ADR + `memory/__init__.py` docstring).

### Neutral / unknown
- Embeddings via `fastembed` are optional. Whether to make them default in v3 depends on real-world retrieval relevance benchmarks (not yet run).
- The Ledger HMAC overhead per tool call (~50µs) is negligible today; if tool call rate grows 10×, may become measurable.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| Single vector store (Chroma/Qdrant local) | One concept, mature tooling | Heavy dep, no native TTL, no native HMAC chain | Overkill — SQLite + FTS5 suffices and ships with Python |
| LLM-based retrieval on every query | Best relevance | $0.003–$0.01/query — multiplies sessions cost by 10× | Cost wall |
| In-memory dict (no persistence) | Simplest | Loses everything between sessions | Defeats purpose |
| Single SQLite store with `type` column | One DB to manage | Conflates session/persistent/audit lifecycles | Coupling makes one change touch everything |
| Append-only event log only (no derived state) | Maximum integrity | Every retrieval scans the log — O(N) per query | Doesn't scale past ~10K entries |

## References

- `memory/__init__.py` — top-level docstring of the design.
- `memory/manager.py::MemoryManager` — façade implementing the sync points.
- `memory/types.py::MemoryType` — the 8 typed categories with decay rules.
- `memory/ledger.py::Ledger` — HMAC implementation.
- `config/settings.py` — `memory_*_db_path`, `memory_decay_*_days`, `ledger_enabled`.
- `hooks/session_lifecycle.py` — orchestration of session start/end across the three layers.
