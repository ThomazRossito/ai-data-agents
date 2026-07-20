# Control Flow (SSIS) → Orquestração (Databricks)

> Control Flow = a orquestração do pacote (tasks + containers + precedence constraints). Alvo:
> **Lakeflow Jobs** (uma task por executable, com dependências). Terminologia 2026: "Databricks
> Workflows" agora é **Lakeflow Jobs**. Ver `execution-model-and-packaging.md` para o modelo único + DAB.

## Tasks → equivalente Databricks

| SSIS Control Flow Task | Equivalente Databricks | Observações |
|---|---|---|
| **Execute SQL Task** | `spark.sql(...)` em notebook, ou task SQL no Workflow / JDBC no source | Se roda no SQL Server de origem, manter via JDBC; se é lógica de negócio, reescrever em Spark SQL |
| **Data Flow Task** | Notebook PySpark **ou** pipeline DLT | Cada Data Flow vira um notebook/pipeline (ver `data-flow-map.md`) |
| **Sequence Container** | Grupo de tasks no Job (dependências) ou seção de notebook | Agrupamento lógico |
| **For Each Loop (ADO/File enumerator)** | Auto Loader (arquivos) **ou** job "for each" parametrizado / loop no notebook | Preferir Auto Loader p/ arquivos (S06); loop só se semântica exigir |
| **For Loop** | Loop Python no notebook (`for i in range(...)`) | |
| **Execute Package Task** | `dbutils.notebook.run(...)` / `%run` ou task filha no Workflow | Pacote-filho vira notebook/job filho |
| **Script Task (C#/VB.NET)** | Notebook Python (reescrita manual) | **S03** — não traduzir literalmente; sinalizar esforço manual |
| **Execute Process Task** | `%sh` / `subprocess` (cautela) ou serviço externo | Evitar; validar necessidade |
| **File System Task** | `dbutils.fs.*` (cp/mv/rm/mkdirs) | |
| **FTP Task** | Python (`paramiko`/`ftplib`/`requests`) em notebook | Credenciais via secret scope |
| **Bulk Insert Task** | `COPY INTO` / Auto Loader | Ingestão de arquivo para Delta |
| **Send Mail Task** | Databricks **Alerts** / SMTP em Python / webhook (Teams/Slack) | Notificação do Job também cobre |
| **Analysis Services / Processing** | — (fora do Databricks) | Sinalizar como fora de escopo / redesenhar |
| **WMI / MSMQ / Transfer Tasks** | Sem equivalente direto | ⚠️ revisão manual |

## Precedence Constraints → dependências e condicionais

| SSIS | Databricks |
|---|---|
| Precedence **Success** | Dependência normal entre tasks do Job (task B `depends_on` A) |
| Precedence **Failure** | Task com `run_if`/regra de falha, ou `try/except` + branch |
| Precedence **Completion** | Dependência com execução independente do status |
| Precedence com **Expression** (ex.: `@Var == 1`) | Condicional no notebook (`if`) ou task condicional / job param |
| Constraints **AND/OR** entre múltiplas origens | Modelar no grafo de dependências do Job |

## Robustez / operação

| SSIS | Databricks |
|---|---|
| **Checkpoints / restartability** | Escritas **idempotentes** (MERGE / overwrite por partição) + retries no Job (**S04**) |
| **Transactions (DTC)** | Atomicidade do Delta (commit por operação) + MERGE; não há DTC distribuído |
| **Event Handlers (OnError/OnWarning)** | `try/except` no notebook + **retry policy** e **alertas** do Job |
| **Package Parameters / Configurations** | **Job parameters** + `dbutils.widgets` |
| **Logging (SSISDB reports)** | Logs do Job + tabela de auditoria Delta + `system.` tables |

## Padrão de saída (orquestração)

- 1 pacote `.dtsx` → 1 **Databricks Job/Workflow** (`.yml` de Job ou via API) com uma task por executable e o grafo de dependências das precedence constraints.
- Data Flow Tasks viram notebooks referenciados pelas tasks (ou um pipeline DLT).
- Variáveis/parâmetros de pacote → job parameters; expressões de constraint → condicionais.
