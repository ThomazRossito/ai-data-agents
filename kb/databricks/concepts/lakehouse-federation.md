# Lakehouse Federation — SQL Server, Hive Metastore e Teradata (Discovery, Perfilamento e Validação)

> Federation NÃO é destino de migração — é um padrão **transicional** de interoperabilidade:
> Databricks consulta o SQL Server ao vivo via **Connection + Foreign Catalog**, sem mover dados.
> Direção única (Databricks → SQL Server), **read-only**, pushdown de predicados via JDBC (verificado
> web, ago/2026). Use para discovery, perfilamento e validação client-side durante a migração; para
> carga em massa de fact tables grandes, use extração (BCP/ADF/SSIS). Fonte: curso *SQL Server
> Migration* — `00 - Foundations/0.4 Lecture - Interoperability Patterns`,
> `03 - Execute/3.2 Lecture - Data Migration and Ingestion`,
> `04 - Activate/4.1 Lecture - Testing and Data Validation`,
> `04 - Activate/4.3 Lecture - Cutover Execution`, `04 - Activate/4.4 Demo - Activation Phase`.
>
> **Seção 8 (Hive Metastore Federation)** cobre uma origem diferente — não um banco relacional
> standalone, mas o **Hive Metastore** de um cluster Hadoop. O mecanismo de Connection + Foreign
> Catalog é o mesmo, mas a Connection aponta para o **banco relacional que sustenta o HMS**
> (MySQL/SQL Server/PostgreSQL), não para um endpoint Thrift — o curso descreve isso com imprecisão
> (ver correção em 8.1). Fonte curso *Hadoop Migration* — `00 - Foundations/0.4 Lecture -
> Interoperability Patterns`; fatos verificados oficialmente em docs.databricks.com (ago/2026) — ver
> seção 8.
>
> **Seção 9 (Teradata Federation & Interop)** cobre dois padrões complementares e de **direção
> oposta**: (a) Lakehouse Federation `CREATE CONNECTION ... TYPE teradata` — Databricks lê o Teradata
> ao vivo (mesma direção das seções 1-8), auth **TD2** apenas (usuário/senha — sem LDAP/Kerberos/
> TDNEGO), DBR 16.1+/SQL Warehouse pro-serverless 2024.50+, **verificado ao vivo na doc oficial**
> (`docs.databricks.com/aws/en/query-federation/teradata`, atualizada 9/abr/2026); e (b) Teradata Open
> Table Format/`CREATE DATALAKE` — direção **inversa**, Teradata lê tabelas Delta/UC via Iceberg REST +
> UniForm. Fonte curso *Teradata Migration* — `00 - Foundations/0.4 Lecture - Interoperability
> Patterns`; ver seção 9 para o que é verificado oficialmente vs. só citado pelo curso.

**Domínio:** Query federation, discovery client-side, profiling sem extração, validação de schema
origem×destino (SQL Server); Hive Metastore Federation — Connection/Foreign Catalog, read-only vs
writeable, HDFS on-premises não suportado (Hadoop); Teradata Federation — `CREATE CONNECTION TYPE
teradata` (auth TD2, DBR 16.1+), pushdown de agregações, ANSI/TMODE case-sensitivity; Teradata Open
Table Format/Iceberg (`CREATE DATALAKE ... TABLE FORMAT ICEBERG`) — direção inversa, feature de nicho

---

## 1. Objetos Unity Catalog Necessários

Dois objetos UC (`0.4 Lecture - Interoperability Patterns`):

| Objeto | Propósito | Quem cria |
|--------|-----------|-----------|
| **Connection** | Armazena host, porta e credenciais do SQL Server (username/password OU Microsoft Entra ID — OAuth / OAuth M2M) | Metastore admin ou usuário com `CREATE CONNECTION` |
| **Foreign Catalog** | Espelha um banco SQL Server inteiro como catalog UC (schema→schema, tabela→tabela); habilita sintaxe UC padrão + governança | Usuário com `CREATE CATALOG` |

**Fluxo:** Connection → Foreign Catalog → query padrão UC roteada via JDBC pelo query engine do Unity Catalog. Suporta SQL Server, Azure SQL Database e Azure SQL Managed Instance (curso 0.4 + verificado web ago/2026).

**Direção única:** Databricks → SQL Server. Não existe padrão Iceberg REST/acesso externo para SQL Server no sentido inverso (0.4 Lecture).

### Compute mínimo (0.4 Lecture — ⚠️ confirmar na doc oficial, pode ter mudado)

