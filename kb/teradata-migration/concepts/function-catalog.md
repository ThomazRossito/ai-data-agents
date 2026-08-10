# Catálogo de Conversão SQL Teradata → Databricks SQL

> Catálogo complementar a `ddl-conversion.md` (tipos/DDL) e a `kb/sql-patterns/concepts/dialect-concepts.md`
> (mapeamento genérico Spark SQL/T-SQL/KQL). Este arquivo cobre **funções, agregação/janela, casting e
> condicionais** especificamente Teradata → Databricks. Irmão de `kb/sql-patterns/concepts/tsql-conversion-catalog.md`
> (mesmo padrão, origem SQL Server). **Este catálogo é filtrado de contaminação Snowflake** — ver §0.

**Domínio:** teradata-migration — Conversão SQL/Funções Teradata → Databricks (Migração)
**Fonte:** Digest auditado `_digest_fase3.md` §4 (`03 - Execute/3.4 Lecture - SQL and Code Conversion.md`,
3752 linhas, lido 100%) e `_digest_fase0-2.md` §1.3 (tabela de mapeamento de funções do Discovery).
**Agentes:** migration-expert, databricks-engineer

---

## ⚠️ §0. Nota de Auditoria — Filtro de Contaminação Snowflake (ler antes de tudo)

O catálogo de funções do curso-fonte mistura, em pontos concretos, **funções reais do Snowflake**
apresentadas como se fossem Teradata (`_digest_fase3.md` §8, achados 3/4/5/6/7/8;
`audits/2026-08-02-curso-teradata-migration-vs-ai-data-agents.md` §2). **Nunca tratar como Teradata**:

| Rotulado "Teradata" pelo curso | Realidade | Evidência |
|---|---|---|
| `ARRAY_AGG(col)`, `ARRAY_AGG(DISTINCT col)` | Snowflake (agregação em array) | `3.4:923-926` |
| `ARRAY_UNIQUE_AGG(col)` | Snowflake | `3.4:923-926` |
| `OBJECT_AGG(key, val)` | Snowflake | `3.4:923-926` |
| `IFF(cond, a, b)` | Snowflake (Teradata usa `CASE WHEN`) | `3.4:2761-2762` |
| `EQUAL_NULL(a, b)` | Snowflake (Teradata usa `IS [NOT] DISTINCT FROM`) | `3.4:2761-2762` |
| `LATERAL FLATTEN` | Snowflake (o bloco Teradata correspondente na verdade usa `JSON_TABLE`) | `3.4:1572` vs `3.4:1512-1524` |
| `ARRAY_CONTAINS(value, array)` (nessa ordem de argumento) | Assinatura Snowflake — Teradata não tem `ARRAY_CONTAINS` nativo documentado | `3.4:1820-1833` |
| `CREATE FUNCTION ... LANGUAGE PYTHON RUNTIME_VERSION = ... HANDLER = ... AS $$ ... $$` | Sintaxe exata do Snowflake Python UDF — Teradata usa Script Table Operator/BYOM/UDF C/Java | `3.4:2122-2133` (autocontradiz `3.4:1894`, 200 linhas antes, que descreve corretamente UDF Teradata) |
| `METADATA$ACTION`, `METADATA$ISUPDATE` | Pseudo-colunas de **Snowflake Streams** | `3.3:258-263` (autocontradiz `3.3:92`, que afirma corretamente "Teradata does not have a built-in 'Stream' object") |

Se qualquer um destes aparecer numa "fonte Teradata" real do usuário, sinalize que a fonte pode não ser
Teradata genuína antes de prosseguir — nunca gerar SQL de conversão tratando essas funções como se
fossem Teradata válido.

---

## 1. Datas

