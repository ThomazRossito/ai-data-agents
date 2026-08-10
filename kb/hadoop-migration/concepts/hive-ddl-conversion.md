# Catálogo de Conversão Hive DDL → Databricks/Delta

> Catálogo normativo para a conversão de **DDL Hive** (Hive Metastore, `CREATE [EXTERNAL] TABLE`,
> SerDe, storage formats, partitioning/bucketing) para **Delta Lake / Unity Catalog**. Irmão de
> `kb/sql-patterns/concepts/hiveql-conversion.md` (que cobre DML/HiveQL/Impala/Pig/MapReduce) e de
> `kb/sql-patterns/concepts/tsql-conversion-catalog.md` (mesmo padrão, origem SQL Server). Consultar
> SEMPRE antes de gerar DDL Delta a partir de um `SHOW CREATE TABLE` do Hive. NÃO inventar mapeamentos
> — construto sem equivalente claro no curso → marcar como incerto e verificar doc oficial.

**Domínio:** hadoop-migration — Conversão Hive DDL → Delta (Migração)
**Fonte:** Curso "Hadoop Migration" — `03 - Execute/3.1 Lecture - Schema and DDL Conversion.md`
(seção principal), complementado por `00 - Foundations/0.3 Lecture - Architecture and Feature
Mapping.md` (namespace/feature mapping) e `00 - Foundations/0.4 Lecture - Interoperability
Patterns.md` (Hive Metastore Federation)
**Agentes:** migration-expert, databricks-engineer (fonte de verdade também para um eventual agente
`hadoop-to-databricks` dedicado — ver `audits/2026-08-02-curso-hadoop-migration-vs-ai-data-agents.md` H1)

---

## ⚠️ Nota de Auditoria — Contaminação do Template SQL Server

O curso-fonte tem trechos de **outras lições** (Discovery, Lakebridge Reconcile, Cutover, FinOps,
Observability) reaproveitados mal-adaptados do curso irmão "SQL Server Migration" — DMVs `sys.*`,
`msdb`, `sp_cdc_*`, tipos `HIERARCHYID`/`GEOGRAPHY` como se fossem "tipos Hadoop", `AdventureWorksDW`,
strings de conexão `jdbc:hadoop://...:1433`. **Nada disso é usado neste arquivo.** As lições `3.1` e
`3.4` (Execute) e `0.3`/`0.4` (Foundations) — usadas aqui — são Hadoop-válidas (Hive/HDFS/Impala) e
não apresentam esse padrão de contaminação. Ver auditoria completa em
`audits/2026-08-02-curso-hadoop-migration-vs-ai-data-agents.md` §0.

## Nota de Nomenclatura (verificado ago/2026)

O curso usa **"Remorph"** como nome do transpilador em todo o texto original. O nome de produto atual
é **"Lakebridge"** — Remorph foi incorporado à Lakebridge, que também integra a tecnologia
**BladeBridge** (adquirida pela Databricks) para parsing/conversão de SQL. Fonte: blog oficial
"Introducing Lakebridge: Free, Open Data Migration to Databricks SQL" (databricks.com/blog, publicado
jun/2025, atualizado 2026). Use **"Lakebridge"** como nome canônico neste KB e em qualquer saída
gerada pelos agentes; quando citar o curso literalmente, indicar "(chamado de 'Remorph' no material
do curso)". Mesmo tratamento dado a "Lakeflow Declarative Pipelines" (antigo "Delta Live Tables") em
`tsql-conversion-catalog.md` — usar sempre o nome atual.

**Escopo confirmado do Lakebridge para Hadoop:** transpila **HiveQL/DDL Hive e Impala SQL** (via
BladeBridge). **NÃO transpila Pig Latin nem MapReduce Java** — ver `hiveql-conversion.md` §9-10 para
o tratamento manual desses dois.

---

## 1. Mapa de Tipos — Hive → Delta

### 1.1 Tipos que Mapeiam Diretamente

