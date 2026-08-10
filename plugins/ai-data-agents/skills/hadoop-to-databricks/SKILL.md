---
name: hadoop-to-databricks
description: "Playbook operacional do agente hadoop-to-databricks: como rodar discovery manual (Beeline/HDFS/YARN/Ranger — sem MCP dedicado a Hive), como obter e formatar o Hive DDL para os geradores, como pontuar complexidade/waves, como produzir o documento de proposta (SPEC) para aprovação humana, como rodar os dois geradores determinísticos (scripts/hive_generate.py e scripts/reconcile_generate.py), como converter Oozie → Lakeflow Jobs e Ranger/Kerberos → Unity Catalog, e como aplicar o runbook de cutover/rollback — tudo para migração de ecossistema Hadoop → Databricks."
updated_at: 2026-08-02
source: kb/hadoop-migration (index + concepts/hive-ddl-conversion + hdfs-ingestion + sqoop-cdc + oozie-orchestration + kb/sql-patterns/concepts/hiveql-conversion + kb/governance/concepts/ranger-kerberos-to-uc + kb/migration/concepts/discovery-assessment + reconciliation + cutover-rollback)
agent: hadoop-to-databricks
domain: hadoop-migration
---

# Skill — Migração Hadoop → Databricks

> Leia na primeira chamada da sessão. Define COMO rodar discovery (majoritariamente manual — não há
> MCP dedicado a Hive/Beeline neste projeto), COMO montar a entrada dos geradores, e COMO conduzir as
> 8 fases. A fonte normativa dos mapeamentos/regras é `kb/hadoop-migration/` +
> `kb/sql-patterns/concepts/hiveql-conversion.md` + `kb/governance/concepts/ranger-kerberos-to-uc.md` +
> `kb/migration/concepts/*` — este skill é o "como fazer".

## Fluxo (8 fases + gate de aprovação)
`DISCOVER → ASSESS → DESIGN → [GATE: SPEC + aprovação humana] → CONVERT → INGEST → CDC → VALIDATE → CUTOVER`

## Passo 1 — DISCOVER

**Sem MCP dedicado a Hive/HDFS/YARN/Ranger.** O MCP `migration_source` deste projeto só suporta
`type: "sqlserver"` e `type: "postgresql"` — não fala HiveQL/Thrift/Beeline. Discovery Hadoop é
**majoritariamente manual**: peça ao usuário/DBA/administrador Hadoop para rodar os comandos abaixo
(via SSH no edge node, Beeline, ou terminal com `hdfs`/`yarn`/`oozie` CLI configurados) e colar/exportar
o resultado de volta para você. **Nunca invente um resultado de DDL, volume ou policy que não foi
fornecido.**

### 1.1 Schema Hive (o insumo do gerador — obrigatório)

```bash
# Uma tabela por vez, ou em lote com um script simples de shell:
beeline -u "jdbc:hive2://<host>:10000/<db>" -e "SHOW CREATE TABLE <db>.<tabela>;" > hive_ddl_raw.txt

# Em lote, para todas as tabelas de um database:
beeline -u "jdbc:hive2://<host>:10000/<db>" -e "SHOW TABLES;" --outputformat=csv2 | tail -n +2 > tables.txt
while read -r t; do
  beeline -u "jdbc:hive2://<host>:10000/<db>" -e "SHOW CREATE TABLE <db>.$t;"
done < tables.txt >> hive_ddl_raw.txt
```

Concatene todos os `CREATE [EXTERNAL] TABLE` num único arquivo `.sql` — é esse arquivo que
`scripts/hive_generate.py` consome (Passo 4). **Não edite manualmente** o DDL bruto antes de rodar o
gerador — ele já lida com SerDe/particionamento/tipos; editar à mão reintroduz o risco que o gerador
existe para evitar.

