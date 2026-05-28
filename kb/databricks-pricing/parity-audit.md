---
title: Auditoria de Paridade — App vs Calculadoras Oficiais
domain: databricks-pricing
updated_at: 2026-05-28
sources:
  - https://www.databricks.com/product/sku-groups
  - https://www.databricks.com/product/pricing
  - https://azure.microsoft.com/en-us/pricing/details/databricks/
  - https://www.databricks.com/product/pricing/product-pricing/instance-types
status: in_progress
---

# Auditoria de Paridade — App vs Calculadoras Oficiais

> **Objetivo:** mapear cada SKU/tier/produto oficial das calculadoras Databricks, Azure e AWS contra o que o nosso `cost_app/databricks` cobre hoje. Identificar gaps e propor expansão.
>
> **Método:** `WebFetch` nas URLs oficiais (SSR-rendered onde possível) + complementação manual quando necessário. Sem invenção de preços.
>
> **Status:** auditoria estrutural completa (SKU group hierarchy). Preços específicos (USD/DBU·h) por SKU ainda pendentes — cada subpágina precisa fetch separado.

---

## 1. Sumário executivo dos GAPS

### 1.1 Tiers (Premium vs Standard)

| App atual | Oficial Databricks |
|---|---|
| Tiers `standard`, `premium`, `enterprise` | **Apenas Premium e Enterprise** existem — Standard NÃO consta na lista de SKUs oficiais |

**Implicação:** todas as referências a "Standard" no nosso catalog YAML estão **erradas**. Databricks descontinuou esse tier (ou nunca foi published como retail).

### 1.2 Compute types ausentes no App

SKUs oficiais que o App NÃO cobre hoje:

| SKU oficial | Status no App | Prioridade |
|---|---|---|
| **Jobs Serverless Compute** (Premium + Enterprise) | ❌ Não existe | 🔴 Alta — workload comum |
| **All-Purpose Serverless Compute** (Premium + Enterprise) | ❌ Não existe | 🔴 Alta — workload comum |
| **Jobs Light Compute** (Premium + Enterprise) | ❌ Não existe | 🟡 Média — legado |
| **Serverless SQL Compute** | ⚠️ Parcial (mapeado como `sql+serverless`) | 🟡 Renomear |
| **SQL Pro Compute** | ⚠️ Parcial (mapeado como `sql+pro`) | 🟢 Já cobre |
| **Database Serverless Compute** (Lakebase) | ❌ Não existe | 🟡 Média — produto novo |
| **Serverless Real-Time Inference** | ❌ Não existe | 🟡 Média (Model Serving) |
| **Model Training** | ❌ Não existe | 🟡 Média |
| **Clean Rooms Collaborator** | ❌ Não existe | 🟢 Baixa — uso especializado |
| **Security and Compliance** add-on | ❌ Não existe | 🟢 Baixa — flag add-on |
| **OpenAI/Anthropic/Gemini Model Serving** | ❌ Não existe | 🟡 Média — workload GenAI |
| **AI Gateway** | ❌ Não existe | 🟢 Baixa — beta |
| **Agent Bricks / Agent Evaluation** | ⚠️ App tem `mosaic_agent` mas raso | 🟡 Refinar |
| **AI Functions** | ❌ Não existe | 🟢 Baixa |
| **Vector Search** | ⚠️ App tem mas sem sub-tiers | 🟡 Refinar |
| **Foundation Model Serving / Proprietary** | ⚠️ App tem `model_serving` mas sem distinção | 🟡 Refinar |
| **Lakeflow Connect** (ingestão managed) | ❌ Não existe | 🟡 Média — novo |
| **Storage** (Databricks Storage SKU) | ❌ Não existe | 🟢 Baixa — add-on cobrança |
| **Data Transfer / Egress** | ❌ Não existe | 🟢 Baixa — secundário |

### 1.3 Photon como SKU separado (não flag)

O App trata Photon como flag boolean dentro do mesmo `compute_type`. **Na realidade**, Databricks lista Photon como SKU **SEPARADO** na hierarquia oficial:
- `Jobs Compute` e `Jobs Compute Photon` são SKUs distintas
- Mesma estrutura pra `All-Purpose Compute` e `DLT`
- Mantemos o toggle no App (UX), mas o engine precisa saber que são SKUs distintas pra cobrar corretamente

### 1.4 Estrutura cross-cloud

