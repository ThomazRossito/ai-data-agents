# Reporting — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** AI/BI Dashboard queries, Direct Lake connection, Power BI, validação de widgets

---

## Query para Dashboard: Campo Exato por Widget

```sql
-- Bar Chart: campo X deve corresponder exatamente ao encoding
SELECT
  regiao,               -- X-axis: "regiao"
  COUNT(*) AS num_vendas,    -- Y-axis: "num_vendas"
  SUM(valor) AS total_vendas -- Y-axis: "total_vendas"
FROM fact_vendas
GROUP BY regiao;
```

Widget encoding DEVE referenciar exatos: X-axis: `regiao`, Y-axis: `total_vendas`, `num_vendas`.

---

## Query Completa para Dashboard de Vendas

```sql
SELECT
  data_venda,
  regiao,
  categoria_produto,
  SUM(valor_liquido) AS total_vendas,
  SUM(quantidade) AS total_items,
  COUNT(DISTINCT id_cliente) AS unique_customers,
  AVG(valor_liquido) AS avg_sale_value
FROM gold_catalog.sales.fact_vendas f
INNER JOIN gold_catalog.sales.dim_cliente c ON f.sk_cliente = c.sk_cliente
INNER JOIN gold_catalog.sales.dim_produto p ON f.sk_produto = p.sk_produto
WHERE data_venda >= CURRENT_DATE() - 90
GROUP BY data_venda, regiao, categoria_produto
ORDER BY data_venda DESC, regiao;
```

Dashboard structure:
1. KPI row (4 contadores: total_vendas, unique_customers, avg_sale_value, total_items)
2. Trends (2 line charts: total_vendas over time, unique_customers over time)
3. Distribution (bar chart: total_vendas por regiao)
4. Details (pivot table: categoria_produto × regiao)

---

## Direct Lake Connection (Power BI / Fabric)

```powerquery
// Conectar tabela Gold via Direct Lake
let
  Source = Sql.Database("lakehouse-connection"),
  fact_vendas = Source{[Item="fact_vendas"]}
in
  fact_vendas
```

```powerquery
// Filtrar SCD2: apenas versão ativa
let
  Source = Sql.Database("..."),
  DimCliente = Source{[Item="dim_cliente"]},
  FilteredActive = Table.SelectRows(DimCliente, each [is_ativo] = true)
in
  FilteredActive
```

---

## Role-Playing Dimensions (Múltiplas Datas)

```powerquery
// Criar 3 cópias lógicas de dim_data
let
  Source = Sql.Database("..."),
  dim_data = Source{[Item="dim_data"]}
in
  dim_data

// Renomear cada cópia:
// dim_data_venda → relacionar a sk_data_venda
// dim_data_entrega → relacionar a sk_data_entrega
// dim_data_faturamento → relacionar a sk_data_faturamento
```

---

## Verificar Modo Direct Lake vs Import

```
Em Power BI Desktop:
1. Home → Transform data → Query Editor
2. Ver "Connection Mode" no rodapé
3. Direct Lake (verde) = OK
4. Import (azul) = Fallback ocorreu
```

---

## Checklist SQL Validation

- [ ] Query retorna dados sem erros
- [ ] Sem NULL em dimensões (WHERE column IS NOT NULL)
- [ ] Field types compatíveis (numeric Y-axis, category X-axis)
- [ ] Execution time < 5 segundos
- [ ] Dados atualizados

## Checklist Widget Validation

- [ ] Query fields existem com nomes exatos
- [ ] Field types match com encodings
- [ ] Sem valores inesperados
- [ ] Dashboard carrega rápido (8-10 widgets max)
- [ ] Títulos e labels configurados em todos os widgets
