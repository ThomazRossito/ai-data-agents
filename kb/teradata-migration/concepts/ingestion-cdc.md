# Ingestão e CDC — Teradata → Databricks

> Escopo: migração de dados (export/ingestão em lote) e Change Data Capture incremental de Teradata
> para os mecanismos do Databricks (`WRITE_NOS`, JDBC, Auto Loader, `COPY INTO`, `MERGE`, `AUTO CDC`,
> Change Data Feed). Fonte normativa: digest auditado `_digest_fase3.md` §2 (`03 - Execute/3.2 Lecture
> - Data Migration and Ingestion.md`, 1082 linhas) e §3 (`03 - Execute/3.3 Lecture - Incremental Sync
> and CDC.md`, 1093 linhas), ambos lidos 100%. Irmão de `kb/hadoop-migration/concepts/sqoop-cdc.md`
> (mesmo padrão, origem Hadoop/Sqoop).
>
> **A sintaxe completa de `AUTO CDC` (SQL + Python, SCD Type 1/2) já está documentada** em
> `kb/spark-patterns/patterns/lakeflow-patterns.md` — este arquivo **não duplica** essa sintaxe; cobre
> o que é específico de Teradata: `WRITE_NOS`, JDBC direto, a matriz de decisão por volume, a ausência
> de objeto "Stream" nativo, e o padrão timestamp+watermark+`MERGE`.

**Domínio:** teradata-migration — Ingestão (`WRITE_NOS`/JDBC/Auto Loader) e CDC (watermark/`AUTO CDC`/CDF)
**Agentes:** migration-expert, databricks-engineer

---

## 1. Padrões de Migração — Visão Geral

| Padrão | Melhor para |
|---|---|
| `TPT`/`WRITE_NOS` → Auto Loader | Tabelas grandes, produção |
| JDBC Connector direto | Tabelas pequenas/médias |
| Lakeflow Connect | Replicação contínua (mencionado só na tabela de padrões do curso, sem exemplo de configuração — `[a verificar]` antes de assumir suporte pronto para Teradata) |

Cite: `_digest_fase3.md` §2.1 (`3.2:44-83`).

---

## 2. Export via `WRITE_NOS` (Native Object Store) — Sintaxe Real Teradata

`WRITE_NOS`/`AUTHORIZATION`/`STOREDAS`/`LOCATION` são sintaxe **real** do Teradata Native Object Store
(NOS), confirmada com link para doc oficial no material-fonte (`_digest_fase3.md` §2.2):

```sql
-- Autorização (curso 3.2:144-147)
CREATE AUTHORIZATION td_migration_auth
AS DEFINER TRUSTED
USER ''
PASSWORD '{"AccessID":"YOUR_AWS_ACCESS_KEY","AccessKey":"YOUR_AWS_SECRET_KEY"}';

-- Export (curso 3.2:227-246)
CREATE MULTISET TABLE export_log AS (
  SELECT * FROM WRITE_NOS (
    ON ( SELECT tran_id, cust_id, ..., CAST(shift_start_time AS VARCHAR(20)) AS shift_start_time, ...
         FROM tddb.checking_tran )
    USING
      LOCATION('/abfss/landing@storage.dfs.core.windows.net/tddb/credit_tran/')
      AUTHORIZATION(td_migration_auth)
      STOREDAS('PARQUET')
  ) AS d
) WITH DATA;
```

⚠️ **Inconsistência de nuvem no exemplo-fonte** (não reproduzir): o curso monta um cenário 100% AWS
(IAM policy JSON com `s3:PutObject`) mas o `LOCATION(...)` acima usa path Azure ADLS Gen2
(`abfss://...dfs.core.windows.net`) — os dois não coexistem na prática; escolher **um** provedor cloud
consistente com o `AUTHORIZATION` real do ambiente do usuário (`_digest_fase3.md` §2.2, achado de
inconsistência).

### 2.1 Tipos na Exportação — Cast Obrigatório

Parquet/CSV não suportam nativamente vários tipos Teradata — fazer `CAST` explícito antes do
`WRITE_NOS`:

