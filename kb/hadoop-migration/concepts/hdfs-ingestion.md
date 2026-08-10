# HDFS → Databricks — Padrões de Ingestão

> Escopo: migração de dados em massa de HDFS (on-premises ou Hadoop-em-cloud) para Delta Lake no
> Databricks. Fonte normativa: curso oficial Databricks *"Hadoop Migration"*, `03 - Execute/3.2
> Lecture - Data Migration and Ingestion`. Fonte de verdade operacional de um futuro agente
> `hadoop-to-databricks` (ver auditoria `audits/2026-08-02-curso-hadoop-migration-vs-ai-data-agents.md`,
> item H4) — até esse agente existir, consultado por `migration-expert` e `databricks-engineer`.
> Irmãos deste domínio: `concepts/hive-ddl-conversion.md` (mapa de tipos e conversão de DDL Hive),
> `concepts/sqoop-cdc.md` (ingestão incremental/CDC) e `concepts/oozie-orchestration.md`
> (orquestração). Ver também
> `kb/databricks/concepts/lakehouse-federation.md` (Federation genérico — hoje só SQL Server; aqui o
> tipo `hive_metastore`) e `kb/migration/concepts/reconciliation.md` (os 7 parity checks,
> reaproveitados 1:1 para origem Hadoop).
>
> **Aviso de proveniência:** o curso Hadoop mistura, em alguns módulos, material mal-adaptado do
> curso irmão *SQL Server Migration* (DMVs T-SQL rotuladas "Hadoop", `AdventureWorksDW`,
> `sp_cdc_*`, connection string `...database.windows.net:1433`). Este arquivo usa **somente** os
> trechos verificados como Hadoop-válidos da lecture 3.2 (Sqoop, DistCp, HDFS, Hive Metastore,
> ORC/Parquet/Avro) — nenhum exemplo aqui vem do resíduo SQL Server. Onde a sintaxe de plataforma
> (Hive Metastore Federation) foi verificada contra a documentação oficial Databricks (não apenas o
> curso), isso está marcado explicitamente.

**Domínio:** HDFS → Delta, Catalog Federation (HMS), DistCp, Direct File Read, formatos, small files, particionamento Hive

---

## 1. Preparação da origem (source readiness)

Antes de qualquer extração em massa, o cluster Hadoop precisa ser estabilizado para garantir um
snapshot consistente. A abordagem depende do tipo de workload e da tolerância a downtime (fonte: 3.2,
"Source Readiness: Preparing Hadoop for Bulk Migration").

| Nível | Ação | Efeito | Quando usar |
|---|---|---|---|
| **Suspensão de jobs** | Pausar todos os Oozie coordinators e cron jobs que escrevem nas tabelas em escopo — via CLI padrão do Oozie (`oozie job -suspend -oozie <url> -id <coordinator-id>`) | Nenhuma escrita nova nas tabelas-alvo | Janela de manutenção agendada, cutover final |
| **HDFS snapshot** | `hdfs dfs -createSnapshot <path> <name>` nos diretórios de origem | Leitura consistente em um ponto no tempo | Downtime mínimo — snapshot enquanto outros jobs continuam em tabelas fora do escopo |
| **Hive ACID freeze** | Travar tabelas Hive ACID ou setar read-only via política Ranger/Sentry | Impede escritas transacionais durante a migração | Somente tabelas Hive 3.x ACID |
| **Sem freeze** | Exportar com a origem viva, reconciliar com sync incremental depois | Fonte continua servindo tráfego; exige catch-up incremental | Requisito de zero downtime — ver `concepts/sqoop-cdc.md` |

**Regra:** suspender coordinators/travar tabelas Hive quebra qualquer pipeline downstream que dependa
delas — sempre coordenar com os donos do workload numa janela acordada (3.2).

> Nota de reaproveitamento: a metodologia de freeze window / matriz de rollback de
> `kb/migration/concepts/cutover-rollback.md` é reaproveitável para o corte final Hadoop — mas os
> comandos concretos lá (`sp_update_job`, LSN via `fn_cdc_get_max_lsn`) são SQL Server. O
> equivalente Hadoop para o freeze é a suspensão de coordinators + `hdfs dfs -createSnapshot` acima.

---

