# AI Data Agents — Índice Central

Sistema multi-agente construído sobre o Claude Agent SDK da Anthropic (modelo Moonshot Kimi K2.6).
Orquestra 22 agentes especialistas em Engenharia, Qualidade, Governança, Análise de Dados, Streaming, FinOps e Web Semântica.

---

## Regras e Governança

- [[supervisor]] — 🧭 Mapa do Orquestrador (hub navegável dos 22 agentes)
- [[Dashboard]] — 📊 Painéis vivos (Dataview): agentes, skills, KB
- [[kb-map]] — 📚 Mapa dos 24 domínios de KB
- [[migracao]] — 🔀 Migração → Databricks (agentes + geradores)
- [[constitution]] — Regras invioláveis de todos os agentes
- [[collaboration-workflows]] — Workflows colaborativos WF-01 a WF-05
- [[task_routing]] — Mapa de delegação e roteamento de tarefas

---

## Agentes

> Mapa completo e navegável em [[supervisor]]. Links apontam para o registry real
> (`data_agents/agents/registry/`) para desambiguar do espelho em `plugins/`.

### Tier 1 — Engineering Core
- [[data_agents/agents/registry/databricks-engineer|databricks-engineer]] — SQL/PySpark/Delta, LakeFlow/DLT, CDC, Jobs, diagnóstico Spark, Genie, AI/BI
- [[data_agents/agents/registry/databricks-ai|databricks-ai]] — RAG, Vector Search, LLMOps, AI Functions, Kafka/Flink/Structured Streaming
- [[data_agents/agents/registry/fabric-engineer|fabric-engineer]] — Fabric: Medallion, Data Factory, Star Schema, Semantic Models/DAX, FinOps
- [[data_agents/agents/registry/python-expert|python-expert]] — Python puro: pacotes, APIs, CLIs, testes
- [[data_agents/agents/registry/migration-expert|migration-expert]] — schema/DDL SQL Server/PostgreSQL → Databricks/Fabric

**Migração dedicada → Databricks:**
- [[data_agents/agents/registry/sqlserver-to-databricks|sqlserver-to-databricks]] — banco SQL Server completo → Databricks
- [[data_agents/agents/registry/ssis-to-databricks|ssis-to-databricks]] — pacotes SSIS (.dtsx) → Databricks
- [[data_agents/agents/registry/ssas-to-databricks|ssas-to-databricks]] — modelos SSAS (.bim/.vpax) + DAX
- [[data_agents/agents/registry/hadoop-to-databricks|hadoop-to-databricks]] — Hadoop (HDFS/Hive/Sqoop/Oozie/Ranger)
- [[data_agents/agents/registry/teradata-to-databricks|teradata-to-databricks]] — Teradata (DBC/BTEQ/TPT/PPI/TASM)

### Tier 2 — Especializados
- [[data_agents/agents/registry/data-quality-steward|data-quality-steward]] — validação, profiling, SLA, reconciliação
- [[data_agents/agents/registry/governance-auditor|governance-auditor]] — auditoria, LGPD, linhagem, RLS/CLS/ABAC
- [[data_agents/agents/registry/dbt-expert|dbt-expert]] — dbt Core: models, testes, snapshots
- [[data_agents/agents/registry/data-contracts-engineer|data-contracts-engineer]] — ODCS, SLA contratual, breaking changes
- [[data_agents/agents/registry/data-mesh-architect|data-mesh-architect]] — Data Mesh, Data Products, governança federada
- [[data_agents/agents/registry/fabric-rti|fabric-rti]] — Fabric RTI: Eventhouse, KQL, Eventstream, Activator
- [[data_agents/agents/registry/fabric-ontology|fabric-ontology]] — OWL 2, RDF, SPARQL, Fabric IQ Ontology
- [[data_agents/agents/registry/azure-analytics-auditor|azure-analytics-auditor]] — auditoria de arquitetura analítica Azure
- [[data_agents/agents/registry/azure-cost-calculator|azure-cost-calculator]] — FinOps: custo Azure
- [[data_agents/agents/registry/databricks-cost-calculator|databricks-cost-calculator]] — FinOps: custo Databricks (DBU)

### Tier 3 — Conversacionais
- [[data_agents/agents/registry/business-analyst|business-analyst]] — intake de requisitos (`/brief`, `/ship`)

### Tier 0 — Direto (sem MCP)
- [[data_agents/agents/registry/geral|geral]] — perguntas conceituais, zero MCP

---

## Knowledge Base (KB)

> Consultada pelos agentes antes de qualquer tarefa (KB-First protocol)

- [[kb/constitution]] — Regras centrais
- [[kb/pipeline-design/index]] — Medallion, cross-platform, orquestração
- [[kb/databricks/index]] — Jobs, Bundles, Unity Catalog, AI/ML
- [[kb/fabric/index]] — Lakehouse, Direct Lake, RTI, Data Factory
- [[kb/sql-patterns/index]] — SQL dialetos, boas práticas
- [[kb/spark-patterns/index]] — Spark, DataFrame, streaming
- [[kb/semantic-modeling/index]] — DAX, Genie Spaces
- [[kb/data-quality/index]] — Profiling, validação, SLA
- [[kb/governance/index]] — Auditoria, PII, compliance
- [[kb/python-patterns/index]] — Packaging, testes, padrões
- [[kb/migration/index]] — Assessment, SQL Server/PostgreSQL

---

## Skills Operacionais

> Playbooks de como executar tarefas (lidos on-demand pelos agentes). São 109 arquivos `SKILL.md` sob `skills/` — a lista completa por domínio está viva no [[Dashboard]] (tabela "Skills por domínio").

---

## Memórias do Sistema

> Capturadas automaticamente durante sessões

- [[data_agents/memory/data/ai-data-agents/index|Índice de memórias]] — memórias ativas do projeto atual

---

## Documentação Estratégica

- [[docs/GAPS_E_MELHORIAS|GAPS_E_MELHORIAS]] — Backlog de melhorias
- [[README]] — Guia completo do projeto
- [[CHANGELOG]] — Histórico de versões

---

## Configuração

- `.claude/CLAUDE.md` — Guia para Claude Code (pasta oculta; o Obsidian não indexa `.claude/`)
- [[Dashboard]] — Painéis Dataview (agentes, skills, KB)