| Tipo Teradata | Exportar como | Motivo |
|---|---|---|
| `TIME` | `CAST AS VARCHAR` | Parquet `INT32 TIME(MILLIS)` não suportado pelo Spark |
| `PERIOD` | `CAST AS VARCHAR` | Sem equivalente Parquet |
| `BYTE` / `VARBYTE` | `CAST AS VARCHAR` | Hex string |
| `INTERVAL` | `CAST AS VARCHAR` | Sem mapeamento Parquet direto |
| `NUMBER` | `CAST AS DECIMAL` | Precisão flexível → fixa |
| `GEOGRAPHY` / `ST_GEOMETRY` | `ST_AsText()` | WKT |
| `JSON` | `CAST AS VARCHAR` | Já compatível como string |

Cite: `_digest_fase3.md` §2.2 (`3.2:253-296`).

---

## 3. Ingestão via `COPY INTO` e Auto Loader

```sql
-- COPY INTO CSV (curso 3.2:404-420)
COPY INTO IDENTIFIER(:lab_catalog).demo_financial.credit_tran
FROM ( SELECT tran_id, channel, cust_id, tran_code, tran_date, principal_amt, interest_amt, new_balance, tran_amt
       FROM '/Volumes/{lab_catalog}/demo_financial/landing/' )
FILEFORMAT = CSV
FORMAT_OPTIONS ('delimiter' = '|', 'header' = 'true', 'mergeSchema' = 'true')
COPY_OPTIONS ('mergeSchema' = 'true');
```

```python
# Auto Loader (curso 3.2:673-702)
df = (spark.readStream
    .format("cloudFiles")
    .option("cloudFiles.format", "parquet")
    .option("cloudFiles.schemaLocation", f"{checkpoint_path}/_schema")
    .option("cloudFiles.inferColumnTypes", "true")
    .load(source_path)
    .withColumn("_ingested_at", current_timestamp())
    .withColumn("_source_file", col("_metadata.file_path")))

(df.writeStream.format("delta")
    .option("checkpointLocation", checkpoint_path)
    .option("mergeSchema", "true")
    .outputMode("append")
    .trigger(availableNow=True)
    .toTable("IDENTIFIER(:lab_catalog).demo_financial.credit_tran_autoloader"))
```

Cite: `_digest_fase3.md` §2.3.

---

## 4. JDBC Direto

```python
td_url = "jdbc:teradata://your-teradata-server/DATABASE=tddb"
df = (spark.read.format("jdbc")
    .option("url", td_url)
    .option("driver", "com.teradata.jdbc.TeraDriver")
    .option("user", dbutils.secrets.get("teradata_migration", "td_user"))
    .option("password", dbutils.secrets.get("teradata_migration", "td_password"))
    .option("dbtable", "LOCATION")
    .option("fetchsize", "10000")
    .load())
```

Porta padrão do Teradata JDBC: **1025** (confirmada também no contexto de Lakehouse Federation — ver
`kb/databricks/concepts/lakehouse-federation.md` §9). Sempre usar secret scope — nunca credencial em
texto plano no notebook (mesmo protocolo de credenciais já documentado para outras fontes em
`data_agents/agents/registry/migration-expert.md`, seção "Protocolo de credenciais da fonte").

Cite: `_digest_fase3.md` §2.4 (`3.2:823-847`).

---

## 5. Matriz de Decisão por Volume

| Volume | Padrão recomendado |
|---|---|
| < 1 GB | JDBC Connector direto |
| 1–100 GB | `WRITE_NOS` → Auto Loader |
| > 100 GB | `WRITE_NOS` → Auto Loader com exports particionados |

Liquid Clustering pós-carga: `ALTER TABLE ... CLUSTER BY (tran_date, cust_id); OPTIMIZE ...;`

**Iceberg/OTF:** o curso nota (honestamente) que Teradata suporta Open Table Format via
`CREATE DATALAKE` (Database Engine 20), mas `WRITE_NOS`/`READ_NOS` só suportam Parquet/CSV — Iceberg
está fora do escopo desses dois comandos. Ver `kb/databricks/concepts/lakehouse-federation.md` §9.2
para o padrão completo `CREATE DATALAKE ... TABLE FORMAT ICEBERG`.

