---
domain: teradata-migration
updated_at: 2026-08-02
agents: [teradata-to-databricks]
---

# Knowledge Base — Migração Teradata → Databricks

> Fonte de verdade operacional do agente **teradata-to-databricks**. Mesmo padrão de
> `kb/hadoop-migration/` e `kb/sqlserver-migration/`: este domínio tem `concepts/` próprios para o
> stack técnico **Teradata-específico** (DDL/tipos, catálogo de funções, ingestão/CDC) e **agrega**
> concepts que já vivem em outras KBs para o terreno **compartilhado** com os cursos-irmãos *SQL
> Server Migration* e *Hadoop Migration* (discovery/assessment, reconciliação, cutover, ABAC).
> Consultar SEMPRE antes de migrar um ambiente Teradata. NÃO inventar mapeamentos — construto sem
> equivalente claro é marcado ⚠️ (ver §6 Flags de Redesign).

## 0. ⚠️ AVISO CRÍTICO — Contaminação Snowflake no Curso-Fonte

O curso oficial Databricks *"Delivery Expert for Teradata Migration"* é a **terceira instância** da
mesma família já absorvida para SQL Server e Hadoop: mesma metodologia (Discover→Design→Execute→
Activate→Enable→Closeout), mesmos frameworks (Complexity Scoring, waves, cutover, reconciliação,
ABAC). Diferente dos dois cursos-irmãos, porém, este está **fortemente contaminado com conteúdo
Snowflake** — auditoria completa em `audits/2026-08-02-curso-teradata-migration-vs-ai-data-agents.md`
§2 encontrou material reaproveitado de um curso-irmão de Snowflake (dataset público "Tasty Bytes"/
`TB_101`) com find-replace imperfeito para "Teradata". **Nada dessa contaminação está codificada
nesta KB.** Os `concepts/` deste domínio usam só os trechos verificados como Teradata-válidos: o
dicionário `DBC.*`, os códigos de tipo de `DBC.ColumnsV`, `WRITE_NOS`/TPT/JDBC, e o catálogo de
funções limpo de contaminação (`QUALIFY`, `OREPLACE`, `ZEROIFNULL`, `LISTAGG`, etc.).

**Nunca tratar os seguintes tokens como sintaxe Teradata** — são Snowflake:

| Token/Padrão | Realidade |
|---|---|
| `VARIANT`, `OBJECT` (como tipo de coluna) | Snowflake. Teradata **tem** `VARIANT_TYPE`, mas é um UDT para **parâmetro de UDF/table operator**, nunca um tipo de coluna semiestruturada |
| `ARRAY_AGG`, `ARRAY_UNIQUE_AGG`, `OBJECT_AGG` | Funções Snowflake |
| `IFF(...)` | Função Snowflake (Teradata usa `CASE WHEN`) |
| `EQUAL_NULL` | Função Snowflake (Teradata usa `IS [NOT] DISTINCT FROM`) |
| `LATERAL FLATTEN` | Sintaxe Snowflake (Teradata usa `JSON_TABLE`/`EXPAND ON`) |
| `METADATA$ACTION`, `METADATA$ISUPDATE` | Pseudo-colunas de Snowflake Streams — Teradata não tem objeto Stream |
| `CREATE FUNCTION ... RUNTIME_VERSION='...' HANDLER='...'` | Sintaxe de UDF do Snowflake — Teradata usa Script Table Operator/BYOM |
| `TIMESTAMP_NTZ`/`TIMESTAMP_LTZ`/`TIMESTAMP_TZ` | Nomes de tipo Snowflake/Databricks — Teradata usa `TIMESTAMP(n)` e `TIMESTAMP(n) WITH TIME ZONE` |
| Dataset/schema `TB_101`/`RAW_POS`/`TRUCK`/`MENU`/`FRANCHISE` | Arquitetura literal do dataset de demo "Tasty Bytes" da Snowflake |

`scripts/teradata_generate.py` roda um **gate automático** contra esses tokens na entrada e falha o
build (código de saída ≠ 0) se detectar qualquer um — trate isso como sinal real de que a "fonte
Teradata" pode não ser Teradata genuína, nunca como falso positivo a ignorar.

