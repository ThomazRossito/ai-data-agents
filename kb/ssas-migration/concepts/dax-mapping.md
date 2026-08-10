# Medidas DAX → SQL de Metric View (ou reescrita manual)

> Medidas DAX **simples** viram expressões SQL numa **Databricks Metric View**. **NÃO existe `CREATE
> MEASURE` em SQL** — o que não couber é **documentado para reescrita**, nunca convertido às cegas.

## Conversível → SQL de Metric View

| Padrão DAX | Equivalente SQL (measure da Metric View) | Notas |
|---|---|---|
| `SUM(T[col])` | `SUM(source.col)` | Agregação direta |
| `COUNT` / `COUNTA` / `COUNTROWS(T)` | `COUNT(source.col)` / `COUNT(*)` | |
| `DISTINCTCOUNT(T[col])` | `COUNT(DISTINCT source.col)` | |
| `AVERAGE` / `MIN` / `MAX` | `AVG` / `MIN` / `MAX` | |
| `DIVIDE(a, b)` | `try_divide(a, b)` | `DIVIDE` trata /0 → usar `try_divide` |
| `SUMX(T, T[a]*T[b])` (linha simples) | `SUM(source.a * source.b)` | Só se a expressão de linha for materializável |
| Razões/percentuais simples | `SUM(x)/try_divide(...)` na measure | |

## ⚠️ Bloqueado / revisão manual (NUNCA converter cegamente)

| Padrão DAX / construto | Por quê | Mitigação |
|---|---|---|
| **Time-intelligence** (`SAMEPERIODLASTYEAR`, `DATEADD`, `TOTALYTD`, `DATESYTD`, `PARALLELPERIOD`) | Depende do modelo de datas + contexto de filtro | Colunas offset na `dim_date` (ex.: `data_ano_anterior`) + window/self-join; reescrita manual |
| **`CALCULATE` com modificadores de contexto** (`FILTER`, `ALL`, `ALLEXCEPT`, `KEEPFILTERS`) | Reescreve o contexto de avaliação — sem análogo SQL direto | View parametrizada / subquery / window; caso a caso |
| **Calculated columns com row context** (`RELATED`, `EARLIER`, `RANKX` por linha) | Contexto de linha do DAX ≠ SQL set-based | Materializar coluna na Silver (PySpark/SQL) antes do consumo |
| **Medidas que referenciam outras medidas em cadeia** | Composição de contexto | Achatar em CTEs; validar equivalência numérica |
| **`USERELATIONSHIP` / relacionamento inativo** | Join alternativo dependente de contexto | Join explícito por caso de uso; documentar |
| **KPIs** (`measure.kpi`: status/trend/target) | Sem semáforo nativo em SQL/Metric View | `CASE WHEN` em view ou lógica no AI/BI Dashboard |
| **Calculation groups** | Sem equivalente nativo | Redesenhar como conjunto de measures/parametrização |
| **Variáveis DAX** (`VAR`/`RETURN`, `SUMMARIZE`, `ADDCOLUMNS`) | Construção tabular intermediária | CTEs / views materializadas |

## Regra de ouro

1. Classifique cada medida: **Simples** (→ SQL de Metric View) ou **Complexa** (**⚠️** → documentar reescrita).
2. Preserve `name`, `formatString`, `displayFolder` no inventário para rastreabilidade.
3. Toda medida convertida entra na **reconciliação** (comparar valor SSAS × SQL nas top-N).
4. **PII** em qualquer expressão/coluna → **PARAR e escalar `governance-auditor`**.
5. Nunca alegar no relatório que uma medida foi "convertida" se ela está na lista ⚠️ — honestidade relatório×código.