| Hive | Delta/Databricks | Nota |
|---|---|---|
| `TINYINT` | `TINYINT` | 1 byte, signed — **diferente do SQL Server** `TINYINT` (0-255 unsigned); aqui é 1:1 direto |
| `SMALLINT` | `SMALLINT` | 2 bytes, signed |
| `INT` / `INTEGER` | `INT` | 4 bytes, signed |
| `BIGINT` | `BIGINT` | 8 bytes, signed |
| `FLOAT` | **`FLOAT`** | **4 bytes, single precision** — ver nota crítica abaixo |
| `DOUBLE` | **`DOUBLE`** | **8 bytes, double precision** — ver nota crítica abaixo |
| `DECIMAL(p,s)` | `DECIMAL(p,s)` | Numérico exato — preservar precisão/escala |
| `STRING` | `STRING` | Comprimento variável |
| `VARCHAR(n)` | `STRING` | Databricks suporta `VARCHAR`, mas `STRING` é preferido — ver §1.2 para a nuance de `CHECK` |
| `CHAR(n)` | `STRING` | Fixed-length no Hive; usar `STRING` no Databricks |
| `BOOLEAN` | `BOOLEAN` | |
| `TIMESTAMP` | `TIMESTAMP` | Precisão de microssegundo no Databricks |
| `DATE` | `DATE` | Sem componente de hora |
| `BINARY` | `BINARY` | |
| `ARRAY<T>` | `ARRAY<T>` | Transfere direto — Spark SQL é superset |
| `MAP<K,V>` | `MAP<K,V>` | Transfere direto |
| `STRUCT<...>` | `STRUCT<...>` | Transfere direto |

> **⚠️ Nota crítica sobre FLOAT/DOUBLE (fato verificado, ago/2026):** Apache Hive `FLOAT` é
> **32-bit single precision** → mapeia para Delta `FLOAT`. Hive `DOUBLE` é **64-bit double
> precision** → mapeia para Delta `DOUBLE`. Isso é o que a lição `3.1` (usada aqui) diz corretamente.
> **Um arquivo diferente do curso (`4.1`, fase Activate) afirma "FLOAT é 64-bit"** — essa afirmação é
> **ERRADA**, é resíduo da contaminação do template SQL Server (onde `FLOAT` sem parâmetro *é*
> double-precision de 8 bytes por padrão T-SQL). **Não usar o `4.1`** como referência para este
> mapeamento — usar apenas a tabela acima, consistente com o Apache Hive Language Manual. Esta é a
> mesma correção já aplicada em `scripts/hive_generate.py` (comentário inline no dict `_PRIM`).
> Importante para reconciliação: `FLOAT`/`DOUBLE` usam tolerância relativa (não exata) no check de
> soma — ver `kb/migration/concepts/reconciliation.md` §1 e `03_reconcile_spec.json` (`numeric_float`).

Cite: `03 - Execute/3.1 Lecture - Schema and DDL Conversion.md`, seção "Types That Map Directly".

### 1.2 Tipos que Exigem Conversão/Atenção

| Hive / Tipo de Origem | Delta/Databricks | Ação |
|---|---|---|
| `UNIONTYPE<...>` | `STRUCT` ou colunas separadas | Sem equivalente direto — reestruturar como `STRUCT` com um campo de tag indicando qual variante está populada |
| `VARCHAR(n)` / `CHAR(n)` | `STRING` | Hive aplica length constraint; `STRING` no Databricks é unbounded — adicionar `CHECK (LENGTH(col) <= n)` se a validação de tamanho for regra de negócio |
| `INTERVAL` (Hive 3.x) | `INTERVAL` nativo do Spark SQL, ou `LONG` | ⚠️ **Incerto** — o curso afirma que Databricks "suporta tipos INTERVAL nativamente", mas não detalha a conversão literal-a-literal a partir da sintaxe de intervalo do Hive 3.x. `scripts/hive_generate.py` trata `INTERVAL` como `STRING` com flag de revisão manual até essa conversão ser validada caso a caso |
| SerDe customizado | Depende do SerDe | Dado gravado via SerDe custom deve ser **lido com o SerDe original** e reescrito em Delta com tipos padrão — não é conversão de DDL, é conversão de dado (uma vez) |
| `VOID` | N/A | Tipo Hive de literal nulo; não aparece em DDL de tabela real — ignorar |

Cite: `03 - Execute/3.1 Lecture - Schema and DDL Conversion.md`, seção "Types That Require Conversion".

### 1.3 Tipos de Origem RDBMS via Sqoop (herdados no Hive)

Quando a tabela Hive foi originalmente populada via **Sqoop** a partir de um RDBMS (padrão comum em
ambientes Hadoop legados), os tipos de origem já passaram por uma primeira conversão lossy para Hive
antes de chegar ao Databricks:

| Tipo RDBMS Original | Tipo Hive (via Sqoop) | Tipo Databricks |
|---|---|---|
| `UNIQUEIDENTIFIER` | `STRING` | `STRING` (validar/gerar novos valores com `uuid()` se necessário) |
| `MONEY` / `SMALLMONEY` | `STRING` ou `DECIMAL` | `DECIMAL(19,4)` — nunca `FLOAT`/`DOUBLE` para valores monetários |
| `DATETIME2` | `STRING` ou `TIMESTAMP` | `TIMESTAMP` |
| `XML` | `STRING` | `STRING` |
| `BIT` | `BOOLEAN` ou `INT` | `BOOLEAN` |

