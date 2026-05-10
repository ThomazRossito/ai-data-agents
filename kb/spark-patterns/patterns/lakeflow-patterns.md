# SDP LakeFlow — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** SDP Bronze/Silver/Gold DDL, AUTO CDC Python + SQL, Expectations, Multi-Schema

---

## Bronze: Auto Loader (SQL)

```sql
CREATE OR REFRESH STREAMING TABLE bronze_sales AS
SELECT
  *,
  _metadata.file_path,
  _metadata.file_modification_time
FROM cloud_files(
  "s3://bucket/sales/",
  "parquet",
  map("cloudFiles.format" → "parquet")
);
```

## Bronze: Auto Loader (Python SDP)

```python
from pyspark import pipelines as dp

@dp.table
def bronze_sales():
    return spark.readStream \
        .option("cloudFiles", "s3://bucket/sales/") \
        .option("cloudFiles.format", "parquet") \
        .load()
```

---

## Silver: STREAMING TABLE com stream()

```sql
-- Correto: STREAMING TABLE com stream()
CREATE OR REFRESH STREAMING TABLE silver_sales AS
SELECT
  id,
  value,
  CURRENT_TIMESTAMP() AS processed_at
FROM stream(bronze_sales)
WHERE value > 0;
```

---

## Gold: MATERIALIZED VIEW

```sql
CREATE OR REFRESH MATERIALIZED VIEW gold_sales_daily AS
SELECT
  DATE(processed_at) AS data,
  COUNT(*) AS num_transacoes,
  SUM(value) AS valor_total,
  AVG(value) AS valor_medio
FROM stream(silver_sales)
GROUP BY DATE(processed_at);
```

---

## AUTO CDC: SQL

```sql
-- CDC automático
CREATE OR REFRESH STREAMING TABLE silver_customers_cdc AS
SELECT
  id,
  name,
  email,
  _change_type,
  _commit_version,
  _commit_timestamp
FROM cdc_read_changes(
  initial_data_source => table("bronze_customers"),
  ignore_deletes => false,
  ignore_column_droppped => false
);

-- SCD2 sobre o CDC
CREATE OR REFRESH MATERIALIZED VIEW gold_customers_scd2 AS
SELECT
  id,
  name AS current_name,
  _commit_timestamp AS effective_from,
  LEAD(_commit_timestamp) OVER (PARTITION BY id ORDER BY _commit_version)
    - INTERVAL 1 SECOND AS effective_to,
  ROW_NUMBER() OVER (PARTITION BY id ORDER BY _commit_version) AS version_number
FROM silver_customers_cdc
WHERE _change_type IN ('UPDATE_POSTIMAGE', 'INSERT');
```

## AUTO CDC: Python SDP

```python
from pyspark import pipelines as dp
from pyspark.sql.functions import col

@dp.table
def silver_customers_cdc():
    return dp.create_auto_cdc_flow(
        source=dp.read_stream("bronze_customers"),
        target="silver_customers_cdc",
        keys=["id"],
        sequence_by="_commit_timestamp"
    )

@dp.materialized_view
def gold_customers_scd2():
    df = dp.read_stream("silver_customers_cdc")
    return df.select(
        "id",
        col("name").alias("current_name"),
        col("__START_AT").alias("effective_from"),
        col("__END_AT").alias("effective_to")
    )
```

---

## Expectations: Data Quality

```python
from pyspark import pipelines as dp

@dp.expect("valid_id", "id > 0")
@dp.expect_or_drop("non_null_email", "email IS NOT NULL")
@dp.table
def silver_customers():
    return dp.read_stream("bronze_customers").filter("id > 0")
```

```sql
-- SQL: expectations inline
CREATE OR REFRESH STREAMING TABLE silver_customers
EXPECT valid_id, non_null_email AS
SELECT
  id,
  COALESCE(email, 'NO_EMAIL') AS email
FROM stream(bronze_customers)
WHERE id > 0;
```

---

## Multi-Schema: Um Pipeline, Múltiplos Schemas

```python
from pyspark import pipelines as dp

@dp.table
def bronze_customers():
    return spark.readStream.option("cloudFiles", "s3://bucket/customers/").load()

@dp.table
def bronze_orders():
    return spark.readStream.option("cloudFiles", "s3://bucket/orders/").load()

@dp.table
def silver_customers():
    return dp.read_stream("bronze_customers").filter("id > 0")

@dp.table
def silver_orders():
    return dp.read_stream("bronze_orders").filter("order_id > 0")

@dp.materialized_view
def gold_sales():
    customers = dp.read_stream("silver_customers")
    orders = dp.read_stream("silver_orders")
    return customers.join(orders, "id")
```
