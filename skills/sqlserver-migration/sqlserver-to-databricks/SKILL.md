---
name: sqlserver-to-databricks
description: "Playbook operacional do agente sqlserver-to-databricks: rodar discovery via DMVs (scripts/mssql_discovery.sql) e tools do MCP migration_source, montar o schema.json de entrada, pontuar complexidade/waves, produzir o documento de proposta (SPEC) para aprovação humana, rodar os dois geradores determinísticos (scripts/sqlserver_generate.py e scripts/reconcile_generate.py), orientar ingestão CDC/Lakehouse Federation, e aplicar o runbook de cutover/rollback — tudo para migração de banco SQL Server → Databricks."
updated_at: 2026-08-02
source: kb/sqlserver-migration (index + kb/migration/concepts/discovery-assessment.md + reconciliation.md + cutover-rollback.md + kb/sql-patterns/concepts/tsql-conversion-catalog.md + kb/databricks/concepts/lakehouse-federation.md + kb/governance/concepts/uc-abac-governed-tags.md)
agent: sqlserver-to-databricks
domain: sqlserver-migration
---

# Skill — Migração SQL Server → Databricks

> Leia na primeira chamada da sessão. Define COMO rodar discovery, COMO montar a entrada dos geradores, e
> COMO conduzir as 8 fases. A fonte normativa dos mapeamentos/regras é `kb/sqlserver-migration/` +
> `kb/migration/concepts/*` + `kb/sql-patterns/concepts/tsql-conversion-catalog.md` — este skill é o "como
> fazer".

## Fluxo (8 fases + gate de aprovação)
`DISCOVER → ASSESS → DESIGN → [GATE: SPEC + aprovação humana] → CONVERT → INGEST → CDC → VALIDATE → CUTOVER`

## Passo 1 — DISCOVER

**Duas fontes de discovery, complementares:**

1. **MCP `migration_source`** (metadados estruturados, tool a tool):
   `migration_source_list_sources` → `migration_source_diagnostics(source=<fonte>)` (valida
   conectividade) → `migration_source_list_schemas` → `migration_source_list_tables` →
   `migration_source_describe_table` (por tabela: colunas/tipos/nullability/PK) →
   `migration_source_get_schema_summary` + `migration_source_count_tables_by_schema` (totais) →
   `migration_source_list_views`/`list_procedures`/`list_functions` +
   `get_view_definition`/`get_procedure_definition`/`get_function_definition` (código-fonte para
   classificar complexidade) → `migration_source_sample_table` (amostra para detectar PII).

2. **`scripts/mssql_discovery.sql`** (queries DMV que o MCP não expõe — row counts via
   `sys.dm_db_partition_stats`, complexidade de procedures via `sys.sql_modules`, SSISDB, SQL Agent
   jobs, status de CDC, RLS/DDM, permissões, Query Store). Este script é **SOMENTE LEITURA** e roda
   **fora do MCP** — peça ao usuário/DBA para executar cada bloco via SSMS/Azure Data Studio/sqlcmd
   contra a instância em escopo, e cole/exporte os resultados (CSV/JSON) de volta para você analisar.
   Nunca invente um resultado de DMV que não foi fornecido.

**Buffer-safe:** para schemas grandes (>50 tabelas), NÃO despeje o output bruto de `describe_table` de
cada tabela no contexto de uma vez — grave um índice compacto em `<saída>/_work/discovery_index.json`
(schema, tabela, contagem de colunas, tipo de cada coluna, PK, nullable) e trabalhe sobre o índice.

Consolide os achados nas 5 categorias de `kb/migration/concepts/discovery-assessment.md` §1: **Data
Assets**, **Pipelines & ETL**, **Consumers & Users**, **Security & Access**, **Operations & SLAs**.

## Passo 2 — ASSESS (scoring, waves, estratégia)

Pontue cada workload (database/domínio) na **Complexity Scoring Matrix** (`discovery-assessment.md` §2),
7 dimensões, 1-4 pontos cada:

| Dimensão | 1pt | 2pt | 3pt | 4pt |
|---|---|---|---|---|
| Table Count | <10 | 10-50 | 50-200 | >200 |
| Data Volume | <10GB | 10-100GB | 100GB-1TB | >1TB |
| T-SQL Complexity | DML simples | procs/UDFs/CTEs | cursors/WHILE/dynamic SQL | CLR/linked servers/OPENROWSET |
| SSIS Complexity | sem SSIS | transforms moderados | Script Tasks/complexos | Script+CLR+serviço externo |
| Dependencies | nenhuma | 1-3 upstream | 4-10 upstream | >10/circular |
| SLA Sensitivity | nenhuma/batch | SLA diário | SLA horário | real-time |
| Consumers | 1 time | 2-5 times | enterprise-wide | externo/customer-facing |

