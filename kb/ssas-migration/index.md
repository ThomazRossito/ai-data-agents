---
domain: ssas-migration
updated_at: 2026-07-26
agents: [ssas-to-databricks]
---

# Knowledge Base — Migração SSAS (modelo tabular) → Databricks

> Fonte de verdade operacional do agente **ssas-to-databricks**. Consultar SEMPRE antes de migrar um
> modelo tabular. NÃO inventar mapeamentos: toda conversão sai deste conjunto (index + concepts).

## 1. Escopo

Migração de **modelos tabulares SSAS** — SQL Server Analysis Services, Azure Analysis Services, Power BI
datasets — cujo artefato é o **`.bim`/TMSL** (JSON) e/ou **`.vpax`** (VertiPaq Analyzer) — para
**Databricks**. Diferente da migração de banco relacional (schema/DDL), que pertence ao `migration-expert`,
e da implementação pesada de pipeline, que pertence ao `databricks-engineer`. Aqui o artefato é o **modelo
semântico** (tabelas + relacionamentos + medidas DAX + roles + BI), não o schema físico.

> **Fato central:** o SSAS tabular é um **motor semântico** — tabelas físicas + relacionamentos + medidas
> DAX + roles de RLS + conectividade BI **fundidos**. **NÃO existe mapeamento 1:1 para SQL.** Migrar =
> **desmontar** o modelo em 3 camadas e mapear cada uma para o construto Databricks correto.

## 2. Estrutura de um `.bim`/TMSL (o que parsear)

O `.bim` é **JSON (TMSL, compatibilityLevel 1200+)**. O objeto raiz tem `model` com:

| Elemento | Significado |
|---|---|
| `model.dataSources[]` | Conexões de origem (protocol, server, database, credential, timeout) |
| `model.tables[]` | Tabelas (dimensões/fatos); cada uma com `columns`, `measures`, `hierarchies`, `partitions` |
| `table.columns[]` | Colunas: `name`, `dataType`, `isHidden`, `sourceColumn`, `sortByColumn` |
| `table.measures[]` | **Medidas DAX**: `name`, `expression` (DAX), `formatString`, `displayFolder`, `kpi` |
| `table.partitions[]` | Partições: `source.type` + `expression` (M / `Value.NativeQuery` SQL) |
| `model.relationships[]` | `fromTable.fromColumn` → `toTable.toColumn`, `isActive`, `crossFilteringBehavior` |
| `model.roles[]` | Roles de RLS: `members` + `tablePermissions[]` (`table`, `filter` DAX, `metadataPermission`) |
| `model.perspectives[]` | Perspectives (subsets de tabelas por persona) — **sem equivalente nativo** |
| `model.cultures[]` / `translations` | Traduções / metadata linguística — **sem equivalente nativo** |
| KPIs (em `measure.kpi`) | status/trend/target — **sem equivalente nativo direto** |

> O **`.vpax`** é um **zip** (VertiPaq Analyzer): contém stats de cardinalidade, tamanho por coluna e uma
> cópia do modelo (DaxVpaView). Útil para dimensionar volume e priorizar. Parsear como zip, nunca `Read` direto.

## 3. Fluxo de conversão (6 fases)

```
PARSE(.bim/.vpax) → INVENTORY → CLASSIFY → MAP (3 camadas) → [GATE: SPEC + aprovação] → GENERATE → RECONCILE
```

> **Gate obrigatório:** entre MAP e GENERATE o agente entrega um **documento de proposta (SPEC)** e
> **PARA para aprovação humana**. Nenhum código é gerado antes do aceite.

## 4. Mapeamento de alto nível — 3 camadas (detalhe nos concepts)

| Camada SSAS | Alvo Databricks | Concept |
|---|---|---|
| **Físico** (tabelas + partições + relacionamentos) | **Delta / Unity Catalog** em Medallion (Bronze→Silver→Gold), **star schema** na Gold | `concepts/tabular-model-map.md` |
| **Semântico** (medidas + dimensões + joins) | **Databricks Metric Views** (measures/dimensions/joins) | `concepts/tabular-model-map.md` + `concepts/dax-mapping.md` |
| **Medidas DAX** | SQL de Metric View (simples) **ou** documentar reescrita (complexas ⚠️) | `concepts/dax-mapping.md` |
| **Segurança** (roles/RLS) | **Unity Catalog row filters / column masks** (ou dynamic views) | `concepts/rls-and-security.md` |
| **Consumo** (relatórios/BI) | **AI/BI Dashboards** + **Genie Spaces** | `concepts/tabular-model-map.md` |

> Trabalho pesado de pipeline/ingestão física → escalar **databricks-engineer**; migração de schema/DDL de
> origem → escalar **migration-expert**; PII → **governance-auditor**; DQ estatística → **data-quality-steward**.

## 5. Metric Views — a camada semântica (Databricks, 2025)

**Metric Views** são o construto de camada semântica do Databricks: definem `source`, `dimensions`,
`measures` e joins em YAML, governados por Unity Catalog e consultáveis por SQL/AI/BI/Genie. São a
substituição direta da camada semântica do SSAS. Medida SSAS simples → `measure` na Metric View com
expressão SQL de agregação. Star schema atômico na Gold; Metric View por cima. Detalhe em `concepts/dax-mapping.md`.

## 6. Anti-padrões e bloqueados (invioláveis)

- **A01 — Tratar o modelo como 1:1 SQL:** é motor semântico; **desmontar em 3 camadas**, nunca um único banco.
- **A02 — Converter DAX complexo às cegas:** time-intelligence (SAMEPERIODLASTYEAR/DATEADD/TOTALYTD),
  `CALCULATE` aninhado, calculated columns com row context → **⚠️ revisão manual** + reescrita.
- **A03 — Fingir `CREATE MEASURE` em SQL:** não existe. Medida vira `measure` de Metric View (SQL) ou é documentada.
- **A04 — Ignorar perspectives/translations/KPIs/calculation groups:** sem equivalente nativo → ⚠️ redesenho.
- **A05 — RLS complexo direto:** bidirecional/multi-tabela/contextual → ⚠️; simples → UC row filter/mask.
- **A06 — `Read` no `.bim`/`.vpax` inteiro:** buffer-safe (parsear via Python, índice em `_work/`).
- **A07 — Gerar código sem aprovação do SPEC:** sempre documento + aceite antes de GENERATE.
- **A08 — Migrar sem reconciliação:** contagem/soma/DISTINCTCOUNT/min-max origem×destino ao final.

## 7. Regras do agente (resumo)

- **Grounding:** todo mapeamento vem desta KB. Construto sem equivalente claro → **⚠️ revisão manual**, nunca inventar.
- **Documento primeiro:** SPEC revisável + aprovação humana ANTES de gerar código.
- **Buffer-safe:** `.bim`/`.vpax` pode ser grande — parsear via Bash/Python, índice em `_work/`, nunca despejar JSON no contexto.
- **Escopo:** decompõe o modelo semântico; **pipeline pesado** → `databricks-engineer`; **schema/DDL** → `migration-expert`; **PII** → `governance-auditor`; **DQ estatística** → `data-quality-steward`.
- **Idioma:** seguir o usuário (PT-BR/EN); nomes de construtos/produtos em inglês.

Concepts: `tabular-model-map.md` · `dax-mapping.md` · `rls-and-security.md`.
