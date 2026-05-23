# Slash Commands

Slash commands skip the Supervisor's clarity checkpoint and route directly to a specialist. Two modes:

- **Express** — direct delegation, no PRD, no approval gate. For unambiguous intents.
- **Full** — DOMA Full flow: clarity checkpoint, plan, approval, then delegation. For complex multi-step work.

Full list lives in [`reference/slash-commands.md`](../reference/slash-commands.md). The most useful subset:

## Daily use

| Command | Target | What it does |
|---|---|---|
| `/sql <query>` | databricks-engineer | Run SQL directly on Databricks |
| `/spark <task>` | databricks-engineer | PySpark / DLT / LakeFlow code |
| `/fabric <task>` | fabric-engineer | Any Fabric task (Lakehouse, Data Factory, DAX, Semantic Model) |
| `/dbt <task>` | dbt-expert | dbt Core models, tests, snapshots |
| `/python <task>` | python-expert | Pure Python (no PySpark) |

## Analysis & quality

| Command | Target | What it does |
|---|---|---|
| `/quality <task>` | data-quality-steward | Profiling, drift detection, SLA |
| `/governance <task>` | governance-auditor | Access audit, PII classification, LGPD/GDPR |
| `/contract <task>` | data-contracts-engineer | ODCS contracts, schema evolution |
| `/diagnose <task>` | databricks-engineer | Spark job diagnosis (OOM, skew, shuffle) |
| `/finops <task>` | fabric-engineer | Capacity Units, rightsizing |

## Architecture & planning

| Command | Target | What it does |
|---|---|---|
| `/plan <objective>` | Supervisor (DOMA Full) | Multi-step planning with thinking enabled |
| `/brief <document>` | business-analyst | Convert transcript → structured backlog (P0/P1/P2) |
| `/medallion <task>` | fabric-engineer | Medallion architecture design |
| `/mesh <task>` | data-mesh-architect | Data Mesh + Data Products |
| `/migrate <source>` | migration-expert | SQL Server / PostgreSQL → Databricks/Fabric |
| `/ontology <task>` | fabric-ontology | OWL 2 design, RDF, Fabric IQ Ontology |

## Multi-agent

| Command | What it does |
|---|---|
| `/party <query>` | Multi-agent parallel — independent perspectives. Flags: `--quality`, `--arch`, `--engineering`, `--migration`, `--full` |
| `/analyze-project [--quality\|--arch\|--databricks\|--fabric] [description]` | 4 specialists in parallel, output to `output/analyze-project/` |
| `/workflow <wf-id> <query>` | Predefined collaborative workflow (WF-01 to WF-06) with context chain |

## Conversational & utility

| Command | What it does |
|---|---|
| `/geral <question>` | Conceptual answer — zero MCP, runs on Kimi K2.6 (~95% cheaper than supervisor flow) |
| `/health` | Platform connectivity status (Databricks, Fabric, MCPs) |
| `/status` | Current session state |
| `/memory <query>` | Query persistent memory |
| `/sessions [all\|<id>]` | List recorded sessions |
| `/resume [last\|<id>]` | Resume a previous session |
| `/ship <title>` | Archive completed task with lessons learned |

The full list with prompt templates lives in `data_agents/config/commands.yaml` and is validated by `scripts/lint_commands.py`. See **[reference/slash-commands.md](../reference/slash-commands.md)** for the canonical list.
