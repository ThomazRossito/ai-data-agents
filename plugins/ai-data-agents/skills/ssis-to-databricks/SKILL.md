---
name: ssis-to-databricks
description: "Playbook operacional do agente ssis-to-databricks: parsear pacotes SSIS (.dtsx XML) para inventariar Control Flow, Data Flow, Connection Managers, variáveis e precedence constraints; classificar por complexidade; e converter para Databricks (PySpark/Spark SQL, Delta MERGE/SCD, Lakeflow/DLT, Workflows/Jobs, Auto Loader) com reconciliação origem×destino."
updated_at: 2026-06-18
source: kb/ssis-migration (index + concepts/control-flow-map + concepts/data-flow-map + concepts/expressions-and-patterns)
agent: ssis-to-databricks
domain: ssis-migration
---

# Skill — Migração SSIS → Databricks

> Leia na primeira chamada da sessão. Define COMO parsear `.dtsx` e COMO mapear para Databricks. A fonte
> normativa dos mapeamentos é `kb/ssis-migration/` — este skill é o "como fazer".

## Fluxo (6 fases)
`PARSE(.dtsx) → INVENTORY → CLASSIFY → MAP → GENERATE → RECONCILE`

## Passo 1 — PARSE (buffer-safe)

`.dtsx` é XML (namespace `DTS:` = `www.microsoft.com/SqlServer/Dts`). **Não** despeje o XML no contexto —
parseie via Bash/Python, escreva um índice em `<saída>/_work/` e trabalhe sobre ele.

```bash
pip install lxml --break-system-packages -q   # ou usar xml.etree padrão
```

```python
import glob, json, os
import xml.etree.ElementTree as ET
NS={"DTS":"www.microsoft.com/SqlServer/Dts"}
def parse_dtsx(path):
    t=ET.parse(path); r=t.getroot()
    def tag(e): return e.tag.split('}')[-1]
    execs=[]  # Control Flow tasks
    for e in r.iter():
        if tag(e)=="Executable":
            execs.append({"type":e.get(f'{{{NS["DTS"]}}}ExecutableType') or e.get("ExecutableType"),
                          "name":e.get(f'{{{NS["DTS"]}}}ObjectName') or e.get("ObjectName")})
    comps=[]  # Data Flow components (pipeline)
    for c in r.iter():
        if tag(c)=="component":
            comps.append({"name":c.get("name"),"componentClassID":c.get("componentClassID")})
    conns=[e.get(f'{{{NS["DTS"]}}}ObjectName') for e in r.iter() if tag(e)=="ConnectionManager"]
    vars=[e.get(f'{{{NS["DTS"]}}}ObjectName') for e in r.iter() if tag(e)=="Variable"]
    prec=sum(1 for e in r.iter() if tag(e)=="PrecedenceConstraint")
    return {"file":os.path.basename(path),"executables":execs,"components":comps,
            "connections":[c for c in conns if c],"variables":[v for v in vars if v],
            "precedence_constraints":prec}
idx=[parse_dtsx(p) for p in glob.glob("<INPUT_DIR>/**/*.dtsx", recursive=True)]
json.dump(idx, open("<OUTPUT_DIR>/_work/ssis_index.json","w"), ensure_ascii=False, indent=2)
print("pacotes:",len(idx),"→ ssis_index.json")
```
> `componentClassID` identifica o tipo do componente de Data Flow (ex.: `...OLEDBSource`,
> `...DerivedColumn`, `...Lookup`, `...OLEDBDestination`). Use-o para mapear via `data-flow-map.md`.

## Passo 2 — INVENTORY
Liste, por pacote: nº de tasks (Control Flow), nº de componentes (Data Flow), connection managers,
variáveis/parâmetros, precedence constraints. Gere uma tabela-resumo (o "mapa do pacote").

## Passo 3 — CLASSIFY (complexidade)
| Complexidade | Critério |
|---|---|
| **Simples** | Data Flow direto (Source→Transform básico→Destination), sem Script |
| **Médio** | Lookups, Conditional Split, Merge Join, SCD, Execute SQL com lógica |
| **Complexo** | Script Task/Component, loops, OLE DB Command, event handlers, checkpoints |
| **Bloqueado/⚠️** | Fuzzy, DQS, SSAS, WMI/MSMQ — sem equivalente nativo (revisão manual) |

## Passo 4 — MAP
Para cada task/componente, aplique os mapas da KB:
- Control Flow → `kb/ssis-migration/concepts/control-flow-map.md` (Workflow/Job).
- Data Flow → `concepts/data-flow-map.md` (PySpark/DLT; SCD via MERGE/APPLY CHANGES; error output → quarentena).
- Expressões/variáveis/conexões → `concepts/expressions-and-patterns.md`.
Decida **Workflows vs DLT** por pacote (index §5). Marque itens sem equivalente como **⚠️ revisão manual**.