## 1. Escopo

Migração de um **data warehouse Teradata Vantage inteiro** — schema físico (`DBC.*`/`SHOW TABLE`),
SET/MULTISET, PRIMARY INDEX/PPI, SQL/BTEQ/SPL, ingestão (`WRITE_NOS`/TPT/FastLoad/MultiLoad/JDBC),
CDC, TASM (workload management) e a camada de segurança (roles/`GRANT`) — para **Databricks**.
**A linguagem de origem é Teradata SQL — NÃO HiveQL.** Diferente de:

- migração de banco relacional **SQL Server** → `kb/sqlserver-migration/` (agente
  `sqlserver-to-databricks`) ou o generalista `kb/migration/` (agente `migration-expert`, também cobre
  PostgreSQL e destino Fabric)
- ecossistema **Hadoop** (HDFS/Hive/HiveQL/Impala/Sqoop/Oozie/Pig/MapReduce/HBase/Ranger/Kerberos) →
  `kb/hadoop-migration/` (agente `hadoop-to-databricks`)
- pacotes **SSIS** (`.dtsx`) → `kb/ssis-migration/` (agente `ssis-to-databricks`)
- modelo tabular **SSAS** (`.bim`/`.vpax`) → `kb/ssas-migration/` (agente `ssas-to-databricks`)

Este agente é o especialista Teradata-específico: origem **só** Teradata Vantage/DBC, destino **só**
Databricks, seguindo a mesma metodologia oficial (Discover→Design→Execute→Activate→Enable→Closeout)
adaptada ao stack técnico Teradata.

## 2. Mapa de Componentes — Teradata → Databricks

