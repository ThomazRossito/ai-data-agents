---
title: Estratégia de implementação — Cobertura Total dos SKUs Databricks
domain: databricks-pricing
created_at: 2026-05-28
status: planning
depends_on:
  - kb/databricks-pricing/parity-audit.md
  - kb/databricks-pricing/extracted-prices-raw.md
---

# Estratégia de implementação — Cobertura Total

> User autorizou "Cobertura total" (~3.000 LOC) em 2026-05-28.
> Dados primários: 25 sub-páginas de pricing oficial coletadas via Chrome MCP em `extracted-prices-raw.md`.
>
> Esta strategy quebra o trabalho em **4 PRs sequenciais** ao invés de um único big-bang.
> Motivo: cada PR é revisável em ~1h, falhas isoladas não bloqueiam o sistema todo, e o usuário pode validar incremental.

---

## Diagnóstico atual (o que está errado no código)

### `data_agents/cost_engine/databricks.py`

| Item                            | Estado atual                          | Problema                                                                       |
| ------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------ |
| `Tier` Literal                  | `"standard" \| "premium" \| "enterprise"` | Standard não existe oficialmente. Azure só tem Premium (= Enterprise).         |
| `ComputeType` Literal           | 8 valores                              | Faltam 13+ SKUs (Lakebase, Foundation Model, Vector Search tiers, etc.)        |
| `_resolve_dbu_rate`             | If/elif por compute_type              | Hard-coded; não escala. Cada SKU novo = mais branches.                         |
| Cost unit                       | Sempre DBU·h                           | Lakebase usa CU·h, Storage usa DSU, tokens usa M-tokens. Engine não modela.    |
| Photon                          | Flag boolean (line 414-424)            | Oficial: SKU separado. Factor heterogêneo (2.0 vs 2.9 conforme SKU).           |
| `dbu_consumption_multiplier`    | Hardcoded 2.0 em photon_modeling      | Errado — varia por SKU. Jobs/DLT=2.9X, All-Purpose=2.0X.                       |

### `data/databricks_pricing/azure.yaml`

| Item                              | Estado atual               | Problema                                                                  |
| --------------------------------- | -------------------------- | ------------------------------------------------------------------------- |
| `serverless_compute.base_per_dbu` | 0.95                       | **WRONG**. Reais: Jobs=0.35, DLT=0.35, SQL=0.70, AP=0.75.                |
| `all_purpose_compute.standard`    | $0.40 no_photon            | Standard não existe; valor é fictício.                                    |
| Faltando                          | Lakebase, AI Gateway, etc. | 13+ SKUs novos não modelados.                                             |

### `data/databricks_pricing/aws.yaml`

Análogo ao Azure — mesmos problemas estruturais.

### `data/databricks_pricing/gcp.yaml`

**Não existe.** App diz "Multi-cloud" mas GCP é zero.

---

## Plano de PRs

### **PR 1 — Foundational refactor** (~600 LOC, ~1h review)

**Scope:** consertar estrutura sem inventar nada. Não adiciona SKUs novos — só ajusta os existentes pra preços corretos e remove ficção.

Arquivos:
- `data_agents/cost_engine/databricks.py`:
  - Remove `"standard"` de `Tier` Literal
  - Adiciona enum `CostUnit` para preparar suporte multi-unit
  - Levanta `ValueError` claro se tier=standard for passado, sugerindo migração pra premium/enterprise
  - Documenta no docstring: Azure Premium = AWS/GCP Enterprise
- `data/databricks_pricing/azure.yaml`:
  - Remove blocos `standard:` de all_purpose_compute e jobs_compute
  - Corrige `serverless_compute.base_per_dbu: 0.95` → estrutura por sub-tipo (jobs/dlt/sql/all_purpose)
  - Adiciona campo `last_verified_against_source: 2026-05-28` + URL específico por SKU
- `data/databricks_pricing/aws.yaml`: idem
- `tests/unit/test_cost_engine_databricks.py`:
  - Test: passar `tier="standard"` levanta `ValueError`
  - Test: serverless variants resolvem pra rates corretos
- `kb/databricks-pricing/parity-audit.md`:
  - Update Status section: PR 1 ✅

**Critério de aceitação:** todos os testes existentes passam (com migração de fixtures `tier=standard` → `tier=premium`); 0 SKUs novos; bug Serverless ($0.95 vs real $0.35/$0.70/$0.75) corrigido.

### **PR 2 — Serverless + Lakebase + GCP scaffold** (~800 LOC)

**Scope:** adiciona o que o user pediu explicitamente como "missing" no audit.

Arquivos:
- `data_agents/cost_engine/databricks.py`:
  - Refator `_resolve_dbu_rate` pra ser data-driven (lê tipo de unit do YAML, não if/elif por compute_type)
  - Adiciona suporte `cost_unit: cu_h` (Capacity Unit Hour) para Lakebase
  - Adiciona suporte `cost_unit: gb_month` (Database Storage)
  - Suporta `promo_until: <date>` field — engine aplica desconto se hoje < date, senão preço listado
