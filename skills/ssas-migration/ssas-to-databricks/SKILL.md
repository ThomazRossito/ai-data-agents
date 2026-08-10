---
name: ssas-to-databricks
description: "Playbook operacional do agente ssas-to-databricks: parsear modelos tabulares SSAS (.bim/TMSL JSON e .vpax) de forma buffer-safe E compacta para inventariar dataSources, tabelas, colunas, medidas DAX, relacionamentos, roles/RLS, perspectives, calculation groups e KPIs; classificar por complexidade; produzir um documento de proposta (SPEC) para aprovação humana; e converter para Databricks (tabelas Delta/Unity Catalog, Metric Views, DAX→SQL, UC row filters/masks, AI/BI Dashboards + Genie) com reconciliação origem×destino."
updated_at: 2026-07-26
source: kb/ssas-migration (index + concepts/tabular-model-map + concepts/dax-mapping + concepts/rls-and-security)
agent: ssas-to-databricks
domain: ssas-migration
---

# Skill — Migração SSAS (modelo tabular) → Databricks

> Leia na primeira chamada da sessão. Define COMO parsear `.bim`/`.vpax` e COMO mapear para Databricks. A
> fonte normativa dos mapeamentos é `kb/ssas-migration/` — este skill é o "como fazer".

## Fluxo (6 fases + gate de aprovação)
`PARSE(.bim/.vpax) → INVENTORY → CLASSIFY → MAP → [GATE: SPEC + aprovação humana] → GENERATE → RECONCILE`

## Passo 1 — PARSE (buffer-safe **E compacto**)

`.bim`/TMSL é **JSON** (raiz `model`); `.vpax` é um **zip** (VertiPaq Analyzer). Duas regras de ouro:
**(1)** nunca dê `Read` no `.bim`/`.vpax` inteiro — parseie via Python; **(2)** o inventário tem que ser
**COMPACTO**: NÃO guarde M-query por partição nem os `ColumnsSegments` do `.vpax` (podem ter 100k+ linhas).
Alvo: `_work/ssas_index.json` e `_work/vpax_summary.json`, cada um **< ~1 MB**. Trabalhe sobre eles.

> ⚠️ **Auditoria 2026-07-26 (modelo BRF `Comercial`):** o dump completo gerou `ssas_index.json` de 7,4 MB
> e um `vpax_stats_snippet.json` de **96 MB** → afogou o contexto e a fase GENERATE deu **timeout**. O
> parser abaixo (testado NESTE mesmo modelo) produz **482 KB + 180 KB** mantendo o inventário útil.

