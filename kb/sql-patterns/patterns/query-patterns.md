# Query Optimization — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** CTE patterns, predicate pushdown, EXPLAIN, semi-joins, aggregate pushdown, TABLESAMPLE

---

## CTE: Queries Complexas

```sql
WITH vendas_filtradas AS (
  SELECT
    id_venda,
    id_cliente,
    valor
  FROM gold_catalog.sales.fact_vendas
  WHERE data_venda >= CURRENT_DATE() - 30
    AND valor > 100
),
clientes_premium AS (
  SELECT DISTINCT id_cliente
  FROM vendas_filtradas
  GROUP BY id_cliente
  HAVING COUNT(*) > 5
)
SELECT
  c.sk_cliente,
  c.cliente_nome,
  COUNT(v.id_venda) AS num_vendas,
  SUM(v.valor) AS valor_total
FROM gold_catalog.sales.dim_cliente c
INNER JOIN clientes_premium cp ON c.nk_cliente = cp.id_cliente
LEFT JOIN vendas_filtradas v ON c.nk_cliente = v.id_cliente
GROUP BY c.sk_cliente, c.cliente_nome
ORDER BY valor_total DESC;
```

---

## Predicate Pushdown: Filtrar Antes de Join

```sql
-- Correto: filtrar antes do JOIN
WITH fact_recente AS (
  SELECT sk_cliente, sk_produto, valor
  FROM fact_vendas
  WHERE data_venda >= CURRENT_DATE() - 7  -- Reduz 1GB → 50MB
),
cliente_sp AS (
  SELECT sk_cliente, nome
  FROM dim_cliente
  WHERE regiao = 'SP'
),
produto_eletro AS (
  SELECT sk_produto, descricao
  FROM dim_produto
  WHERE categoria = 'Eletrônicos'
)
SELECT f.valor, c.nome, p.descricao
FROM fact_recente f
INNER JOIN cliente_sp c ON f.sk_cliente = c.sk_cliente
INNER JOIN produto_eletro p ON f.sk_produto = p.sk_produto;
```

---

## SELECT: Listar Colunas Explicitamente

```sql
-- Correto: apenas colunas necessárias
SELECT
  id_fato,
  sk_cliente,
  valor_liquido,
  data_venda,
  created_at
FROM gold_catalog.sales.fact_vendas
WHERE data_venda >= CURRENT_DATE() - 30;

-- Anti-pattern: SELECT * em produção
-- SELECT * FROM gold_catalog.sales.fact_vendas;
```

---

## EXPLAIN: Analisar Plano

```sql
EXPLAIN SELECT
  c.nome,
  COUNT(f.id_fato) AS num_vendas
FROM gold_catalog.sales.dim_cliente c
LEFT JOIN gold_catalog.sales.fact_vendas f
  ON c.sk_cliente = f.sk_cliente
GROUP BY c.nome;
```

Verificar no output:
- `BroadcastHashJoin` = tabela pequena em broadcast (rápido)
- `ShuffleExchange` = shuffle (overhead — considerar otimizar)
- Predicate pushdown visível no `Scan` com filtro aplicado

---

## Semi-Joins: EXISTS vs JOIN

```sql
-- Correto: EXISTS para teste de existência
SELECT id_cliente, nome
FROM gold_catalog.sales.dim_cliente c
WHERE EXISTS (
  SELECT 1 FROM gold_catalog.sales.fact_vendas f
  WHERE f.sk_cliente = c.sk_cliente
    AND f.valor > 1000
);

-- Equivalente com IN
SELECT id_cliente, nome
FROM gold_catalog.sales.dim_cliente c
WHERE id_cliente IN (
  SELECT DISTINCT sk_cliente FROM gold_catalog.sales.fact_vendas
  WHERE valor > 1000
);

-- Anti-pattern: JOIN + DISTINCT (overhead)
-- SELECT DISTINCT c.id_cliente, c.nome
-- FROM dim_cliente c
-- INNER JOIN fact_vendas f ON c.sk_cliente = f.sk_cliente
-- WHERE f.valor > 1000;
```

---

## Aggregate Pushdown: Agregar Antes de Join

```sql
-- Correto: agregar fact antes do JOIN
WITH vendas_por_cliente AS (
  SELECT
    sk_cliente,
    COUNT(*) AS num_vendas,
    SUM(valor_liquido) AS valor_total
  FROM fact_vendas
  GROUP BY sk_cliente
)
SELECT
  c.nome,
  vc.num_vendas,
  vc.valor_total
FROM dim_cliente c
LEFT JOIN vendas_por_cliente vc ON c.sk_cliente = vc.sk_cliente;
```

---

## TABLESAMPLE: Exploração Rápida

```sql
-- Amostra 1% sem full scan
SELECT * FROM gold_catalog.sales.fact_vendas
TABLESAMPLE (1 PERCENT);

-- Reprodutível com seed
SELECT * FROM gold_catalog.sales.fact_vendas
TABLESAMPLE (1 PERCENT) REPEATABLE (42);
```

---

## ANALYZE TABLE: Coletar Estatísticas

```sql
ANALYZE TABLE gold_catalog.sales.fact_vendas COMPUTE STATISTICS;

DESC FORMATTED gold_catalog.sales.fact_vendas;
-- Output: Num Files, Num Rows, Total Size
```
