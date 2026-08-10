---
name: teradata-to-databricks
description: "Playbook operacional do agente teradata-to-databricks: como rodar discovery manual (dicionário DBC.* via BTEQ/JDBC — sem MCP dedicado a Teradata), como obter e formatar o DDL Teradata (SHOW TABLE) para os geradores, como pontuar complexidade/waves, como produzir o documento de proposta (SPEC) para aprovação humana, como rodar os dois geradores determinísticos (scripts/teradata_generate.py e scripts/reconcile_generate.py com source_dialect=teradata), como escolher entre WRITE_NOS/TPT/JDBC por volume, como tratar QUALIFY e o catálogo de funções, como mapear TASM → SQL Warehouse e Lakehouse Federation, e como aplicar o runbook de cutover/rollback — tudo para migração de data warehouse Teradata → Databricks, com o gate anti-contaminação Snowflake em destaque."
updated_at: 2026-08-02
source: kb/teradata-migration (index + concepts/ddl-conversion + function-catalog + ingestion-cdc) + kb/databricks/concepts/lakehouse-federation (seção Teradata) + kb/migration/concepts/discovery-assessment + reconciliation + cutover-rollback + audits/2026-08-02-curso-teradata-migration-vs-ai-data-agents.md
agent: teradata-to-databricks
domain: teradata-migration
---

# Skill — Migração Teradata → Databricks

> Leia na primeira chamada da sessão. Define COMO rodar discovery (majoritariamente manual — não há
> MCP dedicado a Teradata neste projeto), COMO montar a entrada dos geradores, e COMO conduzir as 8
> fases. A fonte normativa dos mapeamentos/regras é `kb/teradata-migration/` +
> `kb/migration/concepts/*` + `kb/databricks/concepts/lakehouse-federation.md` — este skill é o "como
> fazer". **Leia também `audits/2026-08-02-curso-teradata-migration-vs-ai-data-agents.md` §2 antes de
> confiar em qualquer trecho do curso-fonte oficial — ele está contaminado com Snowflake.**

## Fluxo (8 fases + gate de aprovação)
`DISCOVER → ASSESS → DESIGN → [GATE: SPEC + aprovação humana] → CONVERT → INGEST → CDC → VALIDATE → CUTOVER`

## Passo 1 — DISCOVER

**Sem MCP dedicado a Teradata.** O MCP `migration_source` deste projeto só suporta
`type: "sqlserver"` e `type: "postgresql"` — não fala o protocolo Teradata. Discovery é
**majoritariamente manual**: peça ao usuário/DBA para rodar os comandos abaixo via **BTEQ ou JDBC**
(nunca "Beeline" — isso é a ferramenta CLI do Hive/HiveServer2, sem nenhuma relação com Teradata) e
colar/exportar o resultado de volta para você. **Nunca invente um resultado de DDL, volume ou policy
que não foi fornecido.**

### 1.1 Schema Teradata (o insumo do gerador — obrigatório)

```sql
-- Via BTEQ, uma tabela por vez:
.LOGON <host>/<user>,<password>
SHOW TABLE <db>.<tabela>;
.LOGOFF
```

Em lote, primeiro liste as tabelas físicas via dicionário e depois rode `SHOW TABLE` para cada uma:

```sql
-- DBC.TablesV: TableKind = 'T' são tabelas físicas (View 'V', outros códigos não detalhados
-- de forma confiável na fonte auditada — usar 'T' para o inventário de DDL a converter).
SELECT TRIM(DatabaseName) || '.' || TRIM(TableName) AS full_name
FROM DBC.TablesV
WHERE DatabaseName = '<db>' AND TableKind = 'T'
ORDER BY 1;
```

Concatene todos os `CREATE [SET|MULTISET] TABLE` num único arquivo `.sql` — é esse arquivo que
`scripts/teradata_generate.py` consome (Passo 4). **Não edite manualmente** o DDL bruto antes de rodar
o gerador — ele já lida com opções de tabela/tipos; editar à mão reintroduz o risco que o gerador
existe para evitar.

