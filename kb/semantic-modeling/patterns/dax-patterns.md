# DAX — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** CALCULATE, DIVIDE, SUMX, Time Intelligence, VAR/RETURN, ALL/ALLEXCEPT

---

## CALCULATE — Modificação de Contexto

```dax
-- Medida padrão
Total Sales = SUM(fact_vendas[valor])

-- Com CALCULATE: modificar contexto
Total Sales YTD =
  CALCULATE(
    SUM(fact_vendas[valor]),
    DATESBETWEEN(dim_data[data],
                 STARTOFYEAR(MAX(dim_data[data])),
                 MAX(dim_data[data]))
  )

-- Filtro explícito
Total Sales Premium =
  CALCULATE(
    SUM(fact_vendas[valor]),
    FILTER(dim_cliente, dim_cliente[segmento] = "Premium")
  )

-- Remover filtro de região
Total Sales All Regions =
  CALCULATE(
    SUM(fact_vendas[valor]),
    ALL(dim_cliente[regiao])
  )
```

---

## DIVIDE — Divisão Segura

```dax
-- Nunca usar / diretamente
Average Sale =
  DIVIDE(
    SUM(fact_vendas[valor]),
    COUNT(fact_vendas[id_fato]),
    0  -- Valor default se denominador = 0
  )

-- Percentual do total
Sales Percent =
  DIVIDE(
    [Total Sales],
    CALCULATE([Total Sales], ALL(dim_cliente)),
    0
  )
```

---

## SUMX / AVERAGEX — Iteração

```dax
-- Cálculo complexo linha-por-linha
Margin Amount =
  SUMX(
    fact_vendas,
    (fact_vendas[valor_unitario] - fact_vendas[preco_custo]) * fact_vendas[quantidade]
  )

-- Média de vendas por cliente
Avg Sales per Customer =
  AVERAGEX(
    VALUES(dim_cliente[sk_cliente]),
    CALCULATE(SUM(fact_vendas[valor]))
  )
```

---

## VAR / RETURN — Legibilidade e Performance

```dax
-- Anti-pattern: sem variables
Profit Margin =
  DIVIDE(
    SUM(fact_vendas[valor]) - SUMX(fact_vendas, fact_vendas[preco_custo] * fact_vendas[quantidade]),
    SUM(fact_vendas[valor]),
    0
  )

-- Correto: com VAR (cada cálculo uma vez)
Profit Margin =
  VAR TotalSales = SUM(fact_vendas[valor])
  VAR TotalCost = SUMX(fact_vendas, fact_vendas[preco_custo] * fact_vendas[quantidade])
  VAR Profit = TotalSales - TotalCost
  RETURN
    DIVIDE(Profit, TotalSales, 0)
```

---

## Time Intelligence

```dax
-- Mês anterior
Sales Last Month =
  CALCULATE(
    [Total Sales],
    DATEADD(dim_data[data], -1, MONTH)
  )

-- Crescimento MoM
Sales Growth % =
  DIVIDE(
    [Total Sales] - [Sales Last Month],
    [Sales Last Month],
    0
  )

-- YTD
YTD Sales =
  CALCULATE(
    [Total Sales],
    DATESYTD(dim_data[data])
  )

-- Mesmo período ano anterior
Sales SPLY =
  CALCULATE(
    [Total Sales],
    DATEADD(dim_data[data], -1, YEAR)
  )

-- YoY Growth %
YoY Growth % =
  DIVIDE(
    [Total Sales] - [Sales SPLY],
    [Sales SPLY],
    0
  )
```

---

## ALL / ALLEXCEPT

```dax
-- Remover TODOS os filtros de cliente
Sales Pct of Grand Total =
  DIVIDE(
    [Total Sales],
    CALCULATE([Total Sales], ALL(dim_cliente)),
    0
  )

-- Remover todos exceto categoria
Sales Pct by Category =
  DIVIDE(
    [Total Sales],
    CALCULATE([Total Sales],
              ALLEXCEPT(dim_cliente, dim_cliente[categoria])),
    0
  )
```

---

## USERELATIONSHIP (Relacionamento Inativo)

```dax
-- Usar relacionamento inativo (ex: data de entrega)
Total Vendas por Data Entrega =
  CALCULATE(
    [Total Sales],
    USERELATIONSHIP(fact_vendas[sk_data_entrega], dim_data[sk_data])
  )
```

---

## Formato Dinâmico (K, M, B)

```dax
Sales Formatted =
  IF(ABS([Total Sales]) >= 1000000,
     FORMAT([Total Sales] / 1000000, "0.0M"),
     IF(ABS([Total Sales]) >= 1000,
        FORMAT([Total Sales] / 1000, "0.0K"),
        FORMAT([Total Sales], "0")
     )
  )
```
