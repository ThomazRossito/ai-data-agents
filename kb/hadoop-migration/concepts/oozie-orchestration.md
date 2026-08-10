# Oozie → Lakeflow Jobs — Orquestração

> Escopo: conversão de Oozie workflows, coordinators e bundles para orquestração Databricks via
> **Lakeflow Jobs**. Fonte normativa: curso oficial Databricks *"Hadoop Migration"*, `03 - Execute/3.5
> Lecture - Pipeline and Orchestration`. Fonte de verdade operacional de um futuro agente
> `hadoop-to-databricks` (ver auditoria `audits/2026-08-02-curso-hadoop-migration-vs-ai-data-agents.md`,
> item H6).
>
> Terminologia 2026: "Databricks Workflows" agora é **Lakeflow Jobs** — mesmo modelo já documentado
> para conversão de Control Flow SSIS em `kb/ssis-migration/concepts/control-flow-map.md` e
> `kb/ssis-migration/concepts/execution-model-and-packaging.md` §1. Este arquivo cobre o mapeamento
> **Oozie-específico**; para a sintaxe YAML completa de DAB (multi-task, `run_if`,
> `quartz_cron_expression`), ver `kb/pipeline-design/patterns/orchestration-databricks.md` e
> `kb/databricks/concepts/jobs-concepts.md` — não duplicados aqui.
>
> **Aviso de proveniência:** o "Worked Example" ao final da lecture 3.5 (workflow envolvendo
> `AdventureWorksDW` e um `oozie-sample-workflow.xml` supostamente "checked in") é resíduo
> mal-adaptado do curso irmão *SQL Server Migration* — `AdventureWorksDW` não é um dataset Hadoop.
> **Não usado como fonte aqui**; todo o restante deste arquivo vem das seções Hadoop-válidas de 3.5
> (Oozie, HiveQL, Sqoop, Quartz CRON).

**Domínio:** Oozie workflow/coordinator/bundle → Lakeflow Job, action types, CRON 5→6 campos, delete-and-reload

---

## 0. Primeira pergunta: já existe um orquestrador de terceiros?

Antes de converter Oozie nativo, verifique se o cliente já usa um orquestrador de terceiros:

| Situação | Caminho recomendado |
|---|---|
| Já usa **Apache Airflow**, **dbt**, **Prefect** ou **Dagster** apontando para o Hadoop | **Reapontar** — atualizar connection strings, adaptar dialeto SQL onde necessário; os DAGs/models existentes continuam funcionando contra Databricks. Se já existe operador Databricks no Airflow, a maior parte desta conversão já está feita |
| **Oozie nativo** (workflows, coordinators, bundles) é o orquestrador | Conversão completa — restante deste documento |

(fonte: 3.5, callout de abertura "Already Using Airflow, dbt, or Other Orchestration Tools?") —
**sempre perguntar isso primeiro**; converter Oozie manualmente quando um reapontamento resolveria é
retrabalho desnecessário.

---

## 1. Landscape de orquestração Hadoop (Oozie)

Hadoop oferece três níveis de orquestração via Apache Oozie (fonte: 3.5, §1):

- **Oozie Workflow** — define um DAG de actions. Cada action executa uma query Hive, job Spark,
  script shell, job MapReduce, import Sqoop ou outra tarefa. Dependências via nodes de fork/join e
  decision para branching.
- **Oozie Coordinator** — adiciona agendamento a um workflow. Dispara o workflow por tempo (ex.: a
  cada hora, diariamente à meia-noite) ou por disponibilidade de dado de entrada. Gerencia timezone e
  passa valores de data/hora parametrizados ao workflow.
- **Oozie Bundle** — agrupa múltiplos coordinators para gestão coordenada (start/stop/suspend como
  uma unidade).

---

## 2. Mapa geral Oozie → Lakeflow Jobs

