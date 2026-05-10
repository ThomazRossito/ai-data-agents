# Cross-Platform Fabric ↔ Databricks — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** ABFSS setup SQL, shortcut bash, Export/Upload Python, Data Factory YAML

---

## 1. ABFSS Compartilhado: Setup

```sql
-- 1. Criar External Location no Databricks
CREATE EXTERNAL LOCATION fabric_shared
  URL = 'abfss://container@storageaccount.dfs.core.windows.net/'
  WITH (CREDENTIAL = 'your-credential-name');

-- 2. Criar Schema apontando para ABFSS
CREATE SCHEMA IF NOT EXISTS main.fabric_imported USING EXTERNAL LOCATION fabric_shared;

-- 3. Registrar tabelas Fabric no Unity Catalog
CREATE EXTERNAL TABLE IF NOT EXISTS main.fabric_imported.vendas_fabric
  USING PARQUET
  LOCATION 'abfss://container@storageaccount.dfs.core.windows.net/fabric/vendas/';

-- 4. Pipeline Bronze lendo ABFSS via Auto Loader
CREATE OR REFRESH STREAMING TABLE bronze_fabric_vendas
CLUSTER BY (data_evento)
AS
SELECT
  *,
  _metadata.file_path AS source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  'abfss://container@storageaccount.dfs.core.windows.net/fabric/vendas/',
  format => 'parquet',
  cloudFiles.inferColumnTypes => 'true'
);
```

---

## 2. OneLake Shortcuts: Criar via API REST

```bash
# 1. Autenticar no Fabric
TOKEN=$(az account get-access-token --query accessToken -o tsv)

# 2. Criar Shortcut no Fabric Lakehouse
curl -X POST \
  "https://api.fabric.microsoft.com/v1/workspaces/{workspace-id}/lakehouses/{lakehouse-id}/shortcuts" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "path": "vendas_databricks",
    "target": {
      "onelakeLocationObjectReference": {
        "itemId": "databricks-lakehouse-id",
        "workspaceId": "databricks-workspace-id",
        "path": "/Tables/vendas"
      }
    }
  }'

# 3. Consumir shortcut como tabela virtual no Databricks
# Não precisa de código adicional — shortcut é registrado automaticamente
```

```sql
-- Databricks lê o shortcut como tabela virtual
SELECT COUNT(*) FROM main.silver.vendas_fabric_shortcut;

-- Criar MV sobre o shortcut (sem copiar dados)
CREATE OR REFRESH MATERIALIZED VIEW gold_summary AS
SELECT
  DATE_TRUNC('month', data_evento) AS mes,
  COUNT(*) AS total_vendas,
  SUM(valor) AS receita
FROM main.silver.vendas_fabric_shortcut
GROUP BY DATE_TRUNC('month', data_evento);
```

---

## 3. Export/Upload via API (Storage Separados)

### Padrão Fabric → Databricks

```python
# Python no Fabric Notebook
from pyspark.sql import SparkSession
import requests

spark = SparkSession.builder.getOrCreate()

# 1. Ler dados no Fabric
df = spark.read.parquet("/Volumes/my_lakehouse/Tables/vendas")

# 2. Exportar para blob temporário
df.write.mode("overwrite").parquet(
    "abfss://export@container.dfs.core.windows.net/vendas_export/"
)

# 3. Notificar Databricks via Jobs API
requests.post(
    "https://{workspace}.azuredatabricks.net/api/2.1/jobs/run-now",
    headers={"Authorization": "Bearer {token}"},
    json={"job_id": 123, "job_parameters": {"source_path": "abfss://export@..."}}
)
```

### Padrão Databricks → Fabric

```python
# Python no Databricks
from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

# 1. Ler Gold do Databricks
df = spark.read.table("main.gold.vendas_summary")

# 2. Gravar em ABFSS acessível pelo Fabric
df.write.mode("overwrite").parquet(
    "abfss://shared@storageaccount.dfs.core.windows.net/databricks_export/"
)
# Fabric consome via shortcut ou ABFSS direto
```

### Data Factory Copy Activity

```yaml
# Azure Data Factory pipeline
activities:
  - name: CopyDatabricksToFabric
    type: Copy
    inputs:
      - referenceName: DatabricksDataset
        type: DatasetReference
    outputs:
      - referenceName: FabricDataset
        type: DatasetReference
    typeProperties:
      source:
        type: AzureDataLakeStoreSource
        recursive: true
      sink:
        type: AzureDataLakeStoreSink
```

---

## 4. Exemplo End-to-End: Fabric Bronze → Databricks Silver

### Fabric (exporta diariamente)

```python
from datetime import datetime
from pyspark.sql.functions import col, current_date, datediff

df_vendas = spark.read.table("fabric_db.vendas")
df_recent = df_vendas.filter(datediff(current_date(), col("data_evento")) <= 7)

df_recent.write \
  .mode("overwrite") \
  .parquet(
    f"abfss://shared@storage.dfs.core.windows.net/fabric_export/{datetime.now().strftime('%Y%m%d')}/"
  )
```

### Databricks (consome via Auto Loader → Silver)

```sql
-- Bronze: ingestão do ABFSS
CREATE OR REFRESH STREAMING TABLE bronze_fabric_vendas
CLUSTER BY (data_evento)
AS
SELECT
  *,
  _metadata.file_path AS source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  'abfss://shared@storage.dfs.core.windows.net/fabric_export/',
  format => 'parquet',
  cloudFiles.inferColumnTypes => 'true'
);

-- Silver: tipagem e validação
CREATE OR REFRESH STREAMING TABLE silver_vendas
CLUSTER BY (id_cliente, data_evento)
AS
SELECT
  CAST(id_venda AS BIGINT),
  CAST(id_cliente AS BIGINT),
  CAST(valor_total AS DECIMAL(18,2)),
  CAST(data_evento AS DATE),
  _ingested_at
FROM stream(bronze_fabric_vendas)
WHERE id_venda IS NOT NULL;
```

---

## Checklist de Configuração

- [ ] Storage account ou OneLake accessível de ambas as plataformas
- [ ] ABFSS paths testados com `dbutils.fs.ls()`
- [ ] Unity Catalog External Location criado
- [ ] Permissões RBAC (Storage Blob Data Contributor) configuradas
- [ ] Auto Loader pipeline validado com dados reais
- [ ] OneLake Shortcuts criados (se estratégia #2)
- [ ] Mapeamento de tipos conferido (STRUCT → flatten, MAP → KV pairs)
- [ ] Data Factory pipeline testada (se estratégia #3)
