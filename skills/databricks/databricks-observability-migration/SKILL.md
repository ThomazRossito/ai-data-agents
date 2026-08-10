---
name: databricks-observability-migration
description: "Observability pós-migração SQL Server → Databricks: mapeamento de monitoramento legado (Query Store, SQL Agent, Resource Governor) para system tables Databricks, monitoramento de Lakeflow Jobs/Pipelines (system tables vs event_log flow-level), alertas-as-code via Databricks Asset Bundles (resources.alerts), e sequência de tuning (CLUSTER BY -> OPTIMIZE -> ANALYZE, automatizado por Predictive Optimization). Use quando a tarefa mencionar: observability pós-cutover, system.lakeflow, system.query.history, SQL Alert, DAB alert, handoff de monitoramento pra operações, ou comparação de monitoramento SQL Server vs Databricks."
---

# Databricks Observability — Pós-Migração SQL Server

## Overview

Depois do cutover (fase Closeout), o time de operações precisa de visibilidade equivalente à que tinha no SQL Server — Query Store, SQL Agent job history, Resource Governor — mas usando as primitivas nativas do Databricks: **system tables**, **Lakeflow event logs**, e **SQL Alerts**. Esta skill é o playbook de "day 2" pra esse handoff: qual tabela substitui qual DMV, como monitorar Jobs e Lakeflow Declarative Pipelines (antigo DLT), como configurar alertas como código, e como manter tabelas Delta performáticas sem intervenção manual.

Para o modelo de custo/FinOps da migração (tagging, budgets, quick-wins de economia), ver `kb/databricks-pricing/concepts/finops-migration.md` — arquivo irmão desta skill. Para a mecânica genérica de system tables (não específica de migração), ver `../databricks-unity-catalog/SKILL.md`.

## Quick Reference — Mapa de Monitoramento SQL Server → Databricks

| SQL Server | Databricks | Uso |
|---|---|---|
| Query Store (`sys.query_store_runtime_stats`) / `sys.dm_exec_query_stats` | `system.query.history` | Performance de query, detecção de query lenta |
| `msdb.dbo.sysjobhistory` (SQL Agent) | `system.lakeflow.job_run_timeline` | Histórico de execução de job agendado |
| `sys.dm_os_wait_stats`, `sys.dm_exec_sessions` | `system.billing.usage` | Consumo de recursos / custo |
| SQL Server Audit, `sys.dm_exec_sessions` | `system.access.audit` | Auditoria de login e acesso |
| `sys.sql_expression_dependencies` | `system.access.table_lineage` / `column_lineage` | Linhagem de dados |
| `sys.dm_db_file_space_usage` | `system.storage.predictive_optimization_operations_history` | Eventos de manutenção/otimização de storage |
| Resource Governor | Budgets + Alerts | **Atenção:** não são equivalentes em comportamento — budgets só notificam, não suspendem compute. Ver `kb/databricks-pricing/concepts/finops-migration.md` §3 |

*Fonte: `04 - Activate/4.2` §2 ("SQL Server to Databricks Observability Mapping") + `06 - Closeout/6.1` §2.*

**Acesso:** system tables ficam no catálogo `system`, habilitadas por padrão. Requer `USE CATALOG system` + `USE SCHEMA` no schema relevante + `SELECT` na tabela, concedido por account/metastore admin. São somente-leitura e agregam dados de todos os workspaces da conta na mesma região de cloud.

**Retenção (citada no curso):** billing e audit = 365 dias; query history = 30 dias; job runs = 60 dias. Pra retenção mais longa, exportar via job agendado pro data lake/SIEM corporativo antes que a janela expire.

## Common Patterns

### Pattern 1 — Monitorar execução de Jobs

```sql
SELECT
    j.name AS job_name,
    jrt.run_id,
    jrt.result_state AS result,
    jrt.run_type,
    jrt.trigger_type,
    jrt.period_start_time AS start_time,
    jrt.period_end_time AS end_time,
    jrt.termination_code
FROM system.lakeflow.job_run_timeline jrt
JOIN system.lakeflow.jobs j ON jrt.job_id = j.job_id
WHERE jrt.period_start_time >= current_date() - INTERVAL 30 DAYS
ORDER BY jrt.period_start_time DESC;
```

Use isso pra comparar contra a baseline de `msdb.dbo.sysjobhistory` extraída **antes** do cutover (success rate, avg duration) — sem essa baseline capturada na fase Discover, não há como validar SLA pós-migração.

### Pattern 2 — Monitorar Lakeflow Declarative Pipelines: system tables vs event_log