| Teradata | Databricks SQL | Nota |
|---|---|---|
| `ADD_MONTHS(date, n)` | `ADD_MONTHS(date, n)` ou `DATEADD(MONTH, n, date)` | Direto |
| `date + INTERVAL 'n' DAY` | `date + INTERVAL n DAYS` ou `DATEADD(DAY, n, date)` | Teradata usa valor de intervalo entre aspas |
| `(dt2 - dt1) DAY` | `DATEDIFF(DAY, dt1, dt2)` | Teradata usa subtração de intervalo com qualificador (`DAY(4)`, etc.) |
| `TRUNC(date, 'MON')` | `DATE_TRUNC('MONTH', date)` | Nome/sintaxe diferente |
| `EXTRACT(part FROM date)` | `EXTRACT(part FROM date)` ou `DATE_PART(part, date)` | Direto |
| `CAST(expr AS DATE FORMAT 'YYYY-MM-DD')` | `TO_DATE(expr, 'yyyy-MM-dd')` ou `CAST` | Teradata usa cláusula `FORMAT` |
| `TD_MONTH_END(date)` | `LAST_DAY(date)` | Nome diferente |
| `TD_MONTH_OF_YEAR(date)` | `MONTH(date)` / `DATE_FORMAT(date,'MMMM')` | |
| `TD_DAY_OF_WEEK(date)` | `DAYOFWEEK(date)` / `DATE_FORMAT(date,'EEEE')` | |

Exemplo real de conversão (curso `3.4:317-387`):

```sql
-- Teradata
SELECT a.cust_id, a.acct_start_date, MIN(t.tran_date) AS first_transaction,
       (MIN(t.tran_date) - a.acct_start_date) DAY(4) AS days_to_first_tran
FROM tddb.accounts a JOIN tddb.checking_tran t ON a.cust_id = t.cust_id
GROUP BY a.cust_id, a.acct_start_date SAMPLE 5;

-- Databricks
SELECT c.cust_id, a.acct_start_date, MIN(t.tran_date) AS first_transaction,
       DATEDIFF(DAY, a.acct_start_date, MIN(t.tran_date)) AS days_to_first_tran
FROM IDENTIFIER(:lab_catalog).demo_financial.customer c
JOIN IDENTIFIER(:lab_catalog).demo_financial.accounts a ON c.cust_id = a.cust_id
JOIN IDENTIFIER(:lab_catalog).demo_financial.credit_tran t ON c.cust_id = t.cust_id
GROUP BY c.cust_id, a.acct_start_date ORDER BY days_to_first_tran;
```

⚠️ **Nuance semântica em `SAMPLE n` → `LIMIT n`** (ver §5): o curso troca as duas sem observar que
`SAMPLE` é aleatório e `LIMIT` são as primeiras linhas — diferença semântica real não documentada pelo
curso (`_digest_fase3.md` §4.1).

Cite: `_digest_fase3.md` §4.1.

---

## 2. Strings

| Teradata | Databricks SQL | Nota |
|---|---|---|
| `CONCAT(a,b,c)` | `CONCAT(a,b,c)` | Direto |
| `\|\|` | `\|\|` ou `CONCAT()` | Direto |
| `SUBSTR(str,pos,len)` | `SUBSTR`/`SUBSTRING` | Direto |
| `LEFT`/`RIGHT`/`TRIM`/`LTRIM`/`RTRIM`/`UPPER`/`LOWER`/`REPLACE` | Idênticos | Direto |
| `SPLIT(str,delim)` | `SPLIT(str,delim)` | Direto |
| `SPLIT_PART(str,delim,n)` | `SPLIT_PART` (DBR 14+) | Direto |
| `REGEXP_SUBSTR(str,pat)` | `REGEXP_EXTRACT(str,pat)` | Renomeado |
| `REGEXP_REPLACE` | Idêntico | Direto |
| `LISTAGG(col,delim) WITHIN GROUP (ORDER BY ...)` | `ARRAY_JOIN(ARRAY_SORT(COLLECT_LIST(col)), delim)` | `WITHIN GROUP` genuíno Teradata (`3.4:701-708`); conversão reproduz a ordenação (`3.4:757-763`) |
| `STRTOK_TO_ARRAY(str,delim)` | `SPLIT(str,delim)` | Renomeado |
| `OREPLACE(s, old, new)` | `REPLACE(s, old, new)` | Renomeação direta — genuinamente Teradata, confirmado por conhecimento de domínio (`3.4:3344-3585`, seção com dados não-contaminados) |
| `INDEX(s, sub)` | `INSTR(s, sub)` | Retorna posição |
| `CHARACTERS(s)` | `LENGTH(s)` | Contagem de caracteres |
| `TD_SYSFNLIB.NVP()` | `SPLIT_PART()` / `REGEXP_EXTRACT()` | Parsing name-value |