**Exceção legítima ao "sem MCP":** se o Hive Metastore em questão é **backed por PostgreSQL** (opção
comum de backend do HMS — ver `kb/hadoop-migration/concepts/hdfs-ingestion.md` §3) e você tiver uma
entrada em `MIGRATION_SOURCES` do tipo `postgresql` apontando para esse banco, pode usar
`migration_source_describe_table`/`migration_source_sample_table` para consultar as tabelas brutas do
HMS (`TBLS`, `COLUMNS_V2`, `SDS`, `PARTITIONS`) como discovery em massa complementar. Isso **não
substitui** o `SHOW CREATE TABLE` — é um atalho de inventário quando há centenas de tabelas e acesso
direto ao backing DB do HMS é mais rápido que rodar Beeline tabela-a-tabela.

### 1.2 Volume e HDFS

```bash
hdfs dfs -du -s -h /warehouse/<db>.db/<tabela>     # volume por tabela
hdfs dfs -count /warehouse/<db>.db                 # contagem de diretórios/arquivos/bytes
hdfs dfs -ls -R /warehouse/<db>.db/<tabela> | wc -l  # nº de arquivos (small-file problem, ver hdfs-ingestion.md §7)
```

### 1.3 Jobs/orquestração (Oozie) e compute (YARN)

```bash
oozie job -info <coordinator-id> -oozie http://<host>:11000/oozie   # detalhe de um coordinator
oozie jobs -oozie http://<host>:11000/oozie -jobtype coordinator    # todos os coordinators ativos
yarn application -list -appStates ALL                                # jobs YARN (histórico + ativos)
curl -s "http://<resourcemanager-host>:8088/ws/v1/cluster/apps" | python3 -m json.tool  # YARN REST (baseline de uso)
```

### 1.4 Segurança (Ranger/Kerberos/LDAP)

Ver comandos completos em `kb/governance/concepts/ranger-kerberos-to-uc.md` §9: `SHOW GRANT
USER/GROUP` (HiveQL/Beeline — funciona em qualquer versão do Ranger), REST API pública v2 do Ranger
(`GET /service/public/v2/api/service/{servicename}/policy`) quando disponível, `kadmin.local -q
"list_principals"` (Kerberos), `hdfs groups <user>` (grupos efetivos).

**Buffer-safe:** para clusters grandes (>50 tabelas), NÃO despeje o output bruto de cada
`SHOW CREATE TABLE` no contexto de uma vez — grave um índice compacto em
`<saída>/_work/discovery_index.json` (database, tabela, nº de colunas, partição/bucket, volume) e
trabalhe sobre o índice.

Consolide os achados nas 5 categorias de `kb/migration/concepts/discovery-assessment.md` §1: **Data
Assets**, **Pipelines & ETL** (Oozie/Sqoop), **Consumers & Users**, **Security & Access**
(Ranger/Kerberos), **Operations & SLAs**.

## Passo 2 — ASSESS (scoring, waves, estratégia)

Pontue cada workload (database/domínio Hive) na **Complexity Scoring Matrix** adaptada de
`discovery-assessment.md` §2, 7 dimensões, 1-4 pontos cada:

| Dimensão | 1pt | 2pt | 3pt | 4pt |
|---|---|---|---|---|
| Table Count | <10 | 10-50 | 50-200 | >200 |
| Data Volume | <10GB | 10-100GB | 100GB-1TB | >1TB |
| HiveQL/Pig/MapReduce Complexity | DML simples | UDF/CTE/window | `TRANSFORM`/SerDe custom | Pig Latin/MapReduce/HBase |
| Orchestration Complexity (Oozie) | sem Oozie | workflow simples | coordinator+bundle | fork/join+decision+sub-workflow aninhado |
| Dependencies | nenhuma | 1-3 upstream | 4-10 upstream | >10/circular |
| SLA Sensitivity | nenhuma/batch | SLA diário | SLA horário | real-time |
| Consumers | 1 time | 2-5 times | enterprise-wide | externo/customer-facing |

Soma → wave: **6-10=Wave1, 11-16=Wave2, 17-20=Wave3, 21+=Wave3 c/ especialista** (idêntico ao
curso-gêmeo SQL Server).