> Isso é uma pista de auditoria de dados, não uma regra automática: **inspecionar amostra real** da
> coluna antes de assumir o tipo de origem — colunas `STRING` no Hive podem esconder datas, booleanos
> 0/1, ou GUIDs sem qualquer marcação de schema que o denuncie.

Cite: `03 - Execute/3.1 Lecture - Schema and DDL Conversion.md`, seção "Types That Require
Conversion" (tabela "When migrating data originally sourced from an RDBMS via Sqoop").

---

## 2. SEMPRE Remover — SerDe, Storage Format, Table Properties

Hive DDL carrega diretivas de armazenamento físico que não têm equivalente no Delta Lake (Delta
gerencia serialização, compressão e formato de arquivo automaticamente). **Remover incondicionalmente**:

| Cláusula Hive | Exemplo | Ação Databricks |
|---|---|---|
| `ROW FORMAT SERDE` | `ROW FORMAT SERDE 'org.apache.hadoop.hive.ql.io.orc.OrcSerde'` | Remover — Delta serializa automaticamente |
| `ROW FORMAT DELIMITED` | `ROW FORMAT DELIMITED FIELDS TERMINATED BY ','` | Remover — só relevante para arquivos texto |
| `STORED AS ORC` | `STORED AS ORC` | Remover — Delta é o formato padrão |
| `STORED AS PARQUET` | `STORED AS PARQUET` | Remover — Delta é o formato padrão |
| `STORED AS TEXTFILE` | `STORED AS TEXTFILE` | Remover — converter dado texto para Delta |
| `STORED AS AVRO` | `STORED AS AVRO` | Remover — converter dado Avro para Delta |
| `STORED AS RCFILE` | `STORED AS RCFILE` | Remover — converter RCFile para Delta (formato legado) |
| `STORED AS SEQUENCEFILE` | `STORED AS SEQUENCEFILE` | Remover — converter SequenceFile para Delta (formato legado) |
| `INPUTFORMAT` / `OUTPUTFORMAT` | Classes de I/O custom | Remover — não aplicável ao Delta |
| `WITH SERDEPROPERTIES` | Parâmetros de configuração do SerDe | Remover inteiramente |
| `LOCATION` (tabela external) | `LOCATION '/hdfs/path/...'` | Atualizar para path de cloud storage, OU converter para tabela managed |
| `TBLPROPERTIES ('transactional'='true')` | — | Remover — tabelas Delta são sempre transacionais |
| `TBLPROPERTIES ('orc.compress'=...)` / `('parquet.compression'=...)` | — | Remover — Delta gerencia compressão automaticamente |
| `TBLPROPERTIES ('auto.purge'='true')` | — | Remover — Delta gerencia limpeza de arquivo via `VACUUM` |
| `TBLPROPERTIES ('EXTERNAL'='TRUE')` | — | Remover se convertendo para managed; manter se a tabela permanece external |
| Propriedades de aplicação custom em `TBLPROPERTIES` | — | Migrar para `TBLPROPERTIES` do Delta **se** ainda forem necessárias |

### Exemplo — Antes/Depois

```sql
-- Hive (origem) — beeline -e "SHOW CREATE TABLE sales.order_detail"
CREATE TABLE sales.order_detail (
    order_id        BIGINT,
    product_id      INT,
    quantity        SMALLINT,
    unit_price      DECIMAL(19,4),
    discount_pct    DOUBLE,
    order_date      STRING,
    ship_date       STRING,
    customer_name   STRING,
    status          STRING
)
PARTITIONED BY (order_year INT, order_month INT)
CLUSTERED BY (order_id) INTO 32 BUCKETS
ROW FORMAT SERDE 'org.apache.hadoop.hive.ql.io.orc.OrcSerde'
STORED AS ORC
TBLPROPERTIES ('orc.compress' = 'SNAPPY', 'transactional' = 'true');
```

```sql
-- Databricks — SerDe/storage/bucketing removidos; partição+bucket → Liquid Clustering
CREATE TABLE sales.order_detail (
    order_id        BIGINT,
    product_id      INT,
    quantity        SMALLINT,
    unit_price      DECIMAL(19,4),
    discount_pct    DOUBLE,
    order_date      STRING,
    ship_date       STRING,
    customer_name   STRING,
    status          STRING
)
CLUSTER BY (order_id, order_date)
COMMENT 'Migrated from Hive sales.order_detail';
```