| Oozie | O que faz | Lakeflow Jobs |
|---|---|---|
| Workflow | Define um DAG de actions (Hive, Spark, shell, etc.) | Job multi-task |
| Coordinator | Agenda um workflow com triggers de tempo/dado | Job com schedule trigger |
| Bundle | Agrupa coordinators para gestão coordenada | Múltiplos Jobs (geridos via Databricks Asset Bundles) |
| Hive Action | Executa script HiveQL | SQL task |
| Spark Action | Submete uma aplicação Spark | Spark JAR/Python task |
| Shell Action | Roda script shell/Python | Notebook task |
| Sqoop Action | Roda import/export Sqoop | Lakeflow Connect ou Auto Loader task — ver `concepts/sqoop-cdc.md` |
| MapReduce Action | Submete job MapReduce | Spark task (após reescrita) |
| Sub-workflow | Chama outro workflow | `run_job_task` |
| Fork/Join | Execução paralela com sincronização | Tasks paralelas com `depends_on` |
| Decision node | Branching condicional | `condition_task`/`if_else_task` |
| `oozie.coord.application.datetime` | Data/hora parametrizada | `{{job}}` ou parâmetros/widgets |

(fonte: 3.5, §1 tabela de mapeamento geral)

---

## 3. Control flow nodes → Databricks

| Nó de controle Oozie | Equivalente Databricks | Notas de conversão |
|---|---|---|
| `start` | Início do Job (implícito) | Automático — o Job começa na primeira task |
| `end` | Conclusão do Job (implícito) | Automático — o Job completa quando todas as tasks terminam |
| `kill` | Tratamento de falha de task | Mapear para `max_retries: 0` + notificação de falha |
| `fork` / `join` | Tasks paralelas com `depends_on` | Fork cria branches paralelos; join é uma task que depende de todos os branches |
| `decision` | `condition_task` | Avalia uma condição para escolher a próxima task |
| `action` | Task (tipo depende do action type) | Ver §4 |

(fonte: 3.5, §2 "Control Flow Components")

---

## 4. Action types → tipos de task

| Oozie Action Type | Tipo de Task Databricks | Notas de conversão |
|---|---|---|
| `hive` / `hive2` | SQL task | Scripts HiveQL viram conteúdo de SQL task; a maioria roda como está |
| `spark` | Spark JAR ou Python task | Parâmetros de spark-submit mapeiam para configuração da task |
| `shell` | Notebook task (Python) | Reescrever a lógica shell como células de notebook Python |
| `sqoop` | Ingestão Lakeflow Connect ou Auto Loader | Substituir Sqoop pela ingestão nativa Databricks — ver `concepts/sqoop-cdc.md` |
| `mapreduce` | Spark task (após reescrita) | MapReduce precisa ser reescrito como PySpark primeiro |
| `pig` | SQL ou Python task (após reescrita) | Scripts Pig precisam ser reescritos como Spark SQL/PySpark primeiro |
| `sub-workflow` | `run_job_task` | Chama outro Lakeflow Job |
| `distcp` | Notebook task com `dbutils.fs.cp` ou ferramenta externa | Operações de cópia de arquivo — ver `concepts/hdfs-ingestion.md` |
| `email` | Configuração de notificação do Lakeflow Job | Notificações nativas de e-mail/webhook |
| `java` | Spark JAR task | Empacotar código Java como aplicação Spark |

(fonte: 3.5, §2 "Action Types")

---

## 5. CRON: Oozie (5 campos) → Quartz (6 campos)

Oozie coordinators definem agendamento via atributo `frequency` (ex.: `${coord:days(1)}`,
`${coord:hours(6)}`). Lakeflow Jobs usam **Quartz CRON** (6 campos: segundos, minutos, horas,
dia-do-mês, mês, dia-da-semana) — ao converter, **adicionar um `0` à esquerda para os segundos**
(fonte: 3.5, §6, info box "Oozie CRON to Quartz CRON").

| Oozie Coordinator | Lakeflow Job Trigger |
|---|---|
| `frequency="${coord:hours(1)}"` | CRON: `0 0 * * * ?` (a cada hora) |
| `frequency="${coord:days(1)}"` com `timezone="US/Pacific"` | CRON: `0 0 0 * * ?` com timezone `US/Pacific` |
| `<input-events><data-in>` (disponibilidade de dado) | File arrival trigger no cloud storage |
| `<timeout>120</timeout>` | `timeout_seconds: 7200` na configuração do Job |

(fonte: 3.5, §5 "Example: Oozie Coordinator Scheduling") — sintaxe completa de `schedule` (YAML DAB)
em `kb/pipeline-design/patterns/orchestration-databricks.md`.

