# Catálogo de Conversão Teradata DDL → Databricks/Delta

> Catálogo normativo para a conversão de **DDL Teradata** (`SHOW TABLE`, `DBC.ColumnsV`/`DBC.IndicesV`,
> `CREATE [SET|MULTISET] TABLE`) para **Delta Lake / Unity Catalog**. Irmão de
> `kb/hadoop-migration/concepts/hive-ddl-conversion.md` e `kb/sql-patterns/concepts/tsql-conversion-catalog.md`
> (mesmo padrão, origens Hive/SQL Server). Consultar SEMPRE antes de gerar DDL Delta a partir de DDL
> Teradata. NÃO inventar mapeamentos — construto sem equivalente claro → marcar `[a verificar]`.
> **O gerador determinístico `scripts/teradata_generate.py` implementa exatamente este catálogo** —
> se este arquivo e o gerador divergirem, o gerador é o desempate técnico (ele roda gates que falham o
> build); atualize os dois juntos.

**Domínio:** teradata-migration — Conversão DDL Teradata → Delta (Migração)
**Fonte:** Digests auditados `_digest_fase3.md` §1 (DDL/tipos), `_digest_fase0-2.md` §1 (feature
mapping), citando o curso oficial Databricks "Delivery Expert for Teradata Migration" —
`03 - Execute/3.1 Lecture - Schema and DDL Conversion.md` (2013 linhas, lidas 100%).
**Agentes:** migration-expert, databricks-engineer

---

## ⚠️ Nota de Auditoria — Contaminação do Template Snowflake (crítica, ler antes de tudo)

O curso-fonte reaproveita, em pontos concretos e identificados, **dataset, tipos e funções do
Snowflake** (schema `TB_101`/Tasty Bytes, tipos `VARIANT`/`OBJECT`, sintaxe `col:field::TYPE`) como se
fossem Teradata — muito provavelmente herdado mal-adaptado de um curso-irmão "Snowflake Migration".
Evidência concreta (`_digest_fase3.md` §8, achado 1): a tabela "oficial" de mapeamento de tipos do
curso (`3.1:339-359`) lista `VARIANT`→`VARIANT` e `OBJECT`→`VARIANT` na coluna "Teradata Type", e
`3.1:1006` afirma literalmente *"Databricks now supports a native `VARIANT` type that directly maps to
Teradata's `VARIANT` and `OBJECT` types"* — **falso**: Teradata clássico não tem tipos de coluna
`VARIANT`/`OBJECT` (semi-estruturados). **Este arquivo usa como fonte de tipos SOMENTE os códigos reais
de `DBC.ColumnsV.ColumnType`** (`3.1:144-185`, reproduzidos abaixo em §1) — nunca a tabela contaminada
de `3.1:339-359`.

**Nunca rotular como "tipo Teradata" nenhum destes** (são Snowflake — só podem aparecer no lado de
SAÍDA/Databricks, ou numa nota explícita "isto é Snowflake, não Teradata"): `VARIANT`, `OBJECT`,
`TIMESTAMP_NTZ`, `TIMESTAMP_LTZ`, `TIMESTAMP_TZ` (como nome de tipo Teradata — Teradata usa `TIMESTAMP(n)`
e `TIMESTAMP(n) WITH TIME ZONE`), dataset `TB_101`/`RAW_POS`. Detalhe completo dos 14 achados de
contaminação: `_digest_fase3.md` §8; síntese: `audits/2026-08-02-curso-teradata-migration-vs-ai-data-agents.md` §2.
`scripts/teradata_generate.py` implementa um **gate automático** que falha o build se esses tokens
aparecerem na entrada — se aparecerem numa "fonte Teradata" real do usuário, sinalize que a fonte pode
não ser Teradata genuína antes de prosseguir.

---

## 1. Mapa de Tipos — Teradata → Delta

### 1.1 Fonte de verdade: `DBC.ColumnsV.ColumnType` (códigos de 1-2 letras)

Único lugar do curso com o dicionário de tipos **completo e genuinamente Teradata** — reproduzido
integralmente porque é a base normativa deste catálogo (curso `3.1:144-185`, via `_digest_fase3.md` §1.1):