Cite: `03 - Execute/3.1 Lecture - Schema and DDL Conversion.md`, seções "SerDe and Storage Format",
"Table Properties (TBLPROPERTIES)".

---

## 3. Particionamento e Bucketing → CLUSTER BY (Liquid Clustering)

**Regra central:** `PARTITIONED BY` físico do Hive vira, por padrão, **Liquid Clustering**
(`CLUSTER BY`) no Databricks — não uma tradução 1:1 de partição física.

| Padrão Hive | Opção Databricks | Quando Usar |
|---|---|---|
| `PARTITIONED BY (year INT, month INT)` | `PARTITIONED BY (year, month)` (mantém partição física) | Só para tabelas **muito grandes (1 TB+)** com chave de partição clara e seletiva |
| `PARTITIONED BY (date STRING)` | `CLUSTER BY (date)` (Liquid Clustering) | **Default recomendado** — mais simples, evita partition skew |
| **`CLUSTERED BY (col) INTO N BUCKETS`** | **`CLUSTER BY (col)`** (Liquid Clustering, **sem contagem de buckets**) | Bucketing do Hive mapeia naturalmente para Liquid Clustering — a contagem fixa (`N BUCKETS`) **não tem equivalente e é sempre descartada** |

Quando uma tabela tem **partição E bucket ao mesmo tempo** (padrão comum em fact tables), as colunas
de ambos se combinam em uma única lista `CLUSTER BY`, deduplicada — é exatamente o que
`scripts/hive_generate.py` faz automaticamente (`part_cols + buck_cols`, sem repetição). Exemplo: uma
tabela `PARTITIONED BY (order_year, order_month) CLUSTERED BY (customer_key) INTO 16 BUCKETS` gera
`CLUSTER BY (order_year, order_month, customer_key)`.

> **Liquid Clustering é a recomendação padrão.** Só usar `PARTITIONED BY` físico quando há uma chave
> de partição clara, seletiva, e a tabela ultrapassa 1 TB — caso contrário, Liquid Clustering evita
> partition skew e não exige escolher/manter um esquema de partição manualmente.

Cite: `03 - Execute/3.1 Lecture - Schema and DDL Conversion.md`, seção "Partitioning (PARTITIONED
BY)" e callout "Liquid Clustering is the default recommendation".

---

## 4. Constraints — Hive Informacional → Databricks Enforced

Hive tem suporte limitado a constraints comparado ao Databricks Delta. **Migração é oportunidade**
para codificar como constraint o que antes só existia implicitamente em código de ETL.

| Feature | Hive | Databricks Delta | Ação de Migração |
|---|---|---|---|
| `NOT NULL` | Suportado (Hive 3.x) | Suportado | Transferir direto |
| `PRIMARY KEY` | Informacional apenas (Hive 3.x) | Informacional (usar `RELY` — ver `tsql-conversion-catalog.md` §2.2 para o padrão de sintaxe) | Transferir como está |
| `FOREIGN KEY` | Informacional apenas (Hive 3.x) | Informacional | Transferir como está |
| `CHECK` | **Não suportado** | Suportado e **enforced** | Adicionar onde há regra de qualidade de dado implícita no ETL |
| `DEFAULT` | Não suportado (Hive 3.x tem suporte limitado) | Suportado | Adicionar se o comportamento de default era tratado em lógica de ETL |
| Colunas geradas/computadas | Não suportado | Suportado (`GENERATED ALWAYS AS`) | Adicionar se o ETL calculava colunas derivadas |

```sql
-- Exemplo: codificar regra que antes só existia em ETL
customer_key BIGINT NOT NULL,
is_active    BOOLEAN,
margin       DECIMAL(19,4) GENERATED ALWAYS AS (sales_amount - total_product_cost)
```

Cite: `03 - Execute/3.1 Lecture - Schema and DDL Conversion.md`, seção "Constraint and Schema
Differences" e callout "Use migration as an opportunity to add constraints".

---

## 5. Managed vs External Tables

| Hive | Databricks (Unity Catalog) | Comportamento |
|---|---|---|
| Managed table (sem `EXTERNAL`) | Managed table (default) | Databricks gerencia o ciclo de vida do dado; `DROP TABLE` apaga os dados |
| `CREATE EXTERNAL TABLE ... LOCATION '/path'` | External table com `LOCATION` | Dado persiste após `DROP TABLE`; só a metadata é removida |