## 2. Os 3 padrões — visão geral

| Padrão | Localização da origem | Cloud alvo | Mecanismo-chave | Caso de uso típico |
|---|---|---|---|---|
| **1 — Catalog Federation** | Hive Metastore acessível pela rede | Azure, AWS ou GCP | Unity Catalog Foreign Catalog → HMS | Datasets pequenos/médios, descoberta orientada a metadados, operação híbrida |
| **2 — DistCp → Cloud Storage** | HDFS on-premises ou Hadoop cloud-adjacent | Azure, AWS ou GCP | DistCp / AzCopy / `aws s3 cp` / `gsutil` | Migração em larga escala, desativação de data center |
| **3 — Direct File Read** | Dados HDFS já em cloud storage (ORC/Parquet/Avro) | Mesma cloud do storage | `read_files` / `COPY INTO` / Auto Loader | Hadoop cloud-native (EMR, HDInsight, Dataproc) ou pós-DistCp |

(fonte: 3.2, "Migration Pattern Overview"). **Os padrões se combinam por tabela** — dimensões
pequenas via Federation, fatos grandes via DistCp, Hadoop já-em-cloud via Direct Read (3.2, "Patterns
can be combined").

### Árvore de decisão

1. Dado já está em cloud storage (S3/ADLS/GCS)? → **Padrão 3** (Direct File Read).
2. Dado está em HDFS on-prem e o volume é < ~100 GB **e** o Hive Metastore é alcançável da rede do
   Databricks? → **Padrão 1** (Catalog Federation) — ver limitação importante no §3.
3. Dado está em HDFS on-prem e é grande (≥ ~100 GB) **ou** o HMS não é alcançável? → **Padrão 2**
   (DistCp).

(fonte: 3.2, "Choosing a Pattern" — árvore de decisão)

---

## 3. Padrão 1 — Catalog Federation para Hive Metastore

Unity Catalog federa para um Hive Metastore, expondo tabelas Hive como objetos no Databricks
(read-only ou read-write, conforme abaixo). Serve para descoberta inicial, datasets pequenos e
operação híbrida durante a migração (3.2, "Pattern 1: Catalog Federation to Hive Metastore").

**Mecanismo real (verificado na documentação oficial Databricks, ago/2026 — difere de uma conexão
Thrift ao vivo):** `CREATE CONNECTION ... TYPE hive_metastore` conecta ao **banco relacional que
armazena o catálogo do Hive** (MySQL, SQL Server ou PostgreSQL — o backing DB do próprio Hive
Metastore), não a um serviço Thrift do HiveServer2. A documentação oficial é explícita: **Hive
Metastore Federation não suporta modo remoto sobre Apache Thrift** ("you must provide local mode
configurations instead") e **dado em HDFS on-premises não é um tipo de storage suportado** pela
federação. Na prática, isso refina o Padrão 1 do curso: ele funciona melhor quando (a) o Hive
Metastore é **legado interno do próprio workspace Databricks** (federação cuida da autorização
automaticamente, é read-write), ou (b) o HMS é **externo**, seu banco relacional
(MySQL/SQL Server/PostgreSQL) é alcançável pela rede, **e** os dados das tabelas já estão em cloud
storage suportado (S3 confirmado na doc AWS; confirmar o equivalente ADLS Gen2/GCS na doc da
plataforma correspondente antes de aplicar) — o caso típico de Hadoop já-em-cloud (EMR/HDInsight/
Dataproc) ou de HDFS on-prem já parcialmente migrado para cloud storage. **Para HDFS genuinamente
on-premises sem esse pré-requisito, use o Padrão 2 (DistCp).**

**Sintaxe (3 passos — verificada literalmente na documentação oficial):**

```sql
-- 1. Connection: aponta para o BANCO RELACIONAL por trás do Hive Metastore (não um endpoint Thrift)
CREATE CONNECTION hms_prod TYPE hive_metastore
OPTIONS (
  host '<hostname>',
  port '<port>',
  user secret ('<secret-scope>', '<secret-key-user>'),
  password secret ('<secret-scope>', '<secret-key-password>'),
  database '<database-name>',
  db_type 'MYSQL',        -- ou 'SQLSERVER' / 'POSTGRESQL'
  version '2.3'           -- versões de Hive Metastore suportadas: 0.13, 2.3, 3.1
);

-- 2. Foreign Catalog: espelha o HMS inteiro (UC faz o crawl); paths cobertos por external location
CREATE FOREIGN CATALOG hms_catalog USING CONNECTION hms_prod
OPTIONS (
  authorized_paths 's3://bucket/warehouse/,s3://bucket/other_db/',
  storage_root 's3://bucket/catalog-metadata/'
);

-- 3. Materializar em Delta managed
CREATE TABLE main.bronze.dim_customer AS
SELECT * FROM hms_catalog.<hive_db>.<hive_table>;
```

(fonte: documentação oficial Databricks, "Enable Hive metastore federation for an external Hive
metastore" — verificada ago/2026)

Requer `CREATE CONNECTION` no metastore UC (metastore admins têm por padrão) e `CREATE CATALOG` +
`CREATE FOREIGN CATALOG` na connection para o passo 2. **Authorized paths** são uma camada extra de
segurança — só tabelas sob esses paths são consultáveis via o catalog federado.

| Tipo de Hive Metastore | Read/Write | Autorização |
|---|---|---|
| **Legado interno do workspace Databricks** | Read **e** write (DDL/DML sincronizados nos dois lados) | Federação cuida automaticamente |
| **Externo** (MySQL/SQL Server/PostgreSQL) | **Read-only** | Username/password (ou secret scope) no `CREATE CONNECTION` |
| **AWS Glue** | **Read-only** | IAM role |

(fonte: documentação oficial Databricks, "Hive metastore federation: enable Unity Catalog to govern
tables registered in a Hive metastore" — verificada ago/2026)

**Como funciona, de ponta a ponta:**
1. Jobs Hadoop que escrevem nas tabelas em escopo são pausados (ou snapshots de HDFS são tirados — §1).
2. Databricks lê as tabelas Hive através do Foreign Catalog usando SQL padrão.
3. `CREATE TABLE AS SELECT` (CTAS) ou `INSERT INTO ... SELECT` grava os dados em tabelas Delta managed.
4. Contagem de linhas e checksums são validados contra a origem — ver `kb/migration/concepts/reconciliation.md` §1 (os 7 parity checks se aplicam, trocando o dialeto de origem por HiveQL).

(fonte: 3.2, "How It Works" + validação oficial acima)

| Consideração | Detalhe |
|---|---|
| **Melhor para** | Tabelas pequenas/médias, dimensões, tabelas de metadados, operação híbrida em migração faseada |
| **Rede** | Conectividade ao banco relacional por trás do HMS + external location cobrindo os paths de storage das tabelas |
| **Cloud** | Qualquer cloud do Databricks — desde que o storage das tabelas seja um tipo suportado (HDFS on-prem não é) |
| **Vantagem** | Sem export/staging de arquivo; permite migração tabela-a-tabela incremental |
| **Limitação** | HDFS on-premises não suportado; modo remoto Thrift não suportado; não ideal para petabyte-scale |

> **Federation vs. External Hive Metastore legado:** Databricks também suporta configurar um Hive
> Metastore externo como opção legada de compute (fora do Unity Catalog). Catalog Federation via
> Unity Catalog é a abordagem recomendada — integra com a governança do UC, dá controle de acesso
> granular (inclusive row filters/column masks) e permite migração gradual tabela-a-tabela do Hive
> para o UC (3.2 + documentação oficial).

---

## 4. Padrão 2 — DistCp para Cloud Storage

Padrão mais comum em migrações Hadoop de larga escala: copiar dados do HDFS para cloud object
storage via DistCp (Distributed Copy) ou ferramentas cloud-nativas, depois ingerir em Delta a partir
do cloud storage. DistCp roda como job MapReduce, usando o compute do próprio cluster Hadoop para
paralelizar a cópia (fonte: 3.2, "Pattern 2: DistCp to Cloud Storage").

### Ferramentas de transferência

| Ferramenta | Origem | Destino | Melhor para |
|---|---|---|---|
| **DistCp** | HDFS | ADLS Gen2, S3, GCS (via connector) | HDFS on-premises → qualquer cloud; paralelismo via compute do cluster |
| **AzCopy** | Arquivos locais ou HDFS (via WebHDFS) | ADLS Gen2 | Migrações Azure |
| **`aws s3 cp` / `aws s3 sync`** | Arquivos locais ou HDFS (via mount) | S3 | Migrações AWS |
| **`gsutil`** | Arquivos locais ou HDFS (via mount) | GCS | Migrações GCP |
| **Azure Data Box / AWS Snowball** | Data center local | ADLS Gen2 / S3 | Datasets muito grandes (dezenas de TB+) onde transferência via rede é impraticável |
| **Serviços de transferência cloud (ADF, DataSync, Transfer Service)** | Diversos | ADLS Gen2 / S3 / GCS | Transferências gerenciadas e agendadas, com monitoramento |

Dados Hadoop já estão em formato colunar (ORC/Parquet) na maioria dos casos — diferente de migrações
RDBMS, não há necessidade de exportar para outro formato antes do DistCp: ele copia os arquivos como
estão, preservando o formato (3.2).

### Comando por cloud provider

```bash
# Azure (ADLS Gen2)
hadoop distcp hdfs:///data/ abfss://container@account.dfs.core.windows.net/data/ \
  -update -m 50 -bandwidth 100

# AWS (S3)
hadoop distcp hdfs:///data/ s3a://bucket/data/ \
  -update -m 50 -bandwidth 100

# GCP (GCS)
hadoop distcp hdfs:///data/ gs://bucket/data/ \
  -update -m 50 -bandwidth 100
```

| Cloud alvo | Protocolo | Connector exigido |
|---|---|---|
| **Azure** | A fonte do curso usa `abfs://`; ambientes que exigem TLS/external location no Databricks tipicamente usam a variante segura `abfss://` — confirmar o driver instalado no cluster Hadoop | JAR `hadoop-azure` com connector ABFS |
| **AWS** | `s3a://` | JAR `hadoop-aws` com connector S3A |
| **GCP** | `gs://` | JAR `gcs-connector` |

(fonte: 3.2, "DistCp Configuration by Cloud Provider")

**Flags relevantes:**

| Flag | Efeito |
|---|---|
| `-update` | Transferência incremental — pula arquivos que já existem no destino |
| `-m <N>` | Número de mappers MapReduce — controla o paralelismo da cópia |
| `-bandwidth <MB/s>` | Throttling — limita banda por mapper para não saturar a rede |

(fonte: 3.2, "DistCp Configuration by Cloud Provider" + "Network Considerations")

### Considerações de rede

| Fator | Orientação |
|---|---|
| **Banda** | Estimativa: 1 TB em link de 1 Gbps leva ~2,5 horas — planeje a janela de manutenção de acordo |
| **ExpressRoute / Direct Connect / Interconnect** | Se disponível, usar o circuito dedicado — evita congestionamento de internet, throughput consistente |
| **Paralelismo DistCp** | Ajustar `-m` conforme capacidade do cluster e banda disponível |
| **Compressão** | ORC/Parquet já são comprimidos — compressão adicional no transporte agrega CPU com pouco ganho |
| **Tamanho de arquivo** | Hadoop tende a gerar muitos arquivos pequenos — considerar compactação em HDFS antes do DistCp (ver §7) |

(fonte: 3.2, "Network Considerations")

### Ingestão em Databricks (após o DistCp)

| Mecanismo | Como funciona | Idempotente | Schema evolution | Melhor para |
|---|---|---|---|---|
| **`COPY INTO`** | Comando SQL que carrega arquivos de um path para uma tabela Delta existente; rastreia arquivos já carregados | Sim — pula arquivos já carregados | `mergeSchema` | Cargas batch simples, únicas ou periódicas |
| **Auto Loader** | Fonte Structured Streaming (`cloudFiles`) que monitora um path e ingere incrementalmente | Sim — checkpoint-based exactly-once | Inferência e evolução automática | Ingestão contínua, alto volume de arquivos, produção |
| **`read_files`** | Table-valued function para leitura ad-hoc; suporta todos os formatos | N/A (read-only) | Inferência automática | Exploração rápida, CTAS para carga única |

Todos os três suportam ORC, Parquet, CSV, JSON, Avro e texto. Para dados Hadoop já em ORC/Parquet,
`COPY INTO` ou `read_files` + CTAS é o caminho mais simples; Auto Loader é melhor quando arquivos
chegam ao longo do tempo ou é preciso checkpointing de produção (3.2).

| Consideração | Detalhe |
|---|---|
| **Melhor para** | Migrações de larga escala, desativação de data center, qualquer volume |
| **Rede** | Exige conectividade do cluster Hadoop ao cloud storage alvo; ou transferência física para opções offline |
| **Vantagem** | Desacopla transferência de ingestão; preserva formato original; arquivos podem ser validados antes da conversão para Delta |
| **Limitação** | Exige configurar connectors de cloud storage no cluster Hadoop; DistCp consome compute do cluster |

---

## 5. Padrão 3 — Direct File Read (Hadoop já em cloud)

Quando os dados Hadoop já residem em cloud storage (comum em deployments EMR, HDInsight ou Dataproc,
ou após um DistCp já ter rodado), o Databricks lê os arquivos diretamente e converte para Delta — sem
etapa de transferência adicional. É o padrão mais simples porque o dado já está em cloud storage
(fonte: 3.2, "Pattern 3: Direct File Read").

**Como funciona:**
1. Configurar uma external location ou volume no Unity Catalog apontando para o path de cloud storage onde os arquivos Hadoop residem.
2. Usar `read_files`, `COPY INTO` ou Auto Loader para ler os arquivos ORC/Parquet/texto.
3. Gravar em tabelas Delta managed via CTAS ou `INSERT INTO`.
4. Validar contagem de linhas e qualidade contra os metadados da tabela Hive de origem.

| Consideração | Detalhe |
|---|---|
| **Melhor para** | Deployments Hadoop cloud-native (EMR, HDInsight, Dataproc) ou após DistCp já ter deixado os arquivos em cloud |
| **Rede** | Databricks e o cloud storage devem estar na mesma cloud ou com acesso cross-cloud configurado |
| **Throughput** | Muito alto — limitado só pelo I/O do cloud storage |
| **Vantagem** | Sem transferência de dados; ler e converter in-place. O padrão mais simples quando o dado já está em cloud storage |
| **Limitação** | O dado precisa já estar em cloud storage; não se aplica a HDFS on-premises |

---

## 6. Formatos de arquivo

| Formato | Suporte Databricks | Notas de ingestão |
|---|---|---|
| **Parquet** | Nativo | Melhor formato para migração — preserva tipos e comprime bem |
| **ORC** | Nativo | Totalmente suportado; ler com `read_files(path, format => 'orc')` |
| **Avro** | Nativo | Totalmente suportado; schema embutido no arquivo |
| **Text / CSV** | Nativo | Exige especificação de schema; atenção a delimitador e encoding |
| **SequenceFile** | Via Spark RDD | Ler com `sc.sequenceFile()` em PySpark; converter para DataFrame, depois Delta |
| **RCFile** | Via Hive SerDe | Ler usando o suporte Hive do Spark; converter para Delta |
| **JSON** | Nativo | Suporta estruturas aninhadas; inferência de schema disponível |

(fonte: 3.2, "Handling Different File Formats")

---

## 7. Small-file problem

Ecossistemas Hadoop geram muitos arquivos pequenos com frequência — de imports incrementais Sqoop,
micro-batches de streaming, ou partições Hive de baixo volume. Isso prejudica tanto o DistCp (muitas
transferências pequenas) quanto a ingestão Delta (muitos arquivos Delta pequenos) (fonte: 3.2, "The
Small File Problem").

| Estratégia | Quando usar | Como |
|---|---|---|
| **Compactar antes da transferência** | Recursos de cluster disponíveis e janela de transferência flexível | Job Hive `INSERT OVERWRITE` ou compactação Spark para juntar arquivos pequenos antes do DistCp |
| **Transferir e compactar depois** | Minimizar trabalho no lado da origem | DistCp de todos os arquivos, carregar em Delta, depois `OPTIMIZE` para compactar |
| **Auto Loader com trigger** | Ingestão contínua de arquivos pequenos | Auto Loader agrupa arquivos pequenos automaticamente durante a ingestão |

```sql
-- Compactar pós-carga
OPTIMIZE main.bronze.dim_customer;
```

---

## 8. Tabelas Hive particionadas → Delta

Tabelas Hive particionadas por colunas como `year`, `month` ou `region` armazenam dados em estruturas
de diretório (`/warehouse/table/year=2024/month=01/`). Ao migrar para Delta (fonte: 3.2, "Handling
Hive Partitioned Tables"):

| Abordagem | Descrição |
|---|---|
| **Preservar particionamento** | Se a tabela é muito grande (1 TB+) e a chave de partição é seletiva, manter `PARTITIONED BY` no DDL Delta |
| **Converter para Liquid Clustering** | Para a maioria das tabelas, abandonar particionamento físico e usar `CLUSTER BY` — gestão mais simples, sem partition skew |
| **Ler com descoberta de partição** | Usar `read_files` ou Auto Loader com inferência de partição por path (`key=value`) |

> **Liquid Clustering substitui bucketing do Hive:** se a tabela Hive usava
> `CLUSTERED BY ... INTO N BUCKETS` para otimizar joins, Liquid Clustering entrega o mesmo benefício
> de co-localização sem exigir um número fixo de buckets — mais simples de gerenciar e pode ser
> alterado após a criação da tabela sem reescrever os dados (3.2). Ver
> `kb/spark-patterns/concepts/delta-lake-concepts.md` (CLUSTER BY vs ZORDER).

---

## 9. `LOCATION` externa Hive → managed Delta vs. manter external

Muitas tabelas Hive são `CREATE EXTERNAL TABLE ... LOCATION 'hdfs://...'` (ou já
`LOCATION 'abfss://...'`/`'s3a://...'` em Hadoop cloud-native). Na migração, decida explicitamente
entre:

| Opção | Quando usar | Efeito |
|---|---|---|
| **Managed Delta (default/recomendado)** | Caso padrão — Bronze/Silver/Gold do medallion (ver `kb/migration/index.md`, seção "Arquitetura Medallion para Tabelas Migradas") | Unity Catalog controla o ciclo de vida dos arquivos (localização no managed storage do catalog/schema); `DROP TABLE` remove os dados |
| **Manter external** | Coexistência com jobs Hadoop legados ainda lendo o mesmo path durante a migração faseada, ou storage já organizado por outro motivo (governança externa, retenção) | `CREATE TABLE ... LOCATION '<path>'` aponta para o mesmo storage; `DROP TABLE` remove só o metadado, não os arquivos |

**Regra prática:** ao converter para Delta, use **managed** por padrão — é o caminho recomendado do
Unity Catalog (hierarquia de três níveis `catalog.schema.table`, ver
`kb/databricks/concepts/unity-catalog-concepts.md`). Só mantenha `LOCATION` externa quando houver uma
razão operacional explícita (coexistência, rollback durante a janela de cutover) — e documente a
razão, porque tabelas external não se beneficiam do lifecycle/governança completos do UC (ex.:
predictive optimization é só para tabelas managed). Ver também `concepts/hive-ddl-conversion.md` §5
("Managed vs External Tables") para o mesmo mapeamento sob a ótica de conversão de DDL.

---

## 10. Bronze layer e otimização pós-ingestão

**Design da camada Bronze** (fonte: 3.2, "Bronze Layer Design") — cópia fiel da origem, transformação
mínima:

| Propriedade | Recomendação |
|---|---|
| **Schema** | Espelhar o schema Hive de origem o mais próximo possível; adicionar colunas de metadado |
| **Formato** | Delta (sempre) |
| **Colunas de metadado** | `_source_file`, `_ingest_timestamp`, `_source_table` para lineage |
| **Clustering** | Liquid Clustering na chave primária ou nas colunas mais consultadas |
| **Particionamento** | Só para tabelas muito grandes (1 TB+) com chave de partição clara |
| **Naming** | Nomes de tabela de origem em um schema `bronze` (ex.: `bronze.dim_customer`) |

**Otimização pós-carga** (fonte: 3.2, "Post-Ingestion: Storage Optimization") — ver detalhe
operacional em `kb/spark-patterns/concepts/delta-lake-concepts.md`:

| Estratégia | O que faz | Quando aplicar |
|---|---|---|
| **Liquid Clustering** | Co-localiza linhas relacionadas dentro dos arquivos Delta | Recomendado para a maioria das tabelas — `ALTER TABLE ... CLUSTER BY (col1, col2)` depois `OPTIMIZE` |
| **Particionamento** | Separa fisicamente por valor de chave | Tabelas muito grandes (1 TB+) com chave clara (ex.: data) — `PARTITIONED BY` na criação |
| **`OPTIMIZE`** | Compacta arquivos pequenos | Após cargas em massa, para consolidar os muitos arquivos pequenos herdados do Hadoop |

---

## 11. Dados originalmente importados via Sqoop

Se as tabelas Hive em escopo foram carregadas via Sqoop a partir de um RDBMS, elas herdam problemas de
qualidade de dado específicos (tipos como STRING, `NULL` literal, duplicatas de import incremental) —
tratados em detalhe, junto com a conversão de CDC, em `concepts/sqoop-cdc.md` §7. Regra rápida: se
existir versão ORC/Parquet e versão texto do mesmo import Sqoop, **sempre migrar a versão
ORC/Parquet** (3.2).

---

## Anti-Padrões Locais (HD-I — Ingestão)

| Código | Anti-padrão | Correção |
|---|---|---|
| HD-I01 | Rodar DistCp sem `-update` em transferências incrementais (recopia tudo) | Sempre usar `-update` fora da carga inicial |
| HD-I02 | Ignorar o small-file problem e carregar direto sem `OPTIMIZE` | Compactar antes (Hive) ou depois (`OPTIMIZE`) — §7 |
| HD-I03 | Manter particionamento físico Hive 1:1 em tabelas pequenas/médias | Migrar para Liquid Clustering (`CLUSTER BY`) — só preservar `PARTITIONED BY` em tabelas ≥1TB com chave seletiva — §8 |
| HD-I04 | Migrar a versão texto/CSV de um import Sqoop quando existe versão ORC/Parquet | Sempre preferir ORC/Parquet — §11 |
| HD-I05 | Pular validação de contagem/checksum pós-carga | Aplicar os 7 parity checks de `kb/migration/concepts/reconciliation.md` §1 |
| HD-I06 | Assumir que Catalog Federation (Padrão 1) funciona sobre HDFS on-premises via Thrift | Não suportado pela federação — usar Padrão 2 (DistCp) para HDFS genuinamente on-prem — §3 |
| HD-I07 | Deixar tabela `LOCATION` externa "por hábito" sem decisão explícita managed×external | Decidir e documentar por tabela — §9 |

---

## Referências

- Curso Databricks — *Hadoop Migration* — `03 - Execute/3.2 Lecture - Data Migration and Ingestion`
- `kb/databricks/concepts/lakehouse-federation.md` (padrão Federation — hoje cobre só SQL Server; aqui o tipo `hive_metastore`)
- `kb/databricks/concepts/unity-catalog-concepts.md` (hierarquia 3 níveis, managed vs volumes)
- `kb/spark-patterns/concepts/delta-lake-concepts.md` (OPTIMIZE, CLUSTER BY vs ZORDER)
- `kb/migration/concepts/reconciliation.md` (7 parity checks, 2 fases, tolerâncias)
- `kb/migration/concepts/cutover-rollback.md` (metodologia de freeze window/rollback — comandos concretos lá são SQL Server)
- `concepts/hive-ddl-conversion.md` · `concepts/sqoop-cdc.md` · `concepts/oozie-orchestration.md` (irmãos deste domínio)
- [Hive metastore federation: enable Unity Catalog to govern tables registered in a Hive metastore](https://docs.databricks.com/aws/en/query-federation/hms-federation-concepts) (verificado ago/2026)
- [Enable Hive metastore federation for an external Hive metastore](https://docs.databricks.com/aws/en/query-federation/hms-federation-external) (verificado ago/2026 — sintaxe SQL literal)
- [COPY INTO](https://docs.databricks.com/en/sql/language-manual/delta-copy-into.html)
- [Auto Loader](https://docs.databricks.com/en/ingestion/cloud-object-storage/auto-loader/index.html)
- [read_files](https://docs.databricks.com/en/sql/language-manual/functions/read_files.html)
- [Apache DistCp Documentation](https://hadoop.apache.org/docs/current/hadoop-distcp/DistCp.html)
