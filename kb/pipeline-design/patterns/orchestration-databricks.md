# Orquestração Databricks Jobs — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** Databricks Jobs DAG YAML, run_if conditions, monitoramento via SDK

---

## Multi-Task DAG (DABs YAML)

```yaml
# resources/jobs.yml
resources:
  jobs:
    gold_pipeline:
      name: "Gold Pipeline - Vendas"
      description: "Orquestra Bronze → Silver → Gold"

      job_clusters:
        - job_cluster_key: shared_compute
          new_cluster:
            spark_version: "15.4.x-scala2.12"
            node_type_id: "i3.xlarge"
            num_workers: 2
            spark_conf:
              spark.speculation: "true"

      tasks:
        # Task 1: Validação de dados na Silver
        - task_key: validate_silver
          sql_task:
            alert:
              alert_id: "alert-silver-quality"
              pause_subscriptions: false
            warehouse_id: "abc123"

        # Task 2: Construir Gold (depende de validação)
        - task_key: build_gold
          depends_on:
            - task_key: validate_silver
          run_if: "ALL_SUCCESS"
          notebook_task:
            notebook_path: "../src/gold_build"
            base_parameters:
              catalog: "prod"
              schema: "gold"
          job_cluster_key: shared_compute

        # Task 3: Data quality (depois do Gold)
        - task_key: quality_check
          depends_on:
            - task_key: build_gold
          run_if: "ALL_SUCCESS"
          sql_task:
            warehouse_id: "abc123"
            sql_file: "../queries/gold_quality.sql"

        # Task 4: Notificação (executa sempre, sucesso ou falha)
        - task_key: notify
          depends_on:
            - task_key: quality_check
          run_if: "ALL_DONE"
          notebook_task:
            notebook_path: "../src/notify"

      schedule:
        quartz_cron_expression: "0 2 * * ?"  # 2AM UTC
        timezone_id: "UTC"
        pause_status: "UNPAUSED"

      notification_settings:
        no_alert_for_skipped_runs: false
        no_alert_for_successful_runs: false
        alert_on_failure:
          - email_address: "data-team@company.com"
```

---

## run_if Conditions

```yaml
tasks:
  - task_key: extract
    # ... task definition

  - task_key: transform
    depends_on:
      - task_key: extract
    run_if: "ALL_SUCCESS"  # Executa apenas se extract sucedeu

  - task_key: load
    depends_on:
      - task_key: transform
    run_if: "AT_LEAST_ONE_SUCCESS"  # Executa se pelo menos 1 dep sucedeu

  - task_key: cleanup
    depends_on:
      - task_key: load
    run_if: "ALL_DONE"  # Executa sempre (sucesso ou falha)
```

---

## SQL Alert Task (Quality Gate)

```yaml
# Integração com SQL Alerts como gate no pipeline
tasks:
  - task_key: data_quality_check
    sql_task:
      alert:
        alert_id: "<uuid>"
  - task_key: downstream_task
    depends_on:
      - task_key: data_quality_check
    run_if: "ALL_SUCCESS"
```

---

## Monitoramento via Python SDK

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Listar jobs
for job in w.jobs.list(name_contains="Gold Pipeline"):
    print(f"Job ID: {job.job_id}, Name: {job.job_name}")

# Última execução
runs = w.jobs.list_runs(job_id=123, limit=1)
for run in runs:
    print(f"Run ID: {run.run_id}")
    print(f"State: {run.state}")
    print(f"Start time: {run.start_time}")
    print(f"End time: {run.end_time}")

    for task_run in run.tasks:
        print(f"  Task: {task_run.task_key}, State: {task_run.state}")
```

---

## System Tables: Auditoria de Execuções

```sql
-- Ver execuções de job
SELECT
  job_id,
  run_id,
  state,
  start_time,
  end_time,
  duration_ms
FROM system.jobs.job_run
WHERE job_id = 123
ORDER BY end_time DESC
LIMIT 10;

-- Ver eventos de acesso
SELECT
  timestamp,
  user_name,
  action,
  object_id
FROM system.access.audit
WHERE object_type = 'job'
ORDER BY timestamp DESC;
```

---

## Checklist: Usar Databricks Jobs quando

- [ ] Pipeline é 100% Databricks
- [ ] Precisa de Unity Catalog + governança nativa
- [ ] Multi-task DAG com dependências complexas
- [ ] Monitoramento nativo via System Tables
- [ ] Integração com SQL Alerts como quality gates
