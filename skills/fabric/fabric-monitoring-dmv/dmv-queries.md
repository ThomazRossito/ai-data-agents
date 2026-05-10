# DMV Queries - Referencia Tecnica

## Connection Strings

### Service Principal (SPN)

```
Data Source=powerbi://api.powerbi.com/v1.0/myorg/{WorkspaceName};
Initial Catalog={SemanticModelName};
User ID=app:{ClientId}@{TenantId};
Password={ClientSecret};
```

Exemplo:
```python
conn_str = "Data Source=powerbi://api.powerbi.com/v1.0/myorg/DataLake;Initial Catalog=FactSales;User ID=app:00000000-0000-0000-0000-000000000001@11111111-1111-1111-1111-111111111111;Password=secret123"
```

### User Credentials

```
Data Source=powerbi://api.powerbi.com/v1.0/myorg/{WorkspaceName};
Initial Catalog={SemanticModelName};
User ID={UserEmail};
Password={UserPassword};
```

---

## Querie DMV Comuns

### 1. Listar Tabelas

```dmx
SELECT
    ID,
    Name,
    Description,
    Type
FROM $SYSTEM.TMSCHEMA_TABLES
ORDER BY Name
```

### 2. Listar Partitions (com tamanho)

```dmx
SELECT
    [ID],
    [TableID],
    [Name],
    [RefreshedTime],
    [ModifiedTime],
    [StorageMode],
    [Type]
FROM $SYSTEM.TMSCHEMA_PARTITIONS
ORDER BY [TableID], [Name]
```

### 3. Listar Measures

```dmx
SELECT
    [ID],
    [TableID],
    [Name],
    [Expression],
    [FormatString]
FROM $SYSTEM.TMSCHEMA_MEASURES
WHERE [TableID] IS NOT NULL
```

### 4. Listar Colunas com Tipos de Dados

```dmx
SELECT
    [TableID],
    [Name] as ColumnName,
    [DataType],
    [IsHidden],
    [ColumnType]
FROM $SYSTEM.TMSCHEMA_COLUMNS
ORDER BY [TableID], [Name]
```

### 5. Tamanho do Modelo (Memoria)

```dmx
SELECT
    [ID],
    [Name],
    [Size]
FROM $SYSTEM.TMSCHEMA_TABLES
ORDER BY [Size] DESC
```

### 6. Refresh History (via Power BI REST API, nao DMV)

```
GET /v1/groups/{workspaceId}/datasets/{modelId}/refreshes
```

---

## DAX Queries (execute_queries)

### 1. Contar Linhas de Tabela

```dax
EVALUATE
    SUMMARIZE(
        FactSales,
        "RowCount", COUNTA(FactSales[OrderID])
    )
```

### 2. Modelo Measures

```dax
EVALUATE
    SUMMARIZECOLUMNS(
        DimProduct[Category],
        "Total Sales", [Total Sales Amount],
        "Avg Price", [Average Price]
    )
```

### 3. Diagnose (Error Detection)

```dax
EVALUATE
    SUMMARIZE(
        FactSales,
        "RowCount", COUNTA(FactSales[OrderID]),
        "Min Date", MIN(FactSales[OrderDate]),
        "Max Date", MAX(FactSales[OrderDate])
    )
```

---

## Power BI REST API Endpoints

### Get Refresh History

**GET /v1/groups/{groupId}/datasets/{datasetId}/refreshes**

Parametros:
- `$top=10` -- Limitar resultados
- `$skip=0` -- Pagination offset

Retorno:
```json
{
  "value": [
    {
      "id": "refresh-uuid",
      "startTime": "2026-04-09T10:00:00Z",
      "endTime": "2026-04-09T10:30:00Z",
      "status": "Completed",
      "duration": "PT30M"
    }
  ]
}
```

### Get Refresh Details

**GET /v1/groups/{groupId}/datasets/{datasetId}/refreshes/{refreshId}**

Retorno:
```json
{
  "id": "refresh-uuid",
  "startTime": "2026-04-09T10:00:00Z",
  "endTime": "2026-04-09T10:30:00Z",
  "status": "Completed",
  "duration": "PT30M",
  "type": "Full"
}
```

### Trigger Refresh

**POST /v1/groups/{groupId}/datasets/{datasetId}/refreshes**

Payload:
```json
{
  "notifyOption": "MailOnCompletion",
  "type": "Full",
  "commitMode": "Transactional",
  "maxParallelism": 5
}
```

---

## Exemplos Python

### Monitorar Partitions

```python
from monitoring_dmv import dmv_fetch_partitions_enriched

partitions = dmv_fetch_partitions_enriched(conn_str)
print(partitions[['TableName', 'Name', 'RefreshedTime']])

# Filtrar partitions antigas (>7 dias)
from datetime import datetime, timedelta
old_date = datetime.now() - timedelta(days=7)
old_partitions = partitions[partitions['RefreshedTime'] < old_date]
print(f"Partitions antigas: {len(old_partitions)}")
```

### Executar DAX Customizado

```python
from monitoring_dmv import evaluate_dmv_queries
from semantic_models import execute_queries

# Via DMV (TMSCHEMA)
tables = evaluate_dmv_queries(conn_str, """
    SELECT Name, Size FROM $SYSTEM.TMSCHEMA_TABLES
""")

# Via DAX
sales = execute_queries(
    workspace="analytics",
    semantic_model="FactSales",
    query="""
        EVALUATE
        SUMMARIZECOLUMNS(
            DimDate[Year],
            "Total", [Total Sales]
        )
    """
)
```

### Monitorar Refreshes

```python
from monitoring_dmv import get_semantic_model_refreshes
from datetime import datetime, timedelta

refreshes = get_semantic_model_refreshes(
    workspace="analytics",
    semantic_model="FactSales",
    top=10
)

for r in refreshes:
    start = datetime.fromisoformat(r['startTime'])
    end = datetime.fromisoformat(r['endTime'])
    duration = (end - start).total_seconds()
    print(f"{start.date()} | {r['status']} | {duration}s")

# Verificar ultimas 24 horas
today = datetime.now().date()
recent = [r for r in refreshes
          if datetime.fromisoformat(r['startTime']).date() == today]
print(f"Refreshes hoje: {len(recent)}")
```

---

## Structured Monitoring Dashboard (Python)

```python
from monitoring_dmv import *
import pandas as pd

def monitor_model(workspace, model_name):
    # 1. Conexao
    conn_str = set_dmv_connection_string_spn(
        client_id="...", client_secret="...", tenant_id="...",
        workspace_name=workspace, semantic_model_name=model_name
    )

    # 2. Partitions
    partitions = dmv_fetch_partitions_enriched(conn_str)
    print(f"Total partitions: {len(partitions)}")
    print(partitions.groupby('TableName').size())

    # 3. Refreshes
    refreshes = get_semantic_model_refreshes(workspace, model_name, top=5)
    for r in refreshes:
        print(f"Refresh: {r['startTime']} | {r['status']}")

    # 4. Health
    health = {
        "partitions": len(partitions),
        "last_refresh": refreshes[0]['endTime'] if refreshes else None,
        "status": "OK" if refreshes[0]['status'] == "Completed" else "FAILED"
    }

    return health

# Usar
health = monitor_model("DataLake", "FactSales")
print(health)
```