A maioria das tabelas Hive **external** apontando para paths HDFS deve virar tabela **managed** Delta
na migração — converter `LOCATION` para path de cloud storage só quando acesso externo aos arquivos
brutos for de fato necessário (ex.: outro processo fora do Databricks lê os mesmos arquivos).

Cite: `03 - Execute/3.1 Lecture - Schema and DDL Conversion.md`, seção "External vs Managed Tables".

---

## 6. Namespace — Hive Metastore → Unity Catalog

Hive usa **dois níveis** (`database.table`); Unity Catalog usa **três** (`catalog.schema.table`).
Todo DDL convertido precisa dessa mudança de nível.

| Conceito Hadoop | Equivalente Databricks | Nota |
|---|---|---|
| Hadoop Cluster | Workspace + Unity Catalog Metastore | Múltiplos clusters podem mapear para um metastore |
| Hive Metastore | Unity Catalog Metastore | HMS gerencia metadata de database/tabela; UC unifica governança |
| Hive Database | Unity Catalog Catalog + Schema | Um database Hive tipicamente mapeia para um catalog (ou schema dentro de um catalog, dependendo da estratégia de nomenclatura escolhida no discovery) |
| `database.table` | `catalog.schema.table` | Hive usa naming de 2 níveis; UC adiciona um 3º nível |

> Nomes de database Hive tipicamente já são lowercase com underscore, o que se alinha bem à convenção
> de nomenclatura de catalog/schema do Databricks — planejar a estratégia de mapeamento de namespace
> durante o Discovery, decidindo antecipadamente se cada `database` Hive vira um `catalog` (isolamento
> forte) ou um `schema` dentro de um catalog compartilhado (ex.: `catalog.gold.<tabela>`, ver §10).

Cite: `00 - Foundations/0.3 Lecture - Architecture and Feature Mapping.md`, seção "Object Hierarchy
and Namespace Structure".

### 6.1 Hive Metastore Federation — validação de schema durante a transição

Durante a migração, Unity Catalog pode federar para o Hive Metastore original via **Connection +
Foreign Catalog**, permitindo consultar tabelas Hive ainda não migradas sem mover dado — útil
especificamente para **validar o schema convertido contra o original** antes do cutover:

```sql
-- Comparar schema Hive Metastore (via foreign catalog) com o schema Unity Catalog convertido
SELECT
    h.col_name AS hive_column,
    h.data_type AS hive_type,
    d.col_name AS databricks_column,
    d.data_type AS databricks_type,
    CASE WHEN h.col_name IS NULL THEN 'MISSING IN HIVE'
         WHEN d.col_name IS NULL THEN 'MISSING IN DATABRICKS'
         WHEN h.data_type != d.data_type THEN 'TYPE MISMATCH'
         ELSE 'OK'
    END AS status
FROM hive_federated.dw.dim_customer_columns h
FULL OUTER JOIN (
    SELECT column_name AS col_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'dw' AND table_name = 'dim_customer'
) d ON LOWER(h.col_name) = LOWER(d.col_name)
ORDER BY COALESCE(h.col_name, d.col_name);
```

> Esta seção documenta apenas o uso pontual de Federation para validação de schema (o que o curso
> cobre em `3.1`). A configuração completa de Hive Metastore Federation (Connection, privilégios,
> compute mínimo, padrões de coexistência) é tratada como capability própria em
> `kb/databricks/concepts/lakehouse-federation.md` — **essa KB ainda não documenta o tipo
> `hive_metastore`** (gap aberto, ver `audits/2026-08-02-curso-hadoop-migration-vs-ai-data-agents.md`
> H9); até lá, usar `00 - Foundations/0.4 Lecture - Interoperability Patterns.md` diretamente para
> qualquer detalhe de setup de Federation que vá além da query de validação acima.

Cite: `03 - Execute/3.1 Lecture - Schema and DDL Conversion.md`, seção "Schema Validation";
`00 - Foundations/0.4 Lecture - Interoperability Patterns.md`, seção "Pattern 1: Hive Metastore
Federation".

---

## 7. Views e Materialized Views

