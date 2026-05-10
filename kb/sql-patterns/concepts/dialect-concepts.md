# Dialect Conversion — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** Mapeamento de plataformas, tabelas de comparação Spark SQL / T-SQL / KQL

---

## Mapeamento de Plataformas

| Plataforma | Dialeto | Engine | Uso |
|-----------|---------|--------|-----|
| **Databricks Lakehouse** | Spark SQL | Apache Spark | Data lake, pipelines, ML |
| **Azure Fabric Lakehouse** | T-SQL | SQL Synapse | Data warehouse (SQL) |
| **Azure Fabric Eventhouse** | KQL | Kusto Query Engine | Time-series, logs, eventos |

---

## Date Functions

| Operação | Spark SQL | T-SQL | KQL |
|----------|-----------|-------|-----|
| Data Atual | `CURRENT_DATE()` | `CAST(GETDATE() AS DATE)` | `now()` |
| Timestamp Atual | `CURRENT_TIMESTAMP()` | `GETDATE()` | `now()` |
| Adicionar Dias | `DATE_ADD(date, 7)` | `DATEADD(DAY, 7, date)` | `now() + 7d` |
| Subtrair Dias | `DATE_SUB(date, 7)` | `DATEADD(DAY, -7, date)` | `now() - 7d` |
| Diferença de Datas | `DATEDIFF(DAY, d1, d2)` | `DATEDIFF(DAY, d1, d2)` | `datetime_diff('day', d1, d2)` |
| Extrair Ano | `YEAR(date)` | `YEAR(date)` | `year(date)` |
| Extrair Mês | `MONTH(date)` | `MONTH(date)` | `month(date)` |

---

## String Functions

| Operação | Spark SQL | T-SQL | KQL |
|----------|-----------|-------|-----|
| Concatenar | `CONCAT(s1, s2)` | `CONCAT(s1, s2)` | `strcat(s1, s2)` |
| Substring | `SUBSTRING(str, 1, 5)` | `SUBSTRING(str, 1, 5)` | `substring(str, 1, 5)` |
| Comprimento | `LENGTH(str)` | `LEN(str)` | `strlen(str)` |
| Uppercase | `UPPER(str)` | `UPPER(str)` | `toupper(str)` |
| Lowercase | `LOWER(str)` | `LOWER(str)` | `tolower(str)` |
| Split | `SPLIT(str, delim)` | `STRING_SPLIT(str, delim)` | `split(str, delim)` |

---

## Type Casting

| Conversão | Spark SQL | T-SQL | KQL |
|-----------|-----------|-------|-----|
| String → Int | `CAST(s AS INT)` | `CAST(s AS INT)` | `toint(s)` |
| String → Float | `CAST(s AS DOUBLE)` | `CAST(s AS FLOAT)` | `todouble(s)` |
| String → Date | `CAST(s AS DATE)` | `CAST(s AS DATE)` | `todatetime(s)` |
| Int → String | `CAST(i AS STRING)` | `CAST(i AS VARCHAR)` | `tostring(i)` |

---

## NULL Handling

| Operação | Spark SQL | T-SQL | KQL |
|----------|-----------|-------|-----|
| Teste NULL | `col IS NULL` | `col IS NULL` | `isnull(col)` |
| Substituir NULL | `COALESCE(c1, c2)` | `COALESCE(c1, c2)` | `coalesce(c1, c2)` |
| IFNULL (2 args) | `IFNULL(col, default)` | `ISNULL(col, default)` | `iff(isnull(col), default, col)` |
| NULLIF | `NULLIF(c1, c2)` | `NULLIF(c1, c2)` | `iff(c1 == c2, null, c1)` |

---

## Aggregations

| Função | Spark SQL | T-SQL | KQL |
|--------|-----------|-------|-----|
| SUM | `SUM(col)` | `SUM(col)` | `sum(col)` |
| COUNT DISTINCT | `COUNT(DISTINCT col)` | `COUNT(DISTINCT col)` | `dcount(col)` |
| GROUP_CONCAT | `COLLECT_LIST` | `STRING_AGG` | `make_list` |
| STDDEV | `STDDEV(col)` | `STDEV(col)` | `stdev(col)` |

---

## Window Functions: Suporte por Plataforma

| Operação | Spark SQL | T-SQL | KQL |
|----------|-----------|-------|-----|
| ROW_NUMBER | Sim | Sim | Não suportado |
| RANK | Sim | Sim | Não suportado |
| LAG/LEAD | Sim | Sim | `prev/next` |
| SUM (window) | Sim | Sim | `sum(col) by cat` |

---

## Conditional Logic

| Operação | Spark SQL | T-SQL | KQL |
|----------|-----------|-------|-----|
| IF/CASE | `CASE WHEN ... THEN ... END` | `CASE WHEN ... THEN ... END` | `iff(cond, val1, val2)` |
| Múltiplas condições | `CASE WHEN ... WHEN ...` | `CASE WHEN ... WHEN ...` | `case(c1, v1, c2, v2, ...)` |

---

## Gotchas Críticos

| Gotcha | Plataforma | Solução |
|--------|-----------|---------|
| DATEDIFF ordem dos argumentos | Spark: d2 - d1; igual T-SQL | Testar sempre |
| NULL em comparação | Todas: `NULL = 'X'` → FALSE | Usar IS NULL |
| Window functions | KQL: limitadas | Usar Spark SQL ou T-SQL |
| COALESCE vs ISNULL | COALESCE portável, ISNULL T-SQL específico | Usar COALESCE |
| Type casting implícito | Todas | Sempre CAST explícito |
