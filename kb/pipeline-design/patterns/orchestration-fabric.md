# Orquestração Fabric Data Pipelines — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** Fabric Data Pipelines JSON, chamar Databricks a partir do Fabric, monitoramento

> Para padrões de Copy Activities e Data Factory, veja kb/fabric/patterns/data-factory-patterns.md.
> Para orquestração cross-platform (Data Factory + DABs), veja orchestration-cross-platform.md.

---

## Estrutura de Pipeline Fabric (JSON)

```json
{
  "name": "gold_pipeline_fabric",
  "activities": [
    {
      "name": "CheckSourceData",
      "type": "Lookup",
      "typeProperties": {
        "source": {
          "type": "QueryActivity",
          "query": "SELECT COUNT(*) as cnt FROM silver_vendas"
        }
      }
    },
    {
      "name": "TransformGold",
      "type": "ExecuteNotebook",
      "dependsOn": [{ "activity": "CheckSourceData" }],
      "typeProperties": {
        "notebook": "/gold_vendas",
        "workspace": "my-workspace"
      }
    },
    {
      "name": "NotifySuccess",
      "type": "WebActivity",
      "dependsOn": [{ "activity": "TransformGold" }],
      "typeProperties": {
        "url": "https://prod-XX.logic.azure.com:443/triggers/webhook/...",
        "method": "POST",
        "body": {
          "status": "SUCCESS",
          "timestamp": "@utcnow()"
        }
      }
    }
  ],
  "schedules": [
    {
      "frequency": "Day",
      "interval": 1,
      "startTime": "2026-01-01T02:00:00Z"
    }
  ]
}
```

---

## Chamar Databricks Job via Fabric Pipeline

```json
{
  "name": "TriggerDatabricksJob",
  "type": "ExecuteActivity",
  "typeProperties": {
    "linkedServiceName": "DatabricksLinkedService",
    "command": {
      "type": "Python",
      "script": "databricks jobs run-now --job-id 123 --wait"
    }
  }
}
```

---

## Monitoramento: Fabric Activity Metrics

```python
from azure.identity import DefaultAzureCredential
from azure.monitor.query import MetricsQueryClient

credential = DefaultAzureCredential()
client = MetricsQueryClient(credential)

# Query métricas de Activity
metrics = client.query_resource(
    resource_id=(
        "/subscriptions/{sub}/resourceGroups/{rg}"
        "/providers/Microsoft.DataFactory/factories/{name}"
    ),
    metric_names=["ActivityRuns", "PipelineRuns"],
    granularity="PT1M"
)
```

---

## Cenário: Fabric → Databricks → Fabric (Round-Trip)

Quando usar Data Pipelines para orquestrar o round-trip:

1. Fabric exporta dados (Notebook Activity)
2. Fabric aciona Databricks Job (WebActivity → Jobs API)
3. Databricks processa via Auto Loader e escreve em ABFSS
4. Fabric lê resultado via Shortcut (zero-copy)

```json
{
  "name": "RoundTripOrchestration",
  "activities": [
    {
      "name": "ExportFromFabric",
      "type": "ExecuteNotebook",
      "typeProperties": { "notebook": "/export_to_abfss" }
    },
    {
      "name": "TriggerDatabricks",
      "type": "WebActivity",
      "dependsOn": [{ "activity": "ExportFromFabric" }],
      "typeProperties": {
        "url": "https://{workspace}.azuredatabricks.net/api/2.1/jobs/run-now",
        "method": "POST",
        "headers": { "Authorization": "Bearer @{linkedService().token}" },
        "body": { "job_id": 123 }
      }
    },
    {
      "name": "WaitForDatabricks",
      "type": "Until",
      "dependsOn": [{ "activity": "TriggerDatabricks" }],
      "typeProperties": {
        "expression": "@equals(activity('CheckDatabricksStatus').output.state, 'SUCCESS')",
        "timeout": "PT2H"
      }
    }
  ]
}
```

---

## Checklist: Usar Fabric Data Pipelines quando

- [ ] Usuários são Fabric-first (menos experiência com YAML/código)
- [ ] Pipeline envolve Fabric + Databricks via REST
- [ ] Copy activities dominam o fluxo
- [ ] Integração com Power BI necessária
- [ ] Orquestração via UI é aceitável