> **Timezone e DST:** Oozie coordinators especificam timezone explicitamente. Garanta que o mesmo
> timezone seja setado no schedule do Lakeflow Job para evitar runs perdidos ou duplicados durante o
> cutover — testar o comportamento de agendamento ao redor de transições de DST (fonte: 3.5, §7,
> aviso "Time Zone Handling").

---

## 6. Padrão delete-and-reload

Um padrão comum no Oozie usa uma Hive action para truncar a tabela-alvo e recarregar de uma área de
staging:

| Padrão Oozie | Equivalente Databricks |
|---|---|
| Hive action: `INSERT OVERWRITE TABLE target SELECT * FROM staging` | `CREATE OR REPLACE TABLE target AS SELECT * FROM staging` |
| Shell action: `hadoop fs -rm -r /target/path` seguido de Hive `LOAD DATA` | `CREATE OR REPLACE TABLE target AS SELECT * FROM read_files(...)` |

```sql
-- Substituir delete-and-reload do Oozie por CTAS idempotente
CREATE OR REPLACE TABLE silver.dim_product AS
SELECT * FROM bronze.dim_product_staging
WHERE load_date = :run_date;

-- Ou usar MERGE para updates incrementais (menos I/O, preferível para grão atômico)
MERGE INTO silver.dim_product AS target
USING bronze.dim_product_staging AS source
ON target.product_key = source.product_key
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;
```

(fonte: 3.5, §5 "Example: Oozie Delete-and-Reload Pattern") — preferir `MERGE` quando o grão é
incremental; `CREATE OR REPLACE TABLE` só quando o padrão é de fato full-reload (paridade de
comportamento, não introduz reprocessamento incremental).

---

## 7. Sqoop Action → substituição

| Padrão Sqoop no Oozie | Substituição Databricks |
|---|---|
| Sqoop import (tabela inteira) | Lakeflow Connect, ou `read_files` a partir da saída do DistCp |
| Sqoop incremental append | Auto Loader na landing zone + `MERGE` |
| Sqoop incremental lastmodified | Lakeflow Connect com change tracking |
| Sqoop export (para RDBMS) | Escrita JDBC a partir do Databricks, ou ferramenta de reverse ETL |

(fonte: 3.5, §5 "Example: Oozie Sqoop Action Replacement") — detalhe completo de CDC/incremental em
`concepts/sqoop-cdc.md`. Lakeflow Connect ingere direto do RDBMS para Delta, eliminando o Sqoop; para
dado já em staging via Sqoop no HDFS, ler direto da landing zone do DistCp em vez de recriar o
sub-task Sqoop.

---

## 8. Variáveis e propriedades

| Mecanismo Oozie | Equivalente Databricks | Exemplo |
|---|---|---|
| `${coord:formatTime(coord:nominalTime(),'yyyy-MM-dd')}` | `{{job}}` ou `current_date()` | Data de execução parametrizada |
| Arquivo de propriedades (`job.properties`) | Job parameters | Configuração key-value passada às tasks |
| `${wf:actionData('action-name')}` | Task values / `dbutils.jobs.taskValues` | Passar dado entre tasks |
| `${wf:errorMessage(wf:lastErrorNode())}` | Configuração de notificação de erro | Contexto de falha em alertas |

(fonte: 3.5, §6 "Oozie Variable and Property Conversion")

---

## 9. Bundle → múltiplos Jobs via DABs