| Cloud | Cobertura oficial | App cobre? |
|---|---|---|
| **AWS** | Toda lista de SKUs (Premium + Enterprise) | ⚠️ Parcial via `aws.yaml` |
| **GCP** | Mesma estrutura, com `*` indicando "Iceberg only" e `**` "GCP Marketplace metered" | ❌ Não cobre GCP no App (só catalog YAML) |
| **Azure** | Pricing gerenciado pela Microsoft — só Model Serving aparece na lista DB | ⚠️ Parcial via `azure.yaml` |

**Implicação:** o App diz que cobre "Multi-cloud (Azure + AWS)" mas **nem AWS está completo**. **GCP** está zero.

---

## 2. Listagem completa de SKUs oficiais (extraída da página /product/sku-groups)

### 2.1 AWS Service-specific SKU groups

| SKU group | SKUs incluídos |
|---|---|
| **AWS Jobs Compute** | Premium Jobs Light, Enterprise Jobs Light, Premium Jobs, Enterprise Jobs |
| **AWS Jobs Compute Photon** | Premium Jobs Photon, Enterprise Jobs Photon |
| **AWS All-Purpose Compute** | Premium AP, Enterprise AP |
| **AWS All-Purpose Compute Photon** | Premium AP Photon, Enterprise AP Photon |
| **AWS SQL Compute** | Premium SQL, Enterprise SQL, Premium SQL Pro, Enterprise SQL Pro |
| **AWS DLT Compute** | Premium DLT Core/Pro/Advanced × Enterprise DLT Core/Pro/Advanced |
| **AWS DLT Compute Photon** | Mesma matriz × Photon |
| **AWS Serverless SQL Compute** | Premium + Enterprise |
| **AWS Jobs Serverless Compute** | Premium + Enterprise |
| **AWS All-Purpose Serverless Compute** | Premium + Enterprise |
| **AWS Security and Compliance** | Enhanced Security and Compliance (add-on) |
| **AWS Serverless Inference** | Premium + Enterprise |
| **AWS Model Training** | Premium + Enterprise |
| **AWS Data Transfer** | Public/Private/Inter-Region/Inter-AZ/Internet egress |
| **AWS Databricks Storage** | Databricks Storage SKU |
| **AWS Clean Rooms** | Premium + Enterprise Collaborator |
| **AWS OpenAI Model Serving** | Premium + Enterprise |
| **AWS Anthropic Model Serving** | Premium + Enterprise |
| **AWS Gemini Model Serving** | Premium + Enterprise |
| **AWS Database Serverless Compute** | Premium + Enterprise (Lakebase) |

### 2.2 GCP Service-specific SKU groups

Mesma estrutura do AWS, com pequenas variações de footnote (`*` = iceberg only; `**` = GCP Marketplace metered).

### 2.3 Azure SKU groups (na página)

Apenas 2 SKUs aparecem na página da Databricks:
- Azure OpenAI Model Serving (Premium)
- Azure Gemini Model Serving (Premium)

