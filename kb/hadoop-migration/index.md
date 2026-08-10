---
domain: hadoop-migration
updated_at: 2026-08-02
agents: [hadoop-to-databricks]
---

# Knowledge Base — Migração Hadoop → Databricks

> Fonte de verdade operacional do agente **hadoop-to-databricks**. Mesmo padrão de
> `kb/sqlserver-migration/`: este domínio tem `concepts/` próprios para o stack técnico
> **Hadoop-específico** (Hive DDL, HDFS, Sqoop/CDC, Oozie) e **agrega** concepts que já vivem em
> outras KBs para o terreno **compartilhado** com o curso irmão *SQL Server Migration*
> (discovery/assessment, reconciliação, cutover, ABAC). Consultar SEMPRE antes de migrar um cluster
> Hadoop. NÃO inventar mapeamentos — construto sem equivalente claro é marcado ⚠️ (ver §6 Flags de
> Redesign).

## 0. ⚠️ Nota de Auditoria — Contaminação do Template SQL Server

O curso oficial Databricks *"Hadoop Migration"* é o **gêmeo** do curso *"SQL Server Migration"*
(mesma metodologia, mesmos frameworks — Migration Maturity Model, Complexity Scoring, waves, cutover,
reconciliação, ABAC, FinOps, DABs). Algumas lições do corpus, porém, reaproveitam material mal
adaptado do curso irmão como se fosse Hadoop-nativo: DMVs `sys.*`/`msdb` rotuladas "Hadoop", tipos
`HIERARCHYID`/`GEOGRAPHY` como "tipos Hadoop", `AdventureWorksDW`, connection strings
`jdbc:hadoop://...:1433` (porta/DNS de Azure SQL, não HiveServer2), "Azure Hadoopless" (find-replace
quebrado de "serverless"), `SSDT`/`DACPAC`/"Extended Events" apresentados como observability Hadoop.
**Nada disso está codificado nesta KB.** Toda auditoria completa (achados H1-H11) vive em
`audits/2026-08-02-curso-hadoop-migration-vs-ai-data-agents.md` — os `concepts/` deste domínio usam
só os trechos verificados como Hadoop-válidos (Beeline, `hdfs dfs`, `oozie job`, `yarn application`,
Ranger REST/HiveQL `SHOW GRANT`, `remorph`/`lakebridge transpile --source hive`).

## 1. Escopo

Migração de um **cluster/ecossistema Hadoop inteiro** — **HDFS**, **Hive** (Metastore + HiveQL),
**Impala**, **Spark-on-YARN**, **Sqoop**, **Oozie**, **Pig**, **MapReduce**, **HBase**,
**Ranger/Sentry + Kerberos** — para **Databricks**. Diferente de:

- migração de banco relacional **SQL Server/PostgreSQL** → `kb/migration/` (agente `migration-expert`)
  ou o especialista dedicado `kb/sqlserver-migration/` (agente `sqlserver-to-databricks`)
- pacotes **SSIS** (`.dtsx`) → `kb/ssis-migration/` (agente `ssis-to-databricks`)
- modelo tabular **SSAS** (`.bim`/`.vpax`) → `kb/ssas-migration/` (agente `ssas-to-databricks`)

Este agente é o especialista Hadoop-específico: origem **só** Hadoop/CDH/HDP/Cloudera, destino **só**
Databricks, seguindo a mesma metodologia oficial (Discover→Design→Execute→Activate→Enable→Closeout)
adaptada ao stack técnico Hadoop.

## 2. Mapa de Componentes — Hadoop → Databricks

