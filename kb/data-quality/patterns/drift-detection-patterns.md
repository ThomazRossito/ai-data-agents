# Drift Detection — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** Schema diff SQL, data drift comparativo, drift log DDL

---

## SDP: Auto-Evolution de Schema

```python
# Python SDP com mergeSchema
from pyspark import pipelines as dp

@dp.table(name="bronze_vendas")
def bronze_vendas():
    return spark.readStream.format("cloudFiles") \
        .option("cloudFiles.format", "json") \
        .option("cloudFiles.schemaInferenceMode", "addNewColumns") \
        .option("mergeSchema", "true")  # Auto-evolve schema
        .load("/Volumes/raw/vendas/")
```

---

## Schema Comparison Manual

```sql
-- Tabela de metadados de schema
CREATE TABLE IF NOT EXISTS catalog.quality.schema_history (
  schema_id STRING,
  table_name STRING,
  column_name STRING,
  column_type STRING,
  nullable BOOLEAN,
  ordinal_position INT,
  snapshot_date DATE,
  is_new BOOLEAN,
  is_deleted BOOLEAN
);

-- Snapshot atual
INSERT INTO catalog.quality.schema_history
SELECT
  CONCAT(table_name, '_', current_date()),
  table_name,
  column_name,
  data_type,
  is_nullable,
  ordinal_position,
  current_date(),
  FALSE,
  FALSE
FROM information_schema.columns
WHERE table_catalog = 'main' AND table_schema = 'silver'
ORDER BY table_name, ordinal_position;

-- Detectar novas colunas
SELECT
  current_columns.column_name,
  current_columns.data_type,
  current_columns.ordinal_position,
  'NEW COLUMN' AS change_type
FROM information_schema.columns current_columns
LEFT JOIN catalog.quality.schema_history history
  ON current_columns.column_name = history.column_name
  AND current_columns.table_name = history.table_name
WHERE history.column_name IS NULL
  AND current_columns.table_name = 'silver_vendas';

-- Detectar removidas
SELECT
  history.column_name,
  'DELETED COLUMN' AS change_type
FROM catalog.quality.schema_history history
LEFT JOIN information_schema.columns current_columns
  ON history.column_name = current_columns.column_name
  AND history.table_name = current_columns.table_name
WHERE current_columns.column_name IS NULL
  AND history.table_name = 'silver_vendas'
  AND history.snapshot_date = current_date() - 1;
```

---

## Data Drift: Profiling Comparativo

```sql
-- Comparar perfil de hoje vs semana passada
WITH today_profile AS (
  SELECT
    'TODAY' AS period,
    COUNT(*) AS row_count,
    COUNT(DISTINCT id_cliente) AS unique_clients,
    MIN(valor_total) AS min_valor,
    MAX(valor_total) AS max_valor,
    ROUND(AVG(valor_total), 2) AS avg_valor,
    ROUND(STDDEV(valor_total), 2) AS stddev_valor,
    ROUND(100.0 * SUM(CASE WHEN id_cliente IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS null_pct,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY valor_total), 2) AS median_valor
  FROM silver_vendas
  WHERE data_evento >= current_date()
),
week_ago_profile AS (
  SELECT
    'WEEK_AGO' AS period,
    COUNT(*) AS row_count,
    COUNT(DISTINCT id_cliente) AS unique_clients,
    MIN(valor_total) AS min_valor,
    MAX(valor_total) AS max_valor,
    ROUND(AVG(valor_total), 2) AS avg_valor,
    ROUND(STDDEV(valor_total), 2) AS stddev_valor,
    ROUND(100.0 * SUM(CASE WHEN id_cliente IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS null_pct,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY valor_total), 2) AS median_valor
  FROM silver_vendas
  WHERE data_evento >= current_date() - 7 AND data_evento < current_date() - 6
)
SELECT
  t.row_count AS today_rows,
  w.row_count AS week_ago_rows,
  ROUND(100.0 * (t.row_count - w.row_count) / w.row_count, 2) AS volume_change_pct,
  ROUND(100.0 * (t.avg_valor - w.avg_valor) / w.avg_valor, 2) AS avg_valor_change_pct,
  CASE
    WHEN ABS(ROUND(100.0 * (t.avg_valor - w.avg_valor) / w.avg_valor, 2)) > 20 THEN 'DATA DRIFT: Média alterou >20%'
    WHEN ABS(ROUND(100.0 * (t.row_count - w.row_count) / w.row_count, 2)) > 30 THEN 'DATA DRIFT: Volume alterou >30%'
    WHEN ABS(t.null_pct - w.null_pct) > 5 THEN 'DATA DRIFT: Nulls alteraram >5%'
    WHEN t.max_valor > w.max_valor * 1.5 THEN 'DATA DRIFT: Outlier novo detectado'
    ELSE 'OK'
  END AS drift_status
FROM today_profile t, week_ago_profile w;
```

