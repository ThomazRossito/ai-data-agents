# Expectations — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** @dp.expect, SQL syntax, SQL Alert Tasks, DABs YAML

---

## Bronze: Python SDP (expect — alerta apenas)

```python
from pyspark import pipelines as dp

@dp.table(name="bronze_vendas")
@dp.expect("col('id_venda').isNotNull()", "id_venda deve existir")
@dp.expect("col('data_evento').isNotNull()", "data_evento é obrigatória")
def bronze_vendas():
    return spark.readStream.format("cloudFiles") \
        .option("cloudFiles.format", "json") \
        .load("/Volumes/raw/vendas/")
```

## Silver: Python SDP (expect_or_drop — remove inválidos)

```python
@dp.table(name="silver_vendas")
@dp.expect_or_drop("col('id_cliente').isNotNull()", "Remover vendas sem cliente")
@dp.expect_or_drop("col('valor_total') > 0", "Remover vendas com valor negativo")
@dp.expect_or_drop("col('data_evento').isNotNull()", "Remover eventos sem data")
def silver_vendas():
    return spark.read.table("bronze_vendas") \
        .filter(col("valor_total").isNotNull())
```

## Gold: Python SDP (expect_or_fail — bloqueia)

```python
@dp.materialized_view(name="gold_fact_vendas")
@dp.expect_or_fail("count(*) > 1000", "Fact deve ter mínimo 1000 linhas")
@dp.expect_or_fail("sum(valor_total) > 0", "Receita total deve ser positiva")
def gold_fact_vendas():
    return spark.read.table("silver_vendas") \
        .join(...).groupBy(...)
```

---

## SQL Syntax — Bronze, Silver, Gold

### Bronze SQL
```sql
CREATE OR REFRESH STREAMING TABLE bronze_clientes
CLUSTER BY (id_cliente)
AS
SELECT *
FROM STREAM read_files('/Volumes/raw/clientes/', format => 'json')
WHERE id_cliente IS NOT NULL;

EXPECT (id_cliente IS NOT NULL) AS id_cliente_present;
EXPECT (email IS NOT NULL) AS email_present;
```

### Silver SQL
```sql
CREATE OR REFRESH STREAMING TABLE silver_clientes
CLUSTER BY (id_cliente)
AS
SELECT
  id_cliente,
  CAST(nome AS STRING) AS nome,
  CAST(email AS STRING) AS email,
  CAST(data_criacao AS DATE) AS data_criacao
FROM stream(bronze_clientes)

EXPECT OR DROP (id_cliente IS NOT NULL) AS id_cliente_not_null;
EXPECT OR DROP (email LIKE '%@%.%') AS email_valid;
EXPECT OR DROP (YEAR(data_criacao) >= 2010) AS data_valid;
```

### Gold SQL
```sql
CREATE OR REFRESH MATERIALIZED VIEW gold_dim_cliente
CLUSTER BY (surrogate_key)
AS
SELECT
  ROW_NUMBER() OVER (ORDER BY id_cliente) AS surrogate_key,
  id_cliente,
  nome,
  email
FROM silver_clientes

EXPECT OR FAIL (COUNT(*) > 100) AS min_rows;
EXPECT OR FAIL (COUNT(DISTINCT id_cliente) = COUNT(*)) AS no_duplicates;
```

---

## SQL Alert Tasks: Setup no DABs

```yaml
resources:
  jobs:
    gold_pipeline:
      name: "Gold Pipeline com Quality Checks"
      tasks:
        - task_key: check_silver_volume
          sql_task:
            alert:
              alert_id: "550e8400e29b41d4a716446655440000"
              pause_subscriptions: false
            warehouse_id: "abc123xyz"

        - task_key: build_gold_vendas
          depends_on:
            - task_key: check_silver_volume
          run_if: "ALL_SUCCESS"
          notebook_task:
            notebook_path: ../src/gold_vendas

        - task_key: check_gold_quality
          depends_on:
            - task_key: build_gold_vendas
          sql_task:
            alert:
              alert_id: "660e8400e29b41d4a716446655440001"
            warehouse_id: "abc123xyz"
```

## Exemplos de Alertas SQL

```sql
-- Alert 1: Volume mínimo
SELECT COUNT(*) FROM silver_vendas
WHERE date(data_carga) = current_date()
HAVING COUNT(*) < 500;

-- Alert 2: Duplicatas
SELECT COUNT(*) - COUNT(DISTINCT id_venda) FROM silver_vendas
HAVING COUNT(*) - COUNT(DISTINCT id_venda) > 0;

-- Alert 3: Freshness
SELECT MAX(data_evento) FROM silver_vendas
HAVING MAX(data_evento) < current_date() - 1;

-- Alert 4: Integridade referencial
SELECT COUNT(*) FROM silver_vendas v
LEFT JOIN silver_cliente c ON v.id_cliente = c.id_cliente
WHERE c.id_cliente IS NULL;
```

---

## Dupla Camada: Job + Pipeline

```yaml
resources:
  jobs:
    gold_orchestration:
      tasks:
        # Camada 1: Validação no DAG (SQL Alert Task)
        - task_key: validate_silver
          sql_task:
            alert:
              alert_id: "abc123"

        # Camada 2: Pipeline com expect_or_fail
        - task_key: run_gold_pipeline
          depends_on:
            - task_key: validate_silver
          pipeline_task:
            pipeline_id: "${resources.pipelines.gold_pipeline.id}"
```

---

## Armazenar Resultados de Expectations

```sql
CREATE TABLE IF NOT EXISTS catalog.quality.expectation_results (
  expectation_id STRING,
  table_name STRING,
  rule_name STRING,
  pass_count BIGINT,
  fail_count BIGINT,
  fail_percent DOUBLE,
  created_at TIMESTAMP
);

-- Log a cada execução
INSERT INTO catalog.quality.expectation_results
SELECT
  'bronze_vendas_id_not_null',
  'bronze_vendas',
  'id_venda IS NOT NULL',
  SUM(CASE WHEN id_venda IS NOT NULL THEN 1 ELSE 0 END),
  SUM(CASE WHEN id_venda IS NULL THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN id_venda IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2),
  current_timestamp()
FROM bronze_vendas;
```
