# SSIS Expression Language → Spark + Padrões de Conversão

## Funções (SSIS Expression → Spark SQL / PySpark)

| SSIS | Spark |
|---|---|
| `GETDATE()` | `current_timestamp()` |
| `DATEADD("dd", n, d)` | `date_add(d, n)` / `d + INTERVAL n DAY` |
| `DATEDIFF("dd", a, b)` | `datediff(b, a)` |
| `DATEPART("yyyy", d)` | `year(d)` (e `month`, `day`, `hour`...) |
| `YEAR/MONTH/DAY(d)` | `year(d)`/`month(d)`/`day(d)` |
| `SUBSTRING(s, i, n)` | `substring(s, i, n)` (1-based nos dois) |
| `LEN(s)` | `length(s)` |
| `TRIM/LTRIM/RTRIM(s)` | `trim/ltrim/rtrim(s)` |
| `UPPER/LOWER(s)` | `upper/lower(s)` |
| `REPLACE(s,a,b)` | `replace(s,a,b)` / `regexp_replace` |
| `FINDSTRING(s,sub,1)` | `instr(s, sub)` / `locate` |
| `ISNULL(x)` (teste) | `x IS NULL` |
| `REPLACENULL(x,y)` / `ISNULL(x)?y:x` | `coalesce(x, y)` / `nvl(x,y)` |
| `(DT_STR,n,cp)x` / `(DT_WSTR,n)x` | `cast(x as string)` |
| `(DT_I4)x` / `(DT_NUMERIC,p,s)x` | `cast(x as int)` / `cast(x as decimal(p,s))` |
| `(DT_DBTIMESTAMP)x` | `cast(x as timestamp)` |
| `cond ? a : b` | `when(cond, a).otherwise(b)` / `CASE WHEN` |
| `a && b` / `a \|\| b` / `!a` | `a and b` / `a or b` / `not a` |
| `s1 + s2` (concat) | `concat(s1, s2)` / `s1 || s2` |
| `@[User::Var]` | job parameter / `dbutils.widgets.get("var")` |
| `@[System::PackageName]` etc. | contexto do Job / metadados |

## Connection Managers → conexões Databricks

| SSIS | Databricks |
|---|---|
| OLE DB / ADO.NET (SQL Server, Oracle, DB2) | JDBC + **secret scope** (`dbutils.secrets.get`) |
| Flat File | caminho em ADLS/S3 + Auto Loader |
| Excel | arquivo em storage + leitura |
| FTP | Python + secret scope |
| Credenciais no pacote/config | **secret scope** (nunca hardcode) |

## Padrões obrigatórios

1. **Idempotência (S04):** toda escrita re-executável — `MERGE` por chave ou `INSERT OVERWRITE` por
   partição (`replaceWhere`). Nada de append cego que duplica em reprocesso.
2. **Incremental / CDC:** substituir a lógica de "última data" do SSIS por **watermark** (coluna de
   controle) ou **Auto Loader**/`APPLY CHANGES`. Guardar high-watermark em tabela de controle.
3. **Error handling:** error outputs → **quarentena** (`*_rejected`) ou **DLT expectations** (S05).
4. **Orquestração:** Control Flow → **Workflow/Job** (task por executable); Data Flow de camadas →
   **DLT**. Ver `index.md §5` para a decisão.
5. **Reconciliação (S08):** por Data Flow migrado — contagem origem×destino (tolerância <0.1%), soma de
   colunas numéricas (±0.01%), min/max de datas, sem PK duplicada. Reusar checklist de `kb/migration`.
6. **Secrets:** connection managers → secret scope; nunca imprimir credenciais.

## Sinalização de esforço manual (não auto-converter)

Marque **⚠️ revisão manual** e estime esforço para: **Script Task/Component (C#/VB)**, **Fuzzy
Lookup/Grouping**, **DQS**, **Analysis Services/SSAS**, **WMI/MSMQ**, expressões muito complexas com
lógica proprietária. Converter cegamente esses itens é anti-padrão (S03).

## Rastreabilidade

Para cada executable/componente convertido, registrar: `pacote.dtsx › <task/componente> → <artefato
Databricks gerado>` — para auditoria e reconciliação do inventário.