### 1.2 Volume

```sql
-- Volume por tabela (CurrentPerm em bytes, soma por AMP)
SELECT DatabaseName, TableName, SUM(CurrentPerm) AS bytes_total
FROM DBC.TableSizeV
WHERE DatabaseName = '<db>'
GROUP BY 1, 2
ORDER BY 3 DESC;

-- Estatísticas de coluna já coletadas (cardinalidade, nulos)
SELECT * FROM DBC.TableStatsV WHERE DatabaseName = '<db>' AND TableName = '<tabela>';
```

### 1.3 Query log e consumidores

```sql
-- Quem consulta o quê (histórico de queries — DBQL precisa estar habilitado na origem)
SELECT UserName, DBQLLogTbl.DefaultDatabase, QueryText, StartTime
FROM DBC.DBQLLogTbl
WHERE StartTime >= CURRENT_DATE - 30
ORDER BY StartTime DESC;
```

### 1.4 Dicionário de tipos `DBC.ColumnsV.ColumnType` (referência rápida)

**Esta é a fonte correta e genuinamente Teradata para o catálogo de tipos — nunca use uma tabela de
tipos "Teradata" vinda do curso-fonte sem cruzar com esta, que vem do Teradata Language Reference.**

| Código | Tipo | Código | Tipo |
|---|---|---|---|
| `I` | INTEGER | `CF`/`CV`/`CO` | CHAR/VARCHAR/CLOB |
| `I1` | BYTEINT | `BF`/`BV`/`BO` | BYTE/VARBYTE/BLOB |
| `I2` | SMALLINT | `JN` | JSON |
| `I8` | BIGINT | `XM` | XML |
| `F` | FLOAT | `PD`/`PT`/`PS`/`PM` | PERIOD(DATE/TIME/TIMESTAMP/...) |
| `D` | DECIMAL | `YR`/`YM`/`MO`/`DY`/... | INTERVAL(...) |
| `N` | NUMBER | `A1`/`AN` | ARRAY |
| `DA` | DATE | `UT` | UDT |
| `AT` | TIME | `TZ`/`SZ` | TIME/TIMESTAMP WITH TIME ZONE |
| `TS` | TIMESTAMP | | |

Use esta tabela para interpretar `DBC.ColumnsV.ColumnType` durante o discovery; o mapa completo
código→tipo Delta vive no gerador (`scripts/teradata_generate.py`, dict `_PRIM`) e em
`kb/teradata-migration/concepts/ddl-conversion.md`.

### 1.5 Índices — Primary Index, Secondary Index, Join Index

```sql
SELECT DatabaseName, TableName, IndexType, IndexNumber, ColumnName
FROM DBC.IndicesV
WHERE DatabaseName = '<db>' AND TableName = '<tabela>'
ORDER BY IndexNumber;
```

`IndexType` inclui `P` (Primary Index), `S` (Secondary Index) e `J` (Join Index) — os demais códigos
não são detalhados de forma confiável na fonte auditada; na dúvida, cruze com o Teradata Vantage SQL
Data Dictionary oficial. **Join Index e Secondary Index (USI/NUSI) não têm equivalente 1:1 no Delta**
— sinalize para a Fase 2/3 como candidato a ⚠️ revisão manual/redesign (nunca conversão mecânica).

### 1.6 Segurança e TASM

```sql
-- Roles e GRANTs
SELECT * FROM DBC.AllRightsV WHERE UserName = '<user>' OR DatabaseName = '<db>';

-- Regras de workload management (TASM) — exportar ANTES de qualquer decommission,
-- é o único registro das regras de priorização/throttling em uso.
SELECT * FROM DBC.WorkloadDefinitions;
```