| Código | Tipo Teradata | Código | Tipo Teradata |
|---|---|---|---|
| `I` | INTEGER | `PD` | PERIOD(DATE) |
| `I1` | BYTEINT | `PT` | PERIOD(TIME) |
| `I2` | SMALLINT | `PS` | PERIOD(TIMESTAMP) |
| `I8` | BIGINT | `PM` | PERIOD(TIMESTAMP WITH TIME ZONE) |
| `F` | FLOAT | `UT` | UDT |
| `D` | DECIMAL | `A1`/`AN` | ARRAY |
| `N` | NUMBER | `YR` | INTERVAL YEAR |
| `DA` | DATE | `YM` | INTERVAL YEAR TO MONTH |
| `AT` | TIME | `MO` | INTERVAL MONTH |
| `TS` | TIMESTAMP | `DY` | INTERVAL DAY |
| `TZ` | TIME WITH TIME ZONE | `DH` | INTERVAL DAY TO HOUR |
| `SZ` | TIMESTAMP WITH TIME ZONE | `DM` | INTERVAL DAY TO MINUTE |
| `CF` | CHAR | `DS` | INTERVAL DAY TO SECOND |
| `CV` | VARCHAR | `HR` | INTERVAL HOUR |
| `CO` | CLOB | `HM` | INTERVAL HOUR TO MINUTE |
| `BF` | BYTE | `HS` | INTERVAL HOUR TO SECOND |
| `BV` | VARBYTE | `MI` | INTERVAL MINUTE |
| `BO` | BLOB | `MS` | INTERVAL MINUTE TO SECOND |
| `JN` | JSON | `SC` | INTERVAL SECOND |
| `XM` | XML | | |

`NUMBER` (código `N`) e as variantes `INTERVAL *` **são tipos Teradata genuínos** confirmados por este
dicionário — apesar de o digest de fases 0-2 não ter encontrado exemplo de `CREATE TABLE` prático com
eles (`_digest_fase0-2.md` §1.2); trate-os como reais, apenas sem exemplo de DDL completo no corpus.

### 1.2 Mapa Delta — o que o gerador (`teradata_generate.py`, dict `_PRIM` + `map_type()`) aplica