**Faltam do catálogo do curso** (genuinamente Teradata, ausentes de toda a `3.4` confirmado por grep —
`_digest_fase3.md` §4.2): `OTRANSLATE` (tradução de caracteres) — **[a verificar]** equivalente exato
Databricks; abreviação `SEL` (ver §5).

Cite: `_digest_fase3.md` §4.2.

---

## 3. Agregação e Janelas

| Teradata | Databricks SQL | Nota |
|---|---|---|
| `SUM`/`AVG`/`COUNT`/`MIN`/`MAX` | Idênticos | Direto |
| `MEDIAN(col)` | `PERCENTILE(col, 0.5)` ou `MEDIAN(col)` | Plausível — Teradata tem `MEDIAN` em algumas versões |
| `MODE(col)` | `MODE(col)` (DBR 14+) | Plausível |
| `ZEROIFNULL(col)` | `COALESCE(col, 0)` / `IFNULL(col, 0)` | ✅ `ZEROIFNULL` é função Teradata **real** |
| `NULLIFZERO(col)` | `NULLIF(col, 0)` | ✅ função Teradata **real** |

⚠️ **Não incluídos nesta tabela por serem contaminação Snowflake** (ver §0): `ARRAY_AGG`,
`ARRAY_UNIQUE_AGG`, `OBJECT_AGG`. Se precisar do equivalente Databricks para agregação em coleção a
partir de uma fonte Teradata real, use `COLLECT_LIST(col)` / `COLLECT_SET(col)` / `MAP_FROM_ENTRIES(
COLLECT_LIST(STRUCT(key,val)))` — mas **nunca** documente essas três como "conversão de função
Teradata"; documente-as apenas como destino Databricks, com a fonte real (Teradata) sendo uma expressão
`CASE`/subquery correlacionada equivalente, a avaliar caso a caso.

Cite: `_digest_fase3.md` §4.3.

---

## 4. `QUALIFY` — Nativo, Sem Conversão

```sql
SELECT cust_id, tran_id, tran_date, tran_amt
FROM IDENTIFIER(:lab_catalog).demo_financial.credit_tran
WHERE cust_id BETWEEN 1 AND 100
QUALIFY ROW_NUMBER() OVER (PARTITION BY cust_id ORDER BY tran_date DESC) = 1
LIMIT 10;
```

Idêntico em Teradata e Databricks SQL — **nativo desde Databricks Runtime 10.4 LTS**, confirmado na
doc oficial (`docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-qry-select-qualify`,
atualizada 24/jun/2026). CTE alternativa (`ROW_NUMBER()` em subquery + `WHERE rn = 1`) continua válida
para compatibilidade com versões antigas do Databricks.

Cite: `_digest_fase3.md` §4.9 (seção descrita como "correta e bem verificada" pelo auditor original).

---

## 5. `SAMPLE` / `SEL` / `TOP n`

| Teradata | Databricks SQL | Nota |
|---|---|---|
| `SAMPLE n` (sem % — amostra aleatória de n linhas) | `LIMIT n` (pedagógico) ou `TABLESAMPLE` (semântica correta) | ⚠️ **Não são equivalentes semânticos**: `SAMPLE` é aleatório, `LIMIT` retorna as primeiras linhas por ordem física/de plano. O curso usa `SAMPLE n → LIMIT n` repetidamente (`3.4:215,328,442,1077,1299,1411,3299,3493`) sem observar essa diferença — se a regra de negócio exige amostra aleatória real, usar `TABLESAMPLE` no Databricks, não `LIMIT` |
| `SEL` (abreviação de `SELECT`, uso comum em BTEQ) | `SELECT` | Sintaxe reduzida específica de scripts BTEQ — expandir para `SELECT` completo na conversão; **ausente do catálogo do curso**, confirmado por grep (`_digest_fase3.md` §4.2) |
| `TOP n` | `LIMIT n` | Teradata suporta `SELECT TOP n` como alternativa a `SAMPLE`/`LIMIT`; **também ausente do catálogo do curso** |