**Buffer-safe:** para ambientes grandes (>50 tabelas), NÃO despeje o output bruto de cada
`SHOW TABLE` no contexto de uma vez — grave um índice compacto em
`<saída>/_work/discovery_index.json` (database, tabela, nº de colunas, PI/PPI, volume) e trabalhe
sobre o índice.

Consolide os achados nas 5 categorias de `kb/migration/concepts/discovery-assessment.md` §1: **Data
Assets**, **Pipelines & ETL** (BTEQ/TPT/FastLoad/MultiLoad), **Consumers & Users**, **Security &
Access** (roles/TASM), **Operations & SLAs**.

## Passo 2 — ASSESS (scoring, waves, estratégia)

Pontue cada workload (database/domínio Teradata) na **Complexity Scoring Matrix** adaptada de
`discovery-assessment.md` §2, 7 dimensões, 1-4 pontos cada:

| Dimensão | 1pt | 2pt | 3pt | 4pt |
|---|---|---|---|---|
| Table Count | <10 | 10-50 | 50-200 | >200 |
| Data Volume | <10GB | 10-100GB | 100GB-1TB | >1TB |
| SQL/BTEQ/SPL Complexity | DML simples | CTE/window/macro | BTEQ multi-statement | SPL com lógica de negócio complexa |
| TASM/Workload Complexity | sem TASM | poucas regras simples | múltiplos workload classifiers | throttling/priorização complexa multi-tier |
| Dependencies | nenhuma | 1-3 upstream | 4-10 upstream | >10/circular |
| SLA Sensitivity | nenhuma/batch | SLA diário | SLA horário | real-time |
| Consumers | 1 time | 2-5 times | enterprise-wide | externo/customer-facing |

Soma → wave: **6-10=Wave1, 11-16=Wave2, 17-20=Wave3, 21+=Wave3 c/ especialista** (idêntico aos
cursos-irmãos SQL Server/Hadoop).

**Árvore de decisão Analytics-First vs ETL-First** (`discovery-assessment.md` §5): driver
custo/compliance → **ETL-First**; driver quick-win/IA-BI → **Analytics-First**; default **ETL-First**.

Confirme o **deployment vector** (Teradata on-premises legado vs VantageCloud) — decide a viabilidade
de Lakehouse Federation (`CREATE CONNECTION ... TYPE teradata` exige DBR 16.1+ ou SQL Warehouse
pro/serverless 2024.50+, autenticação **TD2** apenas — ver Passo 5).

## Passo 3 — DESIGN

Proponha Medallion (Bronze/Silver/Gold) e, por tabela, o padrão de ingestão por volume (Passo 5):
**JDBC** (<1GB), **`WRITE_NOS`→Auto Loader** (1-100GB), **`WRITE_NOS` particionado + TPT** (>100GB).
Esboce o modelo de governança (TASM → SQL Warehouse profiles/Job Clusters; roles/`GRANT` → UC
`GRANT`/ABAC). Identifique Join Index/índices secundários em uso (Passo 4c). Isto compõe o **SPEC**.

## GATE — Documento de proposta (SPEC) + aprovação humana (obrigatório)

Entregue o SPEC (formato no `registry/teradata-to-databricks.md` § Formato de Resposta) e **PARE**.
Este projeto adota "sempre documento + aprovação para migrações" (Constituição §2.2 / Supervisor Step
0.6A).

> **O GATE é uma FRONTEIRA DE TURNO, não um passo sequencial.** Entregue o SPEC e **encerre** — quem
> aprova é o **usuário**, numa mensagem seguinte. NÃO gere DDL/código no mesmo turno do SPEC. Um hook
> de enforcement (`enforce_migration_gate`) bloqueia uma 2ª delegação de migração no mesmo turno; se
> você for bloqueado, é sinal de que deveria ter parado — apresente o SPEC e aguarde.

## Passo 4 — CONVERT (só após aprovação) — DETERMINÍSTICO, dirigido por DDL

