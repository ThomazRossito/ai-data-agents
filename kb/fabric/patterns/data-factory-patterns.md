# Data Factory Fabric — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.
> Para padrões de orquestração cross-platform, veja kb/pipeline-design/patterns/orchestration-fabric.md.

**Domínio:** Pipeline CRUD REST, Copy Activity, Dataflow Gen2, scheduling

---

## Criar Pipeline via REST API

```http
POST /workspaces/{workspace-id}/dataPipelines
Content-Type: application/json

{
  "displayName": "DailyETL",
  "description": "Daily ingestion from CRM to Gold",
  "definition": {
    "activities": [
      {
        "name": "CopyCRM",
        "type": "Copy",
        "typeProperties": {
          "source": {
            "type": "SqlServerSource",
            "query": "SELECT * FROM Customer WHERE updated_at > @lastRunTime"
          },
          "sink": {
            "type": "LakehouseTableSink",
            "lakehouseId": "{lakehouse-id}",
            "tableName": "customer_bronze"
          }
        },
        "retryPolicy": {
          "count": 3,
          "intervalInSeconds": 30
        }
      }
    ]
  }
}
```

## Listar / Obter / Atualizar / Deletar

```http
GET    /workspaces/{workspace-id}/dataPipelines
GET    /workspaces/{workspace-id}/dataPipelines/{pipeline-id}/getDefinition
PATCH  /workspaces/{workspace-id}/dataPipelines/{pipeline-id}/updateDefinition
DELETE /workspaces/{workspace-id}/dataPipelines/{pipeline-id}
```

---

## Copy Activity: SQL Source + Lakehouse Sink

```json
{
  "source": {
    "type": "SqlServerSource",
    "sqlReaderQuery": "SELECT * FROM Sales WHERE date >= @{pipeline().parameters.startDate}",
    "queryTimeout": 300
  },
  "sink": {
    "type": "LakehouseTableSink",
    "lakehouseId": "abc-123",
    "tableProperties": {
      "name": "sales_bronze",
      "mode": "overwrite"
    }
  },
  "retryPolicy": {
    "count": 3,
    "intervalInSeconds": 30,
    "type": "ExponentialBackoff"
  },
  "continueOnError": true,
  "errorPolicy": {
    "type": "SkipFailedRows",
    "failurePercentage": 5
  }
}
```

---

## Dataflow Gen2 (Spark-based)

```python
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, to_timestamp

spark = SparkSession.builder.appName("DailyTransform").getOrCreate()

df_raw = spark.read.table("customer_bronze")

df_clean = df_raw \
  .filter(col("customer_id").isNotNull()) \
  .withColumn("updated_at", to_timestamp("updated_at", "yyyy-MM-dd")) \
  .dropDuplicates(["customer_id"])

df_clean.write.format("delta").mode("overwrite") \
  .option("path", "abfss://.../Silver/CRM/customer/") \
  .saveAsTable("customer_silver")
```

---

## Scheduling (Recorrência JSON)

```json
{
  "trigger": {
    "type": "ScheduleTrigger",
    "typeProperties": {
      "recurrence": {
        "frequency": "Day",
        "interval": 1,
        "startTime": "2026-01-01T02:00:00Z",
        "timeZone": "UTC"
      }
    }
  }
}
```

---

## Monitoramento de Runs

```python
import requests

def get_pipeline_runs(workspace_id, pipeline_id, token):
    url = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/dataPipelines/{pipeline_id}/runs"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    return response.json()
```

---

## Parameterização

```json
{
  "parameters": {
    "startDate": {
      "type": "string",
      "defaultValue": "@formatDateTime(utcNow(), 'yyyy-MM-dd')"
    },
    "environment": {
      "type": "string",
      "defaultValue": "dev"
    }
  }
}
```
