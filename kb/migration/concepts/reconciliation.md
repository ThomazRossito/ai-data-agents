# Reconciliação Origem×Destino — Conceitos

> Conceitos e regras normativas para validação origem×destino em migração de banco relacional
> (SQL Server/PostgreSQL) para Databricks/Fabric. Este arquivo **aprofunda e formaliza** o
> `Checklist de Reconciliação` (7 bullets) já existente em `kb/migration/index.md` — não duplica:
> aqui estão os 7 checks com SQL canônico, a regra das 2 fases, tolerâncias determinísticas,
> timing de captura de baseline, a matriz de rollback numérica e o tooling nativo vs. proibido.
> Para mapeamento completo de tipos e DoD por fase, ver `kb/migration/index.md` e
> `kb/checklists/migration-dod.md`.

**Domínio:** Migração cross-platform, reconciliação origem×destino, qualidade de dados pós-migração

**Agente dono:** `data-quality-steward` (Constituição S6 — qualidade nunca é delegada a agentes de
engenharia). Consultado também por `migration-expert` na fase RECONCILE do fluxo de 5 fases
(`ASSESS → ANALYZE → DESIGN → TRANSPILE → RECONCILE`, ver `kb/migration/index.md`).

> **Nota de manutenção:** o frontmatter de `data_agents/agents/registry/data-quality-steward.md`
> ainda lista `kb_domains: [data-quality, databricks, fabric, industry]` — **sem** `migration`.
> Até esse gap ser corrigido no registry, o agente deve ler este arquivo explicitamente sempre
> que a tarefa envolver reconciliação de migração.

---

## 1. Os 7 Tipos de Parity Check

Fonte: curso Databricks — *SQL Server Migration*, `04 - Activate/4.1 Lecture - Testing and Data
Validation.md`, §2 "Data Parity Check Types".

| # | Check | O que valida | Quando usar |
|---|-------|---------------|-------------|
| 1 | **Record Counts** | Total de linhas por tabela bate entre origem e destino | Toda tabela — primeira validação, sempre |
| 2 | **Sum/Aggregations** | Totais de colunas numéricas batem | Colunas financeiras e de quantidade |
| 3 | **Null Counts** | Distribuição de `NULL` não muda | Toda coluna, especialmente após conversão de tipo |
| 4 | **Distinct Counts** | Cardinalidade preservada | Colunas-chave, dimensões |
| 5 | **String Checksums** | Integridade de dado textual | Colunas de texto — **crítico** após conversão de `UNIQUEIDENTIFIER`, `DATETIMEOFFSET` e `GEOGRAPHY`/`GEOMETRY` |
| 6 | **Min/Max Bounds** | Faixa de valores preservada | Datas, timestamps, faixas numéricas |
| 7 | **Hash Row-a-Row** | Integridade linha a linha | Tabelas críticas — validação completa ou por amostragem, via `EXCEPT` |

SQL canônico (checks 1, 2, 3, 4, 6 — sintaxe idêntica nos dois dialetos, ANSI aggregate functions):

```sql
SELECT COUNT(*)                          AS row_count      FROM <table>;              -- (1)
SELECT SUM(<col>), AVG(<col>)            AS sum_col        FROM <table>;              -- (2)
SELECT COUNT(*) - COUNT(<col>)           AS null_count     FROM <table>;              -- (3)
SELECT COUNT(DISTINCT <col>)             AS distinct_count FROM <table>;              -- (4)
SELECT MIN(<col>), MAX(<col>)            AS bounds         FROM <table>;              -- (6)
```