**Regra de ouro:** NÃO escreva DDL/SQL à mão **e NÃO escreva seu próprio gerador** (`generate_*.py`).
Use o arquivo `.sql` do Passo 1.1 (concatenação de `SHOW TABLE`) diretamente:

```bash
python scripts/teradata_generate.py teradata_ddl_raw.sql output/teradata-migration/<slug>
```

Ele emite, **correto-por-construção**:

- `01_ddl_delta.sql` — `CREATE TABLE IF NOT EXISTS catalog.gold.<tabela> ... USING DELTA` com tipos
  mapeados (dict `_PRIM`), `CLUSTER BY` combinando colunas de PRIMARY INDEX + PPI, `COMMENT` com o
  tipo Teradata original (auditoria), `CONSTRAINT ... PRIMARY KEY (...) RELY` se havia
  `UNIQUE PRIMARY INDEX`, aviso inline se a tabela era `SET` (dedup obrigatório — R8).
- `02_type_flags.md` — colunas que exigem revisão manual (`PERIOD`, `INTERVAL`, `ARRAY`/`VARRAY`,
  tipos Teradata desconhecidos) + lista de tabelas `SET` que precisam de deduplicação na ingestão.
- `03_reconcile_spec.json` — spec **pronto** para `scripts/reconcile_generate.py`, já gravado com
  `"source_dialect": "teradata"` (keys = colunas de PRIMARY INDEX, colunas numéricas exatas/float,
  datas, `float_tolerance_pct: 0.0001`).

**Esses arquivos SÃO os entregáveis de DDL.** Não os reescreva à mão, não os "melhore", não gere um
`generate_*.py` paralelo.

### 🔴 GATE ANTI-CONTAMINAÇÃO SNOWFLAKE (rodar e ler antes de aceitar qualquer saída)

O curso-fonte oficial *"Delivery Expert for Teradata Migration"* está **fortemente contaminado** com
material de um curso-irmão de **Snowflake** (dataset "Tasty Bytes"/`TB_101`, find-replace imperfeito)
— confirmado por auditoria completa em `audits/2026-08-02-curso-teradata-migration-vs-ai-data-
agents.md` §2. `scripts/teradata_generate.py` roda um gate na **entrada** que procura por tokens que
são do Snowflake e **NÃO** do Teradata:

| Token/Padrão | Por que NÃO é Teradata |
|---|---|
| `VARIANT`, `OBJECT` (como tipo de coluna) | São do Snowflake. Teradata **tem** `VARIANT_TYPE`, mas é um UDT exclusivo para **parâmetro de UDF/table operator** — nunca um tipo de coluna semiestruturada |
| `ARRAY_AGG`, `ARRAY_UNIQUE_AGG`, `OBJECT_AGG` | Funções Snowflake |
| `IFF(` | Função Snowflake (Teradata usa `CASE WHEN`) |
| `EQUAL_NULL` | Função Snowflake (Teradata usa `IS [NOT] DISTINCT FROM`) |
| `LATERAL FLATTEN` | Sintaxe Snowflake (Teradata usa `JSON_TABLE`/`EXPAND ON`) |
| `METADATA$*` (`METADATA$ACTION`, `METADATA$ISUPDATE`) | Pseudo-colunas de **Snowflake Streams** — Teradata não tem objeto Stream |
| `RUNTIME_VERSION=`, `HANDLER=` | Sintaxe de UDF do Snowflake — Teradata usa Script Table Operator/BYOM |
| `TB_101`, `RAW_POS` | Dataset de demo público da Snowflake ("Tasty Bytes") |
| `TIMESTAMP_NTZ`, `TIMESTAMP_LTZ`, `TIMESTAMP_TZ` | Nomes de tipo Snowflake/Databricks — Teradata usa `TIMESTAMP(n)` e `TIMESTAMP(n) WITH TIME ZONE` |

