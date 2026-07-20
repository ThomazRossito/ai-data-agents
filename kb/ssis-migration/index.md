---
domain: ssis-migration
updated_at: 2026-06-18
agents: [ssis-to-databricks, databricks-engineer, migration-expert]
---

# Knowledge Base — Migração SSIS → Databricks

> Fonte de verdade operacional do agente **ssis-to-databricks**. Consultar SEMPRE antes de converter
> pacotes. NÃO inventar mapeamentos: toda conversão sai deste conjunto (index + concepts).

## 1. Escopo

Conversão de **SQL Server Integration Services (SSIS)** — pacotes **`.dtsx`** (XML) e projetos
`.ispac`/SSISDB — para **Databricks** (PySpark, Spark SQL, Delta Lake, Lakeflow/DLT, Databricks
Workflows/Jobs, Auto Loader). Diferente da migração de banco relacional (schema/DDL), que pertence ao
`migration-expert`. Aqui o artefato é o **pacote ETL** (orquestração + transformações), não o schema.

## 2. Estrutura de um `.dtsx` (o que parsear)

Namespace `www.microsoft.com/SqlServer/Dts` (prefixo `DTS:`).

| Elemento | Significado |
|---|---|
| `DTS:Executable` (raiz = pacote) | O pacote; `Executable` aninhados = tasks do Control Flow |
| `DTS:Executables` | Coleção de tasks/containers do Control Flow |
| `DTS:PrecedenceConstraint` | Dependências entre tasks (Success/Failure/Completion + expressão) |
| pipeline `component` (dentro do Data Flow Task) | Componentes do Data Flow (Source/Transform/Destination) |
| `DTS:ConnectionManager` | Conexões (OLE DB, Flat File, Excel, ADO.NET, FTP) |
| `DTS:Variable` / parâmetros | Variáveis e parâmetros (podem ter Expression) |
| `DTS:EventHandler` (OnError/OnWarning) | Tratamento de eventos |
| `DTS:LoggingOptions` / Checkpoints | Log e checkpoint/restart |

## 3. Fluxo de conversão (6 fases)

```
PARSE(.dtsx) → INVENTORY → CLASSIFY → MAP → GENERATE (PySpark/DLT/Jobs) → RECONCILE
```

## 4. Mapeamento de alto nível (detalhe nos concepts)

- **Control Flow** (orquestração) → **Lakeflow Jobs** (task graph + dependências). Ver `concepts/control-flow-map.md`.
- **Data Flow** (transformações linha-a-linha) → **PySpark/Spark SQL set-based** OU **Lakeflow Spark Declarative Pipelines (SDP)** — escolher UM modelo coerente (ver §5). Ver `concepts/data-flow-map.md`.
> Terminologia 2026: DLT → **Lakeflow SDP**; Workflows → **Lakeflow Jobs**; Asset Bundles → **Declarative Automation Bundles**; ingestão SQL Server → **Lakeflow Connect** (CDC/Change Tracking). Detalhe em `concepts/execution-model-and-packaging.md`.
- **Expression Language + variáveis/parâmetros** → funções Spark + widgets/job params. Ver `concepts/expressions-and-patterns.md`.
- **Connection Managers** → conexões/secret scopes/JDBC/Auto Loader.

## 5. Modelo de execução — escolher UM padrão coerente (não misturar)

> **REGRA DE OURO:** `@dp.*` (SDP) roda em runtime de **pipeline**, não como notebook task. NUNCA
> misturar decorators SDP com orquestração por notebook-task. Detalhe: `concepts/execution-model-and-packaging.md`.

| Padrão | Quando | Como |
|---|---|---|
| **A — SDP declarativo** (recomendado p/ medalhão) | Bronze→Silver→Gold em camadas | Tudo em **Lakeflow SDP** (`@dp.table`, expectations, **create_auto_cdc_flow/APPLY CHANGES** p/ SCD) como **1 pipeline**; passos imperativos (auditoria) como task de **Lakeflow Job** dependente |
| **B — Imperativo** | Muita lógica procedural, loops, chamadas externas | Tudo PySpark em **Lakeflow Jobs** (MERGE/SCD na mão), **zero @dp**; expectations viram checks pós-carga/CHECK constraints |

- Arquivos contínuos → **Auto Loader (cloudFiles)** (não For Each). SQL Server → **Lakeflow Connect** (CDC/Change Tracking; JDBC só fallback).
- **Empacotar como Declarative Automation Bundle (DAB)** — `databricks.yml` + `resources/*.yml` (jobs + pipelines) + targets. Nunca Jobs JSON solto. Usar `skills/databricks/databricks-bundles/SKILL.md`.

## 6. Anti-padrões SSIS→Databricks (invioláveis)

- **S01 — Portar OLE DB Command (row-by-row):** é linha-a-linha; converter para **operação set-based** (MERGE/UPDATE em batch). Nunca reproduzir loop por linha.
- **S02 — Reproduzir Sort/blocking transforms:** Sort do SSIS vira shuffle caro; usar `orderBy` só quando necessário e preferir `MERGE`/window.
- **S03 — Traduzir Script Task/Component (C#/VB) literalmente:** reescrever a lógica em Python/UDF; sinalizar como esforço manual (não auto-converter cegamente).
- **S04 — Ignorar idempotência:** jobs Databricks devem ser re-executáveis (usar MERGE/overwrite por partição), diferente do fluxo transacional do SSIS.
- **S05 — Descartar error outputs/redirect rows:** mapear para **quarentena** (tabela de rejeitados) ou **DLT expectations**, não perder.
- **S06 — Manter For Each Loop de arquivos:** preferir Auto Loader; loop só quando semântica exigir.
- **S07 — Recriar FKs/constraints do destino:** Delta não impõe FK (ver KB migration).
- **S08 — Converter sem reconciliação:** toda conversão precisa de contagem/soma origem×destino.

## 7. Regras do agente (resumo)

- **Grounding:** todo mapeamento vem desta KB. Componente SSIS sem equivalente claro → marcar **⚠️ revisão manual**, nunca inventar.
- **Buffer-safe:** `.dtsx` pode ser grande — parsear via Bash/Python, escrever índice em `_work/`, nunca despejar XML inteiro no contexto.
- **Escopo:** converte pacotes; **schema/DDL** das tabelas → `migration-expert`; **implementação de pipeline pesada** → `databricks-engineer`; **PII** → `governance-auditor`.
- **Idioma:** seguir o usuário (PT-BR/EN); nomes de componentes/produtos em inglês.

Concepts: `control-flow-map.md` · `data-flow-map.md` · `expressions-and-patterns.md` · `execution-model-and-packaging.md`.
