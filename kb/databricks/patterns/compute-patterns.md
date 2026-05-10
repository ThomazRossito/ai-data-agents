# Compute — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** Databricks Connect, Job Clusters, Interactive Clusters, Serverless

---

## Databricks Connect Setup

```bash
# Requer Python 3.12
python3.12 --version

pip install databricks-connect==16.4.0

databricks configure --token --profile databricks
```

```python
from pyspark.sql import SparkSession

spark = SparkSession.builder.remote(url="<workspace-url>", token="<token>").build()

df = spark.read.table("main.analytics.users")
df.count()  # Executa no Databricks, retorna resultado
```

---

## Serverless SQL Warehouse

```bash
databricks warehouses create --name "Analytics WH" \
  --cluster_size "2xlarge" \
  --auto_stop_mins 10
```

---

## Job Clusters em DABs

```yaml
resources:
  jobs:
    etl_job:
      tasks:
        - task_key: extract
          job_cluster_key: shared_compute
          notebook_task:
            notebook_path: ../src/extract.py

  job_clusters:
    - job_cluster_key: shared_compute
      new_cluster:
        spark_version: "15.4.x-scala2.12"
        node_type_id: "i3.xlarge"
        num_workers: 2
        spark_conf:
          spark.speculation: "true"
        aws_attributes:
          availability: "SPOT_WITH_FALLBACK"
```

---

## Interactive Clusters: Boas Práticas

```python
# 1. Listar clusters ANTES de iniciar
result = list_compute(resource="clusters")
# Exibir ao usuário: "Qual cluster usar?"

# 2. Executar código, reutilizar context_id
first_result = execute_code(
    code="df = spark.read.table('main.data.users')",
    compute_type="cluster",
    cluster_id="<user-selected-id>"
)

second_result = execute_code(
    code="df.count()",
    context_id=first_result["context_id"],  # Reutilizar state
    cluster_id=first_result["cluster_id"]
)
```

```yaml
# Auto-termination: OBRIGATÓRIO
autotermination_minutes: 20  # Desligar após 20min inativo
```

---

## Serverless Compute em Jobs

```yaml
resources:
  jobs:
    training_job:
      tasks:
        - task_key: train_model
          python_wheel_task:
            package_name: "ml_package"
            entry_point: "train"
            # Sem cluster_key ou new_cluster → serverless automático
```

**Gotcha:** Serverless não mantém state. Use Volume ou Delta table para passar dados entre tasks.