**Se o gate detectar qualquer um desses tokens na entrada, o build FALHA (código de saída ≠ 0) — trate
isso como um sinal real de que a "fonte Teradata" pode não ser Teradata genuína.** Nunca contorne,
ignore, ou remova o gate; investigue a origem do arquivo com o usuário antes de prosseguir.

Verifique também os demais gates do gerador: nenhuma opção de tabela Teradata (`FALLBACK`,
`JOURNAL`, `CHECKSUM=`, `MERGEBLOCKRATIO`, `MAP=`, `CASESPECIFIC`, `CHARACTER SET`) vazando no
`01_ddl_delta.sql` final; nenhum identificador sem backtick.

### Passo 4b — SQL/BTEQ/SPL

A maioria do SQL Teradata roda com poucos ajustes no Databricks SQL. Catálogo de funções (limpo de
contaminação, `kb/teradata-migration/concepts/function-catalog.md`):

| Teradata | Databricks | Nota |
|---|---|---|
| `QUALIFY` | `QUALIFY` | Nativo no Databricks SQL desde DBR 10.4 LTS — sem tradução necessária |
| `SAMPLE n` | `TABLESAMPLE` | |
| `LISTAGG(col) WITHIN GROUP (ORDER BY ...)` | `ARRAY_JOIN(COLLECT_LIST(col), ',')` | Ordenação requer `SORT_ARRAY`/subquery ordenada antes do `COLLECT_LIST` |
| `OREPLACE(str, a, b)` | `REPLACE(str, a, b)` | |
| `INDEX(str, sub)` | `INSTR(str, sub)` | |
| `CHARACTERS(str)` | `LENGTH(str)` | |
| `ZEROIFNULL(col)` | `COALESCE(col, 0)` | |
| `NULLIFZERO(col)` | `NULLIF(col, 0)` | |
| `ADD_MONTHS(d, n)` | `ADD_MONTHS(d, n)` | Idêntico |
| `(dt2 - dt1) DAY` | `DATEDIFF(dt2, dt1)` | |
| `COLLECT STATISTICS ON t COLUMN c` | `ANALYZE TABLE t COMPUTE STATISTICS FOR COLUMNS c` | |

**Gaps do curso-fonte (funções OLAP genuinamente Teradata que o curso omite — grep confirmou zero
ocorrências no catálogo de funções do curso):** `CSUM`/`MSUM`/`MAVG`/`MDIFF` (cumulative/moving
sum/avg/diff), `RESET WHEN`, `NORMALIZE`, `EXPAND ON` (para `PERIOD`), `PIVOT`/`UNPIVOT`, `OTRANSLATE`,
`SEL`, `TOP n`. Mapeie manualmente para window functions Spark (`SUM(...) OVER (ORDER BY ... ROWS
BETWEEN ...)` para `CSUM`/`MSUM`; `AVG(...) OVER (... ROWS BETWEEN n PRECEDING ...)` para `MAVG`;
`LAG`/`LEAD` para `MDIFF`). `RESET WHEN` não tem frame ANSI direto — marque ⚠️ revisão manual.

Para volume, use **Lakebridge/BladeBridge**: `remorph transpile --source teradata --input-sql <dir>
--output-folder <dir> --catalog-name <cat> --schema-name <schema>` — o Analyzer reconhece BTEQ,
`.fload` e `.mload`, mas **o Agentic Converter ainda não suporta BTEQ** (use o transpile clássico e
sempre revise a saída). Para SPL (Stored Procedure Language): classifique Databricks SQL Scripting
(DBR 16+) vs PySpark conforme complexidade.

### Passo 4c — Join Index / Índices Secundários (flag de redesign, nunca mecânico)

