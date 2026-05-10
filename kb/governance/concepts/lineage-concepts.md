# Lineage — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** Lineage types, impact analysis, documentation standards

---

## Tipos de Lineage

| Tipo | Granularidade | Exemplo |
|------|---------------|---------|
| **Table Lineage** | Tabela → Tabela | silver_vendas → gold_fact_vendas |
| **Column Lineage** | Coluna → Coluna | valor_bruto → valor_liquido |
| **Job Lineage** | Notebook → Tabela | etl_pipeline → bronze_raw |
| **Cross-Platform** | Databricks → Fabric | UC table → Fabric Lakehouse |

---

## Fontes de Lineage por Plataforma

| Plataforma | Fonte | Latência |
|------------|-------|---------|
| **Databricks** | `system.access.table_lineage` | ~15 min |
| **Fabric** | Fabric Community MCP tools | Real-time |
| **Manual** | LINEAGE.md em cada pipeline | Estático |

---

## LINEAGE.md Template

Cada pipeline deve ter um arquivo `LINEAGE.md`:

```
# Lineage: [pipeline_name]

## Source Tables
- `catalog.schema.table_a` — dados brutos de CRM
- `catalog.schema.table_b` — dados de produto

## Transformations
1. Limpeza: remover nulls em id_cliente
2. Join: vendas + clientes
3. Agregação: por data_venda

## Target Tables
- `catalog.gold.fact_vendas` — fatos de venda

## Owner: [team@company.com]
## SLA: Atualizado diariamente às 03:00 UTC
## Impact: Alimenta dashboard Sales Overview
```

---

## Impact Analysis: O Que Muda se Tabela X Mudar?

Antes de modificar qualquer tabela, verificar:
1. Quais tabelas **downstream** dependem dela (via lineage)
2. Quais **dashboards** ou **semantic models** consultam ela
3. Quais **jobs** escrevem nela

---

## Regra: Documentar Antes de Dropar

Antes de `DROP TABLE` ou `ALTER TABLE`, executar impact analysis e notificar owners das tabelas downstream.
