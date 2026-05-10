# Metric Views — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** CREATE METRIC VIEW, COMMENT, CLUSTER BY, Genie, AI/BI, permissões UC

---

## CREATE METRIC VIEW: Sintaxe Básica

```sql
-- Métrica sobre tabela Gold
CREATE METRIC VIEW gold_catalog.sales.metrics_vendas
CLUSTER BY (data, regiao)
AS
SELECT
  data,
  regiao,
  SUM(valor) AS total_vendas
    COMMENT 'Soma das vendas em reais (R$) | Unit: BRL | Frequency: Daily',
  COUNT(*) AS num_transacoes
    COMMENT 'Contagem de transações | Unit: Count | Frequency: Daily',
  AVG(valor) AS venda_media
    COMMENT 'Valor médio por venda em reais (R$) | Unit: BRL | Frequency: Daily'
FROM gold_catalog.sales.fact_vendas
GROUP BY data, regiao
COMMENT 'Métricas de vendas diárias por região | Owner: Sales Analytics | Refresh: Daily 01:00 UTC';
```

---

## Métrica KPI (Fonte Única de Verdade)

```sql
CREATE METRIC VIEW gold_catalog.sales.metrics_kpi AS
SELECT
  DATE(data_venda) AS data,
  SUM(valor_liquido) AS revenue
    COMMENT 'Total receita | Unit: USD | Frequency: Real-time',
  COUNT(DISTINCT id_cliente) AS unique_customers
    COMMENT 'Clientes únicos | Unit: Count',
  DIVIDE(SUM(valor_liquido), COUNT(DISTINCT id_cliente), 0) AS arpu
    COMMENT 'Average Revenue Per User | Unit: USD'
FROM gold_catalog.sales.fact_vendas
GROUP BY DATE(data_venda);
```

---

## Métrica Multi-Dimensional

```sql
CREATE METRIC VIEW gold_catalog.sales.metrics_customer_analysis AS
SELECT
  c.segmento,
  c.regiao,
  p.categoria,
  DATE(f.data_venda) AS data,

  SUM(f.valor_liquido) AS total_vendas,
  AVG(f.valor_liquido) AS avg_sale_value,
  COUNT(f.id_fato) AS transaction_count,
  COUNT(DISTINCT f.id_cliente) AS unique_customers

FROM gold_catalog.sales.fact_vendas f
INNER JOIN gold_catalog.sales.dim_cliente c ON f.sk_cliente = c.sk_cliente
INNER JOIN gold_catalog.sales.dim_produto p ON f.sk_produto = p.sk_produto
GROUP BY c.segmento, c.regiao, p.categoria, DATE(f.data_venda);
```

---

## Exemplo Completo: E-Commerce

```sql
CREATE METRIC VIEW gold_catalog.ecommerce.metrics_orders
OWNER = GROUP 'ecom-analysts'
CLUSTER BY (order_date, product_category)
AS
SELECT
  DATE(o.order_date) AS order_date,
  p.category AS product_category,
  c.segmento AS customer_segment,

  COUNT(DISTINCT o.order_id) AS total_orders
    COMMENT 'Number of orders | Unit: Count | Frequency: Real-time',
  SUM(o.order_value) AS total_revenue
    COMMENT 'Sum of order values in USD | Unit: USD | Frequency: Real-time',
  AVG(o.order_value) AS avg_order_value
    COMMENT 'Average order value in USD | Unit: USD',
  COUNT(DISTINCT o.customer_id) AS unique_customers
    COMMENT 'Unique customers | Unit: Count',
  SUM(CASE WHEN o.status = 'completed' THEN o.order_value ELSE 0 END) AS completed_revenue
    COMMENT 'Revenue from completed orders | Unit: USD'

FROM gold_catalog.ecommerce.fact_orders o
INNER JOIN gold_catalog.ecommerce.dim_product p ON o.product_id = p.product_id
INNER JOIN gold_catalog.ecommerce.dim_customer c ON o.customer_id = c.customer_id

GROUP BY DATE(o.order_date), p.category, c.segmento

COMMENT 'E-commerce order metrics | Owner: Ecommerce Analytics | Refresh: Every 1 hour | SLA: 99.9%';
```

---

## Permissões Unity Catalog

```sql
-- Dar acesso de leitura a grupo
GRANT SELECT ON METRIC VIEW gold_catalog.sales.metrics_vendas
  TO GROUP 'analysts@empresa.com.br';

-- Só data owners podem modificar
GRANT MODIFY ON METRIC VIEW gold_catalog.sales.metrics_vendas
  TO GROUP 'data-owners@empresa.com.br';
```

---

## Classificação via TBLPROPERTIES

```sql
CREATE METRIC VIEW gold_catalog.sales.metrics_vendas
AS SELECT ...
TBLPROPERTIES (
  'classification' = 'Confidencial',
  'owner' = 'sales-analytics@empresa.com.br',
  'sla_refresh' = '01:00 UTC',
  'lineage_source' = 'fact_vendas, dim_cliente, dim_produto'
);
```

---

## Pre-Aggregated (Performance)

```sql
-- Criar MATERIALIZED VIEW pré-agregada
CREATE MATERIALIZED VIEW gold_catalog.sales.metrics_agg AS
SELECT
  DATE(data_venda) AS data,
  regiao,
  SUM(valor) AS total_vendas,
  COUNT(*) AS num_transacoes
FROM gold_catalog.sales.fact_vendas
GROUP BY DATE(data_venda), regiao;

-- Metric View sobre o pré-agregado (mais rápido)
CREATE METRIC VIEW metrics_fast AS
SELECT * FROM gold_catalog.sales.metrics_agg;
```