| Hive | Databricks | Nota |
|---|---|---|
| `CREATE VIEW ... AS SELECT` | Idêntico | Sintaxe padrão transfere direto |
| Views com `LATERAL VIEW EXPLODE` | Suportado | Spark SQL é superset — funciona sem alteração |
| Views referenciando tabelas externas | Atualizar referência | Apontar para as tabelas Delta migradas |
| Views cross-database | Atualizar referência | Trocar nome de database Hive por `catalog.schema` |
| `CREATE MATERIALIZED VIEW ... AS SELECT` | `CREATE MATERIALIZED VIEW ... AS SELECT` (sintaxe idêntica) | |
| Query rewriting automático (Hive 3.x) | Suportado | |
| `ALTER MATERIALIZED VIEW ... REBUILD` (refresh manual) | `REFRESH MATERIALIZED VIEW` | |
| Incremental refresh (Hive 3.x) | Suportado via Lakeflow Declarative Pipelines | Para agregações com refresh frequente, preferir **streaming tables** do Lakeflow Declarative Pipelines em vez de Materialized View standalone |

> Materialized Views SQL standalone requerem SQL Warehouse Serverless ou Pro. Para compute geral,
> implementar via Lakeflow Declarative Pipelines.

Cite: `03 - Execute/3.1 Lecture - Schema and DDL Conversion.md`, seções "Views" e "Materialized
Views".

---

## 8. Exemplo Completo — Dimensão Sqoop-Sourced

Caso representativo: tabela de dimensão originalmente carregada via Sqoop a partir de um RDBMS.

```sql
-- Hive (origem)
CREATE EXTERNAL TABLE dw.dim_customer (
    customer_key     BIGINT,
    customer_id      STRING    COMMENT 'Original UNIQUEIDENTIFIER from source RDBMS',
    first_name       STRING,
    last_name        STRING,
    email            STRING,
    phone            STRING,
    address_line1    STRING,
    city             STRING,
    state_province   STRING,
    postal_code      STRING,
    country          STRING,
    birth_date       STRING    COMMENT 'Stored as yyyy-MM-dd string from Sqoop import',
    created_date     TIMESTAMP,
    modified_date    TIMESTAMP,
    is_active        INT       COMMENT '0 or 1 - BIT equivalent from source'
)
PARTITIONED BY (load_year INT, load_month INT)
CLUSTERED BY (customer_key) INTO 16 BUCKETS
ROW FORMAT SERDE 'org.apache.hadoop.hive.ql.io.orc.OrcSerde'
STORED AS ORC
LOCATION '/warehouse/dw/dim_customer'
TBLPROPERTIES ('orc.compress' = 'ZLIB', 'transactional' = 'false');
```

```sql
-- Databricks (destino)
CREATE TABLE dw.dim_customer (
    customer_key     BIGINT      NOT NULL,
    customer_id      STRING      COMMENT 'Original UNIQUEIDENTIFIER from source RDBMS',
    first_name       STRING      NOT NULL,
    last_name        STRING      NOT NULL,
    email            STRING,
    phone            STRING,
    address_line1    STRING,
    city             STRING,
    state_province   STRING,
    postal_code      STRING,
    country          STRING,
    birth_date       DATE        COMMENT 'Converted from STRING to DATE',
    created_date     TIMESTAMP,
    modified_date    TIMESTAMP,
    is_active        BOOLEAN     COMMENT 'Converted from INT (0/1) to BOOLEAN'
)
CLUSTER BY (customer_key, country)
COMMENT 'Migrated from Hive dw.dim_customer';
```

| Mudança | Motivo |
|---|---|
| Removido `EXTERNAL` | Convertida para tabela managed Delta |
| Removido `ROW FORMAT SERDE` / `STORED AS ORC` / `LOCATION` / `TBLPROPERTIES` | Delta gerencia tudo isso automaticamente |
| Removido `PARTITIONED BY` + `CLUSTERED BY ... BUCKETS` | Substituído por Liquid Clustering (`CLUSTER BY`) |
| `birth_date STRING` → `DATE` | Tipo apropriado em vez da representação string do Sqoop — **validar com `TRY_CAST` antes de converter** (ver alerta abaixo) |
| `is_active INT` → `BOOLEAN` | Tipo apropriado em vez da codificação inteira 0/1 |
| Adicionado `NOT NULL` | Codifica regra que antes só existia implicitamente no ETL |
| Adicionado `COMMENT` | Documentação de linhagem da origem |

> **Atenção a conversões implícitas de tipo:** tabelas Hive frequentemente guardam datas/timestamps
> como `STRING` por causa do comportamento de import do Sqoop. Ao converter para `DATE`/`TIMESTAMP`
> de verdade, validar que todos os valores fazem parse corretamente — usar `TRY_CAST` para identificar
> linhas com strings de data inválidas **antes** de aplicar a conversão em produção.

Cite: `03 - Execute/3.1 Lecture - Schema and DDL Conversion.md`, seção "Full Conversion Example" e
callout "Watch for Implicit Type Conversions".

