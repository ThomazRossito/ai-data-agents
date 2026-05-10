# Performance Spark — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** DataFrame API, broadcast, repartition/coalesce, cache, predicate pushdown, AQE

---

## DataFrame API (vs RDD)

```python
from pyspark.sql.functions import col, sum, count

# Correto: DataFrame API (Catalyst optimizer)
df = spark.read.format("delta").load("/dbfs/user/hive/warehouse/fact_vendas")
result = df.groupBy("regiao").agg(
    sum("valor").alias("total_vendas"),
    count("*").alias("num_transacoes")
)
```

---

## Native Functions (vs UDF)

```python
from pyspark.sql.functions import col, when, round

# Correto: Native (50-100x mais rápido)
df_vendas = df_vendas.withColumn(
    "valor_final",
    round(
        when(col("valor") > 1000, col("valor") * (1 - col("taxa_desconto") * 0.15))
        .otherwise(col("valor") * (1 - col("taxa_desconto"))),
        2
    )
)

# Anti-pattern: UDF Python (lento por serialização)
# @udf(returnType=DoubleType())
# def calculate_discount(valor, taxa): ...
```

---

## broadcast(): Joins com Tabelas Pequenas

```python
from pyspark.sql.functions import broadcast

df_vendas = spark.read.format("delta").load("/warehouse/fact_vendas")   # 10GB
df_categoria = spark.read.format("delta").load("/warehouse/dim_categoria")  # 50MB

# Correto: broadcast da tabela pequena (< 100MB)
result = df_vendas.join(
    broadcast(df_categoria),
    on="id_categoria",
    how="inner"
)
```

---

## repartition() vs coalesce()

```python
# repartition: aumentar paralelismo (com shuffle)
df = spark.read.format("delta").load("/warehouse/fact_vendas")
repartitioned = df.repartition(200)

# coalesce: reduzir partições antes de escrever (sem shuffle)
result_df = df.groupBy("regiao").count()
coalesced = result_df.coalesce(8)
coalesced.write.format("delta").mode("overwrite").save("/warehouse/resultado")
```

---

## cache() e persist()

```python
from pyspark import StorageLevel

df = spark.read.format("delta").load("/warehouse/fact_vendas")

# cache: usar 2+ vezes (MEMORY_AND_DISK)
df.cache()
result1 = df.filter("regiao == 'SP'").count()  # Usa cache
result2 = df.filter("regiao == 'RJ'").count()  # Usa cache
df.unpersist()  # Liberar memória

# persist com controle de storage
df.persist(StorageLevel.DISK_ONLY)   # Dados > 30GB
df.persist(StorageLevel.MEMORY_AND_DISK)  # Default
```

---

## Predicate Pushdown: Filtrar Antes de Join

```python
# Correto: filtrar antes, depois join
df_large_filtered = df_large.filter("regiao == 'SP'")  # 10GB → 500MB
result = df_large_filtered.join(df_medium, on="id")

# Anti-pattern: join depois filtrar
# joined = df_large.join(df_medium, on="id")  # 20GB intermediário
# result = joined.filter("regiao == 'SP'")
```

---

## Shuffle Partition Tuning

```python
# Ajuste baseado no tamanho dos dados
total_size_gb = spark.sql("SELECT SUM(bytes) / 1e9 FROM tbl").collect()[0][0]
num_partitions = max(4, min(2048, int(total_size_gb / 0.5)))  # 0.5GB por partição
spark.conf.set("spark.sql.shuffle.partitions", str(num_partitions))
```

---

## Múltiplas Agregações em Uma Pass

```python
from pyspark.sql.functions import count, countDistinct, sum

# Correto: uma pass com múltiplas agregações
result = df.agg(
    count("*").alias("count_vendas"),
    countDistinct("id_cliente").alias("count_clientes"),
    sum("valor").alias("sum_valores")
)

# Anti-pattern: 3 passes separadas no mesmo DataFrame
# count_vendas = df.count()
# count_clientes = df.select("id_cliente").distinct().count()
# sum_valores = df.agg(sum("valor")).collect()[0][0]
```

---

## foreachBatch: Processar Sem collect()

```python
# Em vez de collect() em DataFrames grandes
def process_batch(pdf):
    print(f"Batch: {len(pdf)} linhas")
    return pdf

# Processar em microbatch no executor
df_grande.mapInPandas(process_batch, schema=df_grande.schema).write.format("delta").save(...)
```