| Compute | Requisito mínimo citado no curso |
|---|---|
| All-purpose / Jobs clusters | DBR 13.3 LTS+, modo de acesso Standard ou Dedicated |
| SQL Warehouses | Pro ou Serverless, channel 2023.40+ |

---

## 2. Matriz de Pushdown

Fonte: `0.4 Lecture - Interoperability Patterns`, seção "Query Pushdown". **Nunca assuma pushdown de agregações/joins sem confirmar o compute** — o plano de execução (`EXPLAIN`) é a forma de verificar antes de rodar em escala.

| Categoria | Pushdown | Compute exigido |
|---|---|---|
| Filtros (`WHERE`) | ✅ Sempre | Qualquer |
| Projeções de coluna (`SELECT` lista de colunas) | ✅ Sempre | Qualquer |
| `LIMIT` | ✅ Sempre | Qualquer |
| Funções parciais: string, matemáticas, data/hora, `CAST`, `ALIAS`, `SORT ORDER` | ✅ Sempre (parcial) | Qualquer |
| Agregações (`GROUP BY`, `COUNT`, `SUM` etc.) | ⚠️ Só com compute qualificado | DBR 13.3 LTS+ **ou** SQL Warehouse |
| Operadores booleanos (`=`, `<`, `<=`, `>`, `>=`, `<=>`) | ⚠️ Só com compute qualificado | DBR 13.3 LTS+ **ou** SQL Warehouse |
| Operadores matemáticos (`+ - * % /`) | ⚠️ Só com compute qualificado | DBR 13.3 LTS+ **ou** SQL Warehouse |
| Operadores bitwise (`^ \| ~`) | ⚠️ Só com compute qualificado | DBR 13.3 LTS+ **ou** SQL Warehouse |
| `ORDER BY` combinado com `LIMIT` | ⚠️ Só com compute qualificado | DBR 13.3 LTS+ **ou** SQL Warehouse |
| **Joins entre tabelas federadas (foreign tables)** | ❌ NUNCA — executado no Databricks após transferência | — |
| **Window functions** | ❌ NUNCA — executado no Databricks após transferência | — |

**Implicação operacional:** perfilar uma tabela grande com `COUNT(*)`/`GROUP BY` em compute sem qualificação (DBR < 13.3, cluster não-SQL-Warehouse) **não** empurra a agregação — a tabela inteira é transferida via JDBC antes de agregar. Confirme o compute antes de perfilar tabelas de grande volume.

---

## 3. Mapeamento de Tipos (SQL Server → Spark, via Federation)

Fonte: `0.4 Lecture - Interoperability Patterns`. Relevante para prever o tipo que aparece no `information_schema.columns` do Foreign Catalog.

| SQL Server | Spark Type | Observação |
|---|---|---|
| `INT` | `IntegerType` | |
| `BIGINT` (signed) | `LongType` | |
| `BIGINT` (unsigned), `DECIMAL`, `MONEY`, `NUMERIC`, `SMALLMONEY` | `DecimalType` | |
| `SMALLINT`, `TINYINT` | `ShortType` | |
| `REAL` | `FloatType` | |
| `FLOAT` | `DoubleType` | |
| `CHAR`, `NCHAR`, `UNIQUEIDENTIFIER` | `CharType` | |
| `NVARCHAR`, `VARCHAR` | `VarcharType` | |
| `TEXT`, `XML` | `StringType` | |
| `BIT` | `BooleanType` | |
| `DATE` | `DateType` | |
| `DATETIME`, `DATETIME2`, `SMALLDATETIME`, `TIME` | `TimestampType` ou `TimestampNTZType` | Controlado pela opção `preferTimestampNTZ` (default `false` → `TimestampType`) |
| `BINARY`, `VARBINARY`, `IMAGE`, `GEOGRAPHY`, `GEOMETRY`, `TIMESTAMP` (rowversion), `UDT` | `BinaryType` | ⚠️ `TIMESTAMP` do SQL Server é rowversion, **não** datetime |

---

## 4. Discovery e Perfilamento Client-Side (sem extração)

Um Foreign Catalog expõe metadados via `information_schema` da mesma forma que um catalog nativo UC — confirmado no curso via `adventureworks.information_schema.columns` (`04 - Activate/4.4 Demo`). Por extensão do mesmo mecanismo (não verificado literalmente no corpus), `information_schema.tables` deve funcionar igual — confirme na doc oficial se for crítico.

**Listar tabelas e colunas da origem sem extrair dados:**
```sql
-- Todas as tabelas do banco SQL Server espelhado no Foreign Catalog `adventureworks`
SELECT table_schema, table_name
FROM adventureworks.information_schema.tables
ORDER BY table_schema, table_name;

-- Colunas + tipos de uma tabela específica na origem
SELECT column_name, data_type, is_nullable
FROM adventureworks.information_schema.columns
WHERE table_schema = 'dbo'
  AND table_name = 'DimCustomer'
ORDER BY ordinal_position;
```

