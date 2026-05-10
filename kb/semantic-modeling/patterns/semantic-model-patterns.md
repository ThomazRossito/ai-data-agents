# Semantic Model — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** DDL das tabelas Gold, relacionamentos, SCD2 filter, hide FKs, TMDL, DAX queries REST

---

## DDL: Fact Table

```sql
CREATE TABLE gold_catalog.sales.fact_vendas (
  -- Surrogate Keys (ocultos no Semantic Model)
  sk_cliente BIGINT,
  sk_produto BIGINT,
  sk_data BIGINT,

  -- Degenerate Dimensions
  numero_nfe STRING,
  numero_pedido STRING,

  -- Measures (valores agregáveis)
  quantidade INT,
  valor_unitario DECIMAL(10, 2),
  valor_bruto DECIMAL(12, 2),
  desconto_reais DECIMAL(10, 2),
  valor_liquido DECIMAL(12, 2),

  -- Controle (ocultos)
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  _is_deleted BOOLEAN
) USING DELTA
CLUSTER BY (sk_data, sk_cliente);
```

---

## DDL: Dimension Tables

```sql
-- dim_cliente com SCD2
CREATE TABLE gold_catalog.sales.dim_cliente (
  sk_cliente BIGINT PRIMARY KEY,
  nk_cliente BIGINT,
  cliente_nome STRING,
  cliente_email STRING,
  cliente_regiao VARCHAR(2),
  cliente_estado VARCHAR(20),
  cliente_segmento VARCHAR(20),
  data_inicio TIMESTAMP,
  data_fim TIMESTAMP,
  is_ativo BOOLEAN,
  versao INT,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
) USING DELTA
CLUSTER BY (sk_cliente);

-- dim_data
CREATE TABLE gold_catalog.shared.dim_data (
  sk_data BIGINT PRIMARY KEY,
  data DATE,
  ano INT,
  trimestre INT,
  mes INT,
  semana INT,
  dia INT,
  nome_mes VARCHAR(20),
  nome_mes_abr VARCHAR(3),
  is_fim_semana BOOLEAN,
  is_feriado BOOLEAN,
  nome_feriado VARCHAR(50),
  is_ativo BOOLEAN
) USING DELTA
CLUSTER BY (sk_data);
```

---

## SCD2: Filtrar Versão Ativa no Semantic Model

```powerquery
// Power Query: filtrar apenas versão ativa
let
  Source = Sql.Database("..."),
  DimCliente = Source{[Item="dim_cliente"]},
  FilteredActive = Table.SelectRows(DimCliente, each [is_ativo] = true)
in
  FilteredActive
```

```dax
// Medida usando SCD2 histórico com USERELATIONSHIP
Total Vendas Historico =
  CALCULATE(
    [Total Sales],
    USERELATIONSHIP(fact_vendas[sk_cliente], dim_cliente_history[sk_cliente])
  )
```

---

## TMDL: Definição do Semantic Model

```json
{
  "compatibility": {
    "compatibilityLevel": 1604
  },
  "model": {
    "tables": [
      {
        "name": "fact_vendas",
        "columns": [
          {
            "name": "valor_liquido",
            "dataType": "decimal",
            "dataCategory": "Measure"
          }
        ]
      }
    ],
    "relationships": [
      {
        "name": "fk_cliente",
        "fromColumn": "fact_vendas[sk_cliente]",
        "toColumn": "dim_cliente[sk_cliente]"
      },
      {
        "name": "fk_data",
        "fromColumn": "fact_vendas[sk_data]",
        "toColumn": "dim_data[sk_data]"
      }
    ]
  }
}
```

### Atualizar Modelo via REST (LRO Pattern)

```http
PATCH /workspaces/{workspace-id}/items/{model-id}/updateDefinition
Content-Type: application/json

{
  "definition": "base64-encoded-model-definition"
}

Response:
{
  "operationId": "123e4567-e89b-12d3-a456-426614174000"
}
```

```http
GET /workspaces/{workspace-id}/operations/{operationId}

{
  "status": "InProgress",
  "resultUri": "/items/{model-id}/getDefinition"
}
```

---

## DAX Query via REST API

```http
POST /groups/{workspace-id}/datasets/{model-id}/executeQueries
Content-Type: application/json

{
  "queries": [
    {
      "query": "EVALUATE SUMMARIZECOLUMNS(dim_cliente[cliente_regiao], 'Total Sales')"
    }
  ]
}
```

---

## Hide FKs no Power BI

No Power BI Desktop:
1. Selecionar coluna `sk_cliente` em fact_vendas
2. Tab "Modeling" → "Hidden" → True
3. Repetir para todas FKs (sk_produto, sk_data)

**Resultado esperado:**
```
fact_vendas (visível ao usuário):
  quantidade
  valor_liquido
  [sk_* colunas ocultas]
```