Cite: `_digest_fase3.md` §2.5 (`3.2:932-1059`).

---

## 6. CDC — Teradata Não Tem Objeto "Stream" Nativo

**Fato explícito do próprio curso, citação literal traduzida:** *"Teradata does not have a built-in
'Stream' object like some cloud data warehouses"* (curso `3.3:92`). Três abordagens reais estão
documentadas:

| Abordagem | Descrição |
|---|---|
| (a) Timestamp-based | Comparar coluna `modified_ts`/`updated_at` com um watermark salvo em tabela de controle |
| (b) Log-based via terceiros | Ferramentas como Qlik Replicate, Informatica, HVR lendo o **transient journal** do Teradata |
| (c) TPT CDC extract | Extração TPT com filtro de timestamp |

⚠️ **Nunca usar `METADATA$ACTION`/`METADATA$ISUPDATE`** como se fossem pseudo-colunas de CDC Teradata
— são colunas reais de **Snowflake Streams**, e o próprio curso se autocontradiz ao introduzi-las 166
linhas depois de afirmar que Teradata não tem Stream (`3.3:258-263` vs `3.3:92`; ver
`function-catalog.md` §0 e `_digest_fase3.md` §8, achado 5).

Cite: `_digest_fase3.md` §3.1 (`3.3:90-177`).

---

## 7. Timestamp-based CDC + `MERGE` (SCD Type 1) — Sintaxe Genuína

```sql
-- Watermark (curso 3.3:101-102)
SELECT MAX(last_processed_ts) INTO :v_watermark FROM tddb_etl.cdc_watermarks WHERE table_name = 'customer_loyalty';

-- CREATE VOLATILE TABLE ... ON COMMIT PRESERVE ROWS é sintaxe Teradata genuína (curso 3.3:103-108)
CREATE VOLATILE TABLE cdc_changes AS (
    SELECT customer_id, first_name, last_name, city, e_mail, modified_ts,
        CASE WHEN is_deleted = 1 THEN 'DELETE'
             WHEN created_ts = modified_ts THEN 'INSERT'
             ELSE 'UPDATE' END AS _operation
    FROM tddb.customer
    WHERE modified_ts > :v_watermark
) WITH DATA ON COMMIT PRESERVE ROWS;

-- MERGE no destino Databricks (curso 3.3:127-147)
MERGE INTO tddb_harmonized.customer_dim AS target
USING cdc_changes AS source
ON target.customer_id = source.customer_id
WHEN MATCHED AND source._operation = 'DELETE' THEN DELETE
WHEN MATCHED THEN UPDATE SET first_name = source.first_name /* ... demais colunas ... */
WHEN NOT MATCHED AND source._operation <> 'DELETE' THEN INSERT (/* ... */) VALUES (/* ... */);
```

Ver `ddl-conversion.md` §7 — `CREATE VOLATILE TABLE` deve virar `TEMP VIEW` no Databricks, nunca
tabela gerenciada permanente.

Cite: `_digest_fase3.md` §3.1 (`3.3:101-147`).

---

## 8. SCD Type 1 (MERGE Direto) e SCD Type 2 Manual (Legado — Preferir `AUTO CDC`)

```sql
-- SCD2 manual em 2 passos (curso 3.3:229-389) — padrão LEGADO, não o alvo recomendado
-- Passo 1: expira registro atual
UPDATE harmonized.customer_dim_scd2
SET valid_to = current_timestamp(), is_current = FALSE
WHERE customer_id IN (SELECT customer_id FROM harmonized.customer_cdc WHERE _operation IN ('UPDATE','INSERT'))
  AND is_current = TRUE;
-- Passo 2: insere nova versão
INSERT INTO harmonized.customer_dim_scd2 (customer_id, first_name, last_name, city, e_mail, valid_from, valid_to, is_current)
SELECT customer_id, first_name, last_name, city, e_mail, current_timestamp(), CAST('9999-12-31' AS TIMESTAMP), TRUE
FROM harmonized.customer_cdc WHERE _operation IN ('UPDATE','INSERT');
```