**Perfilar contagens e NULLs sem mover a base inteira** (mesmas colunas do baseline em `04 - Activate/4.1 Lecture - Testing and Data Validation`, seção "Null count validation", aqui lidas ao vivo via Federation em vez de exportadas por BCP/ADF — confirme compute qualificado, seção 2, antes de rodar em tabelas grandes):
```sql
SELECT
  COUNT(*)                              AS total_rows,
  COUNT(CustomerKey)                    AS non_null_customer_key,
  COUNT(*) - COUNT(CustomerKey)         AS null_customer_key,
  COUNT(PromotionKey)                   AS non_null_promotion_key,
  COUNT(*) - COUNT(PromotionKey)        AS null_promotion_key
FROM adventureworks.dbo.FactInternetSales;
```

---

## 5. Validação de Schema Origem×Destino (query padrão)

Fonte literal: `04 - Activate/4.4 Demo - Activation Phase`, seção "Schema Comparison via Lakehouse Federation". Compara colunas da tabela já migrada (`information_schema.columns` local) contra a tabela ainda ao vivo no SQL Server (`<foreign_catalog>.information_schema.columns`):

```sql
-- Comparação de schema cross-platform (ex.: DimCustomer)
-- Compara colunas da tabela bronze local contra a origem SQL Server via Federation
WITH local_cols AS (
  SELECT column_name, data_type, is_nullable
  FROM information_schema.columns
  WHERE table_schema = 'adventureworks_bronze'
    AND table_name = 'dimcustomer'
),
remote_cols AS (
  SELECT column_name, data_type, is_nullable
  FROM adventureworks.information_schema.columns   -- adventureworks = Foreign Catalog
  WHERE table_schema = 'dbo'
    AND table_name = 'DimCustomer'
)
SELECT
  COALESCE(l.column_name, r.column_name) AS column_name,
  r.data_type AS sqlserver_type,
  l.data_type AS databricks_type,
  CASE
    WHEN l.column_name IS NULL THEN 'MISSING IN TARGET'
    WHEN r.column_name IS NULL THEN 'EXTRA IN TARGET'
    ELSE 'PRESENT'
  END AS status
FROM local_cols l
FULL OUTER JOIN remote_cols r
  ON LOWER(l.column_name) = LOWER(r.column_name)
ORDER BY status DESC, column_name;
```

**Leitura do resultado:**
- `MISSING IN TARGET` → coluna existe na origem, ainda não migrada.
- `EXTRA IN TARGET` → coluna existe no destino mas não na origem (ex.: coluna técnica `_ingestion_date`).
- `PRESENT` → existe nos dois lados; comparar manualmente `sqlserver_type` × `databricks_type` usando a matriz da seção 3 para achar incompatibilidades de tipo — a query **não** sinaliza `TYPE MISMATCH` automaticamente.

**Tolerância de ponto flutuante** (mesma fonte, `4.4 Demo`): ao comparar agregações `FLOAT`/`REAL`, use tolerância (ex.: 0.0001%) em vez de igualdade exata — SQL Server `FLOAT` (IEEE 754 double) alinha com Spark `DOUBLE`, mas arredondamento intermediário pode divergir. `DECIMAL`/`MONEY` devem bater exatamente.

---

## 6. Quando Usar Federation vs Extração (BCP/ADF)

Fonte: `03 - Execute/3.2 Lecture - Data Migration and Ingestion`, "Pattern 1: Lakehouse Federation" vs "Pattern 2: Shared Cloud Storage".

| Critério | Federation (Pattern 1) | Extração — BCP/ADF/SSIS → ADLS Gen2 → `COPY INTO`/Auto Loader (Pattern 2) |
|---|---|---|
| **Volume ideal** | Pequeno/médio (< ~100 GB), tabelas de dimensão/lookup | Médio a muito grande — qualquer volume |
| **Mecanismo** | JDBC via Foreign Catalog, `CTAS`/`INSERT INTO ... SELECT` direto | Export para Parquet (preferencial) → storage compartilhado → ingestão em Delta |
| **Throughput** | Limitado por conexão JDBC única — sem paralelismo na origem | Alto — paralelizável (ADF Copy Activity, múltiplos arquivos) |
| **Rede** | Requer conectividade JDBC ao vivo (VPN, private endpoint, IP público) | Não requer conexão direta SQL Server↔Databricks — ambos acessam o storage |
| **Vantagem** | Mais simples: sem staging, sem tooling de export, sem preocupação de formato | Desacopla export de ingestão; arquivos validáveis antes de carregar; retry sem reexportar |
| **Limitação** | Não serve para fact tables multi-TB | Requer provisionar e gerenciar conta de storage de staging |
| **Uso na migração** | Discovery, perfilamento, validação de schema/contagens, joins pontuais origem×destino, delta final no cutover | Carga em massa de fact tables e tabelas grandes |