| Teradata | Delta/Databricks | Nota |
|---|---|---|
| `BYTEINT` | `TINYINT` | 1 byte, -128..127 — Databricks/Spark **tem** `TINYINT`; mapeamento direto (o curso nunca afirma isso explicitamente, mas é o mapeamento correto e é o que o gerador implementa) |
| `SMALLINT` | `SMALLINT` | Direto |
| `INTEGER` / `INT` | `INT` | Direto |
| `BIGINT` | `BIGINT` | Direto |
| `FLOAT` / `REAL` | `DOUBLE` | Teradata `FLOAT`/`REAL` é sempre 64-bit IEEE — mapear para `DOUBLE`, nunca para Spark `FLOAT` (32-bit). Mesma regra já usada para SQL Server em `reconciliation.md` §3.1; confirmada para Teradata em `_digest_fase4-6.md` §1.3 |
| `DOUBLE PRECISION` | `DOUBLE` | Direto |
| `DECIMAL(p,s)` / `NUMERIC(p,s)` / `NUMBER(p,s)` | `DECIMAL(p,s)` | Precisão máxima 38 (curso `3.1:339-359`, item não-contaminado da tabela) |
| `NUMBER` (sem precisão declarada) | `DECIMAL(38,0)` | Fallback do gerador — revisar escala real na origem |
| `CHAR(n)` / `VARCHAR(n)` / `CLOB` | `STRING` | Sem fixed-length nem CLOB no Databricks — `STRING` é unbounded |
| `DATE` | `DATE` | Direto |
| `TIME(n)` [`WITH TIME ZONE`] | `STRING` | Spark não tem tipo `TIME` nativo — guardar `'HH:MM:SS(.ffffff)'` (curso `3.1:339-359`, gap real e corretamente tratado mesmo na tabela contaminada) |
| `TIMESTAMP(n)` (sem tz) | `TIMESTAMP_NTZ` | Teradata `TIMESTAMP(n)` é sem timezone por padrão → `TIMESTAMP_NTZ` é o Databricks nativo equivalente (**não confundir com a contaminação**: aqui `TIMESTAMP_NTZ` é usado corretamente do LADO DE SAÍDA Databricks, nunca como nome de tipo Teradata) |
| `TIMESTAMP(n) WITH TIME ZONE` | `TIMESTAMP` | Databricks `TIMESTAMP` é tz-aware (instante) — equivalente ao Teradata com fuso |
| `BYTE` / `VARBYTE` / `BLOB` | `BINARY` | Teradata real usa `BYTE`/`VARBYTE`/`BLOB` (não "BINARY" — esse é nome de tipo de destino, nunca de origem) |
| `PERIOD(DATE\|TIME\|TIMESTAMP[ WITH TIME ZONE])` | `STRING` (ou `STRUCT<start,end>` revisado manualmente) | **[flag]** Sem tipo direto — considerar `EXPAND ON` na origem para "achatar" antes de migrar (ver `function-catalog.md` §6) |
| `INTERVAL *` (YEAR/MONTH/DAY/HOUR/MINUTE/SECOND e combinações) | `STRING` (ou decompor em `BIGINT` de segundos/meses) | **[flag]** Sem tipo `INTERVAL` nativo mapeado 1:1 pelo gerador — revisar caso a caso |
| `JSON` | `STRING` | Ou `VARIANT` nativo em **DBR 15.3+** — aí sim uso correto e não-contaminado do tipo `VARIANT` (do lado Databricks) |
| `XML` | `STRING` | Sem tipo XML nativo |
| `BOOLEAN` | `BOOLEAN` | ⚠️ Teradata clássico não tem `BOOLEAN` nativo (usa `BYTEINT`/`CHAR(1)`); só Vantage recente pode ter — **`[a verificar]`** na origem antes de assumir |
| `ARRAY` / `VARRAY` | `STRING` (ou `ARRAY<type>` revisado) | **[flag]** Teradata Vantage recente tem `ARRAY`/`VARRAY` real — revisar tipo do elemento |
| `ST_GEOMETRY` / `GEOMETRY` | `STRING` (WKT via `ST_AsText()`) | Ou tipo `GEOGRAPHY` nativo **DBR 17.1+** — nome correto de origem é `ST_GEOMETRY`, não "GEOGRAPHY" (o curso usa "GEOGRAPHY" de forma imprecisa para o tipo Teradata) |
| Tipo desconhecido | `STRING` (fallback) + flag | Gerador sempre reporta em `02_type_flags.md` para revisão manual — nunca falha silenciosamente |

Cite: `_digest_fase3.md` §1.2 (tabela original + análise item a item), `scripts/teradata_generate.py`
(`_PRIM`, `map_type()`).

---

## 2. Opções de Tabela — SEMPRE Remover

DDL Teradata carrega opções de armazenamento/replicação físico sem equivalente em Delta Lake (Delta
gerencia redundância, compressão e transação automaticamente). **Remover incondicionalmente**:

| Opção Teradata | Exemplo | Ação Databricks |
|---|---|---|
| `FALLBACK` | `,FALLBACK ,` | Remover — redundância de storage cloud substitui a réplica de AMP |
| `NO BEFORE JOURNAL` / `NO AFTER JOURNAL` / `DUAL … JOURNAL` | `NO BEFORE JOURNAL, NO AFTER JOURNAL` | Remover — Delta transaction log + `RESTORE TABLE` cobrem o caso de uso |
| `CHECKSUM = DEFAULT\|ON\|OFF` | `CHECKSUM = DEFAULT` | Remover — Delta garante integridade via transaction log |
| `DEFAULT MERGEBLOCKRATIO` / `MERGEBLOCKRATIO = n` | `DEFAULT MERGEBLOCKRATIO` | Remover — Delta compacta automaticamente (`OPTIMIZE`) |
| `MAP = TD_MAPn` | `MAP = TD_MAP1` | Remover — sem conceito de mapa de storage físico no Delta |
| `COMPRESS (v1, v2, ...)` / `COMPRESS 'x'` | `COMPRESS ('M','F')` | Remover — Delta/Parquet comprime automaticamente (colunar) |
| `CHARACTER SET <charset>` | `CHARACTER SET LATIN` | Remover — `STRING` no Databricks é sempre UTF-8 |
| `[NOT] CASESPECIFIC` | `NOT CASESPECIFIC` | Remover — **⚠️ atenção de collation**: o curso afirma "Delta uses case-insensitive collation by default" (`3.1:1656`) — **isto é FALSO**, verificado na doc oficial: a collation padrão do Databricks é `UTF8_BINARY`, **case-sensitive** (`'A' <> 'a'`). Uma coluna `NOT CASESPECIFIC` na origem que dependia de comparação case-insensitive precisa de `LOWER()`/`UPPER()` explícito na query, ou de uma collation não-default — nunca assumir que o Delta replica o comportamento `NOT CASESPECIFIC` automaticamente |
| `FREESPACE n PERCENT` / `BLOCKCOMPRESSION` | — | Remover — parâmetros físicos sem equivalente Delta |