Heurística de complexidade HiveQL (de scripts `.hql`/procedures, `kb/sql-patterns/concepts/
hiveql-conversion.md` §7,§12): uso de `TRANSFORM`/`MAP`/`REDUCE`/`REFLECT()`/SerDe customizado →
**High**; scripts multi-statement longos (HPL/SQL) → **Medium**; senão **Low**. **Se Pig Latin,
MapReduce Java ou HBase estiverem em uso, marque o workload automaticamente como candidato a wave
posterior** — são reescrita completa, não conversão (Passo 4c).

**Árvore de decisão Analytics-First vs ETL-First** (`discovery-assessment.md` §5): driver
custo/compliance → **ETL-First**; driver quick-win/IA-BI → **Analytics-First**; default **ETL-First**.

Confirme o **vetor de origem** (on-premises CDH/HDP legado / Hadoop cloud-native EMR/HDInsight/
Dataproc) — isso decide o padrão de ingestão dominante no Passo 3 (Federation/Direct Read exigem HMS
acessível e dado em cloud storage suportado; HDFS on-prem genuíno vai por DistCp).

## Passo 3 — DESIGN

Proponha Medallion (Bronze/Silver/Gold) e, por tabela, o padrão de ingestão: **Catalog Federation**
(HMS acessível, dado pequeno/médio já em cloud storage), **DistCp → cloud storage** (HDFS on-prem,
qualquer volume), **Direct File Read** (Hadoop já cloud-native), ou **Sqoop→Lakeflow Connect** (se
Sqoop alimentava a partir de um RDBMS upstream — considere substituir o Sqoop inteiro). Esboce o
modelo de governança (quais Ranger policies viram ABAC/Row Filter/Column Mask; plano de SCIM para
Kerberos/LDAP). Classifique os workflows Oozie por action type (Passo 6). Isto compõe o **SPEC**.

## GATE — Documento de proposta (SPEC) + aprovação humana (obrigatório)

Entregue o SPEC (formato no `registry/hadoop-to-databricks.md` § Formato de Resposta) e **PARE**. Este
projeto adota "sempre documento + aprovação para migrações" (Constituição §2.2 / Supervisor Step 0.6A).

> **O GATE é uma FRONTEIRA DE TURNO, não um passo sequencial.** Entregue o SPEC e **encerre** — quem
> aprova é o **usuário**, numa mensagem seguinte. NÃO gere DDL/código no mesmo turno do SPEC. Um hook
> de enforcement (`enforce_migration_gate`) bloqueia uma 2ª delegação de migração no mesmo turno; se
> você for bloqueado, é sinal de que deveria ter parado — apresente o SPEC e aguarde.

## Passo 4 — CONVERT (só após aprovação) — DETERMINÍSTICO, dirigido por DDL

**Regra de ouro:** NÃO escreva DDL/SQL à mão **e NÃO escreva seu próprio gerador** (`generate_*.py`).
Use o arquivo `.sql` do Passo 1.1 (concatenação de `SHOW CREATE TABLE`) diretamente:

```bash
python scripts/hive_generate.py hive_ddl_raw.sql output/hadoop-migration/<slug>
```

Ele emite, **correto-por-construção** (tipos Hive→Delta mapeados por `_PRIM`, `CLUSTER BY` combinando
partição+bucket, `COMMENT` com o tipo Hive original para auditoria, SerDe/`STORED AS`/`TBLPROPERTIES`/
`LOCATION` sempre removidos):

- `01_ddl_delta.sql` — `CREATE TABLE IF NOT EXISTS catalog.gold.<tabela>` (Delta).
- `02_type_flags.md` — colunas que exigem revisão manual (`UNIONTYPE`, `INTERVAL`, tipos Hive
  desconhecidos).
- `03_reconcile_spec.json` — spec **pronto** para `scripts/reconcile_generate.py` (keys = partição+
  bucket, colunas numéricas exatas/float, datas, `float_tolerance_pct: 0.0001`).

**Esses arquivos SÃO os entregáveis de DDL.** Não os reescreva à mão, não os "melhore", não gere um
`generate_*.py` paralelo. O gerador roda **gates** (SerDe/`STORED AS`/`LOCATION` vazando no DDL final;
identificador sem backtick) e sai com **código ≠ 0** se algo falhar → **NÃO reporte "concluído"** e
corrija a causa.