```python
import glob, json, os, re, zipfile

INPUT_DIR = "<INPUT_DIR>"          # diretório com o(s) .bim/.vpax
OUTPUT_DIR = "<OUTPUT_DIR>"
os.makedirs(f"{OUTPUT_DIR}/_work", exist_ok=True)

_COMPLEX = re.compile(r"\b(CALCULATE|CALCULATETABLE|FILTER|VAR\s|DATEADD|SAMEPERIODLASTYEAR|"
                      r"TOTALYTD|TOTALMTD|DATESYTD|PARALLELPERIOD|ALLEXCEPT|EARLIER|RANKX|"
                      r"TOPN|SUMMARIZE|GENERATE|USERELATIONSHIP|SWITCH)\b", re.IGNORECASE)

def _clip(s, n):
    s = ("\n".join(s) if isinstance(s, list) else (s or "")).strip()
    return s[:n]

def classify(expr):
    return "complex" if _COMPLEX.search(expr or "") else "simple"

def parse_bim(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)                    # json.load é streaming-friendly; NUNCA Read manual
    model = data.get("model", {})
    tables = []
    for tbl in model.get("tables", []):
        cols, meas, parts = tbl.get("columns", []), tbl.get("measures", []), tbl.get("partitions", [])
        p0 = parts[0].get("source", {}) if parts else {}      # partições: só contagem + 1 amostra
        tables.append({
            "name": tbl.get("name"), "isHidden": tbl.get("isHidden", False),
            "n_columns": len(cols), "n_measures": len(meas), "n_partitions": len(parts),
            "n_calc_columns": sum(1 for c in cols if c.get("type") == "calculated"),
            "columns": [{"name": c.get("name"), "dataType": c.get("dataType"),
                         "src": c.get("sourceColumn"),   # nome FÍSICO — essencial p/ gerar SQL correto
                         "isHidden": c.get("isHidden", False), "calc": c.get("type") == "calculated"}
                        for c in cols],
            "measures": [{"name": m.get("name"), "folder": m.get("displayFolder", ""),
                          "isKpi": bool(m.get("kpi")), "format": m.get("formatString", ""),
                          "expr_preview": _clip(m.get("expression", ""), 280),
                          "expr_len": len(_clip(m.get("expression", ""), 10**9)),
                          "class": classify(_clip(m.get("expression", ""), 10**9))} for m in meas],
            "partitions_summary": {"count": len(parts), "source_type": p0.get("type"),
                                   "sample_query": _clip(p0.get("expression", ""), 280)},
        })
    rels = [{"from": f"{r.get('fromTable')}.{r.get('fromColumn')}",
             "to": f"{r.get('toTable')}.{r.get('toColumn')}",
             "active": r.get("isActive", True),
             "xfilter": r.get("crossFilteringBehavior", "single")} for r in model.get("relationships", [])]
    roles = [{"name": ro.get("name"),
              "members": [mm.get("memberName", mm.get("memberId")) for mm in ro.get("members", [])],
              "filters": [{"table": tp.get("name"), "filter": _clip(tp.get("filter", ""), 400)}
                          for tp in ro.get("tablePermissions", [])]} for ro in model.get("roles", [])]
    return {"file": os.path.basename(path), "model_name": model.get("name"),
            "compatibilityLevel": data.get("compatibilityLevel"),
            "dataSources": [{"name": d.get("name"), "type": d.get("type")}
                            for d in model.get("dataSources", [])],
            "counts": {"tables": len(tables), "relationships": len(rels), "roles": len(roles),
                       "measures": sum(t["n_measures"] for t in tables),
                       "complex_measures": sum(1 for t in tables for m in t["measures"]
                                               if m["class"] == "complex")},
            "tables": tables, "relationships": rels, "roles": roles,
            "perspectives": [p.get("name") for p in model.get("perspectives", [])],
            "translations": [tr.get("name") for tr in model.get("translations", [])],
            "cultures": [c.get("name") for c in model.get("cultures", [])]}

def parse_vpax(path, top_n=60):
    with zipfile.ZipFile(path) as z:
        tgt = next((n for n in z.namelist() if n.lower().endswith("daxvpaview.json")), None)
        if not tgt:
            return {"vpax": "sem DaxVpaView.json"}
        with z.open(tgt) as f:
            d = json.load(f)
    cols = d.get("Columns", [])                          # NUNCA leia d["ColumnsSegments"] (100k+ linhas)
    size_key = next((k for k in ("TotalSize", "ColumnSize", "DataSize") if cols and k in cols[0]), None)
    def csize(c):
        return c.get(size_key, 0) if size_key else 0
    return {"tables_stats": [{"table": t.get("TableName"), "rows": t.get("RowsCount"),
                              "size": t.get("TableSize"), "cols_size": t.get("ColumnsSize")}
                             for t in d.get("Tables", [])],
            "top_columns_by_size": [{"col": c.get("FullColumnName"), "type": c.get("DataType"),
                                     "encoding": c.get("Encoding"), "size": csize(c)}
                                    for c in sorted(cols, key=csize, reverse=True)[:top_n]],
            "measures": [{"name": m.get("FullMeasureName"),
                          "expr_preview": _clip(m.get("MeasureExpression", ""), 280),
                          "expr_len": len(m.get("MeasureExpression", "") or "")}
                         for m in d.get("Measures", [])],
            "table_permissions": [{"role": tp.get("RoleName"), "table": tp.get("TableName"),
                                   "filter": _clip(tp.get("FilterExpression", ""), 300)}
                                  for tp in d.get("TablePermissions", [])],
            "calculation_items": [{"group": ci.get("CalculationGroup"), "item": ci.get("ItemName"),
                                   "expr_preview": _clip(ci.get("ItemExpression", ""), 200)}
                                  for ci in d.get("CalculationItems", [])],
            "counts": {"tables": len(d.get("Tables", [])), "columns": len(cols),
                       "measures": len(d.get("Measures", [])), "relationships": len(d.get("Relationships", [])),
                       "calculation_items": len(d.get("CalculationItems", [])),
                       "columns_segments_SKIPPED": len(d.get("ColumnsSegments", []))}}

idx = [parse_bim(p) for p in glob.glob(f"{INPUT_DIR}/**/*.bim", recursive=True)]
json.dump(idx, open(f"{OUTPUT_DIR}/_work/ssas_index.json", "w"), ensure_ascii=False, indent=1)
vpx = [parse_vpax(p) for p in glob.glob(f"{INPUT_DIR}/**/*.vpax", recursive=True)]
json.dump(vpx, open(f"{OUTPUT_DIR}/_work/vpax_summary.json", "w"), ensure_ascii=False, indent=1)
for f in ("ssas_index.json", "vpax_summary.json"):
    mb = os.path.getsize(f"{OUTPUT_DIR}/_work/{f}") / 1e6
    assert mb < 3, f"{f} = {mb:.1f} MB — grande demais; aumente truncagem ou reduza top_n"
    print(f"{f}: {mb:.2f} MB")
```