| Componente Teradata | Equivalente Databricks | Concept normativo |
|---|---|---|
| Dicionário `DBC.*` (`DBC.TablesV`, `DBC.ColumnsV`, `DBC.IndicesV`, `DBC.TableSizeV`) | Discovery manual → Unity Catalog `information_schema` pós-migração | `concepts/ddl-conversion.md` |
| Teradata SQL (DDL + DML, `SHOW TABLE`) | Delta DDL + Spark SQL | `concepts/ddl-conversion.md` |
| SET / MULTISET TABLE | Delta (sem análogo de SET — dedup explícito na ingestão) | `concepts/ddl-conversion.md` §SET |
| PRIMARY INDEX / PPI (`PARTITION BY RANGE_N`/`CASE_N`) | Liquid Clustering (`CLUSTER BY`) | `concepts/ddl-conversion.md` §PI/PPI |
| Join Index / Secondary Index (USI/NUSI) | Materialized view / Liquid Clustering / Z-ORDER — **redesign, sem 1:1** | `concepts/ddl-conversion.md` §5 |
| Catálogo de funções (`QUALIFY`, `OREPLACE`, `ZEROIFNULL`, `LISTAGG`, `CSUM`/`MSUM`/`MAVG`) | Databricks SQL / window functions Spark | `concepts/function-catalog.md` |
| BTEQ / SPL (Stored Procedure Language) | Lakebridge/BladeBridge (BTEQ) + Databricks SQL Scripting/PySpark (SPL) | `concepts/function-catalog.md` |
| `WRITE_NOS` (Native Object Store) / TPT / FastLoad / MultiLoad / JDBC | Auto Loader / `COPY INTO` / JDBC direto | `concepts/ingestion-cdc.md` |
| CDC (sem Stream nativo: timestamp/log-based/TPT CDC) | Auto Loader + `AUTO CDC` / `MERGE` | `concepts/ingestion-cdc.md` |
| `CREATE VOLATILE TABLE ... ON COMMIT PRESERVE ROWS` | `TEMP VIEW`/tabela transiente | `concepts/ingestion-cdc.md` |
| Lakehouse Federation (`CREATE CONNECTION ... TYPE teradata`) | Foreign Catalog (discovery/perfilamento, nunca fact tables grandes) | `kb/databricks/concepts/lakehouse-federation.md` (seção Teradata) |
| Iceberg/UniForm (Teradata Vantage lê UC via `CREATE DATALAKE ... TABLE FORMAT ICEBERG`) | UniForm/Iceberg read compat | `kb/databricks/concepts/lakehouse-federation.md` |
| TASM (`DBC.WorkloadDefinitions`) | SQL Warehouse profiles / Job Clusters | `kb/governance/concepts/uc-abac-governed-tags.md` |
| Roles / `GRANT` / row-level security | Unity Catalog `GRANT` / Row Filter / Column Mask / ABAC | `kb/governance/concepts/uc-abac-governed-tags.md` |
| `DBQLLogTbl` / observabilidade | `system.access.*`, `system.billing.*`, `system.query.*` | `kb/governance/concepts/uc-abac-governed-tags.md` |

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
| DISCOVER (5 categorias; dicionário `DBC.*` via BTEQ/JDBC) | `kb/migration/concepts/discovery-assessment.md` §1 | Comandos manuais (SKILL) — sem MCP dedicado a Teradata |
| ASSESS (Complexity Scoring, waves, Analytics-First×ETL-First) | `kb/migration/concepts/discovery-assessment.md` §2-9 | idem |
| CONVERT — DDL Teradata → Delta (tipos via `DBC.ColumnsV`, SET/MULTISET, PRIMARY INDEX/PPI) | `concepts/ddl-conversion.md` | `scripts/teradata_generate.py` |
| CONVERT — SQL/BTEQ/SPL, catálogo de funções, gaps OLAP (`CSUM`/`MSUM`/`MAVG`/`RESET WHEN`) | `concepts/function-catalog.md` | Lakebridge/BladeBridge (`--source teradata`); SQL Scripting/PySpark (SPL) |
| INGEST — `WRITE_NOS`/TPT/FastLoad/MultiLoad/JDBC por volume | `concepts/ingestion-cdc.md` | delegar implementação a `databricks-engineer` |
| INGEST — Lakehouse Federation (`TYPE teradata`, discovery/validação) | `kb/databricks/concepts/lakehouse-federation.md` §9 | delegar implementação a `databricks-engineer` |
| CDC — timestamp-based / log-based terceiros / TPT CDC (sem Stream nativo) | `concepts/ingestion-cdc.md` §CDC | `AUTO CDC` (`kb/spark-patterns/patterns/lakeflow-patterns.md`) |
| VALIDATE — reconciliação em 2 fases, 7 parity checks, estimador STDDEV (RC07) | `kb/migration/concepts/reconciliation.md` | `scripts/reconcile_generate.py` (`source_dialect: teradata`) |
| CUTOVER — Big Bang/Blue-Green, Decommission Readiness Check, matriz de rollback | `kb/migration/concepts/cutover-rollback.md` | Freeze Teradata-específico (ver `concepts/ingestion-cdc.md`) |
| Governança — TASM/roles/`GRANT` → UC | `kb/governance/concepts/uc-abac-governed-tags.md` | PII → escalar `governance-auditor` |
| Mapeamento genérico de tipos (fallback/dupla checagem) | `kb/migration/index.md` | `skills/migration/SKILL.md` |
| Definition of Done por fase | `kb/checklists/migration-dod.md` | — |
| Playbook operacional (comandos, formato de spec, gerador) | — | `skills/teradata-migration/teradata-to-databricks/SKILL.md` |
| Auditoria completa do curso-fonte (contaminação, fatos verificados) | `audits/2026-08-02-curso-teradata-migration-vs-ai-data-agents.md` | — |

## 5. Reuso Explícito — O Que NÃO é Teradata-Específico

Por ser a terceira instância da mesma família de cursos, ~60% da metodologia já está coberta e **não
deve ser recriada** — só reapontada para o contexto Teradata:

| Capacidade | Onde já existe | Nuance Teradata |
|---|---|---|
| Reconciliação (7 parity checks, 2 fases, tolerâncias, matriz de rollback) | `kb/migration/concepts/reconciliation.md` + `scripts/reconcile_generate.py` | Fonte é Teradata SQL agregado (ANSI aspas-duplas); **RC07 — casar estimador `STDDEV_POP`/`STDDEV_SAMP`**, bug real confirmado no curso-fonte; sem MD5 nativo em toda versão (hash row-a-row é best-effort) |
| Cutover/rollback (freeze, go/no-go, hypercare) | `kb/migration/concepts/cutover-rollback.md` | Estratégias citadas pelo curso: Big Bang e Blue-Green; **Decommission Readiness Check** via `information_schema.tables` × `system.access.audit` |
| Discovery/assessment (Complexity Scoring→waves) | `kb/migration/concepts/discovery-assessment.md` | Fonte é dicionário `DBC.*` via BTEQ/JDBC, não DMVs T-SQL nem Beeline/HDFS |
| ABAC/Governed Tags, row filter/mask | `kb/governance/concepts/uc-abac-governed-tags.md` | Mapeamento de origem é roles Teradata + TASM, não RLS/DDM nem Ranger/Sentry — corrobora ponto a ponto, sem contradição |
| `AUTO CDC` / CDF / SCD, Lakeflow SDP, DABs | `kb/spark-patterns/*`, `kb/databricks/*` | Idêntico — nenhuma adaptação necessária |
| Lakehouse Federation (Connection + Foreign Catalog) | `kb/databricks/concepts/lakehouse-federation.md` | Aqui o tipo de origem é `TYPE teradata` — DBR 16.1+/SQL Warehouse pro/serverless 2024.50+, auth TD2 apenas, porta 1025 |

## 6. Flags de Redesign — Join Index, Índices Secundários e Gaps do Curso-Fonte

Construtos e funções que **não têm tradução mecânica** e exigem tratamento manual/redesign:

| Construto | Por quê não é mecânico | Onde tratar |
|---|---|---|
| **Join Index** | Pré-agregação/pré-join física mantida pelo otimizador; sem equivalente 1:1 — a aproximação (materialized view/tabela pré-agregada) é decisão de design, não tradução | `concepts/ddl-conversion.md` §5 |
| **Secondary Index (USI/NUSI)** | Estrutura de acesso Teradata; no Delta a aproximação depende do padrão de consulta (Liquid Clustering/Z-ORDER/Bloom filter) | `concepts/ddl-conversion.md` §5 |
| **`PERIOD`/`INTERVAL`/`ARRAY`/`VARRAY`** | Sem tipo Delta direto — mapeiam para `STRING`/`STRUCT`/decomposição | `concepts/ddl-conversion.md` §1 |
| **Funções OLAP omitidas pelo curso** (`CSUM`/`MSUM`/`MAVG`/`MDIFF`/`RESET WHEN`/`NORMALIZE`/`EXPAND ON`/`PIVOT`/`UNPIVOT`/`OTRANSLATE`/`SEL`/`TOP n`) | O curso-fonte confirmadamente **omite** essas funções genuinamente Teradata (zero ocorrências no catálogo do curso) — nosso catálogo cobre isso melhor que a fonte, mapeando para window functions Spark | `concepts/function-catalog.md` |
| **BTEQ com controle de fluxo (`.IF`/`.GOTO`/`ACTIVITYCOUNT`/`ERRORCODE`)** | Ainda não confirmado se o Analyzer do Lakebridge/BladeBridge faz parsing completo desses comandos de controle (vs. só o SQL embutido) — tratar como ⚠️ até confirmação | `concepts/function-catalog.md` |

Marcar **⚠️ revisão manual / redesign** — nunca "converter" automaticamente e nunca estimar esforço
como se fosse um mapeamento determinístico do gerador.

## 7. Os 8 Anti-Padrões de Migração (metodologia compartilhada — guardrails obrigatórios)