Soma → wave: **6-10=Wave1, 11-16=Wave2, 17-20=Wave3, 21+=Wave3 c/ especialista**.

Heurística de complexidade T-SQL por procedure (de `sys.sql_modules.definition`, seção 3.2 do
`mssql_discovery.sql`): `CURSOR`/`EXEC(`/`EXECUTE(`/`OPENROWSET`/`OPENQUERY` → **High**; `WHILE` ou
`LEN(definition)>5000` → **Medium**; senão **Low**.

T-shirt sizing por row count (`sys.dm_db_partition_stats`, seção 2 do script): S<1.000, M 1.000-50.000,
L 50.000-1.000.000, XL>1.000.000.

**Árvore de decisão Analytics-First vs ETL-First** (`discovery-assessment.md` §5): driver
custo/compliance → **ETL-First**; driver quick-win/IA-BI → **Analytics-First**; nenhum dos dois →
default **ETL-First**.

Confirme o **vetor de deployment** (on-premises/Azure SQL Database/Azure SQL Managed Instance/AWS RDS) e
a disponibilidade de CDC por vetor (`discovery-assessment.md` §6.1).

## Passo 3 — DESIGN

Proponha Medallion (Bronze/Silver/Gold) e, por tabela, o padrão de ingestão: **CDC** (OLTP ativo, CDC
disponível), **Batch Full** (referência/lookup pequena), **Batch Incremental** (watermark/timestamp), ou
**Federation** (Analytics-First, acesso temporário de leitura). Esboce o modelo de governança (que
colunas precisam de row filter/mask/Governed Tag). Isto compõe o **SPEC**.

## GATE — Documento de proposta (SPEC) + aprovação humana (obrigatório)

Entregue o SPEC (formato no `registry/sqlserver-to-databricks.md` § Formato de Resposta) e **PARE**. Este
projeto adota "sempre documento + aprovação para migrações" (Constituição §2.2 / Supervisor Step 0.6A).

> **O GATE é uma FRONTEIRA DE TURNO, não um passo sequencial.** Entregue o SPEC e **encerre** — quem
> aprova é o **usuário**, numa mensagem seguinte. NÃO gere DDL/código no mesmo turno do SPEC. Um hook de
> enforcement (`enforce_migration_gate`) bloqueia uma 2ª delegação de migração no mesmo turno; se você
> for bloqueado, é sinal de que deveria ter parado — apresente o SPEC e aguarde.

## Passo 4 — CONVERT (só após aprovação) — DETERMINÍSTICO, dirigido por metadados

**Regra de ouro:** NÃO escreva DDL/SQL à mão **e NÃO escreva seu próprio gerador** (`generate_*.py`).
Monte o `schema.json` de entrada a partir do índice do Passo 1 (`_work/discovery_index.json` ou dos
retornos de `migration_source_describe_table`/`list_tables`), no formato:

```json
{
  "model": "AdventureWorks",
  "tables": [
    {"schema":"dbo","name":"FactInternetSales",
     "columns":[
       {"name":"SalesOrderNumber","type":"nvarchar(20)","nullable":false},
       {"name":"OrderQuantity","type":"int","nullable":true},
       {"name":"SalesAmount","type":"money","nullable":true},
       {"name":"OrderDate","type":"datetime2","nullable":true},
       {"name":"SalesKey","type":"bigint","nullable":false,"identity":true}],
     "primary_key":["SalesOrderNumber"]}
  ]
}
```

Rode o gerador:

```bash
python scripts/sqlserver_generate.py <schema.json> output/sqlserver-migration/<slug>
```

Ele emite, **correto-por-construção** (identificadores normalizados + backtick, mapa fixo de tipos
SQL Server→Delta, `COMMENT` com o tipo original para auditoria):

- `01_ddl_databricks.sql` — `CREATE TABLE IF NOT EXISTS catalog.gold.<prefixo>_<tabela>` (Delta, PK `RELY`, `IDENTITY GENERATED BY DEFAULT`).
- `02_type_flags.md` — colunas que exigem revisão manual (`uniqueidentifier`, `geography`, `rowversion`, tipos desconhecidos, `tinyint`).
- `03_reconcile_spec.json` — spec **pronto** para `scripts/reconcile_generate.py` (keys=PK, colunas numéricas exatas/float, datas).

