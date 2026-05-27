---
domain: databricks-pricing
updated_at: 2026-05-27
agents: [databricks-cost-calculator]
---

# Knowledge Base — Databricks Pricing & Cost Calculation

> Conhecimento operacional para o agent **databricks-cost-calculator**. Consultar SEMPRE antes de calcular cenários novos.

## 1. Fonte de Verdade

| Item | Valor |
|---|---|
| Engine | `data_agents.cost_engine.databricks` (determinístico, Fase 0) |
| Catalog Azure | `data/databricks_pricing/azure.yaml` |
| Catalog AWS | `data/databricks_pricing/aws.yaml` |
| Instance prices | `data_agents.cost_app.databricks.instance_prices` (mock 3 regiões Azure + 5 AWS — Fase 1) |
| Smoke test canonical | `4 workers × Standard_DS4_v2 × 8h/day × 22d/month × Jobs Premium sem Photon × brazilsouth = $726.88/mês` |
| MCP server | `databricks_pricing` (9 tools) — entry point: `databricks-pricing-mcp` |
| App Streamlit | `http://localhost:8514` (porta padrão — bridge via `outputs/cost-scenarios/<uuid>.json`) |
| Pricing oficial Databricks | `https://www.databricks.com/product/pricing` (DBU rates) + Azure VM / AWS EC2 retail prices |

> **Nota Fase 1:** Os instance prices são MOCK para 3 regiões Azure (`brazilsouth`, `eastus`, `westeurope`) + 5 AWS (`us-east-1`, `us-west-2`, `eu-west-1`, `ap-southeast-1`, `sa-east-1`). Fora dessas, listar via `list_regions` e pedir cotação real. Fase posterior integrará Azure Retail API + AWS Pricing API.

## 2. Modelo de Custo (cabeçalho)

```
Cluster cost/mês = (DBU_total × DBU_rate) + (Instance_total_hours × Instance_price)
```

Onde:
- **DBU_total/mês** = `(driver_dbu_per_hour + num_workers × worker_dbu_per_hour) × hours_per_day × days_per_month`
- **Instance_total_hours/mês** = `(1 + num_workers) × hours_per_day × days_per_month` (driver + N workers)
- **DBU_rate** = lookup no catalog (compute_type × tier × photon × cloud)
- **Instance_price** = lookup no catalog (SKU × region × cloud), USD/h

## 3. DBU Rates — Catalog Resumido (USD/DBU·h)

### Azure (catalog `azure.yaml`)

| Compute Type | Standard sem Photon | Standard com Photon | Premium sem Photon | Premium com Photon |
|---|---|---|---|---|
| `jobs_compute` | $0.10 | $0.20 | $0.20 | $0.40 |
| `all_purpose_compute` | $0.40 | $0.80 | $0.55 | $1.10 |
| `sql_compute` | n/a | n/a | $0.22 | $0.44 |
| `sql_pro` | n/a | n/a | $0.55 | n/a |
| `sql_serverless` | n/a | n/a | $0.70 | n/a |
| `dlt_core` | $0.20 | n/a | $0.36 | n/a |
| `dlt_pro` | n/a | n/a | $0.54 | n/a |
| `dlt_advanced` | n/a | n/a | $0.72 | n/a |
| `serverless_compute` | n/a | n/a | $0.95 | n/a |

### AWS (catalog `aws.yaml`)

| Compute Type | Standard sem Photon | Standard com Photon | Premium sem Photon | Premium com Photon |
|---|---|---|---|---|
| `jobs_compute` | $0.07 | $0.14 | $0.10 | $0.20 |
| `all_purpose_compute` | $0.40 | $0.80 | $0.55 | $1.10 |
| `sql_compute` | n/a | n/a | $0.22 | $0.44 |
| `serverless_compute` | n/a | n/a | $0.95 | n/a |

> **Photon dobra o DBU rate (~2×).** Veja `concepts/photon-roi.md` para regra de bolso de quando vale a pena.

## 4. Instance Prices — Resumo Mock (Fase 1)

### Azure brazilsouth (canonical region)

| SKU | vCPU | Memory (GB) | USD/h | DBU/h |
|---|---|---|---|---|
| Standard_DS3_v2 | 4 | 14 | $0.263 | 0.75 |
| **Standard_DS4_v2** | **8** | **28** | **$0.526** | **1.5** |
| Standard_DS5_v2 | 16 | 56 | $1.054 | 3.0 |
| Standard_E8ds_v4 | 8 | 64 | $0.60 | 1.5 |
| Standard_E16ds_v4 | 16 | 128 | $1.20 | 3.0 |
| Standard_F8s_v2 | 8 | 16 | $0.40 | 1.0 |
| Standard_F16s_v2 | 16 | 32 | $0.80 | 2.0 |

### AWS us-east-1

| SKU | vCPU | Memory (GB) | USD/h | DBU/h |
|---|---|---|---|---|
| m5.xlarge | 4 | 16 | $0.192 | 0.75 |
| m5.2xlarge | 8 | 32 | $0.384 | 1.5 |
| m5.4xlarge | 16 | 64 | $0.768 | 3.0 |
| r5.xlarge | 4 | 32 | $0.252 | 0.75 |
| r5.2xlarge | 8 | 64 | $0.504 | 1.5 |
| r5.4xlarge | 16 | 128 | $1.008 | 3.0 |
| c5.4xlarge | 16 | 32 | $0.68 | 2.0 |

> Para listar tudo: `databricks_pricing_list_instances(cloud="azure", region="brazilsouth")`.