> Precisa do **DAX completo** de uma medida específica (só na fase GENERATE)? Puxe **sob demanda** do
> `.bim`/`.vpax` (navegue o JSON até a medida X) — **nunca** re-despeje tudo no contexto. O parser real
> `scripts/parse_bim.py` existe e funciona; **este** parser compacto é o canônico do agente (evita a bomba).

## Passo 2 — INVENTORY
Liste, por modelo: dataSources; tabelas (dims/fatos) com nº de colunas/medidas/partições; relacionamentos
(ativos/inativos, cross-filter); roles + filtros DAX; perspectives; **calculation groups/items** (do `.vpax`,
campo `calculation_items`); medidas com contagem `simple` vs `complex` (campo `counts.complex_measures`);
translations/cultures. Priorize por tamanho (`vpax_summary.top_columns_by_size`). Gere a tabela-resumo (o
"mapa do modelo"). ⚠️ Calculation groups e time-intelligence são sinais fortes de complexidade — destaque-os.

## Passo 3 — CLASSIFY (complexidade)
| Complexidade | Critério |
|---|---|
| **Simples** | Tabela/medida direta: dim/fato mapeável, medida SUM/COUNT/DIVIDE |
| **Médio** | Relacionamento inativo, hierarquia, medida com razão, RLS por lookup simples |
| **Complexo** | DAX com `CALCULATE`/variáveis, calculated columns, cross-filter bidirecional |
| **Bloqueado/⚠️** | Time-intelligence, KPIs, **calculation groups/items**, perspectives, translations, RLS complexo |

## Passo 4 — MAP (3 camadas)
- **Físico** → Delta/Unity Catalog Medallion (`kb/ssas-migration/concepts/tabular-model-map.md`); pipeline pesado → escalar databricks-engineer/migration-expert.
- **Semântico** → Metric Views (`tabular-model-map.md`); medidas DAX → SQL ou ⚠️ (`concepts/dax-mapping.md`).
- **Segurança** → UC row filters/column masks (`concepts/rls-and-security.md`).
- **Consumo** → AI/BI Dashboards + Genie Spaces.
Marque itens sem equivalente como **⚠️ revisão manual**.

## GATE — Documento de proposta (SPEC) + aprovação humana (obrigatório)

Antes de gerar QUALQUER código, entregue um **documento de proposta de migração** revisável (inventário,
classificação, mapeamento das 3 camadas, itens ⚠️, plano de fases, reconciliação proposta) e **PARE para
aprovação humana**. Só avance para o GENERATE após o aceite explícito. Este projeto adota "sempre documento
+ aprovação para migrações" (Constituição §2.2 / Supervisor Step 0.6(A)).