**Join Index** é uma pré-agregação/pré-join física mantida pelo otimizador Teradata — **sem
equivalente 1:1** no Delta. A aproximação é uma materialized view ou tabela pré-agregada, mas isso é
trabalho de **design**, não conversão mecânica: avalie o padrão de consulta real antes de propor.
**Secondary Index** (USI/NUSI) são estruturas de acesso — no Delta, avalie Liquid Clustering
adicional, Z-ORDER ou Bloom filter index conforme o padrão de acesso (scans vs point lookups), nunca
"traduza" 1:1 a existência de um índice secundário.

## Passo 5 — INGEST

Documente o contrato Bronze→Silver→Gold (schema-alvo do `01_ddl_delta.sql` + star schema Gold).
Escolha por tabela (do Passo 3), **decisão determinística por volume**:

| Volume | Padrão | Mecanismo |
|---|---|---|
| < 1GB | JDBC direto | `com.teradata.jdbc.TeraDriver` |
| 1-100GB | `WRITE_NOS` → Auto Loader | Native Object Store exporta para Parquet em cloud storage; Auto Loader/`COPY INTO` ingere |
| > 100GB | `WRITE_NOS` particionado + TPT | Teradata Parallel Transporter (unifica FastLoad/MultiLoad/FastExport/TPump) paraleliza a extração por partição/range |

Antes de exportar via `WRITE_NOS`, converta tipos sem serialização direta: `TIME`/`PERIOD`/
`INTERVAL`/`BYTE` → `CAST(... AS VARCHAR)`.

**Lakehouse Federation (`CREATE CONNECTION ... TYPE teradata`)** — confirmado oficialmente
(`kb/databricks/concepts/lakehouse-federation.md`, seção Federation genérico; fatos Teradata
verificados em `audits/2026-08-02-curso-teradata-migration-vs-ai-data-agents.md` §3.6): foreign
catalog no Unity Catalog, requer **DBR 16.1+** ou **SQL Warehouse pro/serverless 2024.50+**,
autenticação **TD2** (usuário/senha) apenas, porta **1025**. Use **só** para discovery, perfilamento
e validação de schema/contagens durante a transição — **nunca** para fact tables grandes (mesmas
regras de pushdown/limitações da Federation genérica — ver `lakehouse-federation.md` §2).

**Interoperabilidade Iceberg/UniForm:** Teradata Vantage (Database Engine 20+) pode ler tabelas Unity
Catalog via `CREATE DATALAKE ... TABLE FORMAT ICEBERG`, permitindo coexistência bidirecional durante a
migração (Teradata lendo Delta/UniForm; Databricks lendo Teradata via Federation).

Implementação pesada do pipeline (Auto Loader, Lakeflow SDP/DLT, jobs de produção) → **escalar
`databricks-engineer`**.

## Passo 6 — CDC

Teradata **não tem objeto Stream nativo** (diferente do Snowflake — não confundir; o próprio
curso-fonte afirma isso corretamente numa seção e se autocontradiz usando pseudo-colunas
`METADATA$*` de Stream 166 linhas depois, ver R16). Identifique o mecanismo real por tabela:

- **Timestamp-based**: watermark (coluna de última modificação) + `MERGE` incremental.
- **Log-based via terceiros**: ferramentas de CDC de log de transação (Qlik, Informatica, HVR) —
  comum quando não há coluna de watermark confiável.
- **TPT CDC**: extração incremental via Teradata Parallel Transporter configurado para captura de
  mudança.

`CREATE VOLATILE TABLE ... ON COMMIT PRESERVE ROWS` é um construto real de **staging de sessão**
(tabela temporária que sobrevive a commits dentro da sessão) — mapeia para `TEMP VIEW`/tabela
transiente no Databricks, **não é em si um mecanismo de CDC**.

**SCD Type 2 sempre `AUTO CDC` com `STORED AS SCD TYPE 2`** — nunca `LAG`/`ROW_NUMBER` manual
(sintaxe completa em `kb/spark-patterns/patterns/lakeflow-patterns.md`, regra R4 de
`kb/spark-patterns/concepts/sdp-rules.md`). Implementação de produção → `databricks-engineer`.

