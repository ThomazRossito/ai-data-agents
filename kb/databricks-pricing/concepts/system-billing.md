---
concept: system-billing
domain: databricks-pricing
updated_at: 2026-05-28
---

# system.billing — Schema oficial e queries comuns

## O que é

`system.billing` é um **schema do Unity Catalog** que expõe consumo Databricks da conta inteira. Permite SQL queries diretas pra análise FinOps de workloads em produção.

**Requer:**
- Unity Catalog habilitado no workspace
- Permissão `USE CATALOG system` + `SELECT ON SCHEMA system.billing`
- Geralmente concedida ao grupo `finance_team` ou account admins

**Engine no projeto:** `data_agents.cost_engine.billing` (Fase 3). MCP server `databricks_billing` expõe 5 tools que consomem essas tabelas.

## Tabelas relevantes

### system.billing.usage (registros granulares de consumo)

| Coluna | Tipo | Descrição |
|---|---|---|
| `usage_date` | DATE | Data do consumo (UTC) |
| `workspace_id` | BIGINT | ID do workspace |
| `sku_name` | STRING | SKU consumido (ex: `PREMIUM_JOBS_COMPUTE_AZURE`) |
| `usage_quantity` | DECIMAL | Quantidade consumida |
| `usage_unit` | STRING | Unidade (sempre `DBU` para DBUs) |
| `cloud` | STRING | `AZURE` \| `AWS` \| `GCP` |
| `usage_metadata` | MAP | Dict com `cluster_id`, `cluster_name`, `job_id`, etc |

> **Atenção:** `usage_metadata.cluster_id` requer **dot notation** em SQL (ex: `usage_metadata.cluster_id AS cluster_id`). No engine do projeto, o `usage_df` recebido já tem `cluster_id` e `cluster_name` como colunas top-level (extração feita pelo caller — mock ou SQL real).

### system.billing.list_prices (preços vigentes/históricos por SKU)

| Coluna | Tipo | Descrição |
|---|---|---|
| `sku_name` | STRING | SKU (chave com `usage`) |
| `cloud` | STRING | Cloud (chave com `usage`) |
| `currency_code` | STRING | `USD` |
| `pricing` | STRUCT | Tem `pricing.default` (USD/DBU) |
| `price_start_time` | TIMESTAMP | Início de vigência |
| `price_end_time` | TIMESTAMP | Fim de vigência (`NULL` = vigente) |

**Pra preço atual:** filtrar `WHERE price_end_time IS NULL`.

### system.compute.clusters (metadata histórica)

| Coluna | Tipo | Descrição |
|---|---|---|
| `cluster_id` | STRING | ID do cluster |
| `cluster_name` | STRING | Nome amigável |
| `cluster_source` | STRING | `UI`, `JOB`, `API` |
| `dbr_version` | STRING | Databricks Runtime |
| `delete_time` | TIMESTAMP | NULL = ativo |

Útil pra resolver `cluster_id` → `cluster_name` quando o `usage_metadata` está incompleto.

## Pattern SKU → compute_type (classify_sku)

O engine usa pattern matching pra classificar SKUs em categorias canônicas. **Ordem importa** porque alguns SKUs contêm múltiplas keywords:

```python
_SKU_PATTERNS = (
    ("SERVERLESS", "serverless_compute"),     # Vem ANTES de SQL/JOBS
    ("ALL_PURPOSE", "all_purpose_compute"),
    ("JOBS", "jobs_compute"),
    ("SQL", "sql_compute"),
    ("DLT", "dlt_core"),
)
```

**Exemplos:**
- `PREMIUM_SERVERLESS_SQL_AZURE` → `serverless_compute` (SERVERLESS ganha)
- `PREMIUM_ALL_PURPOSE_COMPUTE_AZURE` → `all_purpose_compute`
- `PREMIUM_JOBS_COMPUTE_AZURE` → `jobs_compute`
- `PREMIUM_DLT_ADVANCED_AZURE` → `dlt_core`
- `UNKNOWN_SKU_XYZ` → `other`

## Queries comuns (reference — engine wrappa via DataFrames)

### Daily DBU por SKU (últimos 30 dias)

```sql
SELECT
    usage_date,
    sku_name,
    SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE usage_date >= current_date() - 30
GROUP BY usage_date, sku_name
ORDER BY usage_date DESC, total_dbus DESC;
```

