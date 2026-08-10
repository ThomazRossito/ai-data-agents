# 🔀 Migração → Databricks

> Hub dos agentes e artefatos de migração. Todos escalam a partir do [[data_agents/agents/registry/migration-expert|migration-expert]] (roteador) para o especialista dedicado. Arquitetura: [[supervisor]] · KB: [[kb-map]] · Painel: [[Dashboard]]

## Agentes especialistas

| Origem | Agente | KB | Gerador determinístico |
|---|---|---|---|
| Roteador / schema-DDL | [[data_agents/agents/registry/migration-expert|migration-expert]] | [[kb/migration/index|migration]] | — |
| SQL Server (banco inteiro) | [[data_agents/agents/registry/sqlserver-to-databricks|sqlserver-to-databricks]] | [[kb/sqlserver-migration/index|sqlserver-migration]] | `scripts/sqlserver_generate.py` |
| SSIS (.dtsx) | [[data_agents/agents/registry/ssis-to-databricks|ssis-to-databricks]] | [[kb/ssis-migration/index|ssis-migration]] | — |
| SSAS (.bim/.vpax) | [[data_agents/agents/registry/ssas-to-databricks|ssas-to-databricks]] | [[kb/ssas-migration/index|ssas-migration]] | `scripts/ssas_generate.py` |
| Hadoop / Hive | [[data_agents/agents/registry/hadoop-to-databricks|hadoop-to-databricks]] | [[kb/hadoop-migration/index|hadoop-migration]] | `scripts/hive_generate.py` |
| Teradata | [[data_agents/agents/registry/teradata-to-databricks|teradata-to-databricks]] | [[kb/teradata-migration/index|teradata-migration]] | `scripts/teradata_generate.py` |

## Metodologia compartilhada (7 fases)

Discover → Assess → Design → **[gate SPEC + aprovação humana]** → Execute (CONVERT/INGEST/CDC) → Activate (VALIDATE/cutover) → Enable → Closeout.

- **Reconciliação** origem×destino: [[kb/migration/concepts/reconciliation|reconciliation]] + `scripts/reconcile_generate.py` (suporta `source_dialect`: tsql / hive / teradata).
- **Regra de ouro:** rodar os geradores determinísticos (acima) — nunca escrever DDL/SQL à mão nem reimplementar o gerador.
- **Gate anti-contaminação:** o gerador Teradata falha o build se a "fonte Teradata" contiver tokens Snowflake (VARIANT/OBJECT/ARRAY_AGG/METADATA$…). Ver [[audits/2026-08-02-curso-teradata-migration-vs-ai-data-agents|auditoria Teradata]].