## Passo 7 — VALIDATE — DETERMINÍSTICO, 2 fases obrigatórias

```bash
python scripts/reconcile_generate.py output/teradata-migration/<slug>/03_reconcile_spec.json output/teradata-migration/<slug>
```

Como o spec do Passo 4 já grava `"source_dialect": "teradata"`, o gerador **automaticamente**:
- usa identificadores ANSI aspas-duplas (`"col"`) no lado `source` (correto para Teradata) — **sem
  necessidade de ajuste manual de quoting**, diferente do que o `hadoop-to-databricks` precisa fazer
  para HiveQL/Beeline.
- **pula a amostra de hash row-a-row no lado Teradata**, deixando um comentário explicando o porquê
  (Teradata não tem MD5 nativo em toda versão) e recomendando confiar nos agregados (count/sum/null/
  distinct/min-max) ou construir uma UDF MD5 na origem para uma comparação real.

Emite `reconcile_source.sql`, `reconcile_target.sql` (Databricks SQL — roda como está), e
`reconcile_report.md`. Execute a **regra das 2 fases** (`kb/migration/concepts/reconciliation.md` §2):
Fase 1 snapshot aprovada ANTES do CDC/sync incremental ligar; Fase 2 só o delta.

**⚠️ Estimador de STDDEV/VARIANCE (bug real confirmado no curso-fonte, RC07 de
`reconciliation.md`):** Teradata expõe `STDDEV_POP`/`STDDEV_SAMP` explícitos; no Databricks
`STDDEV()` = `STDDEV_SAMP` e `VARIANCE()` = `VAR_SAMP`. Comparar `STDDEV_POP` do Teradata com
`STDDEV()` do Databricks **diverge matematicamente** — sempre case o estimador
(`STDDEV_POP`↔`stddev_pop`, `STDDEV_SAMP`↔`stddev`/`stddev_samp`, `VAR_POP`↔`var_pop`,
`VAR_SAMP`↔`variance`/`var_samp`) antes de comparar. Validação estatística avançada (drift, KS test)
→ escalar `data-quality-steward`.

## Passo 8 — CUTOVER

Aplique o runbook de `kb/migration/concepts/cutover-rollback.md`, com o padrão Teradata-específico:
1. Escolha uma estratégia de cutover — **Big Bang** ou **Blue-Green** (via `WRITE_NOS`/
   `APPLY CHANGES INTO` para capturar o delta final) são as citadas pelo curso-fonte.
2. Delta/sync catch-up final → reconciliação final (Passo 7, Fase 2) → **Go/No-Go Gate**.
3. **Decommission Readiness Check**: cruze `information_schema.tables` (destino, o que já foi
   migrado) × `system.access.audit` (quem realmente consome o quê) antes de sequer considerar
   desligar qualquer parte do Teradata — confirma que nenhum consumidor ainda depende da origem.
4. Switchover de consumidores (dashboards, jobs downstream) → smoke test.
5. **Matriz de rollback numérica:** <0.01% ok; 0.01–1% investigar; **>1% rollback imediato**; falha
   de dashboard crítico ou degradação de performance >50% sem resolução em 1h também disparam
   rollback.
6. **Hypercare** 1-2 semanas + **sign-off explícito por owner** — nunca decommission prematuro; o
   Teradata permanece live até todos os consumidores migrarem.

Antes de qualquer decommission, exporte `DBC.WorkloadDefinitions` (TASM) — é o único registro das
regras de priorização/throttling em uso e deve ser preservado para auditoria mesmo após o cutover.

## Passo Final — AUTO-REVISÃO de sanidade (obrigatório antes de reportar concluído)

NÃO reporte "concluído" se algum falhar:
- [ ] **SPEC foi aprovado** antes de qualquer CONVERT (o gate não foi pulado).
- [ ] **Gate anti-contaminação Snowflake passou** (0 tokens detectados na entrada) — se detectou algo,
  a fonte foi reavaliada com o usuário, não ignorada.
