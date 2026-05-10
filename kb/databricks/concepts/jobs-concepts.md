# Jobs & Workflows — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** Arquitetura multi-task, tipos de task, scheduling, idempotência

---

## Arquitetura: Jobs Multi-Task DAG

Jobs orquestram múltiplas tarefas com dependências explícitas usando `depends_on` + `run_if`.

---

## Tipos de Tarefas

| Tipo | Uso | Compute Recomendado |
|------|-----|---------------------|
| `notebook_task` | Executar notebook (.py/.sql/.scala) | Job Cluster |
| `spark_python_task` | Script Python (não notebook) | Job Cluster |
| `python_wheel_task` | Pacote Python compilado | Serverless |
| `sql_task` | Query SQL ou arquivo .sql | SQL Warehouse |
| `dbt_task` | Transformações dbt | Job Cluster |
| `pipeline_task` | Trigger SDP/DLT pipeline | SDP (próprio compute) |
| `run_job_task` | Chamar outro job | Nenhum (indireto) |
| `for_each_task` | Loop parametrizado | Job Cluster |

---

## Condições `run_if`

| Condição | Executado Quando |
|----------|-----------------|
| `ALL_SUCCESS` (padrão) | Todas as dependências sucesso |
| `ALL_DONE` | Todas completadas (sucesso OU falha) |
| `AT_LEAST_ONE_SUCCESS` | Pelo menos uma sucesso |
| `NONE_FAILED` | Nenhuma falhou (sucesso ou skipped) |
| `ALL_FAILED` | Todas falharam |
| `AT_LEAST_ONE_FAILED` | Pelo menos uma falhou |

**Gotcha:** `run_if` é avaliado APÓS todas dependências completarem. Sem `ALL_DONE`, não espera falhas.

---

## Tipos de Scheduling

| Tipo | Configuração | Uso |
|------|-------------|-----|
| **Cron (Quartz)** | `quartz_cron_expression` | Recorrente por tempo |
| **File Arrival** | `trigger.file_arrival.url` | Reativo a novos arquivos |
| **Table Update** | `trigger.table_update.table_names` | Reativo a mudanças em tabela UC |
| **Manual** | Sem `trigger` | Ad-hoc via SDK |

---

## Idempotência

`idempotency_token` evita execuções duplicadas — tokens idênticos retornam a mesma run (válido por 24 horas).

---

## Variáveis Dinâmicas de Runtime

| Variável | Valor |
|---------|-------|
| `{{start_date}}` | Data de início da run |
| `{{end_date}}` | Data de término |
| `{{job.parameters.env}}` | Parâmetro nomeado |
| `{{job.task_trigger_time}}` | Timestamp trigger |

---

## Gotchas

| Gotcha | Solução |
|--------|---------|
| Timeout é por task, não por job | Configure `timeout_seconds` em cada task longa |
| Grupo "admins" não pode estar em permissions | Já tem acesso total automaticamente |
| File Arrival: URL precisa de permissões da workspace | Verificar IAM/RBAC antes |
| Table Update Trigger: requer Unity Catalog | hive_metastore não suporta |

---

## Checklist Implementação

- [ ] Retry policy configurada (max_retries: 2)
- [ ] `run_if` conditions explícitas em dependências
- [ ] Scheduling cron validado (quartz format)
- [ ] Idempotency tokens em run manual
- [ ] Alertas email em on_failure
- [ ] Timeouts por task definidos
- [ ] Grupo "admins" NUNCA em permissions
- [ ] Parameters validados com `dbutils.widgets.get()`
