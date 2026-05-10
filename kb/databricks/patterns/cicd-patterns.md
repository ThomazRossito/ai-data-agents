# Bundles (DABs) — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** YAML examples, targets, commands, recursos por tipo

---

## Workflow Padrão

```bash
# 1. Validar sintaxe e referências
databricks bundle validate

# 2. Visualizar mudanças (dry-run)
databricks bundle plan

# 3. Deployar para default target
databricks bundle deploy

# 4. Deployar para target específico
databricks bundle deploy -t prod --auto-approve
```

---

## databricks.yml: Multi-Environment

```yaml
bundle:
  name: my-project

include:
  - resources/*.yml

variables:
  catalog:
    default: dev_catalog
  schema:
    default: dev_schema
  warehouse_id:
    lookup:
      warehouse: "Shared SQL Warehouse"

targets:
  dev:
    default: true
    mode: development
    workspace:
      profile: dev-workspace
    variables:
      catalog: dev_catalog
      schema: dev_schema

  prod:
    mode: production
    workspace:
      profile: prod-workspace
    variables:
      catalog: prod_catalog
      schema: prod_schema
```

---

## Jobs (Exemplo Completo)

```yaml
# resources/jobs.yml
resources:
  jobs:
    etl_pipeline:
      name: "[${bundle.target}] ETL"
      tasks:
        - task_key: extract
          notebook_task:
            notebook_path: ../src/notebooks/extract.py  # ../src/ para resources/
          job_cluster_key: shared_cluster

      job_clusters:
        - job_cluster_key: shared_cluster
          new_cluster:
            spark_version: "15.4.x-scala2.12"
            node_type_id: "i3.xlarge"
            num_workers: 2
            aws_attributes:
              availability: "SPOT_WITH_FALLBACK"

      schedule:
        quartz_cron_expression: "0 9 * * ?"
        timezone_id: "America/Los_Angeles"

      permissions:
        - level: CAN_VIEW
          group_name: "users"
        - level: CAN_MANAGE_RUN
          group_name: "data_engineers"
```

---

## Dashboards

```yaml
# resources/dashboards.yml
resources:
  dashboards:
    analytics:
      display_name: "[${bundle.target}] Analytics"
      file_path: ../src/dashboards/analytics.lvdash.json
      warehouse_id: ${var.warehouse_id}
      dataset_catalog: ${var.catalog}      # CLI >= 0.281.0
      dataset_schema: ${var.schema}
      permissions:
        - level: CAN_RUN
          group_name: "users"
```

---

## Pipelines (SDP)

```yaml
# resources/pipelines.yml
resources:
  pipelines:
    etl:
      name: "[${bundle.target}] SDP ETL"
      target: ${var.catalog}.${var.schema}
      libraries:
        - notebook:
            path: ../src/pipelines/dlt.py
      edition: ADVANCED
```

---

## Apps (Env Vars em app.yaml)

```yaml
# resources/app.yml
resources:
  apps:
    my_app:
      name: my-app-${bundle.target}
      source_code_path: ../src/app
```

```yaml
# src/app/app.yaml  ← Env vars AQUI, não no databricks.yml
command:
  - "python"
  - "dash_app.py"

env:
  - name: DATABRICKS_WAREHOUSE_ID
    value: "your-warehouse-id"
  - name: DATABRICKS_CATALOG
    value: "main"
  - name: DATABRICKS_SCHEMA
    value: "my_schema"
```

```bash
# Deploy e start
databricks bundle deploy
databricks bundle run my_app -t dev  # Obrigatório para iniciar
databricks apps logs my-app-dev --profile DEFAULT  # Ver logs
```

---

## Variables para Multi-Ambiente

```yaml
variables:
  catalog: { default: "dev" }
  schema: { default: "dev" }

resources:
  jobs:
    job:
      name: "[${bundle.target}] Job"
      tasks:
        - notebook_task:
            notebook_path: ../src/etl.py
            base_parameters:
              catalog: ${var.catalog}
              schema: ${var.schema}
```

---

## SQL Alerts (Schema v2)

```yaml
resources:
  sql_alerts:
    data_quality:
      display_name: "Data Quality Check"
      query_id: ${resources.sql_queries.quality_check.id}
      condition:
        op: CUSTOM
        threshold: 1
      notification_config:
        email_notifications:
          - "alerts@company.com"
```
