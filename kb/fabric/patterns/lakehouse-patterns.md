# Lakehouse Fabric — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** Spark escrita, V-Order, enable_schemas, REST API, ABFSS

---

## Criar Lakehouse via REST API

```http
POST /workspaces/{id}/lakehouses
Content-Type: application/json

{
  "displayName": "SalesLakehouse",
  "description": "Lakehouse for sales analytics",
  "creationPayload": {
    "enableSchemas": true
  }
}
```

---

## Escrita Bronze (Sem V-Order)

```python
spark.write.format("delta").mode("overwrite") \
  .option("path", "abfss://workspace@onelake.dfs.fabric.microsoft.com/lh.Lakehouse/Bronze/CRM/Customer/") \
  .saveAsTable("bronze_customer")
```

## Escrita Silver com MERGE (SCD Type 2)

```python
from delta.tables import DeltaTable

df_source = spark.read.table("bronze_customer") \
    .filter("customer_id IS NOT NULL") \
    .dropDuplicates(["customer_id"])

delta_table = DeltaTable.forName(spark, "customer_silver")

delta_table.alias("t").merge(
    df_source.alias("s"),
    "t.customer_id = s.customer_id"
).whenMatchedUpdate(set={
    "name": "s.name",
    "updated_at": "s.updated_at"
}).whenNotMatchedInsertAll().execute()
```

## Escrita Gold com V-Order (Obrigatório para Direct Lake)

```python
df.write.format("delta") \
  .option("delta.enableVOrderedWrite", "true") \
  .mode("overwrite") \
  .option("path", "abfss://.../Gold/Sales/dim_customer/") \
  .saveAsTable("dim_customer_gold")
```

---

## Verificar V-Order Aplicado

```python
spark.sql("SELECT * FROM delta.`path`").explain()
# Procure "vorder=true" no output
```

---

## REST API: Lakehouses

```http
# Listar lakehouses
GET /workspaces/{workspace-id}/lakehouses

# Obter detalhes
GET /workspaces/{workspace-id}/lakehouses/{lakehouse-id}

# Atualizar
PATCH /workspaces/{workspace-id}/lakehouses/{lakehouse-id}
{
  "displayName": "UpdatedLakehouse"
}
```

---

## Python: Criar Lakehouse via SDK

```python
from pyfabricops import FabricClient

client = FabricClient()
lakehouse = client.create_lakehouse(
    workspace='Analytics',
    display_name='MainLakehouse',
    enable_schemas=True
)
```

---

## ABFSS Path Format

```python
# Padrão
path = "abfss://{workspace}@onelake.dfs.fabric.microsoft.com/{lakehouse}.Lakehouse/Tables/{table}"

# Exemplo
path = "abfss://MyWorkspace@onelake.dfs.fabric.microsoft.com/SalesLakehouse.Lakehouse/Tables/fact_sales"
```