**Esses arquivos SÃO os entregáveis de DDL.** Não os reescreva à mão, não os "melhore", não gere um
`generate_*.py` paralelo. O gerador roda **gates** (identificador sem backtick no DDL; tipo desconhecido
não revisado) e sai com **código ≠ 0** se algum falhar → **NÃO reporte "concluído"** e corrija a causa
(nunca contorne com um gerador próprio).

**Além do gerador (julgamento de especialista, honesto — não auto-fingível):**
- **Procedures/functions/views:** classifique SQL Scripting (DBR 16+, corpo é DML+controle de fluxo
  simples) vs Python notebook (cursor loops, dynamic SQL, chamadas externas, lógica CLR) —
  `kb/sql-patterns/concepts/tsql-conversion-catalog.md` §4.
- **Cursors:** SEMPRE set-based (`MERGE`/`UPDATE...JOIN`/agregação) — nunca 1:1 (§5 do mesmo catálogo).
- **Lista "requer redesign"** (§6): dynamic SQL, CLR, linked servers, temp tables/table variables,
  `@@IDENTITY`, `OUTPUT` clause, `TRY...CATCH`, `WAITFOR`, full-text search, `XACT_ABORT` — marque ⚠️,
  nunca converta às cegas.
- **PII / masks:** → `governance-auditor`.

**Delegação (fora do escopo deste especialista):** implementação pesada de pipeline (Auto Loader,
Lakeflow SDP/DLT, jobs de produção) → `databricks-engineer`. O `01_ddl_databricks.sql` é o **contrato de
schema**; o pipeline que enche é dele.

## Passo 5 — INGEST

Documente o contrato Bronze→Silver→Gold (schema-alvo do `01_ddl_databricks.sql` + star schema Gold).
Escolha por tabela (do Passo 3): **Lakeflow Connect** (CDC/Change Tracking, preferencial para OLTP
ativo), **Auto Loader** (arquivos), ou **Lakehouse Federation** (Connection + Foreign Catalog — discovery/
perfilamento/validação/dimensões pequenas; **nunca** fact tables multi-TB — ver
`kb/databricks/concepts/lakehouse-federation.md` §6). Implementação de produção → escalar
`databricks-engineer`.

## Passo 6 — CDC

Confirme CDC habilitado na origem (seção 6 do `mssql_discovery.sql`: `sys.databases.is_cdc_enabled` +
`cdc.change_tables`). Configure **Lakeflow Connect (AUTO CDC)** para tabelas ativas. Para catch-up de
deltas finais sem um conector automatizado, use **Change Data Feed** (`table_changes()`) ou **`MERGE`
federado** contra o Foreign Catalog (`kb/databricks/concepts/lakehouse-federation.md` §7,
`kb/migration/concepts/cutover-rollback.md` §2.1-2.2). Implementação de produção → `databricks-engineer`.

## Passo 7 — VALIDATE — DETERMINÍSTICO, 2 fases obrigatórias

Rode o gerador de reconciliação usando o `03_reconcile_spec.json` do Passo 4 (ou monte um spec
equivalente manualmente — ver formato no cabeçalho de `scripts/reconcile_generate.py`):

```bash
python scripts/reconcile_generate.py output/sqlserver-migration/<slug>/03_reconcile_spec.json output/sqlserver-migration/<slug>
```

Emite `reconcile_source.sql` (T-SQL — rodar na origem **ainda em BAU**, antes do CDC catch-up),
`reconcile_target.sql` (Databricks SQL — rodar na Gold) e `reconcile_report.md` (o que comparar,
tolerâncias, matriz de rollback). Gates: nenhuma tabela sem `keys` nem sem `target` — código ≠ 0 se
falhar.

**Regra das 2 fases (obrigatória, `kb/migration/concepts/reconciliation.md` §2):**
1. **Fase 1** — reconcilie o **snapshot histórico** (pós carga inicial) e obtenha **aprovação formal
   ANTES de ligar o CDC**.
2. **Fase 2** — reconcilie **só o delta CDC**, com cutoff date acordado.
Rodar as duas juntas mascara a causa raiz de qualquer mismatch — nunca junte as passadas.

