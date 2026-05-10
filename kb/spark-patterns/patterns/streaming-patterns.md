# Streaming — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** Trigger modes, Auto Loader, Kafka, checkpoints, watermarks, foreachBatch

---

## availableNow: Batch-Like (Recomendado para Pipelines)

```python
from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9092") \
    .option("subscribe", "sales_events") \
    .load()

query = df.writeStream \
    .format("delta") \
    .mode("append") \
    .option("checkpointLocation", "/tmp/ckpt/kafka_sales") \
    .trigger(availableNow=True) \
    .start()

query.awaitTermination()
```

---

## processingTime: Micro-Batch Contínuo

```python
query = df.writeStream \
    .format("delta") \
    .mode("append") \
    .option("checkpointLocation", "/tmp/ckpt/kafka_sales") \
    .trigger(processingTime="10 seconds") \
    .start()
# Não chamar awaitTermination() — query rode indefinidamente
```

---

## Auto Loader (cloudFiles)

```python
df = spark.readStream \
    .format("cloudFiles") \
    .option("cloudFiles.format", "parquet") \
    .option("cloudFiles.schemaLocation", "/tmp/schema_inference") \
    .option("cloudFiles.schemaEvolutionMode", "addNewColumns") \
    .load("s3://bucket/incoming/sales/")

query = df.writeStream \
    .format("delta") \
    .mode("append") \
    .option("checkpointLocation", "/tmp/ckpt/bronze_sales") \
    .trigger(processingTime="5 minutes") \
    .start("/dbfs/user/hive/warehouse/bronze_sales")
```

---

## Kafka: Consumir Tópico

```python
from pyspark.sql.functions import col, from_json

df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka01:9092,kafka02:9092") \
    .option("subscribe", "ecommerce_events") \
    .option("startingOffsets", "latest") \
    .option("maxOffsetsPerTrigger", "100000") \
    .load()

parsed_df = df.select(
    col("timestamp"),
    col("partition"),
    col("offset"),
    from_json(
        col("value").cast("string"),
        "event_id STRING, user_id STRING, amount DECIMAL(10,2), event_time TIMESTAMP"
    ).alias("parsed")
).select("timestamp", "partition", "offset", "parsed.*")

query = parsed_df.writeStream \
    .format("delta") \
    .mode("append") \
    .option("checkpointLocation", "/tmp/ckpt/kafka_ecommerce") \
    .trigger(processingTime="30 seconds") \
    .start("/dbfs/user/hive/warehouse/bronze_ecommerce")
```

---

## Checkpoint: Isolado por Stream

```python
# Cada stream tem seu próprio checkpoint — nunca compartilhar
query_kafka = spark.readStream \
    .format("kafka").load() \
    .writeStream \
    .option("checkpointLocation", "/tmp/ckpt/kafka_stream") \
    .start()

query_files = spark.readStream \
    .format("cloudFiles").load("s3://bucket/") \
    .writeStream \
    .option("checkpointLocation", "/tmp/ckpt/files_stream") \
    .start()
```

---

## Watermark: Dados Atrasados

```python
from pyspark.sql.functions import window, sum, col

df = spark.readStream.format("kafka").load() \
    .withWatermark("event_time", "1 hour")

windowed_agg = df \
    .groupBy(
        window("event_time", "5 minutes", "1 minute"),
        "region"
    ) \
    .agg(sum("amount").alias("total_sales")) \
    .select(
        col("window.start").alias("window_start"),
        col("window.end").alias("window_end"),
        "region",
        "total_sales"
    )

query = windowed_agg.writeStream \
    .format("delta") \
    .mode("append") \
    .option("checkpointLocation", "/tmp/ckpt/sales_windowed") \
    .trigger(processingTime="5 seconds") \
    .start("/dbfs/user/hive/warehouse/gold_sales_5min")
```

---

## Stream-Static Join (Eficiente)

```python
orders_stream = spark.readStream.format("kafka").load()

# Carregar tabela estática (recarregada a cada trigger)
customers_static = spark.read.format("delta") \
    .load("/dbfs/user/hive/warehouse/dim_customers")

joined = orders_stream.join(customers_static, on="customer_id", how="left")
```

---

## foreachBatch: Custom Sink

```python
def process_batch(df, epoch_id):
    if df.count() == 0:
        return

    # Escrever em Delta
    df.write.format("delta").mode("append") \
        .save("/dbfs/user/hive/warehouse/gold_sales")

    # Notificar via webhook
    import requests
    requests.post("https://monitoring.example.com/batch",
                  json={"epoch": epoch_id, "rows": df.count()})

query = df.writeStream \
    .foreachBatch(process_batch) \
    .option("checkpointLocation", "/tmp/ckpt/custom_sink") \
    .trigger(processingTime="10 seconds") \
    .start()
```

---

## dropDuplicates com Watermark

```python
deduped = df \
    .withWatermark("event_time", "1 hour") \
    .dropDuplicates(["event_id", "event_time"])
```