---

## 9. Otimizações Pós-Conversão (sem equivalente Hive)

| Otimização | Sintaxe | Propósito |
|---|---|---|
| Liquid Clustering | `CLUSTER BY (col1, col2)` | Colocaliza linhas relacionadas; substitui bucketing do Hive |
| `OPTIMIZE` | `OPTIMIZE table_name` | Compacta small files — rodar após bulk loads |
| `VACUUM` | `VACUUM table_name RETAIN 168 HOURS` | Remove arquivos de dado antigos não mais referenciados pelo transaction log |
| Predictive Optimization | Habilitado a nível de conta | Roda `OPTIMIZE`/`VACUUM` automaticamente conforme padrão de uso |
| `ZORDER BY` | `OPTIMIZE table_name ZORDER BY (col)` | Alternativa legada ao Liquid Clustering — usar Liquid Clustering em tabelas novas |

Cite: `03 - Execute/3.1 Lecture - Schema and DDL Conversion.md`, seção "Table Properties and
Optimization".

---

## 10. Gerador Determinístico — `scripts/hive_generate.py`

**Nunca escrever o DDL Delta convertido à mão** — usar o gerador, no mesmo padrão de
`scripts/sqlserver_generate.py`/`scripts/ssas_generate.py`: correto-por-construção, com gates que
falham o build em vez de deixar passar um DDL inconsistente.

```bash
python scripts/hive_generate.py <hive_ddl.sql> <outdir>
```

**Entrada:** um arquivo `.sql` com um ou mais `CREATE [EXTERNAL] TABLE` do Hive — tipicamente a saída
de `beeline -e "SHOW CREATE TABLE <db>.<table>"` para cada tabela do escopo.

**Saída (em `<outdir>/`):**

| Arquivo | Conteúdo |
|---|---|
| `01_ddl_delta.sql` | `CREATE TABLE ... USING DELTA` com tipos mapeados (§1), `CLUSTER BY` combinando colunas de partição+bucket (§3), `COMMENT` por coluna preservando o tipo Hive original; SerDe/`STORED AS`/`TBLPROPERTIES`/`LOCATION` sempre removidos (§2) |
| `02_type_flags.md` | Colunas que exigem revisão manual — `UNIONTYPE`, `INTERVAL`, e qualquer tipo Hive não reconhecido (fallback para `STRING` com flag) |
| `03_reconcile_spec.json` | Spec pronto para `scripts/reconcile_generate.py` — já classifica colunas em `numeric_exact`/`numeric_float`/`dates` por tabela e fixa `float_tolerance_pct: 0.0001` |

**Gates que falham o build** (`main()` retorna `1` e imprime "FALHA nos gates" no stderr):

1. **`gate_serde_leak`** — falha se qualquer resquício de `STORED AS`/`ROW FORMAT`/`TBLPROPERTIES`/
   `SERDE`/`LOCATION '...'` aparecer no DDL Delta gerado (regex sobre a saída final).
2. **`gate_unquoted`** — falha se algum identificador de coluna não estiver entre backticks.
3. Tipos Hive **desconhecidos** (fallback `STRING`) são reportados no stderr — não travam o build
   sozinhos, mas devem ser revisados em `02_type_flags.md` antes de aceitar a saída como pronta.

> **Se algum destes gates falhar, NÃO reporte a tarefa como concluída** — o script existe
> exatamente para pegar esses erros antes de um humano revisar manualmente.

### 10.1 Limitações conhecidas do gerador (verificado por leitura direta do código)

- **Schema de destino fixo em `catalog.gold.<tabela>`** — o gerador sempre grava o alvo como
  `catalog.gold.{nome_normalizado}`, **não preserva o nome do database Hive de origem** como
  schema de destino. Se a estratégia de migração usar Bronze/Silver/Gold em vez de carga direta para
  Gold (ver `kb/migration/index.md`, arquitetura Medallion), editar o `01_ddl_delta.sql` gerado ou
  ajustar o script antes de aceitar a saída — não é um bug de tipo, é uma convenção de nomenclatura
  hardcoded que pode não bater com o design da migração em questão.
- **Handoff para `reconcile_generate.py` assume quoting T-SQL no lado "source"** — o
  `03_reconcile_spec.json` emitido por `hive_generate.py` não inclui um campo de dialeto de origem.
  `scripts/reconcile_generate.py` (escrito originalmente para SQL Server) usa **colchetes** (`[col]`)
  para identificadores do lado `source` — sintaxe **inválida** em HiveQL/Beeline (Hive usa backtick).
  Ao gerar `reconcile_source.sql` a partir de um spec produzido pelo `hive_generate.py`, **revisar e
  trocar `[col]` → `` `col` `` manualmente antes de rodar contra o HiveServer2/Beeline**, ou validar
  via a query de Federation (§6.1) como alternativa que evita esse problema de sintaxe.
