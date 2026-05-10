# Medallion Architecture — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** SQL/Python para cada camada Bronze, Silver, Gold

---

## Bronze: Auto Loader com Schema Inference

```sql
-- Padrão Bronze: STREAMING TABLE com Auto Loader
CREATE OR REFRESH STREAMING TABLE bronze_vendas
CLUSTER BY (data_carga)
AS
SELECT
  *,
  _metadata.file_path AS _file_path,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/raw/vendas/',
  format => 'json',
  cloudFiles.schemaInferenceMode => 'addNewColumns',
  cloudFiles.schemaLocation => '/Volumes/raw/vendas/.schema'
);
```

### Configuração SDP (databricks.yml)

```yaml
resources:
  pipelines:
    bronze_pipeline:
      configuration:
        cloudFiles.inferColumnTypes: "true"
        cloudFiles.schemaInferenceMode: "addNewColumns"
        cloudFiles.schemaLocation: "/Volumes/raw/vendas/.schema"
```

---

## Silver: Tipagem, Validação e AUTO CDC

### STREAMING TABLE com Expectations

```sql
CREATE OR REFRESH STREAMING TABLE silver_vendas
CLUSTER BY (id_venda, data_evento)
AS
SELECT
  CAST(id_venda AS BIGINT) AS id_venda,
  CAST(id_cliente AS BIGINT) AS id_cliente,
  CAST(valor_total AS DECIMAL(18,2)) AS valor_total,
  CAST(data_evento AS DATE) AS data_evento,
  UPPER(status) AS status,
  _ingested_at
FROM stream(bronze_vendas)
WHERE
  id_venda IS NOT NULL
  AND valor_total > 0;
```

### Expectations (SDP decorators)

```sql
-- Define expectations na Silver
@expect("id_cliente IS NOT NULL")
@expect_or_drop("valor_total > 0")
@expect_or_drop("UPPER(status) IN ('ATIVO', 'CANCELADO')")
SELECT * FROM stream(bronze_vendas);
```

### SCD2 com AUTO CDC

```sql
-- Histórico completo de mudanças
CREATE OR REFRESH STREAMING TABLE silver_vendas_history
CLUSTER BY (id_venda, __START_AT)
AS
APPLY CHANGES INTO silver_vendas_history
FROM stream(silver_vendas)
KEYS (id_venda)
SEQUENCE BY _ingested_at
COLUMNS * EXCEPT (_ingested_at);
```

---

## Gold: MATERIALIZED VIEW com Star Schema

### Dimensão com Surrogate Key

```sql
-- dim_cliente: MATERIALIZED VIEW obrigatória na Gold
CREATE OR REFRESH MATERIALIZED VIEW gold_dim_cliente
CLUSTER BY (surrogate_key)
AS
SELECT
  ROW_NUMBER() OVER (ORDER BY id_cliente) AS surrogate_key,
  id_cliente,
  nome_cliente,
  cidade,
  pais,
  current_timestamp() AS _created_at
FROM silver_cliente
WHERE id_cliente IS NOT NULL
GROUP BY id_cliente, nome_cliente, cidade, pais;
```

### Tabela de Datas Sintética (SEQUENCE + EXPLODE)

```sql
-- dim_data: NUNCA via SELECT DISTINCT — sempre SEQUENCE + EXPLODE
CREATE OR REFRESH MATERIALIZED VIEW gold_dim_data
CLUSTER BY (data)
AS
SELECT
  CAST(data_seq AS DATE) AS data,
  DAYOFMONTH(data_seq) AS dia,
  MONTH(data_seq) AS mes,
  QUARTER(data_seq) AS trimestre,
  YEAR(data_seq) AS ano,
  DAYOFWEEK(data_seq) AS dia_semana,
  WEEKOFYEAR(data_seq) AS semana_iso
FROM (
  SELECT EXPLODE(SEQUENCE(
    DATE '2020-01-01',
    DATE '2030-12-31',
    INTERVAL 1 DAY
  )) AS data_seq
);
```

### Fato com INNER JOINs

```sql
-- fact_vendas: INNER JOIN com TODAS as dimensões
CREATE OR REFRESH MATERIALIZED VIEW gold_fact_vendas
CLUSTER BY (dim_data_key, dim_cliente_key)
AS
SELECT
  dd.surrogate_key AS dim_data_key,
  dc.surrogate_key AS dim_cliente_key,
  v.id_venda,
  v.valor_total,
  v.qtd_itens,
  COUNT(*) AS qtd_transacoes
FROM silver_vendas v
INNER JOIN gold_dim_cliente dc ON v.id_cliente = dc.id_cliente
INNER JOIN gold_dim_data dd ON CAST(v.data_evento AS DATE) = dd.data
GROUP BY dd.surrogate_key, dc.surrogate_key, v.id_venda, v.valor_total, v.qtd_itens;
```

### Expect_or_fail na Gold (obrigatório)

```sql
@expect_or_fail("dim_data_key IS NOT NULL")
@expect_or_fail("dim_cliente_key IS NOT NULL")
SELECT * FROM gold_fact_vendas;
```

---

## Fluxo de Dados

```
Cloud Storage (JSON, CSV, Parquet)
         ↓
   Auto Loader (read_files + cloudFiles)
         ↓
  bronze_*  ← Raw, _ingested_at, _file_path
         ↓
    STREAM + tipagem + expect_or_drop
         ↓
  silver_*  ← Tipado, validado, AUTO CDC
         ↓
   MATERIALIZED VIEW + INNER JOINs
         ↓
  gold_dim_* / gold_fact_*  ← Star Schema, CLUSTER BY
```
