# Modelo de Execução, Packaging (DAB) e Terminologia 2026

> Corrige as duas falhas mais graves observadas: (1) **misturar** Lakeflow SDP (declarativo) com
> notebooks imperativos numa mesma orquestração, e (2) entregar um **Jobs JSON cru** em vez de um
> **Bundle**. Regras aqui são invioláveis.

## 1. Terminologia atual (jul/2026) — usar os nomes novos

| Nome antigo | Nome atual (2026) | Observação |
|---|---|---|
| Delta Live Tables (DLT) | **Lakeflow Spark Declarative Pipelines (SDP)** | Código `@dp.*` continua funcionando; SKUs/eventlog ainda citam "dlt" |
| Databricks Workflows | **Lakeflow Jobs** | Orquestração (jobs/tasks/triggers); schema `workflow`→`lakeflow` |
| Databricks Asset Bundles (DAB) | **Declarative Automation Bundles** | Ainda `databricks.yml` + CLI `databricks bundle` |
| Ingestão custom (JDBC/ADF) | **Lakeflow Connect** | Conector gerenciado; **SQL Server via Change Tracking/CDC** |
| Conversão manual de pacotes | **Lakebridge** (conversor oficial Databricks) | Converte SSIS/stored procs (~80% automação); este agente é **complementar/AI-assisted** |

## 2. REGRA DE OURO — modelo de execução ÚNICO e coerente

`@dp.table`/`@dp.expect` (SDP) rodam num **runtime de pipeline** (recurso `pipeline`), **não** como
notebook task. **NUNCA misture** decorators SDP com orquestração por notebook-task. Escolha UM padrão
por pipeline:

**Padrão A — SDP declarativo (RECOMENDADO para medalhão):**
- Bronze→Silver→Gold(dims/fatos) como **Lakeflow SDP** (`@dp.table`, expectations `@dp.expect*`, e
  **`create_auto_cdc_flow` / APPLY CHANGES INTO** para SCD1/SCD2 — substitui MERGE manual).
- Roda como **UM recurso `pipeline`** no bundle.
- Passos puramente imperativos (auditoria, notificação, chamadas externas) → notebook tasks numa
  **Lakeflow Job** que **depende** da task de pipeline.

**Padrão B — Imperativo (Lakeflow Jobs + notebooks):**
- Todas as camadas em PySpark imperativo (MERGE/SCD na mão), **ZERO** decorators `@dp`.
- Expectations viram **checks pós-carga** ou **Delta CHECK constraints**.
- Orquestração 100% por **notebook tasks** na Lakeflow Job.

> ❌ Anti-padrão (o erro observado): Silver com `@dp.table` + Gold imperativo + Job com só `notebook_task`
> (sem `pipeline_task`) → o SDP fica órfão e nada roda fim a fim.

## 3. Completude da orquestração

- **Toda camada** (Bronze, Silver, Gold) precisa estar representada na orquestração. **Nunca** deixar
  notebook/pipeline órfão (ex.: Bronze/Silver sem task → Gold lê de tabela vazia).
- **Uma dimensão = uma unidade** (uma task/notebook OU um `create_auto_cdc_flow` no pipeline). Nunca
  apontar N tasks para o mesmo notebook que carrega tudo (roda N× em paralelo e duplica).
- Precedence constraints do SSIS → dependências (`depends_on`) + condicionais (`run_if`/expressão).

## 4. Packaging = Declarative Automation Bundle (DAB) — entregável padrão

Entregue um **bundle**, não Jobs JSON solto. Use a skill `skills/databricks/databricks-bundles/SKILL.md`.

Estrutura mínima:
```
<projeto>/
├── databricks.yml            # bundle: nome; include: resources/*.yml; targets: dev/staging/prod
├── resources/
│   ├── job.yml               # recurso jobs: (Lakeflow Job — orquestra)
│   └── pipeline.yml          # recurso pipelines: (Lakeflow SDP — se Padrão A)
└── src/                      # notebooks/pipelines .py
```
Boas práticas (docs 2026): **um bundle cobre todos os ambientes** (targets dev/staging/prod);
**service principal separado** para deploy vs run-as (run-as por job de produção com acesso mínimo);
**schema pessoal no dev** (`dev_${workspace.current_user.short_name}`) p/ não sobrescrever tabelas;
**serverless** por padrão; recursos declarados em source (não criados via UI).

## 5. Ingestão (Bronze)

- **SQL Server (OLTP):** preferir **Lakeflow Connect** (conector gerenciado; **Change Tracking** para
  tabelas com PK, ou CDC) em vez de JDBC cru. JDBC + secret scope só como fallback.