**⚠️ Limitações conhecidas do gerador (ver `hive-ddl-conversion.md` §10.1) — revisar antes de aceitar
a saída:**
- Schema de destino é sempre `catalog.gold.<tabela>` (não preserva o database Hive de origem como
  schema) — se a estratégia usa Bronze/Silver/Gold em vez de carga direta para Gold, ajuste o
  `01_ddl_delta.sql` gerado antes de aceitar.
- `03_reconcile_spec.json` **não inclui dialeto de origem** — `scripts/reconcile_generate.py` (escrito
  originalmente para SQL Server) usa colchetes `[col]` no lado "source", sintaxe **inválida** em
  HiveQL/Beeline. **Revisar e trocar `[col]` → `` `col` `` manualmente** no `reconcile_source.sql`
  gerado (Passo 7), ou validar via a query de Hive Metastore Federation (`hive-ddl-conversion.md`
  §6.1) como alternativa.

### Passo 4b — HiveQL/Impala/UDF

A maioria do DML HiveQL roda em Databricks SQL **sem alteração** (Spark SQL é superset —
`hiveql-conversion.md` §1). Concentre esforço em:
- `TRANSFORM`/`MAP`/`REDUCE` → UDF Python/`applyInPandas` (§2.1).
- `REFLECT()`/`JAVA_METHOD()` → UDF Python; colunas virtuais `INPUT__FILE__NAME` → `_metadata.file_path` (§2.2).
- Impala: `COMPUTE STATS`→`ANALYZE TABLE`; `INVALIDATE METADATA`/`STRAIGHT_JOIN`→remover; **Kudu→Delta,
  `UPSERT`→`MERGE`** (§3).
- Hive UDF Java: registrar JAR (`CREATE FUNCTION ... USING JAR`) ou reescrever como UDF SQL/Python (§4).
- `SET` do Hive (`hive.execution.engine`, `hive.vectorized.*`, `mapreduce.job.reduces`): **remover
  quase todos** — Catalyst/Photon assumem (§8).
- Para volume, use **Lakebridge**: `remorph transpile --source hive --input-sql <dir> --output-folder
  <dir> --catalog-name <cat> --schema-name <schema>` — **sempre revisar** funções marcadas
  "unsupported" e validar contra dado de teste antes de produção (§11).

### Passo 4c — Flags de Redesign: Pig / MapReduce / HBase (nunca mecânico)

**Lakebridge não transpila nenhum dos três.** Trate como reescrita completa, não conversão:
- **Pig Latin** → PySpark/Spark SQL. Mapa de operações (`LOAD`→`read`, `FILTER`→`WHERE`,
  `FOREACH...GENERATE`→`SELECT`, `GROUP`→`GROUP BY`, `COGROUP`→`FULL OUTER JOIN`) em
  `hiveql-conversion.md` §5. Frequentemente o pipeline Pig inteiro cabe numa única query SQL.
- **MapReduce Java** → PySpark. `Mapper.map()`→`select/withColumn/flatMap`; `Reducer.reduce()`→
  `groupBy().agg()`; secondary sort→`Window`+`row_number()`. Mapa completo em §6.
- **HBase** → Delta Lake, **mas o curso não define um padrão de conversão** (gap documental
  confirmado). NÃO invente uma migração mecânica de row-key/column-family. Escale para um desenho de
  arquitetura dedicado, considerando o padrão de acesso real (scans sequenciais vs point lookups por
  row-key) antes de propor a modelagem Delta — isso é trabalho de design, não de script.

## Passo 5 — INGEST

Documente o contrato Bronze→Silver→Gold (schema-alvo do `01_ddl_delta.sql` + star schema Gold).
Escolha por tabela (do Passo 3): **Catalog Federation** (`CREATE CONNECTION ... TYPE hive_metastore` +
`CREATE FOREIGN CATALOG` — ver `hdfs-ingestion.md` §3 para a sintaxe completa e as limitações reais:
não suporta HDFS on-prem nem Thrift remoto), **DistCp** (`hadoop distcp hdfs:///... abfss://.../
s3a://.../ gs://.../ -update -m <N> -bandwidth <MB/s>` seguido de `COPY INTO`/Auto Loader/`read_files`
— `hdfs-ingestion.md` §4), ou **Direct File Read** (`read_files`/`COPY INTO`/Auto Loader direto sobre
o path de cloud storage — §5). Implementação de produção → escalar `databricks-engineer`.