**Regra prática** (curso, seção "Choosing a Pattern"): os padrões se combinam por tabela — dimensões pequenas migram via Federation, fact tables grandes usam extração. Ferramentas de export: **ADF** (Copy Activity gerenciado, agendamento/retry — melhor para escala), **BCP** (utilitário CLI do SQL Server, exporta CSV/formato nativo, requer conversão extra para Parquet), **SSIS** (pacotes existentes, pode rodar via ADF Integration Runtime). Lakebridge (Databricks Labs) cobre análise/transpilação/reconciliação mas **não move dados** — BCP/ADF/SSIS fazem o export físico.

---

## 7. Uso Durante Coexistência e Cutover

Fonte: `0.4 Lecture` (seção "Use Cases") + `04 - Activate/4.3 Lecture - Cutover Execution`.

| Caso de uso | Descrição |
|---|---|
| **Query Before Migration** | Acessar dado do SQL Server sem extrair |
| **Cross-System Joins** | Juntar tabelas SQL Server com tabelas UC já migradas numa única query (o join roda no Databricks — não é pushed down, ver seção 2) |
| **Data Validation** | Comparar origem × destino lado a lado antes do cutover (seções 4–5) |
| **Gradual Migration** | Migrar objetos incrementalmente enquanto consumidores seguem consultando via Federation |
| **Delta final no cutover** | `MERGE INTO` na tabela bronze usando o Foreign Catalog como `USING` — captura as últimas mudanças da origem no momento do corte (`4.3 Lecture - Cutover Execution`) |

**Federation é padrão transicional, não arquitetura permanente.** Após o dado migrado e validado, **retire o Foreign Catalog e a Connection** (0.4 Lecture, Summary).

---

## 8. Hive Metastore Federation (Hadoop)