Um Oozie bundle agrupa coordinators relacionados. No Databricks, gerenciar Jobs relacionados via
**Databricks Asset Bundles (DABs)** para deploy como infraestrutura-como-código, ou usar tags para
agrupar Jobs relacionados na UI do workspace (fonte: 3.5, §5, "Example: Oozie Bundle to Multiple
Lakeflow Jobs"). Estrutura YAML completa multi-ambiente (dev/staging/prod) em
`kb/pipeline-design/patterns/orchestration-cross-platform.md` — não duplicada aqui.

---

## 10. O que exige atenção manual

| Feature | Por que exige revisão manual | Recomendação |
|---|---|---|
| Actions Java customizadas | Código Java precisa ser revisado para compatibilidade Spark | Reescrever como PySpark ou empacotar como Spark JAR |
| Shell actions com comandos HDFS | Comandos `hadoop fs` precisam de equivalente em cloud storage | Substituir por `dbutils.fs` ou CLI cloud-nativa |
| Monitoramento de SLA do Oozie | Configuração de SLA do Oozie não tem equivalente direto | Usar alertas e monitoramento de SLA do Lakeflow Job |
| Data triggers de coordinator | Checagens de disponibilidade de dado baseadas em arquivo | Usar file arrival triggers ou pipelines contínuos |
| Credenciais Oozie (Kerberos, HCatalog) | Modelo de autenticação é diferente | Mapear para Unity Catalog secrets e service principals — ver auditoria item H8 (Ranger/Kerberos → UC, KB ainda pendente de criação) |
| Dependências cross-workflow | Oozie usa input events de coordinator | Usar `run_job_task` ou sinalização baseada em arquivo |

(fonte: 3.5, §7 "What Requires Manual Attention")

---

## 11. Checklist de conversão

- [ ] Todos os workflows Oozie inventariados e action types catalogados
- [ ] Hive actions convertidas para SQL tasks (compatibilidade HiveQL verificada)
- [ ] Spark actions mapeadas para Spark JAR ou Python tasks
- [ ] Shell actions reescritas como Python notebook tasks
- [ ] Sqoop actions substituídas por Lakeflow Connect ou Auto Loader (`concepts/sqoop-cdc.md`)
- [ ] MapReduce e Pig actions reescritas (fora do escopo deste arquivo — flag de redesign, ver auditoria item H7)
- [ ] Padrões fork/join mapeados para dependências de task paralelas
- [ ] Decision nodes convertidos para condition tasks
- [ ] Schedules de coordinator convertidos para Quartz CRON (timezone verificado — §5)
- [ ] Arquivos de propriedades convertidos para Job parameters
- [ ] Monitoramento de SLA do Oozie substituído por alertas do Lakeflow Job
- [ ] Error handling e notificação configurados em cada Job
- [ ] Verificado se já existe Airflow/dbt/Prefect/Dagster em uso — reapontar em vez de converter (§0)

(fonte: 3.5, "Conversion Checklist", adaptado)

---

## Anti-Padrões Locais (HD-O — Orquestração)

| Código | Anti-padrão | Correção |
|---|---|---|
| HD-O01 | Converter Oozie sem antes perguntar se já existe Airflow/dbt em uso | Sempre checar §0 primeiro — reapontar é mais barato que converter |
| HD-O02 | Copiar o CRON de 5 campos do Oozie direto para `quartz_cron_expression` | Adicionar segundos (6º campo) e validar timezone/DST — §5 |
| HD-O03 | Portar `mapreduce`/`pig` action mecanicamente para PySpark sem revisão | Exige reescrita de lógica, não tradução literal — flag de redesign (auditoria H7) |
| HD-O04 | Assumir que Oozie SLA monitoring tem equivalente 1:1 | Não tem — usar alertas/SLA nativos do Lakeflow Job — §10 |
| HD-O05 | Ignorar Kerberos/HCatalog nas credenciais de origem | Mapear para UC secrets/service principal antes de rodar em produção — §10 |

---

## Referências

- Curso Databricks — *Hadoop Migration* — `03 - Execute/3.5 Lecture - Pipeline and Orchestration`
- `kb/ssis-migration/concepts/control-flow-map.md` (mesma terminologia Lakeflow Jobs, mapeamento equivalente para SSIS Control Flow)
- `kb/ssis-migration/concepts/execution-model-and-packaging.md` (terminologia 2026, packaging DAB)
- `kb/pipeline-design/patterns/orchestration-databricks.md` (sintaxe YAML completa: multi-task DAG, `run_if`, schedule)
- `kb/pipeline-design/patterns/orchestration-cross-platform.md` (DABs multi-ambiente completo)
- `kb/databricks/concepts/jobs-concepts.md` (tipos de task, `run_if`, scheduling, `idempotency_token`)
- `concepts/hive-ddl-conversion.md` · `concepts/hdfs-ingestion.md` · `concepts/sqoop-cdc.md` (irmãos deste domínio)
- [Lakeflow Jobs](https://docs.databricks.com/en/jobs/index.html)
- [Databricks Asset Bundles](https://docs.databricks.com/en/dev-tools/bundles/index.html)
- [Apache Oozie Documentation](https://oozie.apache.org/docs/5.2.1/)
- [Oozie Coordinator Specification](https://oozie.apache.org/docs/5.2.1/CoordinatorFunctionalSpec.html)