Lakeflow Declarative Pipelines (antigo DLT) expõem dois níveis de observability:

| Abordagem | Fonte | Granularidade | Quando usar |
|---|---|---|---|
| **System Tables** | `system.lakeflow.pipeline_update_timeline` | Update-level (por execução do pipeline) | Métricas cross-pipeline, visão de conta inteira, sem setup |
| **Event Log** | `event_log("<pipeline-id>")` TVF, ou tabela configurada via bloco `event_log` no YAML | Flow-level (linhas escritas, expectations, por tabela/flow) | Detalhe operacional de um pipeline específico |

```sql
-- Opção A: system table (sem setup, visão agregada da conta)
SELECT p.name, put.update_id, put.result_state, put.period_start_time
FROM system.lakeflow.pipeline_update_timeline put
JOIN system.lakeflow.pipelines p ON put.pipeline_id = p.pipeline_id
WHERE put.period_start_time >= current_date() - INTERVAL 30 DAYS;

-- Opção B: event_log TVF (detalhe flow-level, sem precisar configurar tabela)
SELECT * FROM event_log("<pipeline-id>") LIMIT 100;

-- Opção B alternativa: tabela de event log configurada no YAML do pipeline
--   event_log:
--     name: event_log_my_pipeline
--     schema: my_schema
--     catalog: my_catalog
SELECT timestamp, event_type, level, message,
       details:flow_name::STRING AS flow_name,
       details:num_output_rows::LONG AS rows_written,
       details:status::STRING AS status
FROM my_catalog.my_schema.event_log_my_pipeline
WHERE event_type IN ('flow_progress', 'flow_definition', 'dataset_definition')
ORDER BY timestamp DESC;
```

*Fonte: 4.2 §4 ("Lakeflow Pipeline Monitoring", "Pipeline Event Logs").*

### Pattern 3 — Alertas como código (Databricks Asset Bundles)

Defina alertas de monitoramento como recursos `resources.alerts` no `databricks.yml` — versionado, revisável, reprodutível entre ambientes (dev/staging/prod).

```yaml
resources:
  alerts:
    migration_job_failure_alert:
      display_name: "Migration Job Failures"
      custom_summary: "{{query_result_rows}} migration job(s) failed in the last hour"
      query_text: |
        SELECT j.name AS job_name, jrt.run_id, jrt.result_state, jrt.period_start_time
        FROM system.lakeflow.job_run_timeline jrt
        JOIN system.lakeflow.jobs j ON jrt.job_id = j.job_id
        WHERE jrt.result_state = 'FAILED'
          AND jrt.period_start_time >= current_timestamp() - INTERVAL 1 HOUR
      warehouse_id: ${var.warehouse_id}
      evaluation:
        comparison_operator: GREATER_THAN
        empty_result_state: OK
        source:
          name: job_name
          aggregation: COUNT
          display: "Failed Jobs"
        threshold:
          value: { double_value: 0 }
        notification:
          notify_on_ok: true
          retrigger_seconds: 3600
          subscriptions:
            - user_email: migration-team@example.com
      schedule:
        pause_status: UNPAUSED
        quartz_cron_schedule: "0 */15 * * * ?"
        timezone_id: America/Sao_Paulo
      permissions:
        - level: CAN_MANAGE
          group_name: migration-admins
        - level: CAN_VIEW
          group_name: data-engineering
```

Campos-chave: `query_text` (SQL do alerta) + `evaluation.threshold` (condição de disparo) + `schedule.quartz_cron_schedule` (frequência) + `notification.subscriptions` (destinos).

**Alternativa via UI** (sem DAB): salvar uma query → menu de três pontos → "Create Alert" → configurar schedule/threshold → atribuir notification destinations.

**Notification destinations suportados:** Email, Slack (webhook), Microsoft Teams (incoming webhook connector), PagerDuty (integration key), Webhook genérico (ServiceNow, Jira, etc). Configurados em **Settings → Notification destinations** (workspace-level) ou via CLI/API.

*Fonte: 4.2 §11 ("Configuring Alerts", exemplo YAML "Migration Job Failure Monitor" e "Data Freshness SLA Monitor") + 6.1 §4 ("Notification Destinations and SQL Alerts").*

### Pattern 4 — Tuning: CLUSTER BY → OPTIMIZE → ANALYZE