- **Arquivos (`sales_*.csv`):** **Auto Loader** (`cloudFiles`), não For Each Loop.
- Sempre com colunas técnicas (`_ingestion_ts`, `_source_system`, `_batch_id`) e escrita idempotente.

## 6. Hardening (pontas soltas observadas na auditoria — corrigir sempre)

- **SK estável e determinística:** usar **coluna IDENTITY** (`GENERATED ALWAYS AS IDENTITY`) ou
  **hash de chave natural**, ou **APPLY CHANGES** (que gerencia a SK). **Nunca**
  `monotonically_increasing_id() + max(sk)` (não-atômico, colide).
- **PII no CÓDIGO, não só no relatório:** mascarar/tokenizar `cpf`/`email`/`birth_date` na **Silver**
  (ou column masking do Unity Catalog), antes de Silver/Gold. Recomendar sem implementar é falha.
- **Sem FK enforced no Delta:** só `FOREIGN KEY ... NOT ENFORCED` (informativo) — nunca constraint executada.
- **Materializar colunas antes de Window/orderBy:** ex.: `.withColumn("lev", F.levenshtein(a,b))` antes
  de usar em `Window`/`orderBy` — não referenciar `F.col("levenshtein(...)")` (coluna inexistente → erro).
- **dim_date cobre a data mais antiga da origem** (não recortar anos → o fato rejeitaria linhas).
- **Idempotência:** `MERGE`/`replaceWhere` por partição — nunca `overwrite` da tabela toda em carga incremental.
- **Timezone:** verificar a TZ da origem (UTC vs local) antes de `to_utc_timestamp`; origem já-UTC não deve ser deslocada.
- **Reconciliação — nuance de fato legado agregado:** se o SSIS gravava um **agregado** (ex.: diário) e
  a nova Gold é **grão atômico**, avisar que a reconciliação 1:1 com a origem **não bate** no grão; reconciliar por totais.
- **Tabelas de referência usadas devem ser criadas** (ex.: `ref.city_master` do Fuzzy) — não deixar dummy vazio.

## 7. Implementação — armadilhas que QUEBRAM o pipeline (obrigatório)

- **Surrogate key é GERADA explicitamente — AUTO CDC NÃO cria SK de negócio.** `create_auto_cdc_flow`
  gerencia versionamento (`__START_AT`/`__END_AT`) e a natural key, mas **não** gera uma surrogate key.
  Gere a SK de UMA forma:
  - coluna `GENERATED ALWAYS AS IDENTITY` na dim-alvo, OU
  - **hash determinístico** da chave natural: `sha2(concat_ws('||', <natural_keys>), 256) AS <dim>_sk`,
    materializada no `*_clean` **ANTES** do AUTO CDC (persiste na dim; o fato casa por ela).
  - O fato só pode ler `*_sk` que **realmente existe** na dim (confira o schema pós-AUTO-CDC).
- **`sequence_by` = coluna TEMPORAL/monotônica** (`updated_at`, `order_ts`) — nunca `_batch_id`/run_id
  (string não-ordenável) → merge não-determinístico.
- **Grão do fato:** carregar as **chaves naturais** (`order_id`, `product_id`) no output do fato — sem elas o grão atômico colide.
- **DDL é REFERÊNCIA no Padrão A.** No SDP, o pipeline é **dono** das tabelas (cria/gerencia). NÃO gere
  `CREATE TABLE` recriando as tabelas do pipeline, nem com schema divergente (a dim pós-AUTO-CDC tem
  `__START_AT/__END_AT`, não `_valid_from/_valid_to`). DDL do migration-expert = catálogo/schema-alvo +
  star schema **documentado**; nunca instruir "executar os DDLs" das tabelas gerenciadas pelo SDP.
- **Ordem de seed:** tabelas de referência lidas pelo pipeline (`dim_date`, `ref.city_master`) são
  populadas **ANTES** da task de pipeline (ou dentro do pipeline) — nunca depois de quem as lê.
- **JDBC incremental:** predicado real e seguro (`.option("query", ...)` ou `WHERE col > '<wm>'` formatado
  com segurança) — **nunca `?` não-bindado** nem interpolação crua (injection). Preferir **Lakeflow Connect** (CDC).
- **DAB — validade:** segredos via `dbutils.secrets`/variável em runtime, **não** `${workspace.secrets...}`
  (namespace inexistente); em SDP `target:` é o **schema** de publicação (não o catalog); `max_retries`/retry
  são **por task**, não no topo do job.

## 8. Honestidade relatório × código (obrigatório)
Nenhum relatório pode afirmar correção/feature que **não esteja no código**. Cada alegação (SK estável,
idempotência `replaceWhere`, notificações enviadas, PII mascarada) tem que ser **rastreável a um trecho real**.
Se a tabela é MATERIALIZED VIEW (full recompute), diga MV — não diga `replaceWhere`. Se a notificação é via
`email_notifications` do Job, diga isso — não afirme "e-mail enviado" dentro do notebook.