> Mesmo par de objetos UC (Connection + Foreign Catalog) da federação SQL Server (seção 1), mas para
> uma origem **Hive Metastore** de um cluster Hadoop. Fonte curso *Hadoop Migration*:
> `00 - Foundations/0.4 Lecture - Interoperability Patterns`, "Pattern 1: Hive Metastore Federation"
> — o curso descreve o mecanismo com imprecisão (ver 8.1). **Fatos abaixo verificados oficialmente**
> (docs.databricks.com, ago/2026): [Hive metastore federation — concepts](https://docs.databricks.com/aws/en/query-federation/hms-federation-concepts)
> e [Enable HMS federation for an external Hive metastore](https://docs.databricks.com/aws/en/query-federation/hms-federation-external).

### 8.1 Correção do curso — o que `CREATE CONNECTION ... TYPE hive_metastore` realmente conecta

O curso (`0.4 Lecture`, quadro "Key Objects" e "Authentication") descreve a Connection como
apontando para "the Hive Metastore Thrift URI", com o Foreign Catalog lendo o storage diretamente e
resolvendo localização "from Hive Metastore" via Thrift. **Isso é impreciso** — verificado
oficialmente:

- `CREATE CONNECTION ... TYPE hive_metastore` conecta ao **banco relacional que armazena os metadados
  do HMS** (parâmetro `db_type`: `MYSQL`, `SQLSERVER` ou `POSTGRESQL`), **não** a um endpoint Thrift
  do HiveServer2/Metastore service. Não há campo de URI Thrift na sintaxe real.
- Metastores suportados: HMS legado **interno** do próprio workspace Databricks, HMS **externo** em
  Apache Hive 0.13/2.3/3.1 (backend MySQL/SQL Server/Postgres), e **AWS Glue**.
- Unity Catalog faz **crawl** do HMS (através dessa conexão ao banco relacional) para popular um
  **Foreign Catalog** (também chamado *federated catalog*); a partir daí, leituras usam essa metadata
  para localizar e ler os arquivos ORC/Parquet diretamente no storage — a **Connection em si não é**
  o caminho de leitura dos dados, só de metadados.

```sql
-- Passo 1: Connection — aponta para o BANCO RELACIONAL que sustenta o HMS, não para um Thrift endpoint
CREATE CONNECTION hms_legado_conn TYPE hive_metastore
OPTIONS (
  host '<host-do-banco-do-hms>',
  port '<porta>',
  user secret ('<secret-scope>', '<secret-key-user>'),
  password secret ('<secret-scope>', '<secret-key-password>'),
  database '<nome-do-banco>',
  db_type 'MYSQL',        -- ou 'SQLSERVER', 'POSTGRESQL'
  version '2.3'           -- versão do Hive Metastore: 0.13, 2.3 ou 3.1
);

-- Passo 2: Foreign Catalog — UC faz crawl do HMS via a Connection acima
CREATE FOREIGN CATALOG IF NOT EXISTS hms_in_uc USING CONNECTION hms_legado_conn
OPTIONS (
  authorized_paths 's3://bucket/hive/warehouse/',   -- storage cloud com os dados reais (ORC/Parquet)
  storage_root 's3://bucket/hms-catalog-metadata/'
);
```

`authorized_paths` restringe quais caminhos de storage cloud o Foreign Catalog pode expor — só
tabelas cobertas por esses paths ficam acessíveis (proteção contra redirecionamento de localização
via metadata do HMS). Requer privilégio `CREATE CONNECTION` no metastore UC (metastore admins têm por
padrão) e `CREATE CATALOG` para o Foreign Catalog.

### 8.2 HDFS on-premises NÃO é suportado

Storage suportado para os dados por trás do HMS federado: **cloud object storage** (S3/ADLS/GCS,
conforme a nuvem). **Dados em cluster HDFS on-premises NÃO são suportados** — nem em "remote mode"
(Thrift), que também não é suportado; a documentação oficial exige configuração em "local mode" para
o restante do mecanismo. Isso corrige qualquer leitura do curso que sugira Hive Metastore Federation
como caminho direto para HDFS on-premises: **para Hadoop on-premises, o padrão é extrair/DistCp para
storage cloud primeiro** (ver `kb/hadoop-migration/concepts/hdfs-ingestion.md`), e só então federar ou
migrar a partir do storage cloud.

### 8.3 Read-only (HMS externo) vs Writeable (HMS legado do workspace)

| Origem federada | Leitura | Escrita |
|---|---|---|
| HMS **externo** (Hive standalone, backend MySQL/SQL Server/Postgres fora do workspace) ou **AWS Glue** | ✅ | ❌ — foreign catalog é **read-only** |
| HMS **legado interno** do próprio workspace Databricks (o HMS que o workspace já usava antes do UC) | ✅ | ✅ — DDL (`CREATE`/`ALTER`/`DROP TABLE`) e DML (`INSERT`/`UPDATE`/`DELETE`) são refletidos **de volta, de forma síncrona**, no HMS subjacente |

O caso *writeable* (HMS legado do workspace) é o que sustenta uma migração incremental de "metastores
espelhados": workloads antigos continuam contra o HMS, workloads novos apontam para o Foreign Catalog
(`USE CATALOG hms_in_uc`), e ambos enxergam o mesmo estado. ⚠️ `DROP SCHEMA ... CASCADE` em um Foreign
Catalog *writeable* **dropa de verdade** as tabelas no HMS subjacente, sem `UNDROP` (HMS não suporta)
— tratar como operação destrutiva real, não como abstração isolada do UC.

### 8.4 Requisitos de Compute e Limitações

| Compute | Suportado |
|---|---|
| Standard / Dedicated access mode, Serverless (todos), SQL Warehouses (todos) | ✅ |
| DBR 13.3 LTS, 14.3 LTS, 15.1+; DBR 16.2+ para Iceberg (Public Preview) | ✅ |
| No isolation clusters | ❌ |

Recursos UC **não suportados** em foreign tables do HMS: predictive optimization, AI Search/
OpenSharing, data quality monitoring, online tables, parte do feature store, e materialized
views/streaming tables do Lakeflow **como destino** de escrita (podem ser usadas como **origem**).
Limitação adicional: não é possível consultar uma tabela federada cujos arquivos ficam **fora** da
location declarada da tabela (ex.: partições externas, `avro.schema.url`) — gera
`UNAUTHORIZED_ACCESS`/`AccessDeniedException`.

### 8.5 Fluxo de Migração Incremental via HMS Federation

Fonte: docs.databricks.com/aws/en/query-federation/hms-federation-concepts, seção "How do you use
Hive metastore federation during migration to Unity Catalog?". Aplica-se ao caso *writeable* (HMS
legado do workspace):

1. Federar o HMS interno → cria `hms_in_uc` (foreign catalog espelho).
2. Workloads **novos** apontam para `hms_in_uc` (`USE CATALOG hms_in_uc` ou default catalog do
   compute) — já ganham controle de acesso UC, lineage e search.
3. Migrar jobs existentes: trocar o catalog default para `hms_in_uc`, mover para compute
   Standard/Dedicated em DBR compatível, revisar grants UC.
4. Desativar acesso direto ao HMS, aplicar **Enforce user isolation**, tornar o catalog federado o
   default do workspace.

Utilitário **UCX** (Databricks Labs) automatiza os passos `enable-hms-federation` e
`create-federated-catalog`.

---

## 9. Teradata Federation & Interop

> Dois padrões **complementares e de direção oposta** (fonte: curso *Teradata Migration* —
> `00 - Foundations/0.4 Lecture - Interoperability Patterns`, via `_digest_fase0-2.md` §2):
> **9.1 Lakehouse Federation** (Databricks lê o Teradata ao vivo — mesma direção das seções 1-8,
> **verificado ao vivo na doc oficial** nesta sessão) e **9.2 Teradata Open Table Format/Iceberg**
> (Teradata lê tabelas Delta/UC — direção **inversa**, e **não verificado independentemente** além do
> que o curso descreve — tratar com mais cautela que 9.1).

### 9.1 Lakehouse Federation para Teradata (`CREATE CONNECTION ... TYPE teradata`)

**Verificado ao vivo nesta sessão** em `docs.databricks.com/aws/en/query-federation/teradata`
(página atualizada **9/abr/2026**) — não apenas repassado do curso:

```sql
-- Conexão (Catalog Explorer ou SQL) — usar secrets, nunca credencial em texto plano
CREATE CONNECTION teradata_federation TYPE teradata
OPTIONS (
  host '<hostname>',
  port '<port>',              -- 1025 é o padrão Teradata JDBC
  user secret ('<secret-scope>', '<secret-key-user>'),
  password secret ('<secret-scope>', '<secret-key-password>'),
  ssl_mode '<ssl_mode>'        -- opcional: require | prefer | verify-ca | verify-full | disable
);

-- Foreign catalog — espelha um banco Teradata inteiro
CREATE FOREIGN CATALOG IF NOT EXISTS teradata_fc USING CONNECTION teradata_federation
OPTIONS (database '<database-name>');
```

**Requisitos confirmados (doc oficial, não apenas o curso):**

| Requisito | Valor |
|---|---|
| Databricks compute | Runtime **16.1+**, modo de acesso **Standard** ou **Dedicated** |
| SQL Warehouses | **Pro ou Serverless**, canal **2024.50+** |
| Autenticação | **Somente TD2** (usuário/senha padrão do Teradata) — **LDAP, Kerberos e TDNEGO NÃO são suportados** |
| TLS | `ssl_mode`: `require`/`prefer`/`verify-ca`/`verify-full`/`disable` — Databricks recomenda aceitar SSL; `disable` só se o servidor não aceitar SSL |
| Permissões | `CREATE CONNECTION` no metastore UC (para a Connection); `CREATE CATALOG` + (ownership da Connection OU `CREATE FOREIGN CATALOG` na Connection) |

Isso confirma exatamente o que o curso já afirmava — *"No RSA key pairs are required — Teradata JDBC
uses password-based authentication"* (`_digest_fase0-2.md` §2, Padrão 2) — e a porta padrão **1025**.

**⚠️ Achado novo desta verificação (não estava nos digests do curso) — mudança de `TMODE` por versão
de Runtime:** o conector Teradata usa `TMODE=ANSI` por padrão em todas as sessões a partir do
**Databricks Runtime 17.1**. Em modo `ANSI`, comparação de string é **case-sensitive**; no modo legado
`TERA` do Teradata, é **case-insensitive** (`'ABC' = 'abc'` avalia `true`). Ao migrar para DBR 17.1+,
SQL Warehouse ou Serverless, o modo de sessão padrão muda de `TERA` para `ANSI` — isso pode alterar o
resultado de views/queries Teradata que dependem de comparação case-insensitive (ex.: `WHERE status =
'Active'` pode não casar mais com `'ACTIVE'`/`'active'`). **Mesma classe de problema já documentada em
`ddl-conversion.md` §2** (a afirmação do curso de que "Delta usa collation case-insensitive por
padrão" é falsa — `UTF8_BINARY` é case-sensitive) — reforça que qualquer comparação de string
Teradata→Databricks deve ser revisada para sensibilidade a maiúsculas/minúsculas, seja via Federation
ao vivo ou pós-migração.

**Pushdown confirmado na doc oficial** (tabela "Supported pushdowns" — capturada parcialmente nesta
verificação): `Aggregates` → suportado em **todo compute** (diferente da matriz de pushdown de SQL
Server, seção 2 acima, onde agregações exigem compute qualificado DBR 13.3+/Warehouse — **não
assumir que a matriz da seção 2 vale idêntica para Teradata**); `Cast` → suportado em todo compute;
`Contains`/`Startswith`/`Endswith`/`Like` → suportado. A listagem completa (filtros, joins, window
functions, `ORDER BY`/`LIMIT`) não foi capturada integralmente nesta sessão — **`[a verificar]`**
consultar a doc oficial para a matriz completa antes de assumir suporte a uma operação não listada
acima.

**Setup do lado Teradata** (curso, `_digest_fase0-2.md` §2 Padrão 2 — não verificado na doc oficial
Teradata nesta sessão, mas plausível e consistente com sintaxe DDL Teradata padrão):

```sql
CREATE ROLE databricks_federation_role;
CREATE USER DATABRICKS_FEDERATION_USER AS PERMANENT = 100e6, PASSWORD = '<senha-forte>';
GRANT databricks_federation_role TO databricks_federation_user;
GRANT SELECT ON DATABASE <database> TO databricks_federation_role;
-- Verificação:
SELECT * FROM DBC.UsersV WHERE UserName = 'DATABRICKS_FEDERATION_USER';
SELECT * FROM DBC.RoleInfoV WHERE RoleName = 'DATABRICKS_FEDERATION_ROLE';
```

**Fontes suportadas pela Lakehouse Federation, conforme citado pelo curso:** "HMS, AWS Glue, Teradata,
MySQL, PostgreSQL" — ⚠️ tratar "HMS" nesta lista com a mesma ressalva da seção 8: HMS é acessado por um
mecanismo de Connection distinto (`TYPE hive_metastore`, que aponta para o banco relacional por trás
do HMS — seção 8.1), não necessariamente o mesmo fluxo simples de `TYPE teradata`/`TYPE mysql`.

### 9.2 Teradata Open Table Format (OTF) / Iceberg — Direção Inversa (Teradata lê Databricks)

⚠️ **Esta subseção é sourced do curso e NÃO foi verificada de forma independente na documentação
oficial da Teradata nesta sessão** (diferente de 9.1, que foi confirmada ao vivo) — tratar com mais
cautela, revalidar antes de propor a um cliente. Fonte: `_digest_fase0-2.md` §2 Padrão 1.

- **Direção:** Databricks é dono do dado (Unity Catalog); Teradata (Database Engine 20) é o motor de
  consulta **externo**, lendo tabelas Delta como Iceberg nativo.
- **Mecanismo do lado Databricks:** Service Principal (OAuth) + Iceberg REST API + **UniForm** — a
  tabela Delta precisa ter `delta.universalFormat.enabledFormats = 'iceberg'`,
  `delta.enableIcebergCompatV2 = true`, `delta.columnMapping.mode = 'name'`.
- **Mecanismo do lado Teradata — feature "Open Table Format" (OTF):**
  ```sql
  CREATE DATALAKE unity_catalog_dl
  USING
    catalog_type('Unity')
    catalog_location('/api/2.1/unity-catalog/iceberg')
    unity_catalog_name('<nome-do-catalog-uc>')
    storage_account_name('<storage-account>')
    tenant_id('<azure-tenant-id>')
    default_cluster_id('<cluster-id>')
  TABLE FORMAT ICEBERG;

  -- Uma vez criado o DATALAKE, todas as tabelas do catálogo ficam acessíveis via notação de 3 partes,
  -- SEM precisar de CREATE TABLE/registro por tabela (auto-discovery):
  SELECT * FROM unity_catalog_dl.demo_schema.customer_bronze;
  ```
- **Requer "Database Engine 20"** (afirmação do curso, não verificada independentemente).
- **`WRITE_NOS`/`READ_NOS` (Native Object Store) NÃO suportam Iceberg** — precisam ser `DATALAKE`; são
  mecanismos distintos (ver `ingestion-cdc.md` §5 sobre `WRITE_NOS`/Parquet/CSV).
- **Time travel do lado Teradata:** `... AT SNAPSHOT ID ...`, `... BEFORE (TIMESTAMP '...')`, funções
  `TD_SNAPSHOTS(...)`/`TD_PARTITIONS(...)`.

⚠️ **Caveat crítico — o próprio curso admite que isto é fora do escopo prático:** a lição de Storage &
Governance do mesmo curso (`_digest_fase0-2.md` §5, 2.3) afirma explicitamente *"Iceberg migration
patterns are outside the scope of this course due to limited adoption"*. **Tratar OTF/`CREATE DATALAKE`
como feature de nicho, não como caminho padrão de interoperabilidade** — o caminho padrão, recomendado
e verificado é a Lakehouse Federation (9.1). Não propor OTF como primeira opção sem o cliente já ter
uma necessidade concreta de BI legado apontando para Teradata durante a coexistência.

### 9.3 Guia de Seleção de Padrão e Duração de Coexistência

Fonte: `_digest_fase0-2.md` §2 ("Pattern Selection Guide", "Why Coexistence").

| Cenário | Padrão recomendado |
|---|---|
| Databricks já é o sistema de registro alvo, mas BI/consumidores legados ainda precisam consultar via Teradata | 9.2 (OTF — Teradata lê Databricks) |
| Databricks precisa consultar o Teradata (ainda fonte viva) durante a migração | 9.1 (Federation — Databricks lê Teradata) |
| BI temporariamente ainda aponta para o Teradata | 9.2 (OTF) |
| Validar dado migrado antes do cutover (comparar origem × destino) | 9.1 (Federation) |

Os dois padrões **podem ser combinados** durante a coexistência.

**Duração típica de coexistência por tamanho de migração:**

| Tamanho (nº de objetos) | Duração típica |
|---|---|
| Small (< 50) | 1-2 meses (considerar pular a coexistência) |
| Medium (50-500) | 3-6 meses |
| Large (500+) | 6-12+ meses (coexistência completa) |

---

## Regras

1. Federation para SQL Server (seções 1-7) é **read-only** — nunca uma via de escrita de volta ao SQL Server. (Hive Metastore Federation tem exceção parcial — ver regra 9.)
2. **Nunca** perfilar/agregar tabelas grandes via Federation em compute sem pushdown de agregação (< DBR 13.3, cluster não-Warehouse) sem avaliar o custo — a tabela inteira é puxada via JDBC primeiro.
3. **Nunca** assumir pushdown de joins entre tabelas federadas ou de window functions — sempre executados no Databricks após transferência (seção 2).
4. Fact tables grandes (multi-TB) → extração (BCP/ADF/SSIS + `COPY INTO`/Auto Loader), não Federation (seção 6).
5. Ao final da migração e validação, **retire** Connection + Foreign Catalog — Federation não deve virar dependência permanente de produção.
6. Confirme a versão mínima de DBR/SQL Warehouse na documentação oficial antes de planejar — os números desta KB vêm do curso e podem ter mudado.
7. Hive Metastore Federation: `CREATE CONNECTION TYPE hive_metastore` aponta para o **banco relacional** do HMS (MySQL/SQL Server/Postgres) — nunca assumir um endpoint Thrift direto (seção 8.1).
8. **Nunca** propor Hive Metastore Federation para dados em HDFS on-premises sem storage cloud — não suportado; extrair/DistCp para cloud primeiro (seção 8.2).
9. Antes de assumir que um Foreign Catalog de HMS aceita escrita, confirmar se a origem é o HMS legado do próprio workspace (writeable) ou um HMS externo/AWS Glue (read-only) — seção 8.3.
10. `DROP SCHEMA/TABLE` num Foreign Catalog de HMS *writeable* é destrutivo de verdade no HMS subjacente (sem `UNDROP`) — tratar com o mesmo rigor de um `DROP` em produção (seção 8.3).
11. Teradata Federation (`CREATE CONNECTION ... TYPE teradata`) autentica **exclusivamente via TD2** (usuário/senha) — LDAP, Kerberos e TDNEGO não são suportados (verificado ao vivo, doc oficial) — nunca proponha um desses três como alternativa (seção 9.1).
12. Exige Databricks Runtime **16.1+** (Standard/Dedicated) ou SQL Warehouse **Pro/Serverless canal 2024.50+** — confirme na doc oficial antes de planejar, mesma cautela da regra 6 (seção 9.1).
13. A partir do Databricks Runtime **17.1+**, o conector Teradata usa `TMODE=ANSI` por padrão (case-sensitive), diferente do modo legado `TERA` do Teradata (case-insensitive) — sempre revisar comparações de string que dependiam do comportamento case-insensitive da origem antes de migrar/federar (seção 9.1).
14. Teradata Open Table Format (`CREATE DATALAKE ... TABLE FORMAT ICEBERG`) é feature de nicho e **não verificada independentemente** nesta KB — o próprio curso-fonte admite que está "fora do escopo... devido à adoção limitada". Não tratar como caminho padrão de interoperabilidade nem propor como primeira opção — o caminho padrão é a Federation (regra 11/seção 9.1). `WRITE_NOS`/`READ_NOS` NÃO suportam Iceberg — só `CREATE DATALAKE` (seção 9.2).