> **O GATE é uma FRONTEIRA DE TURNO, não um passo sequencial.** Entregue o SPEC e **encerre** — quem
> aprova é o **usuário**, numa mensagem seguinte. NÃO gere código no mesmo turno do SPEC. Um hook de
> enforcement (`enforce_migration_gate`) bloqueia uma 2ª delegação de migração no mesmo turno; se você
> for bloqueado, é sinal de que deveria ter parado — apresente o SPEC e aguarde.

## Passo 5 — GENERATE (só após aprovação) — DETERMINÍSTICO, dirigido por metadados

**Regra de ouro:** NÃO escreva o SQL à mão **e NÃO escreva seu próprio gerador** (`generate_*.py`).
Reimplementar a geração faz o modelo (a) usar o **nome de exibição** em vez do `sourceColumn`, ou (b)
nomear a coluna de um jeito no `CREATE TABLE` e de outro na Metric View → **`column not found`**. Cada
run reintroduz um bug NOVO (comprovado — auditoria 2026-07-26: um gerador hand-rolado deixou 223 colunas
de MV sem correspondência no DDL). Rode o gerador **ÚNICO**, versionado e testado — **AGNÓSTICO ao
negócio** (tudo vem do `.bim`: nomes, tipos, sourceColumn, relacionamentos, roles):

```bash
python scripts/ssas_generate.py <INPUT_DIR> output/ssas-migration/<slug>
```

Ele emite, **correto-por-construção** (sourceColumn físico + backtick em TODO identificador):
- `01_ddl_gold.sql` — `CREATE TABLE` (schema-only) de cada tabela, com o mapa fixo SSAS `dataType`→Delta (`kb/ssas-migration/concepts/tabular-model-map.md`).
- `02_metric_views_simples.sql` — Metric Views das medidas **simples** (`SUM/COUNT/DISTINCTCOUNT/MIN/MAX/AVERAGE` de 1 coluna e `DIVIDE` de 2 medidas), `joins` dos relacionamentos ativos.
- `03_medidas_flagadas.md` — medidas **complexas** + as que não resolvem p/ coluna física (**NÃO convertidas**).
- `04_rls_scaffold.sql` — scaffold dos roles (revisar mapeamento e-mail `USERNAME()` → `current_user()` do Entra ID).

- `05_reconciliation.sql` — queries origem×destino (contagem/soma/min-max) — executar nos dois lados.

**Esses arquivos SÃO os entregáveis** de DDL/MV/RLS/reconciliação — copie-os para `output/ssas-migration/<slug>/`.
**NÃO** os reescreva à mão, **NÃO** os "melhore", **NÃO** gere um `generate_*.py` paralelo. O gerador roda **3 gates**
(identificador sem backtick; MV sem `CREATE TABLE`; **coluna de MV que não existe no DDL**) e **sai com código ≠ 0**
se algum falhar → então **NÃO reporte "concluído"** e corrija a CAUSA (nunca contorne com um gerador próprio).

**Além do gerador (julgamento de especialista — honesto, não auto-fingível):**
- **Medidas complexas** (as de `03_medidas_flagadas.md`): reescrita caso a caso via `concepts/dax-mapping.md`. NUNCA finja `CREATE MEASURE`/conversão.
- **Calculation groups / time-intelligence:** redesenho (colunas offset em `dim_calendario` + CTEs). Documente; não auto-converta.
- **Consumo:** proposta de **AI/BI Dashboard** + **Genie Space** (tabelas Gold/Metric Views + sample questions).
- **PII / masks:** → `governance-auditor`.

**Delegação (fora do escopo deste especialista):**
- **Ingestão ETL** (fonte → Bronze→Silver→Gold que **popula** as tabelas): → `databricks-engineer`. O `01_ddl_gold.sql` é o **contrato de schema**; o pipeline que enche é dele.

Feche com um **`migration_report.md`** mapeando construto SSAS → artefato (com os ⚠️ e a nuance de reconciliação: medida agregada legada × grão atômico).