## Passo 5 — GENERATE (modelo ÚNICO + entrega em DAB)

Primeiro **escolha o modelo de execução** (coerente, não misturar — ver `kb/ssis-migration/concepts/execution-model-and-packaging.md`):
- **Padrão A (recomendado):** Bronze→Silver→Gold em **Lakeflow SDP** (`@dp.table`, expectations, `create_auto_cdc_flow`/APPLY CHANGES p/ SCD) = **1 pipeline**; passos imperativos (auditoria) = task de **Lakeflow Job** dependente.
- **Padrão B:** tudo imperativo em **Lakeflow Jobs** (MERGE/SCD na mão), **zero `@dp`**; expectations viram checks pós-carga.
- **Nunca** `@dp` num notebook orquestrado como notebook-task.

Produza, por pacote:
- **Camadas** (Bronze/Silver/Gold) no modelo escolhido — leitura (Auto Loader / **Lakeflow Connect** p/ SQL Server) → transformações → escrita Delta idempotente (`MERGE`/`replaceWhere`) → quarentena dos error outputs. **PII mascarado/tokenizado no código** (Silver). **SK estável** (IDENTITY/hash/APPLY CHANGES).
- **Empacotamento em Declarative Automation Bundle (DAB):** `databricks.yml` + `resources/*.yml` (jobs + pipelines) + `targets` dev/staging/prod (skill `databricks-bundles`). **Toda camada representada** na orquestração (sem Bronze/Silver órfão); **uma dimensão = uma unidade**.
- **Conversão de expressões** aplicada; **variáveis/params** → job params/widgets; **conexões** → secret scope; sem FK enforced.
- Um **relatório de conversão** (`conversion_report.md`) mapeando cada executable/componente → artefato, com os **itens de revisão manual** destacados (Script C#, Fuzzy) e a nuance de reconciliação (fato legado agregado × grão atômico).

## Passo 5c — AUTO-REVISÃO de sanidade (obrigatório antes de reportar concluído)

Rode o checklist (`kb/ssis-migration/concepts/execution-model-and-packaging.md` §7–§10). NÃO reporte
"concluído" se algum falhar. **`py_compile` OK NÃO basta — vários bugs só quebram em runtime (§10).**
- [ ] **SK real gerada** (IDENTITY ou hash da CHAVE NATURAL no `*_clean`, não de atributos mutáveis) — o fato lê `*_sk` que EXISTE na dim pós-AUTO-CDC. `sequence_by` é temporal (não `_batch_id`).
- [ ] **Grão** do fato tem as chaves naturais (order_id, product_id).
- [ ] **Colunas consistentes:** toda coluna lida por um passo existe no passo que a produz.
- [ ] **Sem SyntaxError** (`python -m py_compile`) **E sem armadilha de runtime (§10):** nada de `createDataFrame` com `Column`; nada de `Window`/`row_number` em streaming; nada de join stream-stream sem watermark; watermark de tabela de controle (não `spark.conf` vazio); `dim_date` cobre a data mais antiga real.
- [ ] **DDL = referência** (não recria/nem diverge das tabelas do SDP). Refs (dim_date, city_master) seedadas ANTES do pipeline.
- [ ] **DAB válido:** target=schema, retry por-task, sem `${workspace.secrets}`; segredos via secret scope.
- [ ] **Relatório == código, COM `grep` (o self-check falhou aqui no run 3):** para CADA feature alegada (replaceWhere, MERGE, salt, notificação, Lakeflow Connect, incremental) rode `grep -rn` no código; se não achar, **APAGUE a alegação**. A tabela de artefatos tem que bater com `find <saída> -type f` (não citar `.sql` se o código é `.py`).

## Passo 6 — RECONCILE
Por Data Flow migrado: contagem origem×destino (<0.1%), soma de numéricos (±0.01%), min/max de datas,
PK sem duplicata. Reusar o checklist de `kb/migration`. Para validação estatística avançada → escalar `data-quality-steward`.

## Anti-patterns (fortes)
❌ Portar OLE DB Command linha-a-linha (usar MERGE set-based). ❌ Reproduzir Sort/blocking. ❌ Traduzir
Script C#/VB literalmente (reescrever + sinalizar). ❌ Perder error outputs (quarentena/expectations).
❌ Escrita não idempotente. ❌ Manter For Each de arquivos (usar Auto Loader). ❌ Inventar equivalente
para componente sem mapeamento — marcar ⚠️ revisão manual. ❌ Despejar o XML `.dtsx` no contexto.