---

## Drift Log DDL e Inserção

```sql
-- Tabela de log de detecções de drift
CREATE TABLE IF NOT EXISTS catalog.quality.drift_log (
  drift_id STRING,
  table_name STRING,
  drift_type STRING,  -- SCHEMA | DATA
  change_type STRING,
  metric_name STRING,
  threshold_value DOUBLE,
  detected_value DOUBLE,
  percent_change DOUBLE,
  severity STRING,  -- INFO | WARNING | CRITICAL
  first_detected TIMESTAMP,
  last_detected TIMESTAMP,
  status STRING,  -- OPEN | INVESTIGATING | RESOLVED
  root_cause STRING,
  resolution_date DATE
);

-- Inserir detecção de schema drift
INSERT INTO catalog.quality.drift_log
VALUES (
  CONCAT('DRIFT_', CURRENT_TIMESTAMP_MS()),
  'silver_vendas',
  'SCHEMA',
  'COLUMN_ADD',
  'promo_code',
  NULL, NULL, NULL,
  'INFO',
  CURRENT_TIMESTAMP(),
  CURRENT_TIMESTAMP(),
  'OPEN',
  NULL, NULL
);
```

---

## SQL Alert Task Agendado

```yaml
resources:
  jobs:
    drift_detection:
      name: "Daily Drift Detection"
      tasks:
        - task_key: detect_schema_drift
          sql_task:
            alert:
              alert_id: "schema-drift-detector"
            warehouse_id: "abc123"

        - task_key: detect_data_drift
          sql_task:
            alert:
              alert_id: "data-drift-detector"
            warehouse_id: "abc123"

      schedule:
        quartz_cron_expression: "0 3 * * ?"  # 3 AM diariamente
```

---

## Investigação e Fechamento

```sql
-- 1. Confirmar drift aberto
SELECT * FROM catalog.quality.drift_log
WHERE status = 'OPEN'
ORDER BY first_detected DESC;

-- 2. Investigar lineage (schema drift)
SELECT
  _metadata.file_path,
  COUNT(*) AS record_count,
  CURRENT_TIMESTAMP() AS detected_at
FROM bronze_vendas
WHERE _metadata.file_path LIKE '%2026-04-09%'
GROUP BY _metadata.file_path;

-- 3. Investigar distribuição hora-a-hora (data drift)
SELECT
  HOUR(data_carga) AS hora,
  COUNT(*) AS records,
  ROUND(AVG(valor_total), 2) AS avg_valor,
  MIN(valor_total) AS min_valor,
  MAX(valor_total) AS max_valor
FROM silver_vendas
WHERE data_evento >= current_date()
GROUP BY HOUR(data_carga)
ORDER BY hora DESC;

-- 4. Validar resolução e fechar
UPDATE catalog.quality.drift_log
SET status = 'RESOLVED', resolution_date = current_date()
WHERE drift_id = 'DRIFT_...'
  AND DATEDIFF(current_date(), first_detected) >= 1;
```
