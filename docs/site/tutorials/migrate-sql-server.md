# Tutorial — Migrate SQL Server to Databricks

This walkthrough assumes you have a SQL Server instance with credentials configured (`MIGRATION_SOURCE_*` in `.env`) and a target Databricks workspace.

## Phases

The `migration-expert` agent executes 5 sequential phases:

```
ASSESS  →  ANALYZE  →  DESIGN  →  TRANSPILE  →  RECONCILE
```

## 1. Run the slash command

```bash
ai-data-agents "/migrate quero migrar meu SQL Server (200 tabelas, OLTP) para Databricks"
```

The Supervisor routes this directly to `migration-expert` (DOMA Express because `/migrate` is unambiguous).

## 2. ASSESS — what's in the source?

The agent calls:

- `mcp__migration_source__migration_source_list_sources()` — confirms connectivity
- `mcp__migration_source__migration_source_diagnostics(source="default")` — validates version, perms
- `mcp__migration_source__migration_source_get_schema_summary()` — counts of tables / views / procedures / functions
- `mcp__migration_source__migration_source_count_tables_by_schema()` — distribution

Sample output:

```
🔧 Migration Expert — Phase 1 ASSESS
Source: SQL Server 2019 (connected as: app_reader)
Tables: 187 across 4 schemas
  - dbo:          142 tables
  - audit:         23 tables
  - reporting:     14 tables
  - staging:        8 tables
Views: 34  |  Procedures: 12  |  Functions: 8
PII candidates: 11 tables flagged (will validate in Phase 2)
```

If PII is detected at this stage, the agent **stops** and escalates to `governance-auditor` (Constitution S6) before proceeding — see [`data_agents/agents/registry/migration-expert.md`](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/data_agents/agents/registry/migration-expert.md).

## 3. ANALYZE — categorize tables

Tables are bucketed by migration strategy:

- **Direct migration** — small reference tables, no FK constraints
- **CDC candidates** — high-write OLTP tables, > 1M rows
- **Snapshot + delta** — slowly-changing dimensions
- **Out of scope** — staging / temp tables

## 4. DESIGN — Medallion architecture

The agent generates `output/migration/<source>/architecture.md` with:

- Bronze layer: STREAMING TABLE with `_ingest_timestamp`, `_source_file`
- Silver layer: SCD2 via `AUTO CDC INTO` (no manual MERGE — anti-pattern)
- Gold layer: Star Schema with `dim_data` via `SEQUENCE(...)` (anti-pattern: `SELECT DISTINCT data`)

## 5. TRANSPILE — DDL transformation

For each table, the agent generates Databricks-compatible DDL applying the **M1-M10 auto-review checklist**:

| Check | Action |
|---|---|
| M1: FLOAT/REAL on monetary cols → DECIMAL(19,4) | Always |
| M2: IDENTITY/SERIAL removed | Always |
| M3: FK constraints removed (Delta doesn't enforce) | Always |
| M4: TEXT/NTEXT/IMAGE → STRING/BINARY | Always |
| M5: UNIQUEIDENTIFIER → STRING | Always |
| M6: DATETIMEOFFSET normalized to UTC | Always |
| M7: PARTITIONED BY (_ingestion_date) on Bronze | Always |
| M8: Audit columns (_ingestion_date, _source_system) added | Always |
| M9: No mixing of Spark SQL + T-SQL in same file | Per-platform |
| M10: Fully-qualified `catalog.schema.table` | Always |

## 6. RECONCILE — validate

Final phase: row counts, sum of monetary columns, PK uniqueness checks between source and target. For complex validation (drift detection, statistical comparison), the agent escalates to `data-quality-steward`.

## What gets persisted

- `output/migration/<source>/architecture.md` — design document
- `output/migration/<source>/ddl/<schema>.sql` — transpiled DDL per source schema
- `output/migration/<source>/reconcile_report.md` — final validation summary
- `logs/audit.jsonl` — every MCP call with `session_id` for replay

## Variations

| What | How |
|---|---|
| Target Fabric instead of Databricks | The agent asks during ASSESS if destination is ambiguous; or pass `--target fabric` in the prompt |
| Only TRANSPILE (DDL already provided) | `ai-data-agents "/migrate transpile DDL from PostgreSQL to Databricks: <paste DDL>"` |
| Reconcile only | `ai-data-agents "/migrate apenas reconcile entre src.schema.table e main.silver.table"` |

## See also

- Source agent: [`migration-expert.md`](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/data_agents/agents/registry/migration-expert.md)
- KB: [`kb/migration/`](https://github.com/ThomazRossito/ai-data-agents/tree/refactor/v3.0/kb/migration)
- Skill: [`skills/migration/SKILL.md`](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/skills/migration/SKILL.md)
- MCP server: [`data_agents/mcp_servers/migration_source/`](https://github.com/ThomazRossito/ai-data-agents/tree/refactor/v3.0/data_agents/mcp_servers/migration_source)