- [ ] **Discovery (5 categorias) precedeu o design** — nenhuma decisão de arquitetura sem dados do
  Passo 1.
- [ ] **Gerador de DDL rodou e passou nos gates:** `scripts/teradata_generate.py` saiu com **código
  0** (sem opção de tabela Teradata vazando, sem identificador sem backtick, sem tipo desconhecido não
  revisado).
- [ ] **Gerador de reconciliação rodou e passou nos gates:** `scripts/reconcile_generate.py` saiu com
  **código 0** (toda tabela com `target`).
- [ ] **Sem gerador próprio:** os entregáveis SÃO os arquivos dos dois scripts; nenhum `generate_*.py`
  reescrito nem SQL de reconciliação escrito à mão.
- [ ] **Tabelas `SET`:** dedup explícito documentado na ingestão para cada uma (nunca ignorado o
  aviso do gerador).
- [ ] **Join Index/índices secundários:** nenhum convertido mecanicamente; marcados ⚠️ redesign.
- [ ] **Reconciliação em 2 fases:** Fase 1 aprovada antes do CDC/sync incremental; Fase 2 (delta)
  rodada separadamente; estimador de STDDEV/VARIANCE casado.
- [ ] **Cutover:** estratégia documentada (Big Bang/Blue-Green), Decommission Readiness Check
  executado, matriz de rollback aplicada, sign-off documentado — nunca decommission antes de todos os
  consumidores migrarem.
- [ ] **PII/TASM:** nenhuma policy/mask com PII gerada sem passar por `governance-auditor`.
- [ ] **Relatório == código, COM `grep`:** para CADA feature alegada (DDL, CDC ativo, TASM mapeado,
  reconciliação aprovada, cutover concluído) rode `grep -rn` no diretório de saída; se não achar,
  **APAGUE a alegação**. A tabela de artefatos bate com `find <saída> -type f`.

## Anti-patterns (fortes)

❌ Pular o discovery (5 categorias) antes de propor design. ❌ Gerar DDL/código antes da aprovação do
SPEC — ou no MESMO turno do SPEC. ❌ **Escrever o DDL ou o SQL de reconciliação à mão** — rode
`scripts/teradata_generate.py`/`scripts/reconcile_generate.py`. ❌ **Escrever seu próprio gerador**
(`generate_*.py`) — cada run reintroduz bug novo; consuma a saída dos geradores únicos. ❌ **Tratar
qualquer trecho do curso-fonte oficial como verdade sem passar pelo gate anti-Snowflake** — o curso
está comprovadamente contaminado (`VARIANT`/`OBJECT`/`ARRAY_AGG`/`IFF`/`EQUAL_NULL`/`LATERAL FLATTEN`/
`METADATA$*`/`RUNTIME_VERSION`/`HANDLER=` são Snowflake, não Teradata). ❌ Converter Join Index ou
índices secundários mecanicamente — sempre ⚠️ redesign. ❌ Ingerir uma tabela `SET` sem deduplicação
explícita — o Delta não rejeita duplicatas como o Teradata fazia. ❌ Rodar a reconciliação do
snapshot e do CDC/sync na mesma passada (mascara a causa raiz). ❌ Comparar `STDDEV_POP` (Teradata)
com `STDDEV()` (Databricks) sem casar o estimador — diverge matematicamente. ❌ Usar Lakehouse
Federation para fact tables multi-TB (usar `WRITE_NOS`/TPT + Auto Loader/`COPY INTO`). ❌ Assumir que
o dicionário `DBC.*` tem um MCP dedicado neste projeto — é discovery manual via BTEQ/JDBC. ❌
Decommission prematuro do Teradata antes de todos os consumidores migrarem, do Decommission Readiness
Check e de sign-off formal. ❌ Migrar sem reconciliação em 2 fases nem runbook de cutover.
