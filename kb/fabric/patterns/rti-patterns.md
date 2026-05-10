# RTI Eventhouse — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** KQL syntax, Eventstream REST, Activator config, retention, kusto_ingest

---

## KQL: Queries Padrão

```kusto
// Agregação por evento e janela de tempo
user_events
| where timestamp > ago(1h)
| summarize count() by event_type, bin(timestamp, 5m)
| order by timestamp desc

// JOIN pipeline
user_events
| join kind=left (
    user_master on user_id
) on user_id
| project timestamp, event_type, user_name

// Métricas por hora
user_events
| summarize
    total_events=count(),
    unique_users=dcount(user_id),
    avg_value=avg(value)
    by bin(timestamp, 1h)
```

---

## Criar Tabela Eventhouse

```json
POST /workspaces/{id}/eventhouse/{eventhouse-id}/tables
{
  "tableName": "user_events",
  "schema": [
    {"columnName": "timestamp", "columnType": "datetime"},
    {"columnName": "user_id", "columnType": "string"},
    {"columnName": "event_type", "columnType": "string"},
    {"columnName": "value", "columnType": "real"}
  ]
}
```

---

## Eventstream: Event Hub → Eventhouse

```http
POST /workspaces/{workspace-id}/eventstreams
{
  "displayName": "user-events-stream",
  "type": "EventStream",
  "sources": [
    {
      "type": "EventHub",
      "connectionId": "{connection-id}",
      "eventHubName": "user-events",
      "consumerGroup": "$Default"
    }
  ],
  "destinations": [
    {
      "type": "Eventhouse",
      "eventhouseId": "{eventhouse-id}",
      "tableName": "user_events",
      "mappingType": "Json"
    }
  ]
}
```

---

## Activator: Configurar Trigger

```http
POST /workspaces/{workspace-id}/activator/{activator-id}/triggers
{
  "displayName": "High Error Rate Alert",
  "query": "KQL: user_events | where event_type == 'error' | count",
  "condition": "count > 100",
  "timeWindow": "5m",
  "action": {
    "type": "Email",
    "recipients": ["ops@company.com"],
    "subject": "Error spike detected",
    "body": "Count: {result}"
  }
}
```

---

## Retention Policies

```kusto
// 30 dias hot data, 365 dias total
.alter-merge table user_events policy retention
  softdelete = 30d, recoverability = 365d

// Hot window para tiering
.alter table user_events policy hot_window
  effective_hot_window = 30d
```

---

## Materialized Views

```kusto
// Criar MV com agregação por hora
.create materialized-view hourly_stats
  on table user_events
{
  user_events
  | summarize
      event_count=count(),
      unique_users=dcount(user_id),
      avg_value=avg(value)
      by bin(timestamp, 1h), event_type
}

// Query MV (instantâneo)
hourly_stats
| where timestamp > ago(24h)
| order by timestamp desc
```

---

## kusto_ingest Python

```python
from kusto_client import KustoConnectionStringBuilder, KustoIngestClient
from kusto_client.ingest import IngestionProperties, BlobDescriptor

kcsb = KustoConnectionStringBuilder.with_aad_application_key_authentication(
    kusto_cluster="https://{cluster}.kusto.windows.net",
    aad_app_id="{app_id}",
    app_key="{app_key}",
    authority_id="{tenant_id}"
)

client = KustoIngestClient(kcsb)

ingestion_props = IngestionProperties(
    database="{database}",
    table="{table_name}",
    format=DataFormat.CSV,
    ingestion_mapping_reference="csv_mapping"
)

blob_descriptor = BlobDescriptor(blob_path, size=blob_size)
client.ingest_from_blob(blob_descriptor, ingestion_props)
```

---

## .show Commands (Troubleshooting)

```kusto
// Verificar falhas de ingestion
.show ingestion failures
| where table == "user_events"
| order by FailedOn desc
| limit 10

// Tamanho de tabela
.show table user_events extents
| summarize TotalSize = sum(ExtentSize)

// Listar tabelas
.show tables

// Schema
.show table user_events columns
```