- `data/databricks_pricing/azure.yaml` e `aws.yaml`:
  - Novo bloco `lakebase:` com autoscaling_per_cu_h, always_on_per_cu_h, storage_per_gb_month
  - Novo bloco `lakeflow_connect:` (Managed Connectors + Zerobus)
- NOVO `data/databricks_pricing/gcp.yaml`:
  - Scaffold completo com tier Premium+Enterprise, mesmas keys de aws.yaml
  - Mark pricing as `source: derived_from_aws` quando não temos confirmação GCP-específica
- UI (`data_agents/cost_app/databricks/app.py`):
  - Tab 1: opções selectbox de Serverless agora têm sub-variants (Jobs/DLT/SQL/All-Purpose)
  - Tab 8 (Catálogo): novo bloco Lakebase
- Testes: 6 novos no `test_cost_engine_databricks.py`

### **PR 3 — AI/ML completo** (~1500 LOC)

**Scope:** todos os SKUs AI/ML — esse é o mais pesado.

Arquivos:
- `data_agents/cost_engine/databricks.py`:
  - Suporte `cost_unit: m_tokens`, `cost_unit: dsu`, `cost_unit: question`, `cost_unit: answer`
  - Subschema por SKU permite per-model variants (Foundation Model + Proprietary Foundation Model)
  - Photon como SKU separada (não flag) — flag continua na UI mas resolve pra SKU correta
- Catalogs YAML — todos os 3 (azure/aws/gcp):
  - `model_serving:` (CPU + GPU + tabela DBU/h por GPU instance)
  - `foundation_model_serving:` (Pay-Per-Token + Provisioned Throughput + Batch + tabela por modelo)
  - `proprietary_foundation_model_serving:` (OpenAI + Anthropic + Gemini com per-model DBU rates)
  - `vector_search:` (Standard 2M + Storage Optimized 64M com DBU/h)
  - `ai_gateway:` (Guardrails $/M tok, Inference Tables $/GB, Usage Tracking $/GB)
  - `ai_functions:` (Parse + Extract + Classify, todos $/DBU)
  - `agent_bricks:` (Knowledge Assistant $/answer, Supervisor Agent $/DBU)
  - `agent_evaluation:` ($/M tok input/output, $/question synthetic)
  - `model_training:` (fine-tuning + forecasting, $/DBU)
  - `ai_runtime:` (A10 + H100, $/DBU)
- UI: novos tabs/sub-tabs no app.py:
  - "🧠 LLM Cost Calculator" — input tokens, output tokens, model dropdown, output em $/mês
  - "🔍 Vector Search Calculator" — units, hours, queries
  - "🤖 Agent Bricks Calculator" — answers/month + sub-agent breakdown
- Testes: ~30 novos

### **PR 4 — Platform + Storage + Sharing** (~400 LOC, fechar gaps restantes)

**Scope:** add-ons, storage, sharing, transfer — completa cobertura.

Arquivos:
- Catalogs YAML:
  - `default_storage:` (Default Storage $/DSU + tabela DSU per operation)
  - `data_transfer:` (Private Connectivity, Public Connectivity, Data Egress)
  - `managed_services:` (DQ Monitoring 2x DBU multiplier, FGAC, PO, Data Classification)
  - `platform_addons:` (Enhanced Security and Compliance — 15% Product Spend)
  - `clean_rooms:` (sem preço próprio, redireciona pra Jobs Serverless SKU)
  - `view_sharing:` (3 tiers de cobrança + Open Sharing $0.75)
  - `delta_share_sap_bdc:` (FREE)
- Cost engine: `% Product Spend` add-on aplica multiplicador no total
- UI: Tab 8 Catálogo mostra add-ons + warnings
- Testes: 8 novos

---

## Decisões já tomadas (baseadas em fatos extraídos das 25 páginas)

| Decisão                                                  | Justificativa                                                   |
| -------------------------------------------------------- | --------------------------------------------------------------- |
| `tier=standard` vira erro                                | Não existe oficialmente em nenhuma página                       |
| `Azure.premium == AWS.enterprise == GCP.enterprise`      | "The Premium tier on Azure Databricks corresponds to..."        |
| Photon como **SKU** + UI flag (não só flag)              | Hierarquia oficial: Jobs Compute vs Jobs Compute Photon         |
| Photon factor heterogêneo por SKU                        | Jobs/DLT=2.9X, All-Purpose=2.0X (confirmado nas FAQ)            |
| Serverless inclui compute                                | Confirmado em todas as páginas — fixed em PR já mergeado        |
| Promos com expiry virá campo `promo_until: <date>`       | 8 promos detectadas; engine resolve preço efetivo               |
| GCP segue mesma estrutura de AWS                         | Página `/sku-groups` confirma matriz idêntica + footnotes       |
| Unit types além de DBU                                   | CU·h, DSU, GB·month, GB, M-tokens, answer, question             |
| Per-model DBU rates pra Foundation Model                 | Capturado tabela completa em extracted-prices-raw.md            |

---

## Próximo passo

Implementar **PR 1** (foundational refactor) e abrir PR pra review antes de seguir pra PR 2.

PR 1 não adiciona SKU novo — apenas conserta o que está oficialmente errado (Standard tier inexistente, serverless rate $0.95 quando real é $0.35-$0.75). Risco baixo.
