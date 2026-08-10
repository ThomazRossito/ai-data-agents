---
name: read-sizing-spreadsheet
description: "Converte uma planilha de sizing (Excel T-shirt band, estilo Seatrium) em um cenário de custo estruturado para os agents databricks-cost-calculator e azure-cost-calculator. Reconhece o layout '# / Assumption / Value used in estimate / Basis / Notes' e aliases. Extrai environments, região, volume de dados, fontes, usuários SQL/notebook/Genie/GenAI, growth e exclusões. NUNCA inventa valores — campos ambíguos vão para needs_confirmation."
updated_at: 2026-07-22
source: skills/finops/read-sizing-spreadsheet/parse_sizing.py
agent: databricks-cost-calculator, azure-cost-calculator
domain: finops
---

# Skill — Read Sizing Spreadsheet (FinOps)

> **Uso:** Playbook operacional para consumir uma planilha de sizing enviada pelo
> usuário (ou parceiro Databricks) e transformá-la em um cenário de custo, ANTES
> de calcular. Evita que o usuário tenha que redigitar os inputs em linguagem
> natural quando ele já tem uma planilha estruturada.

## Quando Acionar Esta Skill

- Usuário faz upload de um `.xlsx` com abas "Sizing", "Assumptions", "Platform Sizing" ou similar
- Usuário diz "calcula o custo baseado nessa planilha" / "usa esse sizing"
- Workflow WF-06 (Greenfield) recebe uma planilha como input

## Princípio Fundamental: Zero Invenção (Constituição S3/S7)

O parser extrai apenas o que está na planilha. Quando um campo obrigatório
(região, num_envs, storage) não pode ser derivado com confiança, ele entra em
`scenario["needs_confirmation"]` — e o agent DEVE perguntar ao usuário, nunca
chutar. Linhas que não casam com nenhuma keyword vão para `_unmapped_rows` e
devem ser apresentadas ao usuário para mapeamento manual.

## Como Usar

> ⚠️ **O diretório tem hífen (`read-sizing-spreadsheet`)** — NÃO é importável como
> módulo Python (`import skills.finops.read-sizing-spreadsheet` falha). Use uma das
> duas formas abaixo. A forma recomendada para o agent é rodar como SCRIPT.

### Forma 1 — rodar como script (RECOMENDADO para o agent)

```bash
python3 skills/finops/read-sizing-spreadsheet/parse_sizing.py "/caminho/para/sizing.xlsx"
```

Imprime um JSON com `parsed_fields` + `scenario` (inclui `needs_confirmation`).
O agent lê esse JSON e valida `needs_confirmation` com o usuário antes de calcular.
NÃO tente `import` com o path que tem hífen — vai falhar (foi o que aconteceu num
run real: "O módulo Python não existe ainda").

### Forma 2 — importar por path (se precisar em código Python)

```python
import importlib.util, pathlib
_p = pathlib.Path("skills/finops/read-sizing-spreadsheet/parse_sizing.py")
_spec = importlib.util.spec_from_file_location("parse_sizing", _p)
parse_sizing_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(parse_sizing_mod)

parsed = parse_sizing_mod.parse_sizing("/caminho/sizing.xlsx")
scenario = parse_sizing_mod.sizing_to_scenario(parsed)
if scenario["needs_confirmation"]:
    ...  # PARAR e perguntar ao usuário
```

## Schema esperado da planilha

| Coluna | Aliases reconhecidos |
|---|---|
| # / Ref | "#", "Ref", "Code", "ID" |
| Assumption | "Assumption / driver", "Item", "Requirement" |
| Value | "Value used in estimate", "Value", "Target", "Sized value" |
| Basis | "Basis / source", "Source", "Origin" |
| Notes | "Notes", "Notes for CI&T", "Comments" |

O detector de header é robusto a linhas de prosa (ex: uma nota "Sources: ...
account assumptions where marked" NÃO é confundida com o header, porque exige
múltiplas colunas-sinal + presença de uma coluna "Value").

## Campos extraídos (canonical)

`num_envs`, `cloud_region`, `storage_gb`, `annual_growth_rate`, `batch_etl_volume`,
`streaming`, `num_source_systems`, `num_sql_users`, `num_dashboards`,
`num_notebook_users`, `genie_questions_per_month`, `num_genie_users`,
`genai_questions_per_month`, `genai_llm`, `monitoring_coverage`, `rag`,
`lakebase`, `dr_ha`, `historical_migration`.

## Saída de `sizing_to_scenario`

```json
{
  "cloud": "azure",
  "region": "southeastasia",
  "num_envs": 4,
  "storage_gb": 50000,
  "annual_growth_pct": 20.0,
  "streaming_required": false,
  "num_sql_users": 70,
  "num_notebook_users": 10,
  "genie_questions_per_month": 5000,
  "genai_llm": "Proprietary frontier model (Claude Opus class) ...",
  "workloads": [
    {"code": "ETL_BATCH", "compute_type": "jobs_compute"},
    {"code": "LFC_CONNECT", "compute_type": "jobs_serverless"},
    {"code": "SQL_WAREHOUSE", "compute_type": "sql_serverless"},
    {"code": "NOTEBOOK", "compute_type": "all_purpose_compute"},
    {"code": "MONITORING", "compute_type": "jobs_compute"},
    {"code": "GENIE", "compute_type": "genie"},
    {"code": "AI_SEARCH", "compute_type": "vector_search"},
    {"code": "FM_LLM", "compute_type": "proprietary_foundation_model_serving"}
  ],
  "excluded": ["streaming", "ml_training", "model_serving", "lakebase", "dr_ha", "historical_migration"],
  "needs_confirmation": []
}
```

## Regra crítica pós-parse

Se `scenario["region"]` estiver fora do mock (`brazilsouth`, `eastus`, `westeurope`)
— caso do `southeastasia` — o agent DEVE ativar real-mode (Azure Retail Prices API)
ou avisar que os DBU rates variam por região no Azure (APAC ~20-30% acima do US
reference). Ver KB `azure-infra-for-databricks` e `kb/databricks-pricing/`.

## Encadeamento com WF-06

Numa estimativa greenfield, a saída desta skill alimenta EM PARALELO:
- `databricks-cost-calculator` → workloads (compute + storage)
- `azure-cost-calculator` → infra Azure (num_envs vNets, NAT, PEP, Log, KV, FW, Defender)

O campo `num_envs` dispara a replicação de infra por ambiente.

## Validação

Testado contra a planilha real "Seatrium x Databricks — Platform Sizing
Assumptions (17 Jul 2026)": extrai region=southeastasia, num_envs=4,
storage_gb=50000, num_sql_users=70, genie=5000 q/mo, 8 workloads, 6 exclusões,
zero campos em needs_confirmation. Ver `tests/test_parse_sizing.py`.
