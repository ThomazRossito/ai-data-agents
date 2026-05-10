# Jobs & Workflows — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** DAG YAML, retry policy, scheduling, idempotência, parâmetros

---

## DAG Multi-Task Básico

```yaml
resources:
  jobs:
    etl_pipeline:
      name: "ETL Pipeline — ${bundle.target}"
      tasks:
        - task_key: extract
          notebook_task:
            notebook_path: ../src/extract.py

        - task_key: transform
          depends_on:
            - task_key: extract
          notebook_task:
            notebook_path: ../src/transform.py

        - task_key: load
          depends_on:
            - task_key: transform
          run_if: ALL_SUCCESS
          notebook_task:
            notebook_path: ../src/load.py
```

---

## Retry Policy

```yaml
tasks:
  - task_key: extract
    max_retries: 2
    retry_on_timeout: true
    timeout_seconds: 3600  # 1 hora
    notebook_task:
      notebook_path: ../src/extract.py
```

**Backoff automático:**
- Tentativa 1: falha imediata
- Tentativa 2: espera ~30s
- Tentativa 3: espera ~1min

---

## Tratamento de Falha com run_if

```yaml
tasks:
  - task_key: extract
    notebook_task:
      notebook_path: ../src/extract.py

  - task_key: retry_extract
    depends_on:
      - task_key: extract
    run_if: AT_LEAST_ONE_FAILED
    notebook_task:
      notebook_path: ../src/extract_fallback.py

  - task_key: transform
    depends_on:
      - task_key: retry_extract
    run_if: AT_LEAST_ONE_SUCCESS
    notebook_task:
      notebook_path: ../src/transform.py
```

---

## Scheduling

```yaml
# Cron (Quartz)
schedule:
  quartz_cron_expression: "0 9 * * ?"  # 9 AM diariamente
  timezone_id: "America/Los_Angeles"

# File Arrival
trigger:
  file_arrival:
    min_time_between_triggers_seconds: 3600
    url: "s3://my-bucket/incoming/data/"

# Table Update (requer Unity Catalog)
trigger:
  table_update:
    table_names:
      - "main.raw.incoming_data"
    min_time_between_triggers_seconds: 600
```

---

## Idempotência + Run Manual

```python
from databricks.sdk import WorkspaceClient
import uuid

w = WorkspaceClient()

token = f"etl-run-{date.today()}"  # Ou UUID único

run = w.jobs.run_now(
    job_id=12345,
    idempotency_token=token  # Mesma token = mesma run
)
```

---

## Parâmetros Dinâmicos

```yaml
parameters:
  - name: env
    default: "dev"
  - name: date
    default: "{{start_date}}"

tasks:
  - task_key: extract
    notebook_task:
      notebook_path: ../src/extract.py
      base_parameters:
        env: "{{job.parameters.env}}"
        run_date: "{{job.parameters.date}}"
```

```python
# No notebook
env = dbutils.widgets.get("env")
date = dbutils.widgets.get("run_date")
```

---

## Notificações

```yaml
on_failure:
  email_notifications:
    on_failure:
      - "data-team@company.com"

on_success:
  email_notifications:
    on_success:
      - "data-lead@company.com"
```

---

## Python Wheel Task

```yaml
tasks:
  - task_key: ml_train
    python_wheel_task:
      package_name: "ml_package"
      entry_point: "train"
      parameters: ["--epochs", "50"]
```