## Passo 6 — CDC / Orquestração

**CDC:** Hadoop não tem mecanismo único (`sqoop-cdc.md` §1) — identifique a origem real por tabela:
Sqoop `--incremental append`→Auto Loader; `--incremental lastmodified`→`MERGE` com watermark;
Kafka-Debezium a partir de RDBMS upstream→Auto Loader+`AUTO CDC`; Hive ACID transaction logs→Change
Data Feed/`MERGE`. **SCD Type 2 sempre `AUTO CDC` com `STORED AS SCD TYPE 2`** — nunca `LAG`/
`ROW_NUMBER` manual (sintaxe completa em `kb/spark-patterns/patterns/lakeflow-patterns.md`, regra R4
de `kb/spark-patterns/concepts/sdp-rules.md`). Trate os problemas herdados do Sqoop (datas/booleanos
como `STRING`, literais `"null"`/`"\N"`) no `MERGE`/CTAS de ingestão (`sqoop-cdc.md` §7).

**Orquestração:** primeiro pergunte se já existe Airflow/dbt/Prefect/Dagster apontando para o Hadoop —
se sim, **reapontar** é mais barato que converter Oozie (`oozie-orchestration.md` §0). Senão, mapeie
workflow→Job multi-task, coordinator→Job com schedule trigger, bundle→múltiplos Jobs via DABs. Action
types: `hive`/`hive2`→SQL task; `spark`→Spark task; `shell`→notebook task; `sqoop`→ingestão nativa
(ver CDC acima); `mapreduce`/`pig`→Spark task **após reescrita** (Passo 4c); `sub-workflow`→
`run_job_task`; fork/join→tasks paralelas com `depends_on`; decision→`condition_task`. **CRON: Oozie
tem 5 campos, Quartz (Lakeflow Jobs) tem 6** — adicione `0` à esquerda (segundos) e valide
timezone/DST (`oozie-orchestration.md` §5). Implementação de produção → `databricks-engineer`.

## Passo 7 — VALIDATE — DETERMINÍSTICO, 2 fases obrigatórias

Rode o gerador de reconciliação usando o `03_reconcile_spec.json` do Passo 4 (revise o quoting do
lado "source" antes — ver limitação §10.1 acima):

```bash
python scripts/reconcile_generate.py output/hadoop-migration/<slug>/03_reconcile_spec.json output/hadoop-migration/<slug>
```

Emite `reconcile_source.sql` (revisar `[col]`→`` `col` `` para HiveQL/Beeline), `reconcile_target.sql`
(Databricks SQL — roda como está), e `reconcile_report.md`. Execute a **regra das 2 fases**
(`kb/migration/concepts/reconciliation.md` §2): Fase 1 snapshot aprovada ANTES do CDC/sync incremental
ligar; Fase 2 só o delta. **Lakebridge Reconciler não documenta suporte a `data_source: hive`** — não
assumir automação; reconciliar via os SQLs gerados (agregado manual). Validação estatística avançada
(drift, KS test) → escalar `data-quality-steward`.

## Passo 8 — CUTOVER

Aplique o runbook de `kb/migration/concepts/cutover-rollback.md`, com o freeze Hadoop-específico:
1. Escolha uma estratégia de cutover (Big Bang/Phased/Blue-Green/Canary/A-B/Pilot).
2. **Freeze window:** suspenda coordinators Oozie (`oozie job -suspend -oozie <url> -id
   <coordinator-id>`) e/ou tire um `hdfs dfs -createSnapshot <path> <name>` para leitura consistente
   (`hdfs-ingestion.md` §1) — documente qual mecanismo de detecção de mudança estava em uso (Passo 6)
   como equivalente ao "LSN" do runbook genérico.