## 9. Auto-revisão de sanidade ANTES de entregar (checklist obrigatório, COM prova)

Não marque um item sem PROVAR. `py_compile` OK **não basta** — vários bugs só quebram em runtime (§10).

- [ ] Toda coluna lida por um passo existe no passo que a produz (ex.: fato lê `*_sk` que a dim realmente tem).
- [ ] Zero `SyntaxError`: `python -m py_compile <arquivos .py>` (todos OK).
- [ ] `sequence_by` é temporal; grão do fato tem as chaves naturais.
- [ ] DDL não duplica nem diverge das tabelas do SDP.
- [ ] Tabelas de referência seedadas ANTES de quem as lê.
- [ ] Segredos via secret scope; sem `${workspace.secrets}`; DAB `target`=schema; retry por-task.
- [ ] **Runtime SDP/PySpark (§10):** sem `createDataFrame` com objetos `Column`; sem `Window`/`row_number` em DataFrame streaming; sem join stream-stream sem watermark; watermark lido de tabela de controle (não `spark.conf` vazio); `dim_date` cobre a data mais antiga real.

**Honestidade com DENTE — `grep` obrigatório (o self-check FALHOU aqui no run 3):**
Para CADA feature que o relatório alega, rode `grep` no código. Se o grep não achar, **APAGUE a alegação** (não marque):
- alega `replaceWhere`? → `grep -rn replaceWhere src/` tem que retornar linhas. (No run 3 o relatório afirmou `replaceWhere` sem existir no código — proibido.)
- alega `MERGE` / salt / `Lakeflow Connect` / notificação / incremental? → idem: só afirme o que o `grep` comprova.
- **Tabela de artefatos == arquivos reais:** `find <saída> -type f` tem que bater com a lista do relatório (não citar `.sql` se o código é `.py`).

## 10. Armadilhas de runtime SDP/PySpark (observadas no run 3 — evitar SEMPRE)

Compilar não garante que roda. Estes passam no `py_compile` e quebram em execução:

- **`createDataFrame` recebe VALORES Python, nunca `Column`.** `spark.createDataFrame([(F.lit("2020-01-01").cast("date"), ...)], [...])` falha. Para range de datas: `spark.range(1).select(F.explode(F.sequence(F.to_date(F.lit(start)), F.to_date(F.lit(end)), F.expr("interval 1 day"))))` ou `spark.sql("SELECT explode(sequence(...))")`.
- **`Window`/`row_number` NÃO é suportado em DataFrame streaming** (só janela temporal). Fuzzy match (levenshtein + `row_number` do melhor match) exige leitura **batch** (`spark.read`, não `readStream`). Se por isso a dim precisa de batch e é SCD1, modele como **`@dp.materialized_view` (snapshot atual)** em vez de `create_auto_cdc_flow` — **AUTO CDC exige fonte streaming**.
- **Join stream-stream sem watermark não é suportado.** Quarentena/orphans que cruzam duas Silvers → leitura **batch**.
- **`crossJoin` duplica nomes de coluna** → `F.col("state")` fica ambíguo. Faça **alias** nas colunas da tabela de lookup ANTES do join (ex.: `cm_state`, `cm_city_name`).
- **Watermark NÃO chega ao pipeline via `taskValues`.** `pipeline_task` não recebe `dbutils.jobs.taskValues`; a config do pipeline no bundle é estática. O SDP deve ler o watermark de uma **tabela de controle Delta** (`ref.etl_watermark`), não de `spark.conf.get("watermark_*")` que ninguém seta (senão = full-load todo run).
- **`dim_date` deve cobrir a data mais antiga REAL da origem** (range configurável). INNER JOIN com dim_date recortada **dropa silenciosamente** linhas do fato.
- **SK estável = hash SÓ da chave natural** (`sha2(customer_id)`), não de atributos mutáveis (email/nome) que fazem a SK "trocar". Histórico SCD2 vive em `__START_AT`/`__END_AT`; o fato lê a versão corrente (`filter __END_AT IS NULL`) — ou a SK da versão vigente na data do evento, se precisar de histórico real no fato.

## Fontes (docs Databricks, 2026)
- Lakeflow Spark Declarative Pipelines (ex-DLT): https://docs.databricks.com/aws/en/ldp/where-is-dlt
- Declarative Automation Bundles: https://docs.databricks.com/aws/en/dev-tools/bundles/
- Lakeflow Jobs: https://docs.databricks.com/aws/en/jobs/
- SSIS→Databricks (Lakebridge / decisão de ETL): https://www.databricks.com/blog/decision-framework-etl-migration-databricks