**Para SCD Type 2 de produção, não escreva o `MERGE`/`UPDATE`+`INSERT` de 2 passos manual — use
`AUTO CDC` com `STORED AS SCD TYPE 2`** (sintaxe completa em `kb/spark-patterns/patterns/lakeflow-patterns.md`,
reforçada pela regra **R4** de `kb/spark-patterns/concepts/sdp-rules.md`: "Para SCD2, sempre AUTO CDC —
nunca LAG/LEAD/ROW_NUMBER manual"). O 2-passo acima é o padrão que o curso usa para ilustrar a lógica,
não o padrão-alvo recomendado.

Cite: `_digest_fase3.md` §3.2.

---

## 9. `AUTO CDC INTO` (Lakeflow SDP) — Sintaxe Completa

```sql
CREATE OR REFRESH STREAMING TABLE customer_dim_history;

CREATE FLOW customer_history_flow
AS AUTO CDC INTO customer_dim_history
FROM STREAM(harmonized.customer_cdc)
KEYS (customer_id)
APPLY AS DELETE WHEN _operation = 'DELETE'
SEQUENCE BY _sequence_num
COLUMNS * EXCEPT (_operation, _sequence_num)
STORED AS SCD TYPE 2;
```

Colunas automáticas `__START_AT`/`__END_AT` geradas pelo `AUTO CDC` (documentado corretamente pelo
curso). **`SEQUENCE BY`** exige coluna de tipo ordenável monotônico; `NULL` não suportado; deve existir
uma única atualização distinta por chave para cada valor de sequência (mesma regra já documentada em
`kb/hadoop-migration/concepts/sqoop-cdc.md` §6 para Hadoop — regra compartilhada, não Teradata-específica).

Cite: `_digest_fase3.md` §3.3 (`3.3:436-469`, `3.3:480-481`, `3.3:554-557`).

---

## 10. Monitoramento de CDC

| Métrica | Alvo |
|---|---|
| Event Lag | < 5 min |
| Throughput | > 10.000 rps |
| Error Rate | < 0.01% |
| Sequence Gaps | 0 |
| Checkpoint Lag | < 1.000 registros |

```sql
-- Delta history (curso 3.3:784-794)
SELECT version, operation, operationMetrics.numTargetRowsInserted AS rows_inserted,
       operationMetrics.numTargetRowsUpdated AS rows_updated, operationMetrics.numTargetRowsDeleted AS rows_deleted,
       operationMetrics.numOutputRows AS output_rows, timestamp
FROM (DESCRIBE HISTORY IDENTIFIER(:lab_catalog).cdc_demo.customer_dim)
WHERE operation = 'MERGE' ORDER BY timestamp DESC;

-- Change Data Feed (curso 3.3:833-842, 885-888)
SELECT cust_id, first_name, city, _change_type, _commit_version, _commit_timestamp
FROM table_changes(CONCAT(:lab_catalog, '.cdc_demo.customer_dim'), 0)
ORDER BY _commit_version, cust_id;

-- Event log do pipeline SDP (curso 3.3:981-995) — requer "Publish event log to Unity Catalog"
SELECT timestamp, origin.flow_name AS flow_name, details:flow_progress.status::STRING AS status,
    details:flow_progress.metrics.num_output_rows::INT AS source_rows_read,
    details:flow_progress.metrics.num_upserted_rows::INT AS rows_upserted,
    details:flow_progress.metrics.num_deleted_rows::INT AS rows_deleted,
    details:flow_progress.metrics.backlog_bytes::INT AS backlog_bytes,
    details:flow_progress.data_quality.dropped_records::INT AS dropped_records, message
FROM IDENTIFIER(:lab_catalog).cdc_demo.event_log_cdc_demo
WHERE event_type = 'flow_progress' AND details:flow_progress.status::STRING IN ('COMPLETED','RUNNING')
ORDER BY timestamp DESC LIMIT 20;
```

"Exactly-once" é garantido pelo par checkpoint (Auto Loader/Structured Streaming) + idempotência do
`MERGE`/`AUTO CDC INTO` — implícito no material-fonte, nunca nomeado explicitamente como seção própria.

Cite: `_digest_fase3.md` §3.4.

---

## 11. Reconciliação do Delta de CDC

Reaproveitar `kb/migration/concepts/reconciliation.md` (7 parity checks + regra das 2 fases) para o
delta capturado por qualquer um dos mecanismos acima — **não duplicado aqui**. Atenção a um bug real já
confirmado do próprio curso na fase de Activate (fora do escopo de ingestão/CDC, mas relevante para
quem for gerar SQL de reconciliação a partir deste domínio): o curso extrai baseline com `STDDEV_POP`
mas compara com `STDDEV()` no Databricks (que é alias de `STDDEV_SAMP`, denominador N-1, diferente de
`STDDEV_POP`, denominador N) — sempre usar `STDDEV_POP`/`STDDEV_SAMP` explícitos nos dois lados,
nunca a forma ambígua `STDDEV()`. Fonte: `_digest_fase4-6.md` §1.2.

---

## Anti-Padrões Locais (TD-I — Ingestão/CDC)

| Código | Anti-padrão | Correção |
|---|---|---|
| TD-I01 | Gravar `CREATE VOLATILE TABLE` como tabela Delta gerenciada permanente | `CREATE OR REPLACE TEMP VIEW` (sessão) — ver `ddl-conversion.md` §7 |
| TD-I02 | Assumir que existe UM mecanismo de CDC Teradata a mapear | Identificar a abordagem real por tabela (timestamp/log de terceiros/TPT) antes de escolher o mecanismo-alvo — §6 |
| TD-I03 | Escrever SCD Type 2 manual com `UPDATE`+`INSERT` de 2 passos no Databricks | `AUTO CDC` com `STORED AS SCD TYPE 2` (regra R4, `sdp-rules.md`) — §9 |
| TD-I04 | Tratar `METADATA$ACTION`/`METADATA$ISUPDATE` como pseudo-coluna Teradata | São Snowflake Streams — §6 |
| TD-I05 | Comparar `STDDEV_POP` (origem) com `STDDEV()`/`STDDEV_SAMP` (destino) sem casar o estimador | Padronizar `STDDEV_POP`↔`stddev_pop`, `STDDEV_SAMP`↔`stddev` — §11 |
| TD-I06 | Misturar credenciais IAM AWS com path `abfss://` Azure no mesmo `WRITE_NOS` | Escolher um provedor cloud consistente — §2 |

---

## Referências

- Digest auditado: `_digest_fase3.md` §2 (Data Migration/Ingestion), §3 (Incremental Sync/CDC)
- Digest auditado: `_digest_fase4-6.md` §1.2 (bug `STDDEV_POP`/`STDDEV`)
- `audits/2026-08-02-curso-teradata-migration-vs-ai-data-agents.md`
- Ver também: `kb/teradata-migration/concepts/ddl-conversion.md` · `kb/teradata-migration/concepts/function-catalog.md`
- Ver também: `kb/databricks/concepts/lakehouse-federation.md` §9 (Teradata Federation & Interop)
- Ver também: `kb/spark-patterns/patterns/lakeflow-patterns.md` (sintaxe completa `AUTO CDC`)
- Ver também: `kb/spark-patterns/concepts/sdp-rules.md` (regra R4 — `AUTO CDC` obrigatório para SCD2)
- Ver também: `kb/migration/concepts/reconciliation.md` (7 parity checks, 2 fases)
- Ver também: `kb/hadoop-migration/concepts/sqoop-cdc.md` (mesmo padrão, origem Hadoop/Sqoop)
- [Delta `MERGE INTO`](https://docs.databricks.com/en/delta/merge.html)
- [`AUTO CDC` for Pipelines](https://docs.databricks.com/en/delta-live-tables/cdc.html)
- [Change Data Feed](https://docs.databricks.com/en/delta/delta-change-data-feed.html)
