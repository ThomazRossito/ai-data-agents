# Dialect Conversion — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** Exemplos práticos Spark SQL / T-SQL / KQL para Date, String, Aggregation, Window, Conditional

---

## Date Functions: Exemplos Práticos

### Spark SQL
```sql
-- Últimas 30 dias
SELECT * FROM vendas
WHERE data_venda >= DATE_SUB(CURRENT_DATE(), 30);

-- Diferença em dias
SELECT DATEDIFF(DAY, '2026-01-01', '2026-04-09') AS dias_passados;
```

### T-SQL
```sql
-- Últimas 30 dias
SELECT * FROM vendas
WHERE data_venda >= DATEADD(DAY, -30, CAST(GETDATE() AS DATE));

-- Diferença em dias
SELECT DATEDIFF(DAY, '2026-01-01', '2026-04-09') AS dias_passados;
```

### KQL
```kusto
vendas
| where data_venda >= now(-30d)

// Diferença em dias
print dias_passados = datetime_diff('day', datetime('2026-01-01'), now())
```

---

## NULL Handling: Exemplos

### Spark SQL
```sql
SELECT
  COALESCE(email, 'NO_EMAIL') AS email_clean,
  NULLIF(valor, 0) AS valor_or_null
FROM clientes;
```

### T-SQL
```sql
SELECT
  ISNULL(email, 'NO_EMAIL') AS email_clean,
  NULLIF(valor, 0) AS valor_or_null
FROM clientes;
```

### KQL
```kusto
clientes
| project
  email_clean = iff(isnull(email), 'NO_EMAIL', email),
  valor_or_null = iff(valor == 0, null, valor)
```

---

## Aggregations: Exemplos

### Spark SQL
```sql
SELECT
  regiao,
  SUM(valor) AS total,
  COUNT(*) AS num_vendas,
  AVG(valor) AS media,
  COLLECT_LIST(id_produto) AS produtos
FROM vendas
GROUP BY regiao;
```

### T-SQL
```sql
SELECT
  regiao,
  SUM(valor) AS total,
  COUNT(*) AS num_vendas,
  AVG(valor) AS media,
  STRING_AGG(CAST(id_produto AS VARCHAR), ',') AS produtos
FROM vendas
GROUP BY regiao;
```

### KQL
```kusto
vendas
| summarize
  total = sum(valor),
  num_vendas = count(),
  media = avg(valor),
  produtos = make_list(id_produto)
  by regiao
```

---

## Window Functions: Exemplos

### Spark SQL e T-SQL (idênticos)
```sql
SELECT
  id_cliente,
  data_venda,
  valor,
  LAG(valor) OVER (PARTITION BY id_cliente ORDER BY data_venda) AS valor_anterior,
  SUM(valor) OVER (PARTITION BY id_cliente ORDER BY data_venda
                   ROWS BETWEEN 30 PRECEDING AND CURRENT ROW) AS soma_30dias
FROM vendas;
```

### KQL (diferente — sem ROW_NUMBER/RANK)
```kusto
vendas
| sort by id_cliente, data_venda asc
| extend
  valor_anterior = prev(valor, 1),
  soma_30dias = sum(valor) by id_cliente
```

---

## Conditional Logic: Exemplos

### Spark SQL e T-SQL (idênticos)
```sql
SELECT
  id_cliente,
  CASE
    WHEN valor > 1000 THEN 'Premium'
    WHEN valor > 500 THEN 'Gold'
    WHEN valor > 100 THEN 'Silver'
    ELSE 'Bronze'
  END AS segmento
FROM vendas;
```

### KQL
```kusto
vendas
| project
  id_cliente,
  segmento = case(
    valor > 1000, 'Premium',
    valor > 500, 'Gold',
    valor > 100, 'Silver',
    'Bronze'
  )
```

---

## Type Casting: Exemplos

### Spark SQL
```sql
SELECT
  CAST('123' AS INT) AS num,
  CAST(123.45 AS INT) AS truncado,
  CAST('2026-04-09' AS DATE) AS data;
```

### T-SQL
```sql
SELECT
  CAST('123' AS INT) AS num,
  CAST(123.45 AS INT) AS truncado,
  CAST('2026-04-09' AS DATE) AS data;
```

### KQL
```kusto
print
  num = toint('123'),
  truncado = toint(123.45),
  data = todatetime('2026-04-09')
```

---

## Quick Reference

```
Operação             │ Spark SQL   │ T-SQL      │ KQL
─────────────────────┼─────────────┼────────────┼──────────
Data hoje            │ CURRENT_DATE│ GETDATE()  │ now()
Add 7 dias           │ DATE_ADD()  │ DATEADD()  │ now()+7d
String concat        │ CONCAT()    │ CONCAT()   │ strcat()
NULLs                │ COALESCE()  │ ISNULL()   │ coalesce()
Condicional          │ CASE        │ CASE       │ iff()
COUNT DISTINCT       │ COUNT(DIST.)│ COUNT(D.)  │ dcount()
Window function      │ ROW_NUMBER()│ ROW_NUM()  │ N/A
Type casting         │ CAST()      │ CAST()     │ toint()
```