**Check 7 — Hash Row-a-Row.** Padrão citado explicitamente no curso (4.1 §4, alerta *"Driver-Only
Execution"*): `md5(concat_ws('|', *cols))`. MD5 é um algoritmo padronizado — produz o mesmo digest
hexadecimal nos dois dialetos para o mesmo input, ao contrário de funções de hash proprietárias.

```sql
-- Databricks / Spark SQL (destino)
SELECT <key_cols>,
       md5(concat_ws('|', cast(<col1> AS string), cast(<col2> AS string), ...)) AS row_hash
FROM <target_table>;

-- SQL Server (origem) — mesmo algoritmo MD5, formatado como hex de 32 caracteres
SELECT <key_cols>,
       CONVERT(VARCHAR(32), HASHBYTES('MD5',
         CONCAT_WS('|', CAST(<col1> AS VARCHAR(MAX)), CAST(<col2> AS VARCHAR(MAX)), ...)), 2) AS row_hash
FROM <source_table>;
```

Diff em escala via `EXCEPT` (citado no curso, 4.1 §4, junto com o hash, como alternativa
distribuída a bibliotecas que colam no driver — ver §6.2):

```sql
WITH src AS (SELECT <key_cols>, <row_hash_expr> AS row_hash FROM <source_snapshot>),
     tgt AS (SELECT <key_cols>, <row_hash_expr> AS row_hash FROM <target_table>)
SELECT * FROM src EXCEPT SELECT * FROM tgt   -- ausente ou divergente no destino
UNION ALL
SELECT * FROM tgt EXCEPT SELECT * FROM src;  -- ausente ou divergente na origem
```

**Check 5 — String Checksums — nota de correção obrigatória.** Funções nativas de checksum
(`CHECKSUM_AGG(CHECKSUM(col))` no SQL Server, `hash()`/`crc32()` no Spark — Murmur3/CRC) usam
algoritmos **proprietários e não comparáveis entre plataformas**: valores diferentes não implicam
necessariamente dado divergente, e valores "iguais" por coincidência não garantem nada. Para uma
comparação real de integridade textual entre origem e destino, aplicar a técnica de hash MD5 do
check 7 restrita à(s) coluna(s) de texto sob suspeita. Isso é especialmente crítico porque tanto
Databricks quanto Fabric convertem `UNIQUEIDENTIFIER`, `DATETIMEOFFSET` e `GEOGRAPHY`/`GEOMETRY`
para `STRING`/WKT (ver mapeamento completo em `kb/migration/index.md`) — divergências de
formatação (casas decimais, ordem de coordenadas, caixa alta/baixa em GUID) geram falso mismatch
se comparadas ingenuamente.

---

## 2. Regra das 2 Fases (Obrigatória)

Fonte: curso 4.1 §9 (Lakebridge Reconciler), callout *"Run reconciliation in two distinct steps"*;
reforçado operacionalmente em 4.3 §3–§5 (Cutover Timeline / Freeze Window Components).

**Fase 1 — Reconciliar o snapshot histórico.** Após a carga inicial (bulk load) estar completa no
destino, executar os 7 checks (§1) contra a fonte e obter **aprovação formal antes de ligar CDC**.

**Fase 2 — Reconciliar apenas o delta CDC.** Com CDC ativo, acordar um cutoff date e reconciliar
somente as mudanças capturadas desde a Fase 1.

**Por que não rodar as duas juntas:** rodar a reconciliação histórica e a do CDC em uma única
passada torna muito difícil isolar se um mismatch veio da carga inicial ou do stream de CDC.
Tratar como **2 gates sequenciais** isola a superfície de falha (citação literal do curso).

Ancoragem operacional no runbook de cutover (4.3, tabela *"Freeze Window Components"*): as duas
fases aparecem como etapas distintas da janela de freeze, cada uma com exit criteria própria —

| Fase (Freeze Window) | Exit Criteria |
|---|---|
| **Delta Catch-up** | Contagens batem, sem mudanças pendentes |
| **Reconciliation** | Zero discrepâncias de dados |

O *Cutover Timeline* (4.3 §3, gantt) confirma a sequência: `Delta catch-up sync` → `Final
reconciliation` → `Rollback decision gate`, nessa ordem, nunca em paralelo.

---

## 3. Tolerâncias Determinísticas

Duas fontes de tolerância distintas — não confundir uma com a outra.

### 3.1 Tolerância relativa (comparação manual de agregados — checks 2 e 6)

Fonte: curso 4.1 §3, callout *"Floating Point Tolerance"*.

- `FLOAT`/`DOUBLE`: usar **tolerância relativa** (ex.: 0.0001%) em vez de igualdade exata —
  diferenças de precisão IEEE 754 entre SQL Server e Spark causam divergências mínimas e
  matematicamente insignificantes.
- `DECIMAL`/`NUMERIC`/`MONEY`/`SMALLMONEY`: comparar com **igualdade exata (`=`)**, nunca com
  tolerância — são tipos de ponto fixo em base 10, não sofrem o erro de arredondamento binário
  que afeta `FLOAT`/`DOUBLE` (reforça anti-padrão M01 de `kb/migration/index.md`).
- Mapeamento obrigatório: SQL Server `FLOAT` (padrão = 64-bit, equivalente a `FLOAT(53)`) →
  Spark/Databricks `DOUBLE`; SQL Server `REAL` (32-bit) → Spark `FLOAT`. Mapear na direção errada
  amplifica a divergência de precisão. Tabela completa em `kb/migration/index.md`.

### 3.2 Tolerância absoluta por coluna (Lakebridge `thresholds` — checks `row`/`data`)

Fonte: curso 4.1 §9, exemplo de configuração JSON e de `ColumnThresholds`. Diferente da
tolerância relativa acima: são **limites absolutos** (`lower_bound`/`upper_bound`), na mesma
unidade da coluna, aplicados linha a linha durante o join origem×destino:

```json
"thresholds": [
  {"column_name": "SalesAmount", "type": "float", "lower_bound": "-0.001", "upper_bound": "0.001"}
]
```

Exemplo do curso para a coluna `Freight`: `lower_bound: "-0.0001"`, `upper_bound: "0.0001"`. Cada
coluna `float` reconciliada via Lakebridge **deve** ter threshold explícito — nunca deixar
implícito (equivale a igualdade exata, que falha por IEEE 754).

---

## 4. Baseline no Momento do Export

Fonte: curso 4.1, callout *"Capture baselines at export time, not later"* (posicionado entre §2 e
§3) e callout gêmeo *"Extract test logic at export time too"* (§7).

**Regra:** baselines de validação — row counts, null counts, distinct counts, hashes, agregados —
devem ser capturados **no mesmo momento** do export de dados da fonte. Se a fonte volta a BAU
(business as usual) antes da captura, escritas subsequentes deslocam os valores e a reconciliação
se torna sem sentido.

**Extensão a agregados aprovados pelo negócio:** quando o time de negócio já validou agregados via
Power BI/Tableau, tirar um **snapshot datado** desses relatórios na mesma janela de export, para
que os números já aprovados sejam comparáveis contra o dataset migrado.

**Extensão à lógica de qualidade da fonte (§7 do curso):** a mesma regra de timing vale para
`CHECK` constraints, stored procedures, triggers e SQL Agent jobs — capturar definições de
`sys.check_constraints`, `sys.triggers`, `sys.sql_modules` e `msdb.dbo.sysjobs` na mesma janela do
export, pois também mudam quando a fonte volta a operar.

**Persistência (regra desta KB, sobre o mecanismo de export do curso):** o curso demonstra
exportar via BCP/ADF para CSV em ADLS e carregar como `TEMP VIEW` (4.1 §3). Esse baseline deve ser
**persistido em Delta**, não mantido apenas como view temporária — precisa sobreviver para
comparação na Fase 2 (§2) e para auditoria:

```sql
CREATE TABLE IF NOT EXISTS <metadata_catalog>.reconcile.baseline_<table>
USING DELTA AS
SELECT * FROM csv.`<export_path>`;
```

Capturar depois da janela de export invalida toda a cadeia de reconciliação — não há como
recuperar retroativamente.

---

## 5. Matriz de Rollback Numérica

Fonte: curso `04 - Activate/4.3 Lecture - Cutover Execution.md`, §8 "Rollback Decision Matrix".

| Condição | Severidade | Ação | Rollback? |
|---|---|---|---|
| Discrepância de dados < 0.01% | Baixa | Investigar, continuar monitorando | Não |
| Discrepância de dados 0.01–1% | Média | Pausar cutover, investigar causa raiz | Talvez |
| Discrepância de dados > 1% | Alta | Rollback imediato | Sim |
| Falha crítica de dashboard | Alta | Rollback imediato | Sim |
| Degradação de performance > 50% | Alta | Rollback se não resolvido em 1 hora | Sim |
| Problema não-crítico em relatório | Baixa | Documentar, corrigir in-place | Não |
| Falha de job (não-crítico) | Média | Retry, escalar se persistente | Não |
| Múltiplas falhas de job | Alta | Avaliar escopo, considerar rollback | Talvez |

Esta matriz é o critério de decisão Go/No-Go a aplicar sobre o resultado dos 7 checks (§1) — a
discrepância percentual referida é a mesma medida pelos checks de contagem/agregação (checks 1–2).

---

## 6. Ferramentas de Reconciliação

### 6.1 Lakebridge Reconciler (nativo — preferencial no Databricks)

Fonte: curso 4.1 §9; reforçado em 4.3 §6 ("Run Lakebridge Final Reconciliation").

- **O que é:** ferramenta Databricks Labs que automatiza reconciliação de schema e dados entre
  sistemas de origem e Databricks.
- **Fontes suportadas (documentadas no curso):** Snowflake, Oracle, SQL Server, Synapse.
  **PostgreSQL não está na lista** — para origem PostgreSQL, usar `reconcile_generate.py` (§7) ou
  SQL agregado manual (§6.2).
- **Compute:** exige **Classic Compute** — serverless não é suportado.
- **Plataforma:** exclusivo do Databricks. Para destino **Fabric**, aplicar os mesmos 7 checks
  (§1) via `fabric_sql_readonly`/`fabric_sql_all` (T-SQL) — sem equivalente nativo documentado no
  curso.

**Report types** (curso 4.1 §9, "Reconciliation Report Types"):

| Report Type | Descrição |
|---|---|
| `schema` | Compara nomes de coluna e tipos via transpilação `sqlglot` |
| `row` | Compara contagem de linhas, identifica linhas ausentes em origem/destino |
| `data` | Comparação completa de valores, detecção de mismatch |
| `all` | Roda `schema` + `row` + `data` |
| `aggregate` | Compara valores agregados (`MIN`, `MAX`, `COUNT`, `SUM`, `AVG`, `MEAN`, `MODE`, `STDDEV`, `VARIANCE`, `MEDIAN`) |

`aggregates-reconcile` é a abordagem **preferencial para fact tables grandes** — evita o custo de
um diff linha a linha completo.

**Configuração (JSON, condensado do exemplo do curso):**

```json
{
  "data_source": "mssql",
  "database_config": {
    "source_schema": "dbo",
    "target_catalog": "<catalog>",
    "target_schema": "<schema_destino>"
  },
  "metadata_config": { "catalog": "remorph", "schema": "reconcile", "volume": "reconcile_volume" },
  "report_type": "all",
  "secret_scope": "<secret_scope>",
  "version": 1,
  "tables": [
    {
      "source_name": "FactInternetSales",
      "target_name": "factinternetsales",
      "join_columns": ["SalesOrderNumber", "SalesOrderLineNumber"],
      "thresholds": [
        {"column_name": "SalesAmount", "type": "float", "lower_bound": "-0.001", "upper_bound": "0.001"}
      ],
      "transformations": [
        {"column_name": "OrderDate", "source": "CONVERT(VARCHAR, OrderDate, 121)",
         "target": "DATE_FORMAT(OrderDate, 'yyyy-MM-dd HH:mm:ss')"}
      ]
    }
  ]
}
```

`transformations` normaliza diferenças de formato/precisão antes da comparação (`source` = SQL
válido no dialeto de origem, `target` = SQL válido no dialeto de destino) — usar para datas,
`NULL` sentinela (`COALESCE(..., '_null_')`), etc.

**Fluxo CLI (curso 4.1 §9, passo a passo):**

```bash
databricks labs install lakebridge
databricks secrets create-scope <secret_scope>
databricks secrets put-secret <secret_scope> user       --string-value "<user>"
databricks secrets put-secret <secret_scope> password   --string-value "<password>"
databricks secrets put-secret <secret_scope> host       --string-value "<host>"
databricks secrets put-secret <secret_scope> port       --string-value "1433"
databricks secrets put-secret <secret_scope> database   --string-value "<database>"

databricks labs lakebridge configure-reconcile          # interativo (opcional, alternativa ao JSON acima)
databricks workspace mkdirs /Users/<email>/.lakebridge
databricks workspace import /Users/<email>/.lakebridge/<config>.json --file <local_config>.json --format AUTO

databricks labs lakebridge reconcile                    # schema / row / data
databricks labs lakebridge aggregates-reconcile         # agregados — preferencial p/ fact tables grandes
```

API Python/notebook equivalente usa `TableRecon`, `Table`, `ColumnThresholds`, `Aggregate`,
`ReconcileConfig`, `DatabaseConfig`, `ReconcileMetadataConfig` e os serviços
`TriggerReconService.trigger_recon(...)` (row-level) /
`TriggerReconAggregateService.trigger_recon_aggregates(...)` (agregado). Ambos levantam
`ReconciliationException` com `.reconcile_output.recon_id` em caso de falha; sucesso retorna
`result.recon_id`.

**Output:** resultados persistidos em tabelas Delta (sob `metadata_config`), cada execução recebe
um `recon_id` único para rastreio, e `configure-reconcile` provisiona automaticamente 2 dashboards
AI/BI:

| Dashboard | Componente | Conteúdo |
|---|---|---|
| Reconciliation Metrics | Summary Table | `status`, `missing_in_source`/`target`, `absolute_mismatch`, `threshold_mismatch`, `mismatch_columns`, `schema_comparison` |
| Reconciliation Metrics | Schema Details | colunas/tipos origem vs. Databricks + flag `is_valid` |
| Reconciliation Metrics | Drill Down | amostra de registros com mismatch/ausência |
| Reconciliation Metrics | Daily Validation Report | total de execuções falhas, tabelas destino falhas/sucesso |
| Reconciliation Metrics | Trend Charts | mismatches, threshold mismatches, ausências ao longo do tempo |
| Aggregate Reconciliation Metrics | Summary Table | resultado das funções de agregação (`SUM`, `COUNT`, ...), `group_by_columns`, `status` |
| Aggregate Reconciliation Metrics | Drill Down | `source_value` vs. `target_value` com status de match |
| Aggregate Reconciliation Metrics | Trend Charts | mismatches de agregados e ausências ao longo do tempo |

Filtros comuns: `recon_id`, `report_type`, `source_type`, tabela origem/destino, `executed_by`,
período, `category`, `aggregate_type`.

### 6.2 Validação em Escala sem Lakebridge

Fonte: curso 4.1 §4, alerta *"Driver-Only Execution: Chispa and assertDataFrameEqual"*. Para
validação de migração em escala de produção, usar abordagens **distribuídas**:

- Comparação de agregados SQL (`COUNT`, `SUM`, `MIN`, `MAX`) — checks 1, 2, 6 (§1)
- `EXCEPT` para detecção de diff linha a linha — check 7 (§1)
- Comparação baseada em hash (`md5(concat_ws('|', *))`) — check 7 (§1)
- Lakebridge Reconciler — reconciliação automatizada de schema/row/data (§6.1)
- Lakeflow Pipelines Expectations — enforcement de qualidade **em runtime**, contínuo (não
  substitui a reconciliação pontual pós-migração, é complementar)

### 6.3 Proibido em Produção

Fonte: curso 4.1 §4 (alertas *"Driver-Only Execution"* e *"Great Expectations Requirements"*).

| Ferramenta | Motivo da proibição | Uso permitido |
|---|---|---|
| Chispa (`assert_df_equality`) | Faz `.collect()` — traz ambos os DataFrames para o driver | Testes unitários com amostra pequena apenas |
| `pyspark.testing.assertDataFrameEqual` | Mesmo motivo — coleta os dois DataFrames no driver | Testes unitários PySpark 3.5+ apenas |
| Great Expectations | Exige Classic Compute; integração Spark também coleta no driver para validação | Validação de amostra — nunca full-table scan |

Todas as três **OOMam em tabelas grandes**. Nenhuma delas é um substituto válido para os checks do
§1 em produção — servem apenas para testes unitários de transformação com dados de amostra.

### 6.4 Delta CHECK Constraints — o que é de fato enforced

Fonte: curso 4.1 §5 ("Delta Table Constraints").

| Constraint | SQL Server | Delta | Enforcement |
|---|---|---|---|
| `NOT NULL` | enforced | enforced | Ambos |
| `PRIMARY KEY` | enforced | informativo | Só SQL Server |
| `FOREIGN KEY` | enforced | informativo | Só SQL Server |
| `UNIQUE` | enforced | informativo (preview) | Só SQL Server |
| `CHECK (expr)` | enforced | enforced | Ambos |
| `DEFAULT` | aplicado no insert | aplicado no insert | Ambos |

`PK`/`FK`/`UNIQUE` no Delta **não bloqueiam** escrita de duplicatas ou órfãos — são apenas
metadados/hints para o otimizador. A reconciliação (§1) é a **única garantia real** de unicidade e
integridade referencial pós-migração, não a constraint.

Nota operacional: `ALTER TABLE ... ADD CONSTRAINT ... CHECK` valida contra dados **já existentes**
ao ser adicionado — falha se houver violação. Corrigir dados antes, ou usar `DROP CONSTRAINT`
durante troubleshooting de migração.

---

## 7. Gerador Determinístico — `scripts/reconcile_generate.py`

Script em desenvolvimento (ainda não existe em `scripts/` no momento da escrita desta KB). Deve
seguir o mesmo padrão de `scripts/ssas_generate.py`: **determinístico** e **agnóstico de cliente**
(dirigido inteiramente pelos parâmetros de entrada — nada hardcoded a um negócio específico),
finalizando com **gates de sanidade** que saem com código de saída diferente de zero se qualquer
gate falhar (nunca "conclui" emitindo SQL quebrado).

**Contrato esperado:**

- **Entrada:** pares `(tabela_origem, tabela_destino)` + colunas-chave (`join_columns`) + lista
  opcional de colunas a comparar + thresholds opcionais por coluna (tolerância float/decimal, ver
  §3).
- **Saída:** SQL determinístico dos 7 checks (§1), pronto para rodar nos dois dialetos (SQL
  Server/PostgreSQL na origem; Spark SQL ou Fabric T-SQL no destino), mais um relatório
  consolidado de status (pass/fail por check e por tabela).
- **Gates de sanidade esperados:** nenhuma coluna referenciada que não exista no schema de
  origem/destino; toda chave de join coberta por PK/índice documentado; toda comparação de coluna
  `FLOAT`/`DOUBLE` tem threshold explícito (nunca `=` implícito — ver §3.1).

**Quando usar vs. Lakebridge Reconciler:**

| Cenário | Ferramenta |
|---|---|
| Destino Databricks + Classic Compute disponível | Lakebridge Reconciler (§6.1) — nativo, dashboards automáticos |
| Destino Fabric, origem PostgreSQL, ou sem Classic Compute provisionado | `reconcile_generate.py` — SQL determinístico, roda em qualquer compute/dialeto |
| Validação ad-hoc rápida de um par de tabelas durante desenvolvimento | `reconcile_generate.py` |
| Reconciliação de produção governada, com trilha de auditoria em dashboard | Lakebridge Reconciler |

**Integração:** invocado pelo `data-quality-steward` na fase RECONCILE (`kb/migration/index.md`) e
pelo slash command `/migrate`. O `migration-expert` também consome sua saída durante a mesma fase
do fluxo de 5 fases.

---

## Anti-Padrões Locais desta KB

| Código | Anti-Padrão | Correção |
|---|---|---|
| RC01 | Rodar reconciliação do snapshot histórico e do delta CDC na mesma passada | Rodar em 2 fases sequenciais, aprovar a Fase 1 antes de ligar CDC (§2) |
| RC02 | Usar Chispa / `assertDataFrameEqual` / Great Expectations para validar tabelas de produção em escala | Reservar para testes unitários com amostra pequena; usar SQL agregado + `EXCEPT` + hash ou Lakebridge em produção (§6.2, §6.3) |
| RC03 | Capturar baseline de reconciliação depois que a fonte já voltou a BAU | Capturar no mesmo momento do export, persistir em Delta (§4) |
| RC04 | Comparar `FLOAT`/`DOUBLE` com igualdade exata (`=`) | Usar tolerância relativa (ex. 0.0001%) ou `thresholds` absolutos do Lakebridge (§3) |
| RC05 | Tratar `PK`/`FK`/`UNIQUE` do Delta como enforcement real de integridade | São apenas informativos (exceto `NOT NULL`/`CHECK`) — validar via reconciliação, não via constraint (§6.4) |
| RC06 | Usar `CHECKSUM_AGG`/`hash()`/`crc32()` nativos para comparar integridade textual entre plataformas | Algoritmos proprietários não comparáveis — usar MD5 (mesmo digest nos dois dialetos) (§1, check 5) |
| RC07 | Comparar desvio-padrão/variância entre origem e destino sem casar o **estimador** (populacional vs amostral) | Casar explicitamente: `STDDEV_POP`↔`stddev_pop`, `STDDEV_SAMP`↔`stddev`/`stddev_samp`, `VAR_POP`↔`var_pop`, `VAR_SAMP`↔`variance`/`var_samp`. No Spark/Databricks `STDDEV()`=`STDDEV_SAMP` e `VARIANCE()`=`VAR_SAMP`; no Teradata `STDDEV_POP`/`STDDEV_SAMP` são explícitos — comparar `STDDEV_POP` do Teradata com `STDDEV()` do Databricks **diverge** matematicamente (lição do curso Teradata, lecture 4.1) |

---

## Checklist de Aplicação

- [ ] Baseline (row/null/distinct counts, hashes, agregados) capturado no momento do export, antes da fonte voltar a BAU
- [ ] Agregados já aprovados pelo negócio (Power BI/Tableau) com snapshot datado da mesma janela
- [ ] Os 7 checks (§1) executados para cada tabela em escopo
- [ ] Fase 1 (snapshot histórico) aprovada formalmente antes de ligar CDC
- [ ] Fase 2 (delta CDC) reconciliada separadamente, com cutoff date acordado
- [ ] Tolerância relativa aplicada em `FLOAT`/`DOUBLE`; igualdade exata em `DECIMAL`/`MONEY`
- [ ] Matriz de rollback (§5) usada na decisão Go/No-Go do cutover
- [ ] Lakebridge Reconciler configurado (Databricks + Classic Compute) ou T-SQL manual (Fabric) ou `reconcile_generate.py` (PostgreSQL/ad-hoc)
- [ ] Nenhuma validação de produção usando Chispa/`assertDataFrameEqual`/Great Expectations em tabela grande
- [ ] Estimador de `STDDEV`/`VARIANCE` casado entre origem e destino (populacional vs amostral, RC07)
- [ ] Anti-padrões RC01–RC07 verificados

---

## Referências

- Curso Databricks — *SQL Server Migration* — `04 - Activate/4.1 Lecture - Testing and Data Validation.md` (§2 Data Parity Check Types; §3 Extracting Validation Baselines; §4 Testing Frameworks; §5 Delta Table Constraints; §7 Extracting Test Logic; §9 Lakebridge Reconciler)
- Curso Databricks — *SQL Server Migration* — `04 - Activate/4.3 Lecture - Cutover Execution.md` (§3 Cutover Timeline; §4 Freeze Window Planning; §5 Executing the Freeze; §6 Delta Catch-up Synchronization; §8 Rollback Planning)
- Lakebridge Reconcile — documentação oficial (citada no curso): `https://databrickslabs.github.io/lakebridge/docs/reconcile/`
- `kb/migration/index.md` — mapeamento de tipos completo (SQL Server/PostgreSQL → Databricks/Fabric) e checklist macro de reconciliação (não duplicado aqui)
- `kb/checklists/migration-dod.md` — Definition of Done por fase de migração
- `scripts/ssas_generate.py` — padrão de gerador determinístico com gates (referência de estilo para `reconcile_generate.py`, §7)
- `scripts/reconcile_generate.py` — gerador determinístico desta reconciliação (em desenvolvimento, referenciado na §7)
