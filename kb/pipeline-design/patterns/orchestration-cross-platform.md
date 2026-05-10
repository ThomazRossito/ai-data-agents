# Orquestração Cross-Platform — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** DABs full YAML (multi-environment), Azure Data Factory cross-cloud JSON

---

## DABs: Estrutura Completa Multi-Environment

```yaml
# databricks.yml
bundle:
  name: data-agents-prod
  target: prod

variables:
  environment:
    default: dev
  catalog:
    default: dev_catalog

targets:
  dev:
    variables:
      environment: dev
      catalog: dev_catalog

  staging:
    variables:
      environment: staging
      catalog: staging_catalog

  prod:
    variables:
      environment: prod
      catalog: prod_catalog

resources:
  pipelines:
    bronze_ingestion:
      name: "[${var.environment}] Bronze Ingestion"
      configuration:
        cloudFiles.schemaInferenceMode: "addNewColumns"
      cluster:
        num_workers: 2
        spark_version: "15.4.x"

  jobs:
    gold_build:
      name: "[${var.environment}] Gold Build Pipeline"
      tasks:
        - task_key: build_gold_dim
          pipeline_task:
            pipeline_id: ${resources.pipelines.bronze_ingestion.id}

        - task_key: build_gold_facts
          depends_on:
            - task_key: build_gold_dim
          notebook_task:
            notebook_path: ../src/gold_facts

      schedule:
        quartz_cron_expression: "0 2 * * ?"
        timezone_id: "UTC"
```

### Deploy Workflow (CLI v0.279.0+)

```bash
# 1. Validar antes de implantar
databricks bundle validate

# 2. Ver plano de mudanças (para CI/CD)
databricks bundle plan -o json > plan.json

# 3. Deploy nativo (sem Terraform)
databricks bundle deploy

# 4. Deploy para produção
databricks bundle deploy -t prod

# 5. Executar job
databricks bundle run gold_build

# 6. Destruir recursos
databricks bundle destroy
```

---

## Azure Data Factory: Pipeline Cross-Platform

```json
{
  "name": "CrossPlatformETL",
  "activities": [
    {
      "name": "CopyFromDataLake",
      "type": "Copy",
      "inputs": [
        {
          "referenceName": "AzureBlobSource",
          "type": "DatasetReference"
        }
      ],
      "outputs": [
        {
          "referenceName": "DatabricksDestination",
          "type": "DatasetReference"
        }
      ]
    },
    {
      "name": "RunDatabricksJob",
      "type": "WebActivity",
      "dependsOn": [{ "activity": "CopyFromDataLake" }],
      "typeProperties": {
        "url": "https://databricks.com/api/2.1/jobs/run-now",
        "method": "POST",
        "headers": {
          "Authorization": "Bearer @{linkedService().accessToken}"
        },
        "body": {
          "job_id": 123
        }
      }
    }
  ]
}
```

---

## Cenários por Ferramenta

### Cenário A: Pipeline Databricks puro (Bronze → Silver → Gold)
**Recomendado:** DABs

```yaml
resources:
  pipelines:
    medallion:
      # Todos os 3 layers em 1 pipeline SDP
      transformations: "sql/**"
```

### Cenário B: Múltiplos ambientes (dev → staging → prod)
**Recomendado:** DABs com targets

```bash
databricks bundle deploy -t dev
databricks bundle deploy -t staging
databricks bundle deploy -t prod
```

### Cenário C: Cross-platform multi-cloud (Azure + AWS + GCP)
**Recomendado:** Azure Data Factory

- Copy activities em massa
- Integração com Power BI / Synapse
- Orquestração com ADF triggers (Event Grid, Blob storage)

### Cenário D: Fabric → Databricks → Fabric (round-trip)
**Recomendado:** Data Factory + OneLake Shortcuts

1. Fabric exporta dados para ABFSS
2. Data Factory orquestra a movimentação
3. Databricks processa via Auto Loader
4. Databricks escreve em ABFSS
5. Fabric consome via shortcut

---

## Checklist de Seleção

### Use DABs se:
- [ ] Versionar em Git é obrigatório
- [ ] Multi-ambiente (dev, staging, prod) é necessário
- [ ] Deploy via CLI + CI/CD (GitHub Actions, etc)
- [ ] Pipeline é principalmente Databricks

### Use Data Factory se:
- [ ] Cross-platform (Databricks + Fabric + Data Lake)
- [ ] Orquestração complexa multi-cloud
- [ ] Integração com Azure Synapse necessária
- [ ] Copy activities em massa dominam o fluxo
