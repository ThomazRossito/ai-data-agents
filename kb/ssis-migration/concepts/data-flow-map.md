# Data Flow (SSIS) → PySpark / Spark SQL / DLT

> Data Flow = o pipeline linha-a-linha do SSIS (Source → Transforms → Destination). Alvo: transformações
> **set-based** em PySpark/Spark SQL, ou **Lakeflow SDP** (ex-DLT) quando for ingestão em camadas — mas
> **um modelo só** por pipeline (ver `execution-model-and-packaging.md`). Cada Data Flow Task vira um
> notebook OU uma `@dp.table` no pipeline (nunca os dois misturados).

## Sources

| SSIS Source | Spark |
|---|---|
| **OLE DB / ADO.NET Source** | `spark.read.format("jdbc")` (ou ler do Bronze já ingerido) |
| **Flat File Source** (CSV/TXT) | `spark.read.csv(...)` ou **Auto Loader** (`cloudFiles`) |
| **Excel Source** | `spark.read.format("com.crealytics.spark.excel")` ou pandas p/ arquivos pequenos |
| **XML Source** | `spark.read.format("xml")` (spark-xml) |
| **Raw File / Recordset** | Delta/temp view intermediária |

## Transforms

| SSIS Transform | Spark | Nota |
|---|---|---|
| **Derived Column** | `.withColumn(name, expr(...))` | Traduzir a expressão (ver expressions-and-patterns) |
| **Data Conversion** | `.withColumn(c, col(c).cast(t))` | |
| **Lookup** | `join` (broadcast p/ dimensão pequena) | "No match" output → left_anti / quarentena |
| **Merge Join** | `df1.join(df2, keys, "inner/left/outer")` | SSIS exige Sort antes; no Spark não precisa |
| **Union All** | `df1.unionByName(df2, allowMissingColumns=True)` | |
| **Conditional Split** | múltiplos DataFrames via `.filter(cond)` | Cada saída = 1 DataFrame |
| **Multicast** | `.cache()` + múltiplas escritas/ramos | |
| **Aggregate** | `.groupBy(...).agg(...)` | |
| **Sort** | `.orderBy(...)` | **S02** — evitar; caro (shuffle). Só se necessário |
| **Pivot / Unpivot** | `.groupBy().pivot()` / `stack()`/`unpivot` | |
| **Row Count** | `.count()` / accumulator | Guardar em variável de auditoria |
| **Slowly Changing Dimension (SCD Wizard)** | **`MERGE INTO`** (SCD1/SCD2) ou **DLT `APPLY CHANGES INTO`** | Ver padrão SCD abaixo |
| **OLE DB Command** (por linha) | **`MERGE`/`UPDATE` set-based** | **S01** — nunca linha-a-linha |
| **Lookup + OLE DB Command (upsert)** | `MERGE INTO ... WHEN MATCHED/NOT MATCHED` | |
| **Script Component** (C#/VB) | UDF / `mapInPandas` (reescrita manual) | **S03** — sinalizar esforço manual |
| **Fuzzy Lookup / Fuzzy Grouping** | Sem nativo → join aproximado / biblioteca (ex.: soundex, levenshtein) | ⚠️ revisão manual |
| **Term Extraction/Lookup, DQS** | Sem nativo | ⚠️ revisão manual |
| **Cache Transform** | broadcast / `.cache()` | |

## Destinations

| SSIS Destination | Spark |
|---|---|
| **OLE DB Destination (append)** | `.write.format("delta").mode("append")` |
| **OLE DB Destination (upsert via SCD/OLE DB Command)** | `MERGE INTO` |
| **Flat File Destination** | `.write.csv(...)` / export |
| **Recordset Destination** | Delta/temp view |

## Error outputs (redirect rows) → quarentena / expectations

- SSIS "Redirect row" no error output → em Databricks: filtrar linhas inválidas para uma **tabela de
  quarentena** (`*_rejected`) com o motivo, **ou** usar **DLT `EXPECT ... ON VIOLATION DROP/FAIL`**.
- **S05** — nunca descartar silenciosamente as linhas com erro.

## Padrão SCD (substitui o SCD Wizard)

**SCD1 (overwrite):**
```sql
MERGE INTO silver.dim_cliente t USING updates s ON t.nk = s.nk
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
```
**SCD2 (histórico):** MERGE que fecha o registro corrente (`_is_current=false`, `_valid_to=now`) e
insere a nova versão — ou **DLT `APPLY CHANGES ... STORED AS SCD TYPE 2`**.

## Padrão de saída (Data Flow)

- 1 Data Flow Task → 1 notebook PySpark (ou pipeline DLT) com: leitura → transformações encadeadas →
  escrita Delta, + tratamento de error outputs (quarentena) + reconciliação de contagem.