**Engine equivalente:** `aggregate_dbu_daily(usage_df, period)`

### Top clusters por custo

```sql
SELECT
    usage_metadata.cluster_id AS cluster_id,
    usage_metadata.cluster_name AS cluster_name,
    SUM(usage_quantity) AS total_dbus,
    SUM(usage_quantity * p.pricing.default) AS estimated_cost
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
    ON u.sku_name = p.sku_name AND u.cloud = p.cloud
WHERE usage_date >= current_date() - 30
  AND p.price_end_time IS NULL
  AND usage_metadata.cluster_id IS NOT NULL
GROUP BY usage_metadata.cluster_id, usage_metadata.cluster_name
ORDER BY estimated_cost DESC
LIMIT 10;
```

**Engine equivalente:** `top_cost_clusters(usage_df, prices_df, period, limit=10)`

### Breakdown por compute_type

```sql
SELECT
    CASE
        WHEN sku_name LIKE '%SERVERLESS%' THEN 'serverless_compute'
        WHEN sku_name LIKE '%ALL_PURPOSE%' THEN 'all_purpose_compute'
        WHEN sku_name LIKE '%JOBS%' THEN 'jobs_compute'
        WHEN sku_name LIKE '%SQL%' THEN 'sql_compute'
        ELSE 'other'
    END AS compute_type,
    SUM(usage_quantity) AS total_dbus,
    SUM(usage_quantity * p.pricing.default) AS cost_usd
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
    ON u.sku_name = p.sku_name AND u.cloud = p.cloud
WHERE usage_date >= current_date() - 30
  AND p.price_end_time IS NULL
GROUP BY 1
ORDER BY cost_usd DESC;
```

**Engine equivalente:** `cost_by_compute_type(usage_df, prices_df, period)`

## Tools MCP disponíveis (4 + 1 bridge)

| Tool | SQL equivalente |
|---|---|
| `databricks_billing_diagnostics` | `SELECT count(*) FROM system.billing.usage WHERE usage_date >= current_date() - 7` |
| `databricks_billing_get_dbu_usage_daily` | Daily DBU por SKU (acima) |
| `databricks_billing_get_top_cost_clusters` | Top clusters (acima) |
| `databricks_billing_get_cost_by_compute_type` | Breakdown compute_type (acima) |
| `databricks_billing_compare_estimate_vs_actual` | Bridge: ver `estimate-vs-actual.md` |

## Mock mode (Chunk 3.1)

Engine consome **DataFrames** — não conecta direto no Databricks. Caller injeta:

- **Mock mode** (`DATABRICKS_BILLING_MOCK_MODE=true`): `billing_mock.py` gera 60d sintéticos com 5 clusters fictícios (`etl-bronze-prod`, `etl-silver-prod`, `ml-training-prod`, `ad-hoc-analytics`, `dlt-streaming`) e 4 SKUs (jobs, all_purpose, sql, serverless). Determinístico via seed.

- **Real mode** (`mock_mode=false`): integração `databricks-sdk` + warehouse pra rodar SQL. **Placeholder no Chunk 3.1** — RuntimeError informativo até integração ficar pronta em chunk posterior.

## Caveats / regras

- **Dados em UTC.** Cuidado ao filtrar por dia em timezones diferentes — `usage_date` é UTC.
- **`usage_quantity` é DBU, não USD.** Custo só após JOIN com `list_prices`.
- **`price_end_time IS NULL`** = vigente. Sem esse filtro, JOIN traz preços históricos múltiplos por SKU.
- **`usage_metadata.cluster_id IS NULL`** pra Jobs serverless, DLT compartilhado. Excluir do top_cost_clusters (o engine já faz).
- **Multi-region:** `usage` não tem coluna `region` direta. Pra cotar variação por região, usar SKU pattern ou inferir via `cluster_id` × `system.compute.clusters.cluster_source`.

## Onde está codificado

- Schema reference: `skills/databricks/databricks-unity-catalog/5-system-tables.md`
- Engine: `data_agents/cost_engine/billing.py`
- Mock generator: `data_agents/cost_app/databricks/billing_mock.py`
- MCP server: `data_agents/mcp_servers/databricks_billing/server.py`
