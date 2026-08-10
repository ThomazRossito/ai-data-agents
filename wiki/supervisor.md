# 🧭 Supervisor (Data Orchestrator)

> **Por que esta nota existe:** o Supervisor real é **código Python** (`data_agents/agents/prompts/supervisor_prompt.py` + `data_agents/agents/supervisor.py`), não um arquivo `.md` — por isso ele **não aparece sozinho no Graph View** do Obsidian. Esta nota é o **mapa navegável** dele: o hub em Markdown que liga o Supervisor aos 22 agentes especialistas via wikilinks, para o graph refletir a arquitetura real.

O Supervisor **nunca** executa código, acessa MCP ou gera SQL/PySpark. Ele apenas **planeja, decompõe, delega e sintetiza** (regras S1–S7).

Regras invioláveis: [[constitution]] · Roteamento/delegação: [[task_routing]] · Workflows: [[collaboration-workflows]] · Índice geral: [[index]]

---

## Tier 1 — Engineering Core

- [[data_agents/agents/registry/databricks-engineer|databricks-engineer]] — Databricks completo: Spark SQL/Unity Catalog, PySpark/Delta, LakeFlow/DLT, CDC, Jobs, diagnóstico Spark, Genie, AI/BI
- [[data_agents/agents/registry/databricks-ai|databricks-ai]] — RAG, Vector Search, LLMOps, AI Functions, Kafka/Flink/Spark Structured Streaming
- [[data_agents/agents/registry/fabric-engineer|fabric-engineer]] — Microsoft Fabric: Medallion, Data Factory, Star Schema, Semantic Models/DAX, governança, FinOps
- [[data_agents/agents/registry/python-expert|python-expert]] — Python puro: pacotes, APIs, CLIs, testes
- [[data_agents/agents/registry/migration-expert|migration-expert]] — schema/DDL SQL Server/PostgreSQL → Databricks/Fabric; roteia para os especialistas de migração abaixo

### Migração dedicada → Databricks (T1)

- [[data_agents/agents/registry/sqlserver-to-databricks|sqlserver-to-databricks]] — banco SQL Server inteiro → Databricks (DMV discovery, scoring, reconciliação, cutover)
- [[data_agents/agents/registry/ssis-to-databricks|ssis-to-databricks]] — pacotes SSIS (.dtsx) → Databricks Workflows/PySpark
- [[data_agents/agents/registry/ssas-to-databricks|ssas-to-databricks]] — modelos tabulares SSAS (.bim/.vpax) + DAX → Metric Views/Genie
- [[data_agents/agents/registry/hadoop-to-databricks|hadoop-to-databricks]] — Hadoop (HDFS/Hive/Sqoop/Oozie/Ranger) → Databricks
- [[data_agents/agents/registry/teradata-to-databricks|teradata-to-databricks]] — Teradata (DBC/BTEQ/TPT/PPI/TASM) → Databricks

## Tier 2 — Especializados

- [[data_agents/agents/registry/data-quality-steward|data-quality-steward]] — qualidade cross-platform: expectations, profiling, SLA, reconciliação
- [[data_agents/agents/registry/governance-auditor|governance-auditor]] — Unity Catalog, PII/LGPD, linhagem, RLS/CLS/ABAC
- [[data_agents/agents/registry/dbt-expert|dbt-expert]] — dbt Core: models, testes, snapshots
- [[data_agents/agents/registry/data-contracts-engineer|data-contracts-engineer]] — ODCS, SLA contratual, breaking changes
- [[data_agents/agents/registry/data-mesh-architect|data-mesh-architect]] — Data Mesh, Data Products, governança federada
- [[data_agents/agents/registry/fabric-rti|fabric-rti]] — Fabric Real-Time Intelligence: Eventhouse, KQL, Eventstream, Activator
- [[data_agents/agents/registry/fabric-ontology|fabric-ontology]] — OWL 2, RDF, SPARQL, Fabric IQ Ontology
- [[data_agents/agents/registry/azure-analytics-auditor|azure-analytics-auditor]] — auditoria de arquitetura analítica Azure
- [[data_agents/agents/registry/azure-cost-calculator|azure-cost-calculator]] — FinOps: estimativa de custo Azure
- [[data_agents/agents/registry/databricks-cost-calculator|databricks-cost-calculator]] — FinOps: estimativa de custo Databricks (DBU)

## Tier 3 — Conversacional

- [[data_agents/agents/registry/business-analyst|business-analyst]] — intake de requisitos (`/brief`, `/ship`)

## Tier 0 — Direto (sem MCP)

- [[data_agents/agents/registry/geral|geral]] — perguntas conceituais, zero MCP

---

## Base de Conhecimento (KB) por domínio

Os agentes consultam a KB antes de planejar (protocolo KB-First):

[[kb/databricks/index|kb: databricks]] · [[kb/fabric/index|kb: fabric]] · [[kb/spark-patterns/index|kb: spark-patterns]] · [[kb/sql-patterns/index|kb: sql-patterns]] · [[kb/pipeline-design/index|kb: pipeline-design]] · [[kb/semantic-modeling/index|kb: semantic-modeling]] · [[kb/data-quality/index|kb: data-quality]] · [[kb/governance/index|kb: governance]] · [[kb/python-patterns/index|kb: python-patterns]] · [[kb/migration/index|kb: migration]] · [[kb/sqlserver-migration/index|kb: sqlserver-migration]] · [[kb/ssis-migration/index|kb: ssis-migration]] · [[kb/ssas-migration/index|kb: ssas-migration]] · [[kb/hadoop-migration/index|kb: hadoop-migration]] · [[kb/teradata-migration/index|kb: teradata-migration]] · [[kb/data-contracts/index|kb: data-contracts]] · [[kb/data-mesh/index|kb: data-mesh]] · [[kb/semantic-web/index|kb: semantic-web]]

---

## 🔎 Como ver isto no Graph View

1. Abra esta nota e clique em **Local Graph** (ícone de grafo na barra lateral, ou `⌘P` → "Open local graph"). Profundidade **2** já mostra: Supervisor → 22 agentes → KB.
2. No **graph global**, filtre o ruído: `path:agents/registry OR file:supervisor` (mostra só o Supervisor + os 22 agentes).
3. Em **Groups** (engrenagem do graph), coloque cores por pasta: `path:agents/registry`, `path:kb`, `path:skills`.

> Os 109 nós idênticos "SKILL" são reais (cada skill é um arquivo `SKILL.md`); use os filtros acima para escondê-los. Esta nota **não** altera nenhum agente nem código — é só navegação.