- **`INTERVAL` sempre vira `STRING` com flag** — não há tentativa de conversão para o tipo `INTERVAL`
  nativo do Spark SQL (consistente com a incerteza marcada em §1.2).

---

## Checklist de Conversão DDL

- [ ] Todo `ROW FORMAT`, `STORED AS`, `SERDE`, `INPUTFORMAT`/`OUTPUTFORMAT` removido (§2)
- [ ] Tipos Hive mapeados corretamente — atenção a `FLOAT`/`DOUBLE` (§1.1, usar a tabela desta KB,
      **não** o arquivo `4.1` contaminado do curso) e a colunas `STRING` que deveriam ser `DATE`/
      `TIMESTAMP`/`BOOLEAN` de verdade (§8)
- [ ] `PARTITIONED BY` avaliado — convertido para Liquid Clustering, exceto tabelas 1TB+ com chave
      seletiva clara (§3)
- [ ] `CLUSTERED BY ... INTO N BUCKETS` substituído por `CLUSTER BY` sem contagem fixa (§3)
- [ ] `LOCATION` de tabela external atualizado para cloud storage, ou convertida para managed (§5)
- [ ] `TBLPROPERTIES` limpo — removidas propriedades de storage engine, mantida metadata de aplicação
      relevante (§2)
- [ ] `NOT NULL`/`CHECK`/`DEFAULT`/`GENERATED` adicionados onde a regra existia implicitamente no ETL
      (§4)
- [ ] `COMMENT` adicionado para documentação de linhagem
- [ ] Namespace de 2 níveis (`db.table`) convertido para 3 níveis (`catalog.schema.table`) (§6)
- [ ] Views atualizadas para referenciar os nomes de tabela migrados (§7)
- [ ] Query de validação de schema (federated Hive Metastore × Unity Catalog) executada (§6.1)
- [ ] DDL gerado via `scripts/hive_generate.py` — nunca escrito à mão — com os 2 gates passando (§10)
- [ ] `03_reconcile_spec.json` revisado (quoting do lado source corrigido) antes de rodar
      `scripts/reconcile_generate.py` (§10.1)

---

## Referências

- Curso "Hadoop Migration" — `03 - Execute/3.1 Lecture - Schema and DDL Conversion.md`
- Curso "Hadoop Migration" — `00 - Foundations/0.3 Lecture - Architecture and Feature Mapping.md`
- Curso "Hadoop Migration" — `00 - Foundations/0.4 Lecture - Interoperability Patterns.md`
- Ver também: `kb/sql-patterns/concepts/hiveql-conversion.md` (DML/HiveQL/Impala/Pig/MapReduce)
- Ver também: `kb/sql-patterns/concepts/tsql-conversion-catalog.md` (mesmo padrão, origem SQL Server —
  ver especialmente §2.2 `RELY` e §4 SQL Scripting, reaproveitáveis aqui)
- Ver também: `kb/migration/index.md` (Arquitetura Medallion, fluxo de 5 fases, anti-padrões)
- Ver também: `kb/migration/concepts/reconciliation.md` (tolerâncias, 7 parity checks, 2 fases)
- Ver também: `scripts/hive_generate.py` (gerador determinístico documentado em §10) e
  `scripts/reconcile_generate.py` (consome `03_reconcile_spec.json`)
- Ver também: `audits/2026-08-02-curso-hadoop-migration-vs-ai-data-agents.md` (auditoria completa do
  curso, achados H1-H11, nota de contaminação §0)
- [Databricks SQL Language Reference - CREATE TABLE](https://docs.databricks.com/en/sql/language-manual/sql-ref-syntax-ddl-create-table.html)
- [Delta Lake Data Types](https://docs.databricks.com/en/sql/language-manual/sql-ref-datatypes.html)
- [Liquid Clustering](https://docs.databricks.com/en/delta/clustering.html)
- [Apache Hive Language Manual — Types](https://cwiki.apache.org/confluence/display/Hive/LanguageManual+Types)
- [Introducing Lakebridge (Databricks Blog, jun/2025)](https://www.databricks.com/blog/introducing-lakebridge-free-open-data-migration-databricks-sql)
- [Lakebridge (GitHub)](https://github.com/databrickslabs/lakebridge)