Cite: `_digest_fase3.md` §1.5 (tabela `3.1:1644-1656` "Table Options and Properties Comparison" +
achado de FALLBACK ausente da tabela + achado de collation incorreta), `scripts/teradata_generate.py`
(`_TABLE_OPTS` regex).

### Exemplo — Antes/Depois (DDL genuíno do curso, único `CREATE TABLE` Teradata completo do corpus)

```sql
-- Teradata (origem) — saída real de SHOW TABLE (curso 3.1:248-270)
CREATE SET TABLE YOUR_DATABASE_NAME.customer ,FALLBACK ,
     NO BEFORE JOURNAL,
     NO AFTER JOURNAL,
     CHECKSUM = DEFAULT,
     DEFAULT MERGEBLOCKRATIO,
     MAP = TD_MAP1
     (
      cust_id INTEGER,
      income INTEGER,
      age SMALLINT,
      gender CHAR(1) CHARACTER SET LATIN NOT CASESPECIFIC
      -- ... demais colunas omitidas no exemplo original
      )
UNIQUE PRIMARY INDEX ( cust_id );
```

```sql
-- Databricks — FALLBACK/JOURNAL/CHECKSUM/MERGEBLOCKRATIO/MAP/CHARACTER SET/CASESPECIFIC removidos;
-- SET TABLE → aviso de dedup obrigatório; UNIQUE PRIMARY INDEX → CLUSTER BY + PK RELY
-- ⚠️ ATENÇÃO: origem era SET TABLE (Teradata rejeita duplicatas exatas de linha).
-- O Delta NÃO tem análogo de SET table → a ingestão DEVE deduplicar explicitamente
--   (ROW_NUMBER() ... QUALIFY = 1  ou  MERGE), ou o resultado pode conter duplicatas.
CREATE TABLE IF NOT EXISTS catalog.gold.customer (
  `cust_id` INT COMMENT 'INTEGER',
  `income` INT COMMENT 'INTEGER',
  `age` SMALLINT COMMENT 'SMALLINT',
  `gender` STRING COMMENT 'CHAR(1) CHARACTER SET LATIN NOT CASESPECIFIC',
  CONSTRAINT `pk_customer` PRIMARY KEY (`cust_id`) RELY
) USING DELTA
CLUSTER BY (`cust_id`);
```

Cite: `_digest_fase3.md` §1.1 (DDL genuíno), §7.1 (regras determinísticas do gerador).

---

## 3. SET vs MULTISET — Gate Obrigatório de Dedup

**Semântica:** `SET` table rejeita linha duplicada exata na inserção (todas as colunas idênticas);
`MULTISET` permite duplicatas. **O curso nunca explica essa semântica nem dá orientação de conversão**
(`_digest_fase3.md` §1.3, gap confirmado, zero menção no checklist final de `3.1`) — apesar de
`CREATE SET TABLE` aparecer no único DDL genuíno do corpus (§2 acima) e `CREATE MULTISET TABLE` aparecer
em `3.2:228`.

**Regra normativa (preenchendo o gap do curso):**

- Delta Lake **sempre** se comporta como MULTISET — não há constraint de unicidade de linha física.
- **`SET` table de origem → a ingestão DEVE deduplicar explicitamente**, com `ROW_NUMBER() OVER (...)
  QUALIFY = 1` ou `MERGE`, ou o Delta resultante pode conter duplicatas que o Teradata nunca permitiu
  na fonte. Isso é um **gate de qualidade**, não uma opção.
- **`MULTISET` table de origem → sem gate adicional** (já permite duplicatas na fonte; comportamento
  preservado por padrão no Delta).