**Tolerâncias:** `FLOAT`/`DOUBLE` → relativa (±0.0001%); `DECIMAL`/`MONEY`/contagens → exata. Os 7 parity
checks (record count, sum/aggregations, null count, distinct count, string checksum via MD5, min/max
bounds, hash row-a-row) vêm de `kb/migration/concepts/reconciliation.md` §1. Validação estatística
avançada (drift, distribuições, KS test) → escalar `data-quality-steward`.

## Passo 8 — CUTOVER

Aplique o runbook de `kb/migration/concepts/cutover-rollback.md`:
1. Escolha a **estratégia de cutover** (Big Bang/Phased/Blue-Green/Canary/A-B Testing/Pilot Group) — §1.
2. **Freeze window** com exit criteria por fase: Pre-Freeze → Delta Catch-up → Reconciliation → Go/No-Go
   Gate → Cutover → Smoke Test (§2). Documente o **LSN** (`sys.fn_cdc_get_max_lsn()`) antes do freeze (§3).
3. **Matriz de rollback numérica** (§6): <0.01% ok; 0.01–1% investigar; **>1% rollback imediato**; falha
   de dashboard crítico ou degradação de performance >50% sem resolução em 1h também disparam rollback.
4. **Consumer switchover** (§8): atualizar connection strings/DNS de BI, apps, ETL downstream.
5. **Smoke test** (§9) pós-cutover.
6. **Hypercare** 1-2 semanas (§11) + **sign-off explícito por owner** (§12) — nunca decommission
   prematuro; SQL Server permanece live até todos os consumidores migrarem.

## Passo Final — AUTO-REVISÃO de sanidade (obrigatório antes de reportar concluído)

NÃO reporte "concluído" se algum falhar:
- [ ] **SPEC foi aprovado** antes de qualquer CONVERT (o gate não foi pulado).
- [ ] **Discovery (5 categorias) precedeu o design** — nenhuma decisão de arquitetura sem dados de Passo 1.
- [ ] **Gerador de DDL rodou e passou nos gates:** `scripts/sqlserver_generate.py` saiu com **código 0**.
- [ ] **Gerador de reconciliação rodou e passou nos gates:** `scripts/reconcile_generate.py` saiu com
  **código 0** (toda tabela com `keys` e `target`).
- [ ] **Sem gerador próprio:** os entregáveis SÃO os arquivos dos dois scripts; nenhum `generate_*.py`
  reescrito nem SQL de reconciliação escrito à mão.
- [ ] **Cursors/Dynamic SQL:** nenhum convertido 1:1; set-based ou marcado ⚠️ na lista de redesign.
- [ ] **Reconciliação em 2 fases:** Fase 1 aprovada antes do CDC; Fase 2 (delta) rodada separadamente.
- [ ] **Cutover:** freeze window com exit criteria, matriz de rollback aplicada, sign-off documentado —
  nunca decommission antes de todos os consumidores migrarem.
- [ ] **PII/ABAC:** nenhuma policy/mask com PII gerada sem passar por `governance-auditor`.
- [ ] **Relatório == código, COM `grep`:** para CADA feature alegada (DDL, CDC ativo, reconciliação
  aprovada, cutover concluído) rode `grep -rn` no diretório de saída; se não achar, **APAGUE a
  alegação**. A tabela de artefatos bate com `find <saída> -type f`.

## Anti-patterns (fortes)

❌ Pular o discovery (5 categorias) antes de propor design. ❌ Gerar DDL/código antes da aprovação do
SPEC — ou no MESMO turno do SPEC. ❌ **Escrever o DDL ou o SQL de reconciliação à mão** — rode
`scripts/sqlserver_generate.py`/`scripts/reconcile_generate.py`. ❌ **Escrever seu próprio gerador**
(`generate_*.py`) — cada run reintroduz bug novo (drift entre DDL e reconciliação); consuma a saída dos
geradores únicos. ❌ Reproduzir `CURSOR`/Dynamic SQL linha-a-linha. ❌ Rodar a reconciliação do snapshot e
do CDC na mesma passada (mascara a causa raiz). ❌ Usar Lakehouse Federation para fact tables multi-TB
(usar extração + Auto Loader/`COPY INTO`). ❌ Misturar ABAC com row filter/mask manual na mesma tabela
(`UC_ABAC_MULTIPLE_ROW_FILTERS`). ❌ Decommission prematuro do SQL Server antes de todos os consumidores
migrarem e sign-off formal. ❌ Migrar sem reconciliação em 2 fases nem runbook de cutover.
