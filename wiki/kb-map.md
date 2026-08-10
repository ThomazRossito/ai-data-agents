# 📚 Mapa de Knowledge Base (KB)

> Hub navegável dos 24 domínios de KB. Os agentes consultam a KB **antes** de planejar (protocolo KB-First). Índice geral: [[index]] · Arquitetura: [[supervisor]] · Painéis: [[Dashboard]]

## Plataforma & Engenharia
- [[kb/databricks/index|databricks]] — Unity Catalog, Delta, Jobs, Bundles, AI/ML
- [[kb/fabric/index|fabric]] — Lakehouse, Direct Lake, RTI, Data Factory
- [[kb/spark-patterns/index|spark-patterns]] — Delta, streaming, performance, SDP
- [[kb/sql-patterns/index|sql-patterns]] — DDL, dialetos, star schema, otimização
- [[kb/pipeline-design/index|pipeline-design]] — Medallion, ETL/ELT, orquestração
- [[kb/semantic-modeling/index|semantic-modeling]] — DAX, Direct Lake, Metric Views
- [[kb/python-patterns/index|python-patterns]] — concorrência, testes, packaging, CLI

## Qualidade & Governança
- [[kb/data-quality/index|data-quality]] — expectations, profiling, drift, SLA
- [[kb/governance/index|governance]] — Unity Catalog, PII/LGPD, linhagem, RLS/CLS/ABAC
- [[kb/data-contracts/index|data-contracts]] — ODCS, SLA, breaking changes
- [[kb/data-mesh/index|data-mesh]] — domínios, Data Products, governança federada
- [[kb/semantic-web/index|semantic-web]] — OWL 2, RDF, SPARQL

## Migração (por origem)
- [[kb/migration/index|migration]] — assessment, reconciliação, cutover (compartilhado)
- [[kb/sqlserver-migration/index|sqlserver-migration]] — SQL Server → Databricks
- [[kb/ssis-migration/index|ssis-migration]] — SSIS (.dtsx) → Databricks
- [[kb/ssas-migration/index|ssas-migration]] — SSAS tabular → Metric Views
- [[kb/hadoop-migration/index|hadoop-migration]] — Hadoop/Hive → Databricks
- [[kb/teradata-migration/index|teradata-migration]] — Teradata → Databricks

## FinOps, Azure & Checklists
- [[kb/databricks-pricing/index|databricks-pricing]] — DBU, rightsizing, FinOps
- [[kb/azure-pricing/index|azure-pricing]] — custo Azure
- [[kb/azure-infra-for-databricks/index|azure-infra-for-databricks]] — infra Azure p/ Databricks
- [[kb/analytics-azure-spec/index|analytics-azure-spec]] — spec analítica Azure
- [[kb/industry/index|industry]] — padrões por indústria
- [[kb/checklists/index|checklists]] — checklists operacionais