| SQL Server | Databricks | Quando aplicar |
|---|---|---|
| Índices clustered, table partitioning | Liquid Clustering | Colunas de filtro de alta cardinalidade |
| Índices columnstore clustered | `CLUSTER BY` | Colunas frequentemente filtradas |
| Índices non-clustered, full-text | Bloom filters / data skipping | Point lookups em tabelas grandes |
| Indexed Views | Materialized Views / tabelas agregadas | Queries de agregação repetidas |
| Plan cache, buffer pool | Query result cache | Queries idênticas repetidas |

```sql
-- 1. Definir a chave de clustering
ALTER TABLE catalog.schema.factinternetsales
CLUSTER BY (OrderDateKey, ProductKey);

-- 2. Compactar arquivos pequenos + aplicar clustering
OPTIMIZE catalog.schema.factinternetsales;

-- 3. Atualizar estatísticas pra otimização de query
ANALYZE TABLE catalog.schema.factinternetsales COMPUTE STATISTICS FOR ALL COLUMNS;
```

**Predictive Optimization automatiza os 3 passos acima** em tabelas Unity Catalog managed (não externas, não Delta Sharing) — habilitado por padrão em contas criadas a partir de 11/nov/2024, com rollout em contas existentes concluindo ~ago/2026 (verificação web; o curso original citava fev/2026). Detalhe completo (escopo, billing, SQL de habilitação) em `kb/databricks-pricing/concepts/finops-migration.md` §8 — não duplicado aqui.

```sql
-- Verificar histórico de operações automáticas
SELECT table_name, operation_type, operation_status, start_time, end_time
FROM system.storage.predictive_optimization_operations_history
WHERE start_time >= current_date() - INTERVAL 90 DAYS
ORDER BY start_time DESC;
```

*Fonte: 4.2 §10 ("Performance Tuning Before Cutover") + `kb/databricks-pricing/concepts/finops-migration.md` §8.*

## Common Issues

| Problema | Solução |
|---|---|
| Job history não cobre período pré-migração | System tables só têm dados desde a habilitação da conta — capturar baseline do `msdb.dbo.sysjobhistory` **antes** do cutover (fase Discover) e persistir em Delta separado |
| `pipeline_update_timeline` não mostra detalhe de linha/expectation | Granularidade é update-level; usar `event_log("<pipeline-id>")` ou a tabela `event_log_*` configurada pra detalhe flow-level |
| Alert não dispara | Conferir `warehouse_id` válido, sintaxe do `quartz_cron_schedule`, e `empty_result_state` (OK vs alerta silencioso quando a query não retorna linhas) |
| Acesso negado a `system.*` | Faltando `USE CATALOG system` + `USE SCHEMA` + `SELECT` na tabela — pedir a account/metastore admin |
| Dados de system table sumiram após alguns dias/meses | Retenção limitada por schema (30-365 dias) — configurar export agendado pro data lake/SIEM se precisar histórico maior |
| Predictive Optimization não está rodando numa tabela | Confirmar que é **managed table** (não external/Delta Sharing) e que está habilitado no nível certo (schema/catalog/conta) — checar via `DESCRIBE SCHEMA EXTENDED` |
| Query de custo por tag retorna `NULL`/vazio | Tags não propagaram pra `custom_tags` — cluster/job/warehouse criado sem tag, ou cluster policy não está aplicada — ver `finops-migration.md` §4 |

## Related Skills

- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** — mecânica genérica de system tables (lineage, audit, billing), volumes
- **[databricks-jobs](../databricks-jobs/SKILL.md)** — configuração de notifications/monitoring nativo de Jobs
- **[databricks-bundles](../databricks-bundles/SKILL.md)** — deployment de recursos DAB (`resources.alerts`, `resources.jobs`)
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** — configuração do bloco `event_log` no YAML do pipeline
- **[pricing](../pricing/SKILL.md)** — cotação de custo Databricks (agent `databricks-cost-calculator`)
- **[migration](../../migration/SKILL.md)** — playbook das 5 fases de migração (ASSESS → VALIDATE)

## Resources

- [System Tables Overview](https://docs.databricks.com/en/admin/system-tables/index.html)
- [SQL Alerts](https://docs.databricks.com/en/sql/user/alerts/index.html)
- [Notification Destinations](https://docs.databricks.com/aws/en/admin/workspace-settings/notification-destinations)
- [Data Quality Monitoring](https://docs.databricks.com/aws/en/data-governance/unity-catalog/data-quality-monitoring)
- [Audit Logs](https://docs.databricks.com/en/admin/account-settings/audit-logs.html)
- [Delta Optimization](https://docs.databricks.com/en/delta/optimize.html)