3. Delta/sync catch-up final → reconciliação final (Passo 7, Fase 2) → **Go/No-Go Gate**.
4. Switchover de consumidores (dashboards, jobs downstream) → smoke test.
5. **Matriz de rollback numérica:** <0.01% ok; 0.01–1% investigar; **>1% rollback imediato**; falha
   de dashboard crítico ou degradação de performance >50% sem resolução em 1h também disparam
   rollback.
6. **Hypercare** 1-2 semanas + **sign-off explícito por owner** — nunca decommission prematuro; o
   cluster Hadoop permanece live até todos os consumidores migrarem.

## Passo Final — AUTO-REVISÃO de sanidade (obrigatório antes de reportar concluído)

NÃO reporte "concluído" se algum falhar:
- [ ] **SPEC foi aprovado** antes de qualquer CONVERT (o gate não foi pulado).
- [ ] **Discovery (5 categorias) precedeu o design** — nenhuma decisão de arquitetura sem dados do Passo 1.
- [ ] **Gerador de DDL rodou e passou nos gates:** `scripts/hive_generate.py` saiu com **código 0**
  (sem SerDe/`STORED AS`/`LOCATION` vazando, sem identificador sem backtick).
- [ ] **Gerador de reconciliação rodou e passou nos gates:** `scripts/reconcile_generate.py` saiu com
  **código 0** (toda tabela com `target`); quoting do lado "source" revisado para HiveQL (§10.1).
- [ ] **Sem gerador próprio:** os entregáveis SÃO os arquivos dos dois scripts; nenhum `generate_*.py`
  reescrito nem SQL de reconciliação escrito à mão.
- [ ] **Pig/MapReduce/HBase:** nenhum convertido mecanicamente; marcados ⚠️ redesign com esforço
  estimado como reescrita completa (não como mapeamento determinístico).
- [ ] **Reconciliação em 2 fases:** Fase 1 aprovada antes do CDC/sync incremental; Fase 2 (delta)
  rodada separadamente.
- [ ] **Cutover:** freeze Hadoop-específico documentado (Oozie suspend + hdfs snapshot), matriz de
  rollback aplicada, sign-off documentado — nunca decommission antes de todos os consumidores
  migrarem.
- [ ] **PII/Ranger:** nenhuma policy/mask com PII gerada sem passar por `governance-auditor`.
- [ ] **Relatório == código, COM `grep`:** para CADA feature alegada (DDL, CDC ativo, Oozie
  convertido, reconciliação aprovada, cutover concluído) rode `grep -rn` no diretório de saída; se não
  achar, **APAGUE a alegação**. A tabela de artefatos bate com `find <saída> -type f`.

## Anti-patterns (fortes)

❌ Pular o discovery (5 categorias) antes de propor design. ❌ Gerar DDL/código antes da aprovação do
SPEC — ou no MESMO turno do SPEC. ❌ **Escrever o DDL ou o SQL de reconciliação à mão** — rode
`scripts/hive_generate.py`/`scripts/reconcile_generate.py`. ❌ **Escrever seu próprio gerador**
(`generate_*.py`) — cada run reintroduz bug novo; consuma a saída dos geradores únicos. ❌ Converter
Pig Latin/MapReduce Java/HBase mecanicamente — sempre reescrita completa ou redesign (nunca "flag
rápida", nunca estimativa como se fosse determinístico). ❌ Rodar a reconciliação do snapshot e do
CDC/sync na mesma passada (mascara a causa raiz). ❌ Usar Catalog Federation para HDFS genuinamente
on-premises ou fact tables multi-TB (usar DistCp + Auto Loader/`COPY INTO`). ❌ Assumir que Kerberos/
keytab tem equivalente 1:1 no Databricks (é substituição por IdP+SCIM, não conversão). ❌ Misturar
ABAC com row filter/mask manual na mesma tabela (`UC_ABAC_MULTIPLE_ROW_FILTERS`). ❌ Decommission
prematuro do cluster Hadoop antes de todos os consumidores migrarem e sign-off formal. ❌ Migrar sem
reconciliação em 2 fases nem runbook de cutover. ❌ Confiar cegamente em um endpoint de export/audit
do Ranger sem confirmar a versão em uso (`ranger-kerberos-to-uc.md` §8) — usar `SHOW GRANT`/UI como
fallback.
