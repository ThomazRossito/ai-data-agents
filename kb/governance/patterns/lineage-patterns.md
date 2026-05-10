# Lineage — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** system.lineage SQL, recursive lineage, Fabric community MCP, impact analysis

---

## Lineage Databricks: system.access.table_lineage

```sql
-- Tabelas que alimentam uma tabela (upstream)
SELECT DISTINCT source_table_full_name, source_column_name
FROM system.access.table_lineage
WHERE target_table_full_name = 'main.analytics.users'
  AND event_date >= current_date() - 7;

-- Tabelas que dependem de uma tabela (downstream)
SELECT DISTINCT target_table_full_name
FROM system.access.table_lineage
WHERE source_table_full_name = 'main.silver.vendas'
  AND event_date >= current_date() - 7;
```

---

## Lineage Recursiva Multi-Nível

```sql
WITH RECURSIVE lineage AS (
  SELECT source_table_full_name, target_table_full_name, 1 AS level
  FROM system.access.table_lineage
  WHERE target_table_full_name = 'main.analytics.dashboard_source'
    AND event_date >= current_date() - 7

  UNION ALL

  SELECT tl.source_table_full_name, tl.target_table_full_name, l.level + 1
  FROM system.access.table_lineage tl
  JOIN lineage l ON tl.target_table_full_name = l.source_table_full_name
  WHERE tl.event_date >= current_date() - 7 AND l.level < 5
)
SELECT * FROM lineage ORDER BY level;
```

---

## Impact Analysis: Antes de Modificar Tabela

```sql
-- Impacto de modificar silver_vendas
SELECT
  target_table_full_name AS impacted_table,
  COUNT(DISTINCT source_column_name) AS columns_referenced,
  COUNT(*) AS access_count
FROM system.access.table_lineage
WHERE source_table_full_name = 'main.silver.vendas'
  AND event_date >= current_date() - 30
GROUP BY target_table_full_name
ORDER BY access_count DESC;
```

---

## Fabric Community MCP: Lineage

```python
from mcp import ClientSession

async def get_fabric_lineage(lakehouse_id: str):
    async with ClientSession() as session:
        # Listar dependências
        result = await session.call_tool(
            "mcp__fabric_community__get_lineage",
            arguments={
                "lakehouse_id": lakehouse_id,
                "include_upstream": True,
                "include_downstream": True
            }
        )
        return result

# Impacto em relatórios
async def get_report_dependencies(semantic_model_id: str):
    async with ClientSession() as session:
        result = await session.call_tool(
            "mcp__fabric_community__get_report_dependencies",
            arguments={"model_id": semantic_model_id}
        )
        return result
```

---

## LINEAGE.md Template

```markdown
# Lineage: etl_vendas_gold

## Source Tables
- `catalog.silver.vendas` — vendas transformadas
- `catalog.silver.clientes` — dimensão clientes
- `catalog.silver.produtos` — dimensão produtos

## Transformations
1. Filtrar vendas com status != CANCELADO
2. Join: vendas + clientes (sk_cliente)
3. Join: vendas + produtos (sk_produto)
4. Calcular valor_liquido = valor_bruto * (1 - desconto)

## Target Tables
- `catalog.gold.fact_vendas` — fatos de venda

## Owner: data-eng@empresa.com.br
## SLA: Atualizado diariamente às 03:00 UTC
## Impact: Dashboard Sales Overview, Semantic Model Sales Analytics
```