| Componente Hadoop | Equivalente Databricks | Concept normativo |
|---|---|---|
| HDFS (arquivos ORC/Parquet/Avro/texto) | Delta Lake (Volumes / cloud storage) | `concepts/hdfs-ingestion.md` |
| Hive Metastore (HMS) | Unity Catalog Metastore (3 níveis `catalog.schema.table`) | `concepts/hive-ddl-conversion.md` §6 |
| HiveQL (DDL + DML) | Delta DDL + Spark SQL (superset de HiveQL) | `concepts/hive-ddl-conversion.md`, `kb/sql-patterns/concepts/hiveql-conversion.md` |
| Impala SQL | Databricks SQL / SQL Warehouse (Photon) | `kb/sql-patterns/concepts/hiveql-conversion.md` §3 |
| Spark-on-YARN | Databricks Runtime (clusters, jobs, serverless) | — (compute gerenciado, sem YARN/ResourceManager) |
| Sqoop (import/export RDBMS↔HDFS) | Lakeflow Connect / Auto Loader / `MERGE` | `concepts/sqoop-cdc.md` |
| Oozie (workflow/coordinator/bundle) | Lakeflow Jobs (multi-task + schedule trigger) | `concepts/oozie-orchestration.md` |
| Pig Latin | PySpark / Spark SQL — **redesign, não transpilação** | `kb/sql-patterns/concepts/hiveql-conversion.md` §5 |
| MapReduce Java | PySpark — **redesign, não transpilação** | `kb/sql-patterns/concepts/hiveql-conversion.md` §6 |
| HBase (NoSQL wide-column) | Delta Lake — **redesign arquitetural, gap documental do curso** | `kb/sql-patterns/concepts/hiveql-conversion.md` §10 |
| Ranger / Sentry (autorização) | Unity Catalog ABAC / `GRANT` / Row Filter / Column Mask | `kb/governance/concepts/ranger-kerberos-to-uc.md` |
| Kerberos + LDAP/AD (autenticação/identidade) | IdP federado (SSO) + SCIM provisioning + Service Principal | `kb/governance/concepts/ranger-kerberos-to-uc.md` §4 |
| Ambari / Cloudera Manager | Databricks Account/Workspace Console + System Tables | `kb/governance/concepts/ranger-kerberos-to-uc.md` §10 |
| Hive/HDFS/YARN audit logs | `system.access.audit`, `system.billing.usage` | `kb/governance/concepts/ranger-kerberos-to-uc.md` §10 |

## 3. Fluxo de Migração (8 fases + gate)

```
DISCOVER → ASSESS → DESIGN → [GATE: SPEC + aprovação humana] → CONVERT → INGEST → CDC → VALIDATE → CUTOVER
```