Cite: `_digest_fase3.md` §4.1 (nuance semântica `SAMPLE`), §4.2 (gap `SEL`/`TOP n` confirmado por grep).

---

## 6. ⚠️ Gaps do Curso — Funções OLAP Genuinamente Teradata Omitidas

**Achado central desta auditoria:** o curso **nunca menciona**, em nenhuma das 3752 linhas de `3.4`
(confirmado por grep — zero ocorrências), um conjunto de funções OLAP clássicas e genuinamente
Teradata, mapeáveis para window functions Spark. Isso é uma lacuna de conteúdo real do curso — este
catálogo a preenche:

| Teradata (OLAP clássico) | Databricks SQL (window function equivalente) | Status |
|---|---|---|
| `CSUM(col, order_col)` — soma cumulativa | `SUM(col) OVER (ORDER BY order_col ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` | Mapeamento direto — `[a verificar]` sintaxe exata Vantage 20.x |
| `MSUM(col, n, order_col)` — soma móvel de n linhas | `SUM(col) OVER (ORDER BY order_col ROWS BETWEEN n PRECEDING AND CURRENT ROW)` | Idem |
| `MAVG(col, n, order_col)` — média móvel de n linhas | `AVG(col) OVER (ORDER BY order_col ROWS BETWEEN n PRECEDING AND CURRENT ROW)` | Idem |
| `MDIFF(col, n, order_col)` — diferença móvel (valor atual − valor há n linhas) | `col - LAG(col, n) OVER (ORDER BY order_col)` | Idem |
| `RESET WHEN <condição>` (reinicia acumulador de `CSUM`/`MSUM`/`MAVG` a cada mudança de condição) | **Sem frame ANSI direto** — reformular com `PARTITION BY` de um grupo de reset calculado (ex.: `SUM(CASE WHEN <condição de quebra> THEN 1 ELSE 0 END) OVER (ORDER BY ...)` como chave de partição sintética), ou UDF | **[a verificar]** — sem equivalente 1:1 confirmado; marcar para validação caso a caso, nunca assumir tradução mecânica |
| `NORMALIZE` (consolida linhas `PERIOD` sobrepostas/adjacentes em uma única linha) | Sem equivalente nativo — lógica custom (self-join + `LEAD`/`LAG` por chave, ou UDF) | **[a verificar]** |
| `EXPAND ON <coluna PERIOD>` (explode uma linha com coluna `PERIOD` em N linhas, uma por sub-período) | `EXPLODE` sobre um array de datas gerado (ex.: `sequence(start, end, interval)` + `EXPLODE`) | **[a verificar]** — depende da granularidade desejada |
| `PIVOT` / `UNPIVOT` | `PIVOT` clause do Databricks SQL existe, mas com sintaxe diferente (ver `kb/sql-patterns/concepts/tsql-conversion-catalog.md` §3.8 para a diferença de colchetes/aspas) — Teradata suporta ambos nativamente | Mapeamento existe, mas sintaxe não é 1:1 — revisar seção própria antes de gerar |

**Nunca estimar esforço de conversão destes como se fosse mapeamento determinístico do gerador** —
`scripts/teradata_generate.py` não cobre SQL/DML (só DDL), e este catálogo os marca explicitamente como
requerendo revisão manual, principalmente `RESET WHEN`/`NORMALIZE`/`EXPAND ON`, que não têm frame ANSI
ou função Spark equivalente confirmada.

Cite: `_digest_fase3.md` §4.3 (gap confirmado por grep), §7.1 (item 5 da proposta do gerador), §9
(lista de fatos a verificar na web); `audits/2026-08-02-curso-teradata-migration-vs-ai-data-agents.md`
§5 P2 ("completar os gaps de conteúdo do próprio curso").

---

## 7. Casting

