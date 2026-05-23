# Memory Layer

Three independent layers, each opt-in via `.env`:

```
                                      ┌──────────────────────────────┐
                                      │  HMAC Ledger (optional)      │
                                      │  Tamper-evident signed chain │
                                      │  data_agents/memory/ledger.py│
                                      └──────────────┬───────────────┘
                                                     │ signs entries
                                                     ▼
┌─────────────────────────┐    ┌──────────────────────────────┐
│  ShortTermMemory        │    │  LongTermMemory              │
│  SQLite + FTS5/BM25     │    │  SQLite FTS5 + decay         │
│  Per-session            │    │  Cross-session, persistent   │
│  TTL ~3 days            │    │  Tag-indexed, type-categorized│
└──────────┬──────────────┘    └──────────────┬───────────────┘
           │ context within run                │ retrieved per query
           └─────────────────┬─────────────────┘
                             ▼
                   Supervisor system prompt
                   (enriched at session_start)
```

## Layer 1 — ShortTermMemory

- **What**: tools, file paths, decisions made within a single CLI/UI session.
- **Where**: `data_agents/memory/data/short_term__<project_id>.db`.
- **TTL**: 3 days by default (`SHORT_TERM_TTL_DAYS=3` in `.env`).
- **Indexing**: SQLite FTS5 BM25 over `content`; optional semantic search via fastembed (extra `[memory]`).
- **Why**: gives the next turn in the same session a way to recall "what we did 5 prompts ago" without bloating the LLM context window.

## Layer 2 — LongTermMemory

- **What**: persistent knowledge across sessions. Types:
    - `architecture` — never decays (RLS rules, schema invariants)
    - `progress` — decays after ~14 days
    - `feedback` — decays after ~90 days
    - `lesson_learned` — preventive patterns (high confidence, slow decay)
    - `data_asset` — table/view discovery results
    - `pipeline_status` — last known state of a Job/Pipeline
    - `user` — preferences, naming conventions
- **Where**: `data_agents/memory/data/long_term__<project_id>.db`.
- **Decay**: `data_agents/memory/decay.py` — confidence reduces over time per type.
- **Retrieval**: `data_agents/memory/retrieval.py` — semantic + FTS scoring, top-N injected into Supervisor prompt at session start.
- **Why**: lessons learned in session N should benefit session N+1, especially `lesson_learned` (e.g. "agent X loops on tool Y when called without arg Z").

## Layer 3 — HMAC Ledger (optional)

- **What**: tamper-evident audit trail. Every JSONL entry in `logs/audit.jsonl` is signed with a per-session HMAC key.
- **Where**: signed inline in the audit log (`ledger_entry_hash` field).
- **Enable**: `LEDGER_ENABLED=true` in `.env`.
- **Why**: lets a downstream verifier prove that the audit log was not altered after the fact. Useful for compliance scenarios.

## Configuration

```ini
# .env
MEMORY_ENABLED=true              # master switch — both ShortTerm and LongTerm
MEMORY_RETRIEVAL_ENABLED=true    # inject memories into Supervisor prompt
MEMORY_CAPTURE_ENABLED=true      # extract memories from sessions
LEDGER_ENABLED=false             # opt-in HMAC chain
SHORT_TERM_TTL_DAYS=3
PROJECT_ID=auto                  # 'auto' → uses cwd().name; or set explicitly
```

`PROJECT_ID` is critical: it suffixes the DB filenames (`long_term__<project_id>.db`) so multiple projects on the same filesystem don't share memory.

## Anti-patterns

1. **Don't share memory DBs across projects**. The project_id suffix exists for a reason — if you symlink `long_term.db` between repos, you'll get cross-contamination of `lesson_learned` entries that no longer apply.
2. **Don't rely on the Ledger for tamper-proofing against root**. HMAC signs entries against a key stored in the session config — anyone with read access to the key can re-sign. The Ledger guards against *external* replay/insertion, not local root.

## See also

- [ADR-002](../reference/adrs.md) — why three layers (vs naive RAG)
- [`data_agents/memory/`](https://github.com/ThomazRossito/ai-data-agents/tree/refactor/v3.0/data_agents/memory) — source
- [`tests/integration/test_long_term.py`](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/tests/integration/test_long_term.py) — SQLite FTS5 contract tests