`scripts/teradata_generate.py` implementa esse gate automaticamente: toda tabela `SET` gera um
comentário de alerta obrigatório no topo do `CREATE TABLE` (ver exemplo em §2 acima) e é listada em
`02_type_flags.md` sob "Tabelas SET (dedup obrigatório na ingestão)".

Cite: `_digest_fase3.md` §1.3, §7.1 (regra 3 do gerador), `_digest_fase0-2.md` §1.1 (linha "Table
(SET/MULTISET) → Managed Delta Table" com nota "semântica de dedup de SET precisa de atenção").

---

## 4. PRIMARY INDEX / Partitioned Primary Index (PPI) → Liquid Clustering

### 4.1 PRIMARY INDEX / UNIQUE PRIMARY INDEX → CLUSTER BY (+ PK RELY)

Tabela `3.1:1649-1656` ("Table Options and Properties Comparison"): *"`PRIMARY INDEX (col)` — Row
distribution across AMPs; drives co-located joins and data skew risk → Remove; use Liquid Clustering
`CLUSTER BY (col)`"*.

```sql
-- PRIMARY INDEX (cols) / UNIQUE PRIMARY INDEX (cols) → CLUSTER BY (Liquid Clustering)
CLUSTER BY (cust_id, tran_date)

-- Se UNIQUE PRIMARY INDEX, adicionar também PK informacional (habilita otimizador, não é enforced)
CONSTRAINT pk_customer PRIMARY KEY (cust_id) RELY
```

`NUPI`/`UPI` (`DBC.IndicesV.UniqueFlag`) — a distinção unique/non-unique do índice primário **não** gera
unicidade enforced no Delta; vira apenas metadado/comentário (o `RELY` habilita otimizações de join,
nunca substitui validação real de unicidade — usar Lakeflow Declarative Pipelines expectations para
isso, mesmo padrão de `tsql-conversion-catalog.md` §2.2).

### 4.2 Partitioned Primary Index (PPI) — `RANGE_N`/`CASE_N` → CLUSTER BY ou PARTITIONED BY

**PPI é uma lacuna real de cobertura do curso** — o termo "PPI"/"PARTITIONED PRIMARY" nunca aparece
explicitamente no corpus (`_digest_fase3.md` §1.4, zero ocorrências confirmadas por grep). A única
referência é um comentário isolado dentro de um bloco de código genuíno:

```sql
-- Databricks (curso 3.1:1662-1676) — único exemplo real de particionamento pós-conversão
CREATE TABLE IF NOT EXISTS IDENTIFIER(:lab_catalog).demo_financial.credit_tran_clustered (
    cust_id       INT, tran_id INT, tran_date DATE, tran_amt DECIMAL(12,2), channel STRING
)
CLUSTER BY (tran_date, cust_id)   -- Liquid clustering: replaces Teradata PARTITION BY RANGE_N
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true', 'delta.deletedFileRetentionDuration' = 'interval 7 days')
COMMENT 'Checking transactions with liquid clustering enabled';
```

**Regra normativa de decisão (preenchendo o gap do curso, aplicada pelo gerador):**

- Extrair coluna(s) e granularidade de `RANGE_N(col BETWEEN ... AND ... EACH INTERVAL ...)` ou
  `CASE_N(...)`.
- **Cardinalidade de partição > 10⁴ valores distintos → preferir Liquid Clustering** (`CLUSTER BY`) —
  evita explosão de diretórios/partition skew.
- **Cardinalidade baixa e estável (≤ 10⁴) → `PARTITIONED BY (col)`** é aceitável.
- Quando a tabela tem **PRIMARY INDEX e PPI simultaneamente**, combinar as colunas em uma única
  `CLUSTER BY`, deduplicada — mesmo padrão que `hive_generate.py` já aplica para partição+bucket
  (`part_cols + pi_cols`, sem repetição); é exatamente o que `teradata_generate.py` faz
  (`t["pi_cols"] + t["part_cols"]`, `dict.fromkeys` para dedup).

Cite: `_digest_fase3.md` §1.4, §7.1 (regra do gerador), `_digest_fase0-2.md` §1.1 ("Partition Primary
Index (PPI) → Liquid Clustering (particionamento automático)").

---

## 5. Secondary Index / Join Index — Sem Equivalente 1:1

**Nunca gerar DDL automático para estes dois** — apenas comentário de migração assinalando revisão manual:

| Objeto Teradata | Ação recomendada |
|---|---|
| Secondary Index (SI) / Unique Secondary Index (USI) | Comentário: "considerar Z-Order/Liquid Clustering na(s) coluna(s) de filtro frequente" — sem tradução mecânica |
| Join Index (JI) | Comentário: "considerar Materialized View ou Lakeflow Streaming Table" — **fontes do curso divergem sobre o alvo exato**: `_digest_fase0-2.md` §1.1 sugere "Join Index → Materialized View"; `_digest_fase3.md` §1.4 cita uma linha de tabela dizendo "Join Index → Lakeflow Pipelines Streaming Table" (`3.1:1340`), mas **nenhum exemplo de `CREATE JOIN INDEX` real** aparece em nenhum dos dois materiais — avaliar caso a caso pelo padrão de consumo real, nunca assumir um dos dois automaticamente |
| Aggregate Join Index (AJI) | Comentário: "considerar Materialized View/Aggregate table" (`_digest_fase4-6.md` §2.4, mapa de otimização) |

Nenhum dos três tem tradução determinística no gerador — `scripts/teradata_generate.py` não emite DDL
para índices secundários/Join Index, apenas os ignora silenciosamente na extração de `PRIMARY INDEX`
(regex específica só casa `PRIMARY\s+INDEX`).

Cite: `_digest_fase3.md` §1.4, §7.1 (regra "Secondary Index (SI/USI) e Join Index (JI)"),
`_digest_fase0-2.md` §1.1, `_digest_fase4-6.md` §2.4.

---

## 6. IDENTITY / SEQUENCE

`SEQUENCE` Teradata → `GENERATED ALWAYS AS IDENTITY` (nova chave sempre gerada pelo sistema) ou
`UUID()` (se a PK precisa apenas ser única, não sequencial) — conforme o padrão de uso observado na
origem. Direto e sem ambiguidade (curso `3.1:1641`, `_digest_fase3.md` §1.5, §1.7).

---

## 7. VOLATILE TABLE → TEMP VIEW (nunca tabela gerenciada permanente)

`CREATE VOLATILE TABLE ... ON COMMIT PRESERVE ROWS` é sintaxe Teradata genuína (usada em CDC — ver
`ingestion-cdc.md` §8) para uma tabela de sessão temporária. **Nunca converter para tabela Delta
gerenciada permanente** — o equivalente correto é `CREATE OR REPLACE TEMP VIEW` (escopo de sessão),
preservando a semântica de "vida curta, sem persistência entre sessões".

Cite: `_digest_fase3.md` §3.1 (exemplo genuíno de `CREATE VOLATILE TABLE`), §7.1 (regra do gerador).

---

## 8. Views e Materialized Views

### 8.1 Views — conversão quase 1:1

ANSI joins idênticos entre Teradata e Databricks SQL. Exemplo real:

```sql
-- Databricks (curso 3.1:1129-1148)
CREATE OR REPLACE VIEW IDENTIFIER(:lab_catalog).demo_financial.customer_account_v AS
SELECT c.cust_id, c.first_name, c.last_name, c.city_name, c.state_code,
       a.acct_nbr, a.acct_type, a.acct_start_date, a.starting_balance, a.ending_balance,
       t.tran_id, t.tran_date, t.tran_amt, t.channel, t.tran_code
FROM IDENTIFIER(:lab_catalog).demo_financial.customer c
JOIN IDENTIFIER(:lab_catalog).demo_financial.accounts a ON c.cust_id = a.cust_id
LEFT JOIN IDENTIFIER(:lab_catalog).demo_financial.credit_tran t ON c.cust_id = t.cust_id;
```

### 8.2 Materialized View — 8 limitações reais do Teradata (verificadas contra a doc oficial Teradata)

Antes de decidir SQL Materialized View vs Lakeflow Declarative Pipelines `@dp.materialized_view` no
destino, confirmar se a MV de origem já respeita estas limitações reais do Teradata (curso `3.1:1347-1358`,
descrito como "bem documentado, com link para a doc real da Teradata" pelo auditor):

1. Single-table only (sem joins nem self-joins)
2. Escopo de single-database
3. Não pode consultar outras MVs, views, dynamic tables ou UDTFs
4. Sem window functions, UDF, `HAVING`, `ORDER BY` ou `LIMIT`
5. Agregados limitados a `COUNT`/`SUM`/`AVG`/`MIN`/`MAX`/`STDDEV`/`VARIANCE`
6. Sem `DISTINCT` combinado com agregado
7. Funções não-determinísticas proibidas
8. (Implícito das 7 anteriores) qualquer MV de origem que **viole** uma destas regras é sinal de que
   o objeto pode não ser uma MV Teradata clássica — revisar antes de assumir

**Destinos possíveis:** SQL Materialized View (`CREATE OR REFRESH MATERIALIZED VIEW`, exige DBSQL
Serverless/Pro) ou Lakeflow Declarative Pipelines `@dp.materialized_view` (curso `3.1:1439-1533`) — a
segunda é necessária se a lógica de origem, apesar das limitações acima, precisar de joins/window
functions **no destino** (ex.: consolidando múltiplas MVs single-table Teradata em uma única MV
Databricks mais rica).

⚠️ **Bug de SQL confirmado no exemplo do curso** (`3.1:1439-1453`) — não reproduzir: a lista
`SELECT`/`GROUP BY` do exemplo original repete `c.state_code` duas vezes. Revisar sempre a saída
gerada antes de aceitar — nunca copiar colunas duplicadas por inércia do exemplo-fonte.

Cite: `_digest_fase3.md` §1.6.

---

## 9. Objetos Teradata-específicos — Sem Tradução de DDL (comentário/redesign)

| Objeto Teradata | Alternativa Databricks | Observação |
|---|---|---|
| Full-Text Index / Text UDF | Vector Search Index + AI Functions | Redesign, não transpilação |
| Data Format Specification (TPT/FastLoad) | Opções de `read_files()` | Ver `ingestion-cdc.md` |
| Authorization Object + NOS | External Location + Volume (Unity Catalog) | Ver `ingestion-cdc.md` §2 |
| Timestamp-based CDC | Change Data Feed (CDF) | Ver `ingestion-cdc.md` §11 |
| Stored Procedure / Macro | Databricks Workflow / Lakeflow / SQL Scripting | `Macro` é conceito só-Teradata (`_digest_fase4-6.md` §1.7) |
| TPT / FastLoad | Auto Loader | Ver `ingestion-cdc.md` |

Cite: `_digest_fase3.md` §1.7 (tabela `3.1:1633-1642`).

---

## 10. Gerador Determinístico — `scripts/teradata_generate.py`

**Nunca escrever o DDL Delta convertido à mão.** Uso:

```bash
python scripts/teradata_generate.py <teradata_ddl.sql> <outdir>
```

**Entrada:** arquivo `.sql` com um ou mais `CREATE [SET|MULTISET] TABLE` do Teradata — tipicamente a
saída de `SHOW TABLE db.tabela;`.

**Saída (em `<outdir>/`):**

| Arquivo | Conteúdo |
|---|---|
| `01_ddl_delta.sql` | `CREATE TABLE ... USING DELTA` com tipos mapeados (§1), `CLUSTER BY` combinando `PRIMARY INDEX` + PPI (§4), `PRIMARY KEY ... RELY` se `UNIQUE PRIMARY INDEX`, `COMMENT` por coluna preservando o tipo Teradata original; `FALLBACK`/`JOURNAL`/`CHECKSUM`/`MERGEBLOCKRATIO`/`MAP`/`CASESPECIFIC` sempre removidos (§2); aviso obrigatório de dedup se `SET TABLE` (§3) |
| `02_type_flags.md` | Colunas que exigem revisão manual (`PERIOD`, `INTERVAL`, `JSON`, tipos desconhecidos) + lista de tabelas `SET` |
| `03_reconcile_spec.json` | Spec pronto para `scripts/reconcile_generate.py` (`source_dialect: "teradata"`, `float_tolerance_pct: 0.0001`, colunas classificadas em `numeric_exact`/`numeric_float`/`dates`) |

**Gates que falham o build** (`main()` retorna `1`, imprime "FALHA nos gates" no stderr — **se
qualquer um falhar, NÃO reporte a tarefa como concluída**):

1. **Contaminação Snowflake na entrada** — regex sobre `VARIANT`/`OBJECT`/`ARRAY_AGG`/
   `ARRAY_UNIQUE_AGG`/`OBJECT_AGG`/`IFF(`/`EQUAL_NULL`/`LATERAL FLATTEN`/`METADATA$`/
   `RUNTIME_VERSION`/`HANDLER =`/`TB_101`/`RAW_POS`/`TIMESTAMP_NTZ`/`TIMESTAMP_LTZ`/`TIMESTAMP_TZ` —
   se algum destes aparecer no DDL de entrada rotulado "Teradata", **a fonte provavelmente não é
   Teradata genuína**.
2. **Opção Teradata vazando no DDL Delta de saída** — `FALLBACK`/`JOURNAL`/`CHECKSUM=`/
   `MERGEBLOCKRATIO`/`MAP=TD_MAP`/`CASESPECIFIC`/`CHARACTER SET` não devem sobreviver à conversão.
3. **Identificador sem backtick** no DDL gerado.
4. **Tipos Teradata desconhecidos** (fallback `STRING`) são reportados no stderr — não travam o build
   sozinhos, mas devem ser revisados em `02_type_flags.md` antes de aceitar a saída como pronta.

---

## Checklist de Conversão DDL

- [ ] Tipos mapeados via §1 (fonte: `DBC.ColumnsV`, nunca a tabela contaminada `3.1:339-359`)
- [ ] `FALLBACK`/`JOURNAL`/`CHECKSUM`/`MERGEBLOCKRATIO`/`MAP`/`COMPRESS`/`CHARACTER SET`/`CASESPECIFIC` removidos (§2)
- [ ] Collation revisada manualmente se a origem usava `NOT CASESPECIFIC` — Databricks é case-sensitive por padrão (§2)
- [ ] `SET TABLE` → gate de dedup obrigatório documentado na ingestão (§3)
- [ ] `PRIMARY INDEX`/`UNIQUE PRIMARY INDEX` → `CLUSTER BY` (+ `PK ... RELY` se unique) (§4.1)
- [ ] PPI (`RANGE_N`/`CASE_N`) avaliado pela regra de cardinalidade — `CLUSTER BY` vs `PARTITIONED BY` (§4.2)
- [ ] Secondary/Join Index tratados como comentário — nunca DDL automático (§5)
- [ ] `SEQUENCE` → `IDENTITY`/`UUID()` (§6)
- [ ] `VOLATILE TABLE` → `TEMP VIEW`, nunca tabela gerenciada (§7)
- [ ] Materialized View de origem validada contra as 8 limitações reais antes de escolher o destino (§8.2)
- [ ] DDL gerado via `scripts/teradata_generate.py` — nunca escrito à mão — com os 4 gates passando (§10)
- [ ] Nenhum token Snowflake (`VARIANT`/`OBJECT`/`ARRAY_AGG`/etc.) rotulado como "tipo/sintaxe Teradata"

---

## Referências

- Digest auditado: `_digest_fase3.md` §1 (DDL Teradata → Delta), §7 (proposta do gerador), §8 (contaminação)
- Digest auditado: `_digest_fase0-2.md` §1 (feature/architecture mapping)
- Digest auditado: `_digest_fase4-6.md` §1.3, §2.4 (FLOAT/otimização)
- `audits/2026-08-02-curso-teradata-migration-vs-ai-data-agents.md`
- `scripts/teradata_generate.py` (gerador determinístico documentado em §10)
- Ver também: `kb/teradata-migration/concepts/function-catalog.md` · `kb/teradata-migration/concepts/ingestion-cdc.md`
- Ver também: `kb/hadoop-migration/concepts/hive-ddl-conversion.md` (mesmo padrão, origem Hive)
- Ver também: `kb/sql-patterns/concepts/tsql-conversion-catalog.md` (mesmo padrão, origem SQL Server)
- Ver também: `kb/databricks/concepts/lakehouse-federation.md` §9 (Teradata Federation & Interop)
- [Databricks SQL Language Reference - CREATE TABLE](https://docs.databricks.com/en/sql/language-manual/sql-ref-syntax-ddl-create-table.html)
- [Liquid Clustering](https://docs.databricks.com/en/delta/clustering.html)
- [Databricks Collation (verificado ago/2026 — UTF8_BINARY é case-sensitive)](https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-collation)