| Teradata | Databricks SQL | Nota |
|---|---|---|
| `CAST(col AS VARCHAR(n))` | `col::STRING` ou `CAST(col AS STRING)` | Direto |
| `CAST(col AS JSON)` | `col::VARIANT` (DBR 15.3+) | Teradata JSON real existe desde 17.10 — mapeamento plausível |
| `TRYCAST(col AS type)` | `TRY_CAST(col AS type)` | ⚠️ **[a verificar]** — não confirmado que `TRYCAST` (sem underscore) exista no Teradata clássico; pode ser confusão do curso com `TRY_CAST` (nome usado por SQL Server/Snowflake/Databricks, todos com underscore) |

Cite: `_digest_fase3.md` §4.7.

---

## 8. Condicionais e NULL

| Teradata | Databricks SQL | Nota |
|---|---|---|
| `CASE WHEN ... END` | `CASE WHEN ... END` ou `IF(cond, a, b)` | Direto |
| `COALESCE` / `NVL` / `NVL2` / `NULLIF` | Idênticos nos dois lados | Direto |
| `a IS [NOT] DISTINCT FROM b` | `a <=> b` (ou `NOT (a <=> b)`) | ANSI real, suportado em ambos |
| `ZEROIFNULL(col)` | `COALESCE(col, 0)` | ✅ real (repetido de §3 por completude) |
| `NULLIFZERO(col)` | `NULLIF(col, 0)` | ✅ real (repetido de §3 por completude) |

⚠️ **Não incluídos por serem contaminação Snowflake** (ver §0): `IFF(cond,a,b)` e `EQUAL_NULL(a,b)` —
o curso os apresenta como "conversão Teradata→Databricks" (`3.4:2761-2762`), mas ambos são nomes de
função **Snowflake**. O equivalente Teradata genuíno de `IFF` é `CASE WHEN`; de `EQUAL_NULL` é
`IS [NOT] DISTINCT FROM` (já na tabela acima).

Cite: `_digest_fase3.md` §4.8.

---

## Anti-Padrões Locais (TD-F — Function Catalog)

| Código | Anti-padrão | Correção |
|---|---|---|
| TD-F01 | Tratar `ARRAY_AGG`/`ARRAY_UNIQUE_AGG`/`OBJECT_AGG`/`IFF`/`EQUAL_NULL`/`LATERAL FLATTEN` como função Teradata | São Snowflake — ver §0. Nunca gerar conversão a partir delas sem antes sinalizar contaminação de fonte |
| TD-F02 | Converter `SAMPLE n` → `LIMIT n` sem observar a diferença semântica (aleatório vs primeiras linhas) | Usar `TABLESAMPLE` se a regra de negócio depender de amostra aleatória real — §5 |
| TD-F03 | Estimar `CSUM`/`MSUM`/`MAVG`/`MDIFF`/`RESET WHEN`/`NORMALIZE`/`EXPAND ON` como conversão mecânica de baixo esforço | São gaps reais sem tradução 1:1 confirmada — marcar `[a verificar]` e revisar caso a caso — §6 |
| TD-F04 | Assumir que `TRYCAST` (sem underscore) é sintaxe Teradata válida | Não confirmado — verificar na origem antes de gerar `TRY_CAST` como "equivalente direto" — §7 |

---

## Referências

- Digest auditado: `_digest_fase3.md` §4 (catálogo completo de conversão SQL/código)
- Digest auditado: `_digest_fase0-2.md` §1.3 (tabela de mapeamento de funções do Discovery)
- `audits/2026-08-02-curso-teradata-migration-vs-ai-data-agents.md` §2 (contaminação), §5 P2 (gaps)
- Ver também: `kb/teradata-migration/concepts/ddl-conversion.md` · `kb/teradata-migration/concepts/ingestion-cdc.md`
- Ver também: `kb/sql-patterns/concepts/tsql-conversion-catalog.md` §3.8 (`PIVOT` sem colchetes, mesma
  nuance de sintaxe aplicável a partir do Teradata)
- Ver também: `kb/sql-patterns/concepts/dialect-concepts.md` (mapeamento genérico Spark SQL/T-SQL/KQL)
- [QUALIFY clause — Databricks](https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-qry-select-qualify)
- [Databricks SQL Language Reference — Window Functions](https://docs.databricks.com/en/sql/language-manual/sql-ref-window-functions.html)