## Passo 5c — AUTO-REVISÃO de sanidade (obrigatório antes de reportar concluído)
NÃO reporte "concluído" se algum falhar:
- [ ] **SPEC foi aprovado** antes de gerar código (o gate não foi pulado).
- [ ] **Buffer-safe E compacto:** nenhum `Read` no `.bim`/`.vpax` inteiro; inventário veio de `_work/ssas_index.json` + `_work/vpax_summary.json`, cada um **< ~1 MB** (a `assert` do parser passou); `ColumnsSegments` NÃO foi despejado.
- [ ] **DAX honesto:** toda medida na lista ⚠️/`03_medidas_flagadas.md` NÃO é alegada como "convertida"; nenhuma `CREATE MEASURE` em SQL.
- [ ] **Gerador rodou e passou nos 3 gates:** `scripts/ssas_generate.py` saiu com **código 0** — sem identificador com espaço sem backtick; sem Metric View sem `CREATE TABLE`; **e sem coluna de MV que não existe no DDL** (o bug de drift do gerador hand-rolado).
- [ ] **Sem gerador próprio:** os entregáveis SÃO os arquivos do `ssas_generate.py`; NÃO existe `generate_*.py` reescrito nem `metric_views/` paralelo com estrutura/nomes diferentes.
- [ ] **Coluna física, não display name:** as expressões das Metric Views usam `sourceColumn` (via o gerador), nunca o nome de exibição com espaço.
- [ ] **Metric View válida:** `source` aponta para tabela Gold criada no `01_ddl_gold.sql`; `measures` são SQL agregável.
- [ ] **RLS:** row filter/mask referencia coluna/tabela existente; `current_user()`/grupo corretos; sem duplicar dados.
- [ ] **PII:** nenhuma coluna/medida/filtro com PII gerado sem passar por `governance-auditor`.
- [ ] **Relatório == código, COM `grep`:** para CADA feature alegada (Metric View, row filter, mask, dashboard, medida convertida) rode `grep -rn` no diretório de saída; se não achar, **APAGUE a alegação**. A tabela de artefatos bate com `find <saída> -type f`.

## Passo 6 — RECONCILE
O gerador já emite `05_reconciliation.sql` (contagem + `SUM` das colunas numéricas + `MIN/MAX` de datas
por tabela, com a dica do lado origem). **Execute nos dois lados** (origem na fonte, destino no Gold) e
compare — somas com tolerância ±0.01%. Complemente com `DISTINCTCOUNT` das dimensões e top-N medidas SSAS
(DAX) × Databricks (SQL). Reusar o checklist de `kb/migration`. ⚠️ Medida legada agregada (VertiPaq) × grão
atômico: 1:1 pode não bater no grão. Validação estatística avançada → escalar `data-quality-steward`.

## Anti-patterns (fortes)
❌ Tratar o modelo tabular como 1:1 SQL (desmontar em 3 camadas). ❌ Converter DAX complexo às cegas
(time-intel/CALCULATE/calc columns → ⚠️). ❌ Fingir `CREATE MEASURE` em SQL. ❌ Ignorar
perspectives/translations/KPIs/calculation groups. ❌ RLS complexo direto (bidirecional/contextual → ⚠️).
❌ `Read` no `.bim`/`.vpax` inteiro. ❌ **Despejar `ColumnsSegments` do `.vpax` ou M-queries por partição**
(bomba de contexto → timeout no GENERATE; use o parser compacto). ❌ Gerar código antes da aprovação do
SPEC — ou no MESMO turno do SPEC. ❌ **Escrever o DDL/SQL de Metric View à mão** (usa o nome de exibição
com espaço + esquece backtick → não parseia no Databricks) — rode `scripts/ssas_generate.py`. ❌ **Escrever
seu próprio gerador** (`generate_*.py`) ou reimplementar a geração — cada run reintroduz bug novo (drift: o
CREATE TABLE e a MV divergem no nome da coluna); consuma a saída do gerador único. ❌ Referenciar coluna
pelo **nome de exibição** em vez do `sourceColumn` físico. ❌ Migrar sem reconciliação.