Mesmo framework dos cursos-irmãos *SQL Server Migration* e *Hadoop Migration* (Migration Maturity
Model): **Skipping Assessment** · **Big-Bang Migration** · **Premature Decommission** ·
**Lift-and-Shift Mentality** · **No Parallel Validation** · **Ignoring Dialect/Semantic Gaps** ·
**Ignoring Change Management** · **Underestimating Governance**. Risco genérico em
`kb/migration/concepts/discovery-assessment.md` §7; manifestação Teradata-específica de cada um:

| Anti-Padrão | Manifestação Teradata |
|---|---|
| Skipping Assessment | Pular discovery via `DBC.*`/`SHOW TABLE` antes de propor design — dependências de BTEQ/TPT/TASM ocultas geram complexidade surpresa |
| Big-Bang Migration | Migrar todo o ambiente de uma vez; sem wave por database/domínio |
| Premature Decommission | Desligar o Teradata antes de todos os consumidores migrarem e do Decommission Readiness Check |
| Lift-and-Shift Mentality | Replicar PRIMARY INDEX/Join Index 1:1 sem Medallion/Liquid Clustering/redesign |
| No Parallel Validation | Cutover sem reconciliação em 2 fases (snapshot aprovado antes do CDC, depois só o delta) |
| Ignoring Dialect/Semantic Gaps | Tratar o curso-fonte contaminado com Snowflake sem o gate anti-contaminação (§0) — a manifestação mais severa deste anti-padrão neste domínio |
| Ignoring Change Management | Não treinar/envolver administradores Teradata na validação |
| Underestimating Governance | Não mapear TASM/roles → UC SQL Warehouse/ABAC antes do cutover |

## 8. Regras do Agente (resumo)

- **Grounding:** todo mapeamento vem das KBs listadas em §4. Construto sem equivalente claro
  (`PERIOD`, `INTERVAL`, `ARRAY`/`VARRAY`, Join Index) → **⚠️ revisão manual**, nunca inventar
  equivalência.
- **Gate obrigatório:** SPEC + aprovação humana entre DESIGN e CONVERT (§3) — fronteira de turno.
- **Gate anti-contaminação Snowflake:** rodado automaticamente por `scripts/teradata_generate.py` na
  entrada — falha o build se detectar tokens Snowflake (§0). Tratar como sinal real, nunca contornar.
- **Geradores determinísticos:** `scripts/teradata_generate.py` (Teradata DDL → Delta + flags + spec
  de reconciliação já com `source_dialect: teradata`) e `scripts/reconcile_generate.py` (SQL de
  reconciliação) — nunca escritos à mão, nunca reimplementados.
- **SET vs MULTISET:** tabelas `SET` exigem deduplicação explícita na ingestão — Delta não tem
  análogo de rejeição automática de duplicatas.
- **Reconciliação em 2 fases + estimador STDDEV:** snapshot histórico aprovado ANTES de ligar o
  CDC/sync incremental; depois só o delta. Sempre casar `STDDEV_POP`/`STDDEV_SAMP` entre origem e
  destino (RC07).
- **Cutover:** runbook completo (Big Bang ou Blue-Green, Decommission Readiness Check, matriz de
  rollback, hypercare, sign-off) — nunca decommission prematuro do Teradata.
- **Escopo:** data warehouse Teradata completo. Origem SQL Server/PostgreSQL/Hadoop ou destino Fabric
  → `migration-expert`/`sqlserver-to-databricks`/`hadoop-to-databricks`; implementação pesada de
  pipeline → `databricks-engineer`; PII/TASM/roles em escala → `governance-auditor`; validação
  estatística avançada → `data-quality-steward`.
- **Idioma:** seguir o usuário (PT-BR/EN); nomes de construtos/produtos em inglês.

Concepts próprios deste domínio: `concepts/ddl-conversion.md` · `concepts/function-catalog.md` ·
`concepts/ingestion-cdc.md`. Concepts agregados de outros domínios (por design — terreno
compartilhado, ver §5): `kb/migration/concepts/discovery-assessment.md` ·
`kb/migration/concepts/reconciliation.md` · `kb/migration/concepts/cutover-rollback.md` ·
`kb/databricks/concepts/lakehouse-federation.md` · `kb/governance/concepts/uc-abac-governed-tags.md`.
