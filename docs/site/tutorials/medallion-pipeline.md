# Tutorial — Build a Medallion Pipeline

Build a Bronze → Silver → Gold pipeline on Databricks Unity Catalog using slash commands.

## Scenario

You have CSV files landing in `s3://my-landing/orders/` and want to produce a Gold layer star schema (`fact_orders`, `dim_customers`, `dim_products`, `dim_date`) for BI consumption.

## 1. Generate the Bronze layer

```bash
ai-data-agents "/pipeline cria Bronze STREAMING TABLE para s3://my-landing/orders/ usando Auto Loader. Schema inference automática. Adiciona _ingest_timestamp e _source_file."
```

`databricks-engineer` returns a DLT pipeline definition (Spark SQL) and creates it via `mcp__databricks__create_pipeline`. Output includes the pipeline_id.

## 2. Generate the Silver layer

```bash
ai-data-agents "/pipeline cria Silver para bronze.orders aplicando SCD2 via AUTO CDC INTO. Chave: order_id. Sequência: updated_at."
```

The agent:

1. Reads `kb/pipeline-design/index.md` (KB-First) to confirm SCD2 pattern.
2. Generates the `APPLY CHANGES INTO silver.orders` DLT code.
3. Includes expectations (quality rules per Medallion layer):
    - Bronze: WARN on nulls in critical columns
    - Silver: DROP rows that fail data type checks
    - Gold: FAIL pipeline on business-rule violations

## 3. Generate the Gold star schema

```bash
ai-data-agents "/schema desenha Gold star schema para silver.orders. dim_customers, dim_products, dim_date sintética via SEQUENCE, fact_orders com INNER JOIN."
```

This triggers `fabric-engineer` (despite "Databricks" in the conversation — `/schema` is platform-agnostic; the Supervisor routes to whoever has Star Schema design in its KB).

Output: `output/architecture/medallion-orders.md` + DDL files.

The dim_data table is **always** generated synthetically:

```sql
SELECT explode(sequence(DATE'2020-01-01', DATE'2030-12-31', INTERVAL 1 DAY)) AS date_id
```

NEVER `SELECT DISTINCT order_date FROM silver.orders` — this is enforced as an anti-pattern in `kb/pipeline-design/index.md`.

## 4. Validate quality

```bash
ai-data-agents "/quality define SLA para gold.fact_orders. Critérios: freshness < 1 hora, completeness > 99%, validity por business rule (amount > 0)."
```

`data-quality-steward` writes expectations as DLT rules in the Gold layer pipeline. Drift detection baseline is captured for the next run to compare against.

## 5. Add governance

```bash
ai-data-agents "/governance audita gold.fact_orders para PII e RLS. Cliente é PII? Quais perfis devem ter acesso?"
```

`governance-auditor` runs and (if PII is detected) recommends RLS / column masking. The agent does **not** implement the RLS — only audits. Implementation goes back to `databricks-engineer` via escalation rules (Constitution S6).

## What you should see in `output/`

```
output/
├── architecture/
│   └── medallion-orders.md
├── pipelines/
│   ├── orders_bronze.sql
│   ├── orders_silver.sql
│   └── orders_gold.sql
├── ddl/
│   ├── dim_customers.sql
│   ├── dim_products.sql
│   ├── dim_date.sql
│   └── fact_orders.sql
├── quality/
│   └── orders_sla.md
└── governance/
    └── orders_audit.md
```

## What goes into `logs/`

- `logs/audit.jsonl` — every tool call with session_id + agent_name
- `logs/sessions.jsonl` — cost / tokens / duration per query
- `logs/sessions/<session_id>.jsonl` — full transcript

## Variations

| Variation | How |
|---|---|
| Run on Fabric instead | `/fabric` instead of `/pipeline`/`/spark` |
| Data Vault 2.0 instead of Star Schema | `/schema desenha Data Vault 2.0 ...` |
| Streaming-only (no Gold materialization) | `/streaming` instead of `/pipeline` (routes to `databricks-ai`) |

## See also

- [Constitution](../concepts/constitution.md) — S6 governance never delegated to engineering
- [`kb/pipeline-design/`](https://github.com/ThomazRossito/ai-data-agents/tree/refactor/v3.0/kb/pipeline-design) — Medallion patterns
- [`skills/databricks/databricks-spark-declarative-pipelines/SKILL.md`](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/skills/databricks/databricks-spark-declarative-pipelines/SKILL.md) — DLT skill