Pricing principal Azure Databricks é gerenciado pela Microsoft (https://azure.microsoft.com/pricing/details/databricks/).

### 2.4 MCT Model Training (cross-cloud)

- MCT Model Training On Demand
- MCT Model Training Res (reservation)
- MCT Model Training Hero Res

---

## 3. URLs de pricing oficiais (cada uma é uma sub-categoria)

Da página `/product/pricing/product-pricing/instance-types` extraí o sidebar com 20 sub-páginas distintas:

| Sub-página | URL | Cobertura App |
|---|---|---|
| Lakeflow Jobs | `/product/pricing/lakeflow-jobs` | ⚠️ Parcial (jobs_compute) |
| Lakeflow Spark Declarative Pipelines (DLT) | `/product/pricing/lakeflow-spark-declarative-pipelines` | ⚠️ Parcial (delta_live_tables) |
| Lakeflow Connect | `/product/pricing/lakeflow-connect` | ❌ Não cobre |
| Databricks SQL | `/product/pricing/databricks-sql` | ⚠️ Parcial (sql + tiers) |
| Lakebase | `/product/pricing/lakebase` | ❌ Não cobre |
| Compute for Data Science (Interactive) | `/product/pricing/datascience-ml` | ⚠️ Parcial (all_purpose_compute) |
| Databricks Apps | `/product/pricing/databricks-apps` | ❌ Não cobre |
| AI Gateway | `/product/pricing/ai-gateway` | ❌ Não cobre |
| Agent Bricks | `/product/pricing/agent-bricks` | ⚠️ Parcial (mosaic_agent) |
| AI Functions | `/product/pricing/ai-functions` | ❌ Não cobre |
| Model Serving | `/product/pricing/model-serving` | ⚠️ Parcial (model_serving) |
| Foundation Model Serving | `/product/pricing/foundation-model-serving` | ❌ Não cobre |
| Proprietary Foundation Model Serving | `/product/pricing/proprietary-foundation-model-serving` | ❌ Não cobre |
| Vector Search | `/product/pricing/vector-search` | ⚠️ Parcial (vector_search) |
| Agent Evaluation | `/product/pricing/agent-evaluation` | ❌ Não cobre |
| Foundation Model Training | `/product/pricing/foundation-model-training` | ❌ Não cobre |
| AI Runtime | `/product/pricing/ai-runtime` | ❌ Não cobre |
| Platform Tiers and Add-ons | `/product/pricing/platform-addons` | ❌ Não cobre |
| Managed Services | `/product/pricing/managed-services` | ❌ Não cobre |
| Data Transfer and Connectivity | `/product/pricing/data-transfer-connectivity` | ❌ Não cobre |
| Storage | `/product/pricing/storage` | ❌ Não cobre |
| Delta Share from SAP BDC | `/product/pricing/delta-share-sap-business-data-cloud` | ❌ Não cobre |
| Clean Rooms | `/product/pricing/clean-rooms` | ❌ Não cobre |
| View Sharing | `/product/pricing/view-sharing` | ❌ Não cobre |
| Beta Products | `/product/pricing/beta-products` | ❌ Não cobre |

---

## 4. Status atual da auditoria

### ✅ Concluído (2026-05-28)
- Estrutura SKU group hierarchy AWS + GCP (vinda da `/product/sku-groups`)
- Mapeamento de 25 sub-páginas de pricing oficiais
- Diff vs catalog YAML atual (gaps identificados em 1.2)
- **Fetch das 25 sub-páginas concluído** via Chrome MCP → `kb/databricks-pricing/extracted-prices-raw.md`
- **Estratégia de implementação** definida em `kb/databricks-pricing/implementation-strategy.md` (4 PRs)
- **PR 1 (foundational refactor) implementado**:
  - Engine: helper `validate_tier()` + warning quando `tier='standard'` é usado
  - YAML: `serverless_compute.base_per_dbu` corrigido de $0.95 (fictício) → $0.35 (real Jobs Serverless)
  - YAML: blocos `standard:` marcados com `_deprecated: true` + comentário explicativo
  - YAML: Azure premium/enterprise mapping documentado
  - billing_mock.py: PREMIUM_SERVERLESS_COMPUTE_* atualizado pra $0.35
  - 9 testes novos (`TestTierValidation` + `TestServerlessRateCorrection`)
  - 227 testes passando, ruff verde

### ✅ PR 2 implementado (2026-05-28, post-merge)
- **Engine**: `ComputeType` Literal expandido com `jobs_serverless`, `dlt_serverless`, `all_purpose_serverless`. `CloudName` Literal expandido com `"gcp"`.
- **YAMLs (azure + aws)**: Sub-types serverless com rates oficiais; bloco `lakebase` ($/CU·h, 2 promo prices); bloco `lakeflow_connect` (Managed Connectors + Zerobus); `serverless_compute` antigo agora com `_deprecated: true`; `photon_modeling.factor_by_sku` heterogêneo (2.9X Jobs/DLT, 2.0X All-Purpose).
- **gcp.yaml**: scaffold completo criado (350 LOC) — Premium+Enterprise, 7 regions, 25 GCE machine types, lakeflow_connect; Lakebase intencionalmente ausente (não disponível em GCP per oficial).
- **instance_prices.py**: + `_GCP_PRICES_USD_HOUR` mock (50 SKUs, 7 regions). Real-mode GCP é trabalho futuro (Google Cloud Billing API).
- **app.py**: Tab 1 selectbox de compute_type expandido com 3 novos serverless variants + DEPRECATED tag no antigo. Cloud Provider selectbox + "GCP Databricks (beta)". Tab 8 Catálogo mostra Lakebase + Lakeflow Connect blocks.
- **Tests**: +30 testes novos (TestServerlessSubTypes, TestGcpCatalog, TestLakebaseSchema, TestLakeflowConnectSchema). 260 testes do escopo cost passam.

### ✅ PR 3 implementado (2026-05-28, post-merge PR 2)
- **Catalogs (azure + aws + gcp)**: 10 novos blocos AI/ML top-level adicionados nos 3:
  - `model_serving` (CPU + GPU + tabela DBU/h por size: T4=10.48 → A100 80GB×8=628)
  - `foundation_model_serving` (Pay-Per-Token $0.50/$1.50 + PT $6/h + Batch $6/h + 12 modelos com per-model DBU rates)
  - `proprietary_foundation_model_serving` (OpenAI 10 modelos GPT 5.x + Anthropic/Gemini stubs)
  - `vector_search_v2` (Standard 2M + Storage Optimized 64M)
  - `ai_functions` (Parse + Extract + Classify, $0.07/DBU promo até 2026-06-30)
  - `ai_gateway` (Guardrails $1.50/M tok + Inference Tables + Usage Tracking)
  - `agent_bricks` (Knowledge Assistant $0.15/answer + Supervisor $0.07/DBU, promo até 2026-06-30)
  - `agent_evaluation` (tokens + $0.35/question synthetic)
  - `model_training` (fine-tuning + forecasting $0.65/DBU + DBU estimates Llama)
  - `ai_runtime` (A10 $2.50 + H100 $7.00; só AWS + Azure)
- **app.py**: Tab 8 Catálogo expandida com 10 seções dataframe (cada uma com promo dates + source URL)
- **Photon SKU**: documentado heterogeneamente em `photon_modeling.factor_by_sku` (PR 2). Engine continua com flag — refactor estrutural completo fica pra PR 5+
- **Tests**: +99 (TestAiMlSkusPresent parametrizado 10 blocks × 3 clouds + classes por bloco). 169 testes do cost_engine_databricks.py passam, 287 do escopo cost. ruff format + check verdes.

### ⏳ Pendente (PR 4)
- **PR 4** (~400-600 LOC): Default Storage (DSU + per-operation), Data Transfer (Private/Public/Egress), Managed Services (DQ Monitoring com 2x DBU mult, Predictive Optimization, FGAC, Data Classification), Platform Add-ons (Enhanced Security 15% of Product Spend), Clean Rooms, View Sharing (3 tiers + Open Sharing), Delta Share SAP BDC (FREE)
- Captura Anthropic + Gemini per-model DBU tables (escopo PR 4 ou separado)
- Real-mode GCP via Google Cloud Billing API (escopo PR 4 ou separado)
- Engine refactor pra modelar scenarios AI/ML (LLMScenario, VectorSearchScenario) — escopo PR 5+

---

## 5. Limitações conhecidas

- **Calculadoras client-rendered:** `databricks.com/product/pricing` e Azure pricing são SPA — `WebFetch` retorna shell. Página `/product/sku-groups` foi exceção (HTML SSG completo).
- **Preços por região:** mesma SKU varia de preço entre regiões. Catalog YAML atual usa só 1 valor "base" por SKU.
- **Negotiated discounts:** preços listados são retail. Clientes enterprise geralmente pagam menos.
- **Mudanças frequentes:** Databricks lança features novas mensalmente — auditoria é snapshot, não permanente.

---

## 6. Próximas decisões pro usuário

Baseado nos gaps identificados, 3 níveis de cobertura possíveis:

### Mínimo viável (resolve 80% dos casos pré-venda)
- Adicionar Jobs Serverless Compute + All-Purpose Serverless Compute
- Adicionar tier Premium/Enterprise correto (remover Standard)
- Adicionar Lakebase (Database Serverless) — produto novo importante
- ~600 LOC

### Cobertura média
- Tudo do mínimo + Model Serving (Foundation/OpenAI/Anthropic/Gemini)
- + Vector Search com sub-tiers
- + Agent Bricks completo
- ~1.500 LOC

### Cobertura total
- Tudo das categorias acima + Clean Rooms + Data Transfer + Storage + Security add-ons + Lakeflow Connect + AI Gateway + AI Functions
- ~3.000 LOC

**Próximo passo recomendado:** user decide nível de cobertura → eu faço fetch das sub-páginas relevantes pra extrair preços → atualizo catalog YAML + app.py.