## 5. Workflow Canonical (referência)

Cenário canônico que valida o engine (smoke test):

| Parâmetro | Valor |
|---|---|
| Cloud | `azure` |
| Region | `brazilsouth` |
| Compute type | `jobs_compute` |
| Tier | `premium` |
| Photon | `false` |
| Driver | `Standard_DS4_v2` (1.5 DBU/h, $0.526/h) |
| Worker | `Standard_DS4_v2` (1.5 DBU/h, $0.526/h) |
| Num workers | 4 |
| Hours/day | 8.0 |
| Days/month | 22 |

**Cálculo passo-a-passo (auditável):**
- Total instance hours/mês = (1 + 4) × 8 × 22 = **880 h**
- Total DBU/mês = (1.5 + 4 × 1.5) × 8 × 22 = 7.5 × 176 = **1.320 DBU**
- DBU cost = 1.320 × $0.20 = **$264.00**
- Instance cost = 880 × $0.526 = **$462.88**
- **Total mensal = $726.88** ✅

Esse número é a "Hello World" do engine — toda alteração no código deve preservá-lo.

## 6. Conceitos relacionados (links)

- [DBU model](concepts/dbu-model.md) — anatomia do DBU rate, multipliers Photon, comparação entre compute types
- [DBCU Commit](concepts/dbcu-commit.md) — Pre-purchase 1y/3y, breakeven, casos de uso
- [Photon ROI](concepts/photon-roi.md) — quando Photon compensa: regra de bolso e métricas de validação
- [Multi-cloud](concepts/multi-cloud.md) — diferenças Azure vs AWS no modelo DBU + instance pricing
- [Instance pricing (mock Fase 1)](concepts/instance-pricing.md) — limitações do mock + roadmap pra Azure Retail / AWS Pricing API

## 7. Tools MCP disponíveis (13 totais)

### Cotação determinística (Chunk 2.1 — 9 tools)

| Tool | Uso |
|---|---|
| `databricks_pricing_diagnostics` | Smoke test inicial (chame na 1ª pergunta da sessão) |
| `databricks_pricing_get_dbu_rate` | Lookup determinístico (compute_type × tier × photon × cloud) |
| `databricks_pricing_get_instance_price` | Lookup determinístico (SKU × region × cloud) |
| `databricks_pricing_list_instances` | Discovery quando SKU não está no catalog |
| `databricks_pricing_list_regions` | Discovery quando region não está no catalog |
| `databricks_pricing_calc_cluster_cost` | **Tool principal** — custo total mensal + breakdown DBU/Instance |
| `databricks_pricing_compare_payg_vs_dbcu` | Comparação 1y/3y com breakeven (quando user pede "DBCU", "RI", "savings") |
| `databricks_pricing_currency_convert` | USD→BRL (ou outra) via fx_rate |
| `databricks_pricing_save_scenario` | **Bridge Agent → App** — salvar em `outputs/cost-scenarios/<uuid>.json` (CONDICIONAL — só com pedido explícito) |

### Bridge App → Agent (Chunk 2.3 — 4 tools)

| Tool | Uso |
|---|---|
| `databricks_pricing_list_scenarios(filter_source?, filter_cloud?)` | Lista cenários salvos com filtros opcionais. Use quando user pergunta "quais cenários você tem?" |
| `databricks_pricing_load_scenario(uuid)` | Carrega envelope completo (uuid, name, source, parent_uuid + scenario). Use para "carrega XYZ e recalcula com 8 workers" |
| `databricks_pricing_search_scenarios(query, limit=10)` | Busca fuzzy por name+description. Use para "carrega o cenário do ETL Bronze" |
| `databricks_pricing_delete_scenario(uuid)` | **DESTRUCTIVE.** Só com pedido explícito ("limpa o cenário X"). Idempotente: retorna `deleted=false` se uuid não existe |

### Source vocabulary (rastreamento de linhagem)

| Source | Origem |
|---|---|
| `agent` | Cenário gravado pelo agent via `save_scenario` |
| `manual` | Cenário criado novo no App (Tab "Cenário Cluster") |
| `app-edited` | Cenário carregado de outro existente (qualquer source) e re-salvo. Inclui `parent_uuid` rastreando linhagem |
| `import` | Reservado pra futura tool de import bulk |

## 8. Cliente nominal vs sem cliente (slug rules)

Igual ao `azure-cost-calculator`:

| Nome do usuário | Slug | Path |
|---|---|---|
| "Cliente Banco Z" | `banco_z` | `output/prj_banco_z/` |
| "Magalu" | `magalu` | `output/prj_magalu/` |
| "Aviação Cêltica" | `aviacao_celtica` | `output/prj_aviacao_celtica/` |
| (sem cliente nominal) | timestamp + scenario | `output/cost-databricks/<YYYYMMDD>_<scenario_slug>/` |

**Validação:** SEMPRE preserve underscore entre palavras. "magalu prod" → `magalu_prod`, NÃO `magaluprod`.

## 9. O que este KB NÃO cobre

- **system.billing** (workload já em produção): Fase 3 (`databricks-engineer` agent, fora deste KB)
- **Rightsizing baseado em métricas reais**: Fase 4
- **Negociação de DBCU customizado** (volumes enterprise > $100k/ano): pedir cotação real à Databricks Account Team
- **Reserved Instances de VM** (Azure RI 1y/3y ou AWS RI): suportado parcialmente via `discount_pct_spot` e `discount_pct_ri` no catalog — para precisão, consultar Azure Pricing Calculator / AWS Cost Calculator