Mapeamento à metodologia oficial do curso: DISCOVER/ASSESS/DESIGN ≈ *Discover*+*Design*; CONVERT ≈
*Execute*; INGEST/CDC/VALIDATE/CUTOVER ≈ *Activate*; observabilidade/governança contínua pós-cutover ≈
*Enable*/*Closeout* (fora do escopo direto deste agente).

> **Gate obrigatório:** entre DESIGN e CONVERT o agente entrega um documento de proposta (**SPEC**) e
> **PARA para aprovação humana** (Step 0.6A / Constituição §2.2). Nenhum DDL/código é gerado antes do
> aceite — reforçado por um hook de enforcement (`enforce_migration_gate`) que bloqueia uma 2ª
> delegação de migração no mesmo turno.

## 4. Mapa de Concepts — Onde Está Cada Coisa

| Fase | Concept normativo | Ferramenta |
|---|---|---|
| DISCOVER (5 categorias; Beeline/HDFS/YARN/Ranger) | `kb/migration/concepts/discovery-assessment.md` §1 | Comandos manuais (SKILL) — sem MCP dedicado a Hive |
| ASSESS (Complexity Scoring, waves, Analytics-First×ETL-First) | `kb/migration/concepts/discovery-assessment.md` §2-9 | idem |
| CONVERT — Hive DDL → Delta (tipos, SerDe, particionamento/bucketing) | `concepts/hive-ddl-conversion.md` | `scripts/hive_generate.py` |
| CONVERT — HiveQL/Impala/UDF/Pig/MapReduce/HBase | `kb/sql-patterns/concepts/hiveql-conversion.md` | Lakebridge (HiveQL/Impala apenas); redesign manual (Pig/MapReduce/HBase — §6) |
| INGEST — HDFS → Databricks (Federation/DistCp/Direct File Read) | `concepts/hdfs-ingestion.md` | delegar implementação a `databricks-engineer` |
| INGEST — Hive Metastore Federation (discovery/validação) | `concepts/hive-ddl-conversion.md` §6.1, `concepts/hdfs-ingestion.md` §3 | `kb/databricks/concepts/lakehouse-federation.md` (Federation genérico) |
| CDC — Sqoop incremental / Hive ACID / Kafka-Debezium | `concepts/sqoop-cdc.md` | `AUTO CDC` (`kb/spark-patterns/patterns/lakeflow-patterns.md`) |
| Orquestração — Oozie → Lakeflow Jobs | `concepts/oozie-orchestration.md` | DAB YAML (`kb/pipeline-design/patterns/orchestration-databricks.md`) |
| VALIDATE — reconciliação em 2 fases, 7 parity checks | `kb/migration/concepts/reconciliation.md` | `scripts/reconcile_generate.py` |
| CUTOVER — freeze window, matriz de rollback, hypercare | `kb/migration/concepts/cutover-rollback.md` | Freeze Hadoop-específico: `oozie job -suspend` + `hdfs dfs -createSnapshot` |
| Governança — Ranger/Sentry/Kerberos/HDFS ACL → UC | `kb/governance/concepts/ranger-kerberos-to-uc.md` | PII → escalar `governance-auditor` |
| Mapeamento genérico de tipos (fallback / dupla checagem) | `kb/migration/index.md` | `skills/migration/SKILL.md` |
| Definition of Done por fase | `kb/checklists/migration-dod.md` | — |
| Playbook operacional (comandos, formato de spec, gerador) | — | `skills/hadoop-migration/hadoop-to-databricks/SKILL.md` |

## 5. Reuso Explícito — O Que NÃO é Hadoop-Específico

Por ser o curso-gêmeo do SQL Server Migration, ~60% da metodologia já está coberta e **não deve ser
recriada** — só reapontada para o contexto Hadoop:

| Capacidade | Onde já existe | Nuance Hadoop |
|---|---|---|
| Reconciliação (7 parity checks, 2 fases, tolerâncias, matriz de rollback) | `kb/migration/concepts/reconciliation.md` + `scripts/reconcile_generate.py` | Fonte é HiveQL/agregado manual, não T-SQL — Lakebridge Reconciler **não documenta** `data_source` Hive (ver `concepts/sqoop-cdc.md` §9) |
| Cutover/rollback (freeze, go/no-go, hypercare) | `kb/migration/concepts/cutover-rollback.md` | Freeze = `oozie job -suspend` + `hdfs dfs -createSnapshot` (não LSN de CDC) |
| Discovery/assessment (Complexity Scoring→waves) | `kb/migration/concepts/discovery-assessment.md` | Fonte é Beeline/YARN REST/Ranger, não DMVs T-SQL |
| ABAC/Governed Tags, row filter/mask | `kb/governance/concepts/uc-abac-governed-tags.md` | Mapeamento de origem é Ranger/Sentry, não RLS/DDM — ver `ranger-kerberos-to-uc.md` |
| FinOps (system.billing, tagging, rightsizing) | `kb/databricks-pricing/concepts/finops-migration.md` | Baseline via YARN REST (`/ws/v1/cluster/apps`), não Query Store |
| Lakehouse Federation (Connection + Foreign Catalog) | `kb/databricks/concepts/lakehouse-federation.md` | Aqui o tipo de origem é o **Hive Metastore** (banco relacional por trás do HMS), não um RDBMS standalone — detalhe completo em `concepts/hdfs-ingestion.md` §3 |
| `AUTO CDC` / CDF / SCD, Lakeflow SDP, DABs | `kb/spark-patterns/*`, `kb/databricks/*` | Idêntico — nenhuma adaptação necessária |

## 6. Flags de Redesign — Pig / MapReduce / HBase (nunca conversão mecânica)

Três construtos do ecossistema Hadoop **não têm transpilação automática** (Lakebridge/BladeBridge não
cobre nenhum dos três) e exigem **reescrita completa**, não tradução linha-a-linha:

| Construto | Por quê não é mecânico | Onde tratar |
|---|---|---|
| **Pig Latin** | Linguagem procedural de data flow; sem parser/transpiler oficial | `kb/sql-patterns/concepts/hiveql-conversion.md` §5 — mapa de operações → PySpark/Spark SQL |
| **MapReduce Java** | `Mapper`/`Reducer`/`Partitioner` exigem reescrita estrutural completa | `kb/sql-patterns/concepts/hiveql-conversion.md` §6 — `Mapper`→`select/flatMap`, `Reducer`→`groupBy().agg()` |
| **HBase** | Modelo NoSQL wide-column fundamentalmente diferente de tabela relacional; **o curso não desenvolve um padrão de conversão** (gap documental confirmado) | `kb/sql-patterns/concepts/hiveql-conversion.md` §10 — escalar para desenho de arquitetura dedicado, considerando o padrão de acesso real (scans vs point lookups) antes de definir a modelagem Delta |

Marcar **⚠️ revisão manual / redesign** — nunca "converter" automaticamente e nunca estimar esforço
como se fosse um mapeamento determinístico do gerador.

## 7. Os 8 Anti-Padrões de Migração (metodologia compartilhada — guardrails obrigatórios)

Mesmo framework do curso-gêmeo *SQL Server Migration* (Migration Maturity Model — confirmado
compartilhado pela auditoria): **Skipping Assessment** · **Big-Bang Migration** · **Premature
Decommission** · **Lift-and-Shift Mentality** · **No Parallel Validation** · **Ignoring Dialect/
Semantic Gaps** · **Ignoring Change Management** · **Underestimating Governance**. Risco genérico em
`kb/migration/concepts/discovery-assessment.md` §7; manifestação Hadoop-específica de cada um:

| Anti-Padrão | Manifestação Hadoop |
|---|---|
| Skipping Assessment | Pular discovery via Beeline/YARN REST/Ranger antes de propor design — dependências de Oozie/Sqoop ocultas geram complexidade surpresa |
| Big-Bang Migration | Migrar todo o cluster de uma vez; sem wave por database/domínio |
| Premature Decommission | Desligar o cluster Hadoop antes de todos os consumidores (dashboards, jobs Oozie downstream) migrarem |
| Lift-and-Shift Mentality | Replicar HDFS diretório-por-diretório ou Hive DB 1:1 sem Medallion/Liquid Clustering/redesign de HBase |
| No Parallel Validation | Cutover sem reconciliação em 2 fases (snapshot aprovado antes do CDC, depois só o delta) |
| Ignoring Dialect/Semantic Gaps | Tratar Pig/MapReduce/HBase como se fossem transpiláveis como HiveQL (§6) |
| Ignoring Change Management | Não treinar/envolver administradores Hadoop/Ranger na validação |
| Underestimating Governance | Não mapear Ranger/Sentry/Kerberos → UC ABAC/SCIM antes do cutover — o maior delta de segurança entre os dois ecossistemas |

## 8. Regras do Agente (resumo)

- **Grounding:** todo mapeamento vem das KBs listadas em §4. Construto sem equivalente claro
  (`UNIONTYPE`, `INTERVAL` Hive, SerDe customizado, Pig/MapReduce/HBase) → **⚠️ revisão manual**,
  nunca inventar equivalência.
- **Gate obrigatório:** SPEC + aprovação humana entre DESIGN e CONVERT (§3) — fronteira de turno.
- **Geradores determinísticos:** `scripts/hive_generate.py` (Hive DDL → Delta + flags + spec de
  reconciliação) e `scripts/reconcile_generate.py` (SQL de reconciliação) — nunca escritos à mão,
  nunca reimplementados.
- **Reconciliação em 2 fases:** snapshot histórico aprovado ANTES de ligar o CDC/sync incremental;
  depois só o delta. Nunca rodar as duas juntas.
- **Cutover:** runbook completo (suspensão de coordinators Oozie + `hdfs dfs -createSnapshot` como
  freeze, matriz de rollback, hypercare, sign-off) — nunca decommission prematuro do cluster Hadoop.
- **Escopo:** ecossistema Hadoop completo. Origem SQL Server/PostgreSQL ou destino Fabric →
  `migration-expert`; implementação pesada de pipeline → `databricks-engineer`; PII/Ranger/Kerberos em
  escala → `governance-auditor`; validação estatística avançada → `data-quality-steward`.
- **Idioma:** seguir o usuário (PT-BR/EN); nomes de construtos/produtos em inglês.

Concepts próprios deste domínio: `concepts/hive-ddl-conversion.md` · `concepts/hdfs-ingestion.md` ·
`concepts/sqoop-cdc.md` · `concepts/oozie-orchestration.md`. Concepts agregados de outros domínios (por
design — terreno compartilhado, ver §5): `kb/migration/concepts/discovery-assessment.md` ·
`kb/migration/concepts/reconciliation.md` · `kb/migration/concepts/cutover-rollback.md` ·
`kb/sql-patterns/concepts/hiveql-conversion.md` · `kb/databricks/concepts/lakehouse-federation.md` ·
`kb/governance/concepts/ranger-kerberos-to-uc.md`.
