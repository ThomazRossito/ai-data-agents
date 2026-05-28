---
title: Extração bruta de preços oficiais Databricks (raw)
domain: databricks-pricing
captured_at: 2026-05-28
source: navigation via Chrome MCP (Claude for Chrome) em www.databricks.com/product/pricing/*
captured_view: Premium tier, AWS cloud, default region (a menos que indicado)
note: |
  Defaults capturados na primeira navegação de cada URL.
  Para clouds/tiers alternativos: Azure tem só Premium oficialmente; "Azure Premium = AWS/GCP Enterprise" (fato confirmado em todas as páginas).
  GCP segue mesma estrutura de AWS (per /product/sku-groups).
  Enterprise tier no AWS/GCP é tipicamente 10–20% acima de Premium — varia por SKU; quando ambos foram capturados, registrado explicitamente.
  Photon SKU rate emission: 2.9X DBU rate vs. non-Photon (confirmado na lakeflow-jobs FAQ).
---

# Preços oficiais brutos por SKU

## 1. Lakeflow Jobs — `/product/pricing/lakeflow-jobs`

**View: Premium / AWS / default**

| SKU                | $ / DBU | Inclui compute? | Notes                                   |
| ------------------ | ------- | --------------- | --------------------------------------- |
| Jobs Classic       | 0.15    | ❌ separado     | Compute billed pelo cloud provider      |
| Jobs Serverless    | 0.35    | ✅ incluído     | Standard & Performance Optimized modes  |

Photon: DBU emission rate 2.9X vs non-Photon (aplicado em Jobs Classic Photon SKU).
Jobs Serverless tem Photon "automatically enabled" — não é configurável.
Jobs Serverless Standard: "up to 70% cheaper for some workloads than Performance Optimized mode" (heurística, não preço).

## 2. Lakeflow Spark Declarative Pipelines (DLT) — `/product/pricing/lakeflow-spark-declarative-pipelines`

**View: Premium / AWS / default**

| SKU                       | $ / DBU | Inclui compute? | Notes                                       |
| ------------------------- | ------- | --------------- | ------------------------------------------- |
| DLT Serverless            | 0.35    | ✅ incluído     | Standard & Performance Optimized modes     |
| DLT Classic Core          | 0.20    | ❌ separado     | SQL/Python pipelines                        |
| DLT Classic Pro           | 0.25    | ❌ separado     | + CDC                                       |
| DLT Classic Advanced      | 0.36    | ❌ separado     | + Data quality expectations + monitoring   |

Photon Classic: 2.9X DBU rate.
Serverless: Photon auto-enabled.

## 3. Databricks SQL — `/product/pricing/databricks-sql`

**View: Premium / AWS / default**

| SKU            | $ / DBU | Inclui compute? | Notes                                     |
| -------------- | ------- | --------------- | ----------------------------------------- |
| SQL Classic    | 0.22    | ❌ separado     | Self-managed warehouse                    |
| SQL Pro        | 0.55    | ❌ separado     | + Predictive I/O, ETL, ML/Python UDF      |
| SQL Serverless | 0.70    | ✅ incluído     | Includes cloud instance cost              |

Materialized Views & Streaming Tables em SQL: cobrado em **DLT Serverless rate** ($0.35/DBU), billed sob "Automated Serverless SKUs" — NÃO no SKU SQL.

## 4. Lakebase (Database Serverless) — `/product/pricing/lakebase`

**View: Premium / AWS / default. Disponível só AWS + Azure (sem GCP).**

| SKU                              | Preço        | Unidade           | Notes                                              |
| -------------------------------- | ------------ | ----------------- | -------------------------------------------------- |
| Lakebase Autoscaling Compute     | 0.092*       | $/CU·h            | includes cloud instance. CU = Capacity Unit       |
| Lakebase Always-On Compute (min) | 0.069*       | $/CU·h            | minimum usage tier (no scale-to-zero)             |
| Database Storage                 | 0.345        | $/GB·month        | Fault-tolerant distributed storage                 |

*PROMOTION: 50% off price shown until **2027-01-31** — full price = 2x above. Documentar como ambos no YAML (current promotional + listed). Engine deve usar `effective_until` opcional.

CU (Capacity Unit) é nova unidade — engine não suporta hoje. Precisa de UNIT_TYPE enum: {DBU·h, CU·h, GB·month, M-tokens, ...}.

## 5. Lakeflow Connect — `/product/pricing/lakeflow-connect`

**View: Premium / AWS / default**

| SKU                         | Preço  | Unidade | Free tier             | Notes                                |
| --------------------------- | ------ | ------- | --------------------- | ------------------------------------ |
| Managed Connectors          | 0.35   | $/DBU   | 100 DBU/workspace/day | Bills as Jobs Serverless / Auto-Serv |
| Zerobus Ingest              | 0.050* | $/GB    | -                     | Push event data direta no Delta Lake |

*PROMOTION: 50% off until **2026-09-01** — full = $0.10/GB.

Zerobus introduz nova unidade: **$/GB ingested**. Bills aparecem como "Jobs Serverless" ou "Automated Serverless" SKU.

## 6. Compute for Data Science (Interactive / All-Purpose) — `/product/pricing/datascience-ml`

**View: Premium / AWS / default**

| SKU                                | $ / DBU | Inclui compute? | Notes                                    |
| ---------------------------------- | ------- | --------------- | ---------------------------------------- |
| Classic All-Purpose Clusters       | 0.55    | ❌ separado     | Manual instance selection                |
| All-Purpose Serverless             | 0.75    | ✅ incluído     | Auto instance, enhanced autoscaler       |

Photon factor: **2X** vs non-Photon (diferente de Jobs/DLT 2.9X). Photon classic auto-enabled em Serverless.

## 7. Databricks Apps — `/product/pricing/databricks-apps`

**View: Premium / AWS / default**

| SKU            | $ / DBU | Inclui compute? | Notes                                              |
| -------------- | ------- | --------------- | -------------------------------------------------- |
| App Capacity   | 0.75    | ✅ incluído     | Medium app = 0.5 DBU/h, Large app = 1 DBU/h        |

Bills aparecem como "All-Purpose Serverless" ou "Interactive Serverless" SKU.

## 8. AI Gateway — `/product/pricing/ai-gateway`

**View: Premium / AWS / default**

| SKU              | Preço | Unidade   | Notes                                       |
| ---------------- | ----- | --------- | ------------------------------------------- |
| AI Guardrails    | 1.50  | $/M tok   | Filtra input/output                         |
| Inference Tables | 0.50  | $/GB      | Audit das chamadas — increments 1KB        |
| Usage Tracking   | 0.100 | $/GB      | API monitoring — increments 1KB             |

Novas unidades: **$/M tokens** (milhão), **$/GB**. Inference + Usage cobrados em incrementos de 1KB.

## 9. Agent Bricks — `/product/pricing/agent-bricks`

**View: Premium / AWS / default**

| SKU                  | Preço  | Unidade   | Notes                                                        |
| -------------------- | ------ | --------- | ------------------------------------------------------------ |
| Knowledge Assistant  | 0.150* | $/Answer  | Só answers que acessam KB. + ingest/parse/embed/VS billing  |
| Supervisor Agent     | 0.070* | $/DBU     | + cobranças de sub-agents nos preços nativos                 |

*PROMOTION: 50% off até **2026-06-30** — full = 2x acima.

Nova unidade: **$/Answer** (Knowledge Assistant). Setup/storage cobrados em SKUs subjacentes (Vector Search, Foundation Model Serving para embedding).

## 10. AI Functions — `/product/pricing/ai-functions`

**View: Premium / AWS / default**

| SKU                  | $ / DBU | Promo? | Notes                                            |
| -------------------- | ------- | ------ | ------------------------------------------------ |
| AI Parse Document    | 0.070*  | 50%off | Parse PDF/docs → Delta tables                    |
| AI Extract           | 0.070*  | 50%off | Extract estruturado de spark binary (após parse) |
| AI Classify          | 0.070*  | 50%off | Classify spark binary (após parse)               |

*PROMOTION: 50% off até **2026-06-30** — full = $0.14/DBU.

Bills aparecem como "Serverless Real-time Inference" SKU.

DBU consumption estimates (referência só):
- AI Parse: 10-90 DBU/1k pages (varia com complexity)
- AI Extract: 30-90 DBU/1k inputs
- AI Classify: 3-60 DBU/1k docs

## 11. Model Serving — `/product/pricing/model-serving`

**View: Premium / AWS / default**

| SKU         | $ / DBU | Inclui compute? | Notes                                              |
| ----------- | ------- | --------------- | -------------------------------------------------- |
| CPU Serving | 0.070   | ✅ incluído     | Bills per concurrent request                       |
| GPU Serving | 0.070   | ✅ incluído     | Bills per GPU instance/hour — tabela DBU/h abaixo  |

**GPU Serving DBU rates** (DBU/h por instance):

| Instance Size       | GPU config                       | DBU/h  |
| ------------------- | -------------------------------- | ------ |
| Small               | T4 ou equivalente                | 10.48  |
| Medium              | A10G x 1GPU ou equivalente       | 20.00  |
| Medium 4X           | A10G x 4GPU ou equivalente       | 112.00 |
| Medium 8x           | A10G x 8GPU ou equivalente       | 290.80 |
| Large 8X 40GB       | A100 40GB x 8GPU ou equivalente  | 538.40 |
| Large 8X 80GB       | A100 80GB x 8GPU ou equivalente  | 628.00 |

GPU custo/h efetivo = DBU/h × $0.070. Ex: A100 80GB×8 = 628 × 0.070 = $43.96/h.

Foundation models → usar **Foundation Model API** (próxima seção), não esse SKU.

## 12. Foundation Model Serving — `/product/pricing/foundation-model-serving`

**View: Premium / AWS / default**

| SKU                    | Preço | Unidade           | Notes                                      |
| ---------------------- | ----- | ----------------- | ------------------------------------------ |
| Pay-Per-Token Input    | 0.50  | $/M tokens        | Context ≤ 128K tokens                      |
| Pay-Per-Token Output   | 1.50  | $/M tokens        |                                            |
| Provisioned Throughput | 6.00  | $/hour/PT unit    | High throughput production. Per-minute     |
| Batch Inference        | 6.00  | $/hour/throughput | Auto-scales throughput bands               |

**Per-model DBU rates** (Pay-Per-Token + Provisioned Throughput):

| Model                | DBU/M input | DBU/M output | DBU/h (entry PT) | DBU/h (scaling PT) |
| -------------------- | ----------- | ------------ | ---------------- | ------------------ |
| Llama 4 Maverick     | 7.143       | 21.429       | 85.714           | 85.714             |
| Llama 3.3 70B        | 7.143       | 21.429       | 85.714           | 342.857            |
| Qwen 3 Next 80B      | 2.143       | 17.143       | 78.571           | 78.571             |
| GPT OSS 120B         | 2.143       | 8.571        | 71.429           | 71.429             |
| Gemma 3 12B          | 2.143       | 7.143        | 71.429           | 71.429             |
| Llama 3.1 8B         | 2.143       | 6.429        | 53.571           | 106.000            |
| GPT OSS 20B          | 1.000       | 4.286        | 53.571           | 53.571             |
| Llama 3.2 3B         | n/a         | n/a          | 46.429           | 92.857             |
| Llama 3.2 1B         | n/a         | n/a          | 42.857           | 85.714             |
| Qwen 3 0.6B Embedding| 0.286       | n/a          | 25.000           | 25.000             |
| GTE                  | 1.857       | n/a          | 20.000           | 20.000             |
| BGE Large            | 1.429       | n/a          | 24.000           | 24.000             |

Entry capacity: só Azure+AWS em US/Canada/Brasil para base models.
Fine-tuned models: cobrado igual ao base. Mas Entry capacity não disponível pra fine-tuned.

## 13. Proprietary Foundation Model Serving — `/product/pricing/proprietary-foundation-model-serving`

**View: Premium / AWS / OpenAI vendor / default region**

| SKU                    | $/DBU | Notes                          |
| ---------------------- | ----- | ------------------------------ |
| Pay-Per-Token          | 0.07  | Por DBU consumed pela request  |
| Batch Inference        | 0.07  |                                |

Vendors disponíveis no select: OpenAI, Anthropic, Gemini. **Os 3 têm mesmo $0.07/DBU**, diferença está nos DBU rates por modelo.

**OpenAI DBU rates (DBU / M tokens, Global Short context, key models):**

| Model               | Input    | Output    | Cache writes | Cache reads | Batch DBU/h |
| ------------------- | -------- | --------- | ------------ | ----------- | ----------- |
| GPT 5.5             | 71.429   | 428.571   | 71.429       | 7.143       | 214.286     |
| GPT 5.4/5.5 Pro     | 428.571  | 2,571.429 | 428.571      | 42.857      | 1,142.857   |
| GPT 5.4             | 35.714   | 214.286   | 35.714       | 3.571       | 192.857     |
| GPT 5.4 mini        | 10.714   | 64.286    | 10.714       | 1.071       | 107.143     |
| GPT 5.4 nano        | 2.857    | 17.857    | 2.857        | 0.286       | 71.429      |
| GPT 5 (base)        | 17.857   | 142.857   | 17.857       | 1.786       | 131.429     |
| GPT 5 mini          | 3.571    | 28.571    | 3.571        | 0.357       | 71.429      |
| GPT 5 nano          | 0.714    | 5.714     | 0.714        | 0.071       | 53.571      |
| GPT 5.2 Codex       | 25.000   | 200.000   | 25.000       | 2.500       | n/a         |
| GPT 5.1 Codex Max   | 17.857   | 142.857   | 17.857       | 1.786       | n/a         |

In-geo (regional) variant: ~10% uplift sobre Global Short.
Long context (GPT 5.4/5.5 Pro): ~2x uplift sobre Global Short.

Bills: AWS/GCP → "OpenAI Model Serving" SKU. Azure → ADI Service (precisa Azure Commit + Sales contact). Cada vendor tem sua SKU.

Anthropic e Gemini: estrutura idêntica ($0.07/DBU), tabelas DBU completas no site — TODO no follow-up se for necessário cobrir todos modelos.

## 14. Vector Search — `/product/pricing/vector-search`

**View: Premium / AWS / default**

| SKU                          | Compute $/h | Storage $/GB·mo | Capacity      | DBU/h |
| ---------------------------- | ----------- | --------------- | ------------- | ----- |
| Vector Search Standard       | 0.28        | 0.230 (30GB free) | 2M vectors/unit  | 4.00  |
| Vector Search Storage Opt.   | 1.28        | 0.046           | 64M vectors/unit | 18.29 |

Effective $/DBU US East = $0.07. AP regions = $0.088-$0.09/DBU (~25% uplift).

Bills aparecem como "Serverless Real-time Inference" SKU.

## 15. Agent Evaluation (MLflow) — `/product/pricing/agent-evaluation`

**View: Premium / AWS / default**

| SKU                              | Preço | Unidade        | Notes                       |
| -------------------------------- | ----- | -------------- | --------------------------- |
| Agent Evaluation Input           | 0.15  | $/M tokens     | Auto-assessment labels      |
| Agent Evaluation Output          | 0.60  | $/M tokens     |                             |
| Agent Evaluation Synthetic Data  | 0.35  | $/question     | Gera Qs sintéticas          |

Inclui compute. Nova unidade: **$/question**.

## 16. Foundation Model Training — `/product/pricing/foundation-model-training`

**View: Premium / AWS / default. Status: PREVIEW**

| SKU                           | $/DBU | Notes                                              |
| ----------------------------- | ----- | -------------------------------------------------- |
| Model Training - fine-tuning  | 0.65  | Inclui compute. DBU count varia com model + data  |
| Model Training - forecasting  | 0.65  | Inclui compute. DBU baseado em duração            |

DBU consumption refs (fine-tuning):
- Llama 3.3 70B: 225 DBU (10M words) → 11,000 DBU (500M words)
- Llama 3.1 8B: 100 DBU → 4,400 DBU
- Llama 3.2 1B: 25 DBU → 1,100 DBU

## 17. AI Runtime — `/product/pricing/ai-runtime`

**View: Premium / AWS / default. Status: PREVIEW. Disponível só AWS + Azure (sem GCP).**

| SKU              | $/DBU | Notes                                       |
| ---------------- | ----- | ------------------------------------------- |
| A10 On Demand    | 2.50  | Train/fine-tune smaller models, A10 GPUs    |
| H100 On Demand   | 7.00  | Train/fine-tune large models, H100 GPUs     |

Bills aparecem como "Model Training" SKU. DBU = GPU hours × tipo de GPU.

## 18. Platform Tiers & Add-ons — `/product/pricing/platform-addons`

**View: AWS (sem distinção de tier — esta página define as tiers)**

| Add-on                            | Premium | Enterprise                        |
| --------------------------------- | ------- | --------------------------------- |
| Enhanced Security and Compliance  | —       | **15% of Product Spend** (before discounts) |

Tier features (Premium vs Enterprise):
- Premium: Workspace, Performance, Governance básica
- Enterprise: + Advanced compliance and security for mission-critical data

Add-on Enhanced S&C: cobrado como **% do gasto base**, não SKU separado.

## 19. Managed Services — `/product/pricing/managed-services`

**View: Premium / AWS / default**

| SKU                              | $/DBU | Promo? | Notes                                                    |
| -------------------------------- | ----- | ------ | -------------------------------------------------------- |
| Data Quality Monitoring          | 0.35* | 50%off | Until **2026-08-01**. Powered by UC + serverless. DBU 2x multiplier! |
| Predictive Optimization          | 0.35  | —      | Auto-otimização de tabelas                              |
| Fine Grained Access Control      | 0.35  | —      | FGAC em Single User clusters                            |
| Data Classification              | 0.35  | —      | Detecta PII automaticamente                              |

*Data Quality Monitoring tem **multiplicador 2x DBU** — cada DBU consumido conta como 2 pra cobrança.

## 20. Data Transfer & Connectivity — `/product/pricing/data-transfer-connectivity`

**View: general (sem preço explícito; detalhe em docs do cloud).**

Connection types billed:

| Type                          | Unit                | Notes                                          |
| ----------------------------- | ------------------- | ---------------------------------------------- |
| Private Connectivity          | $/GB                | Per GB data processed                          |
| Private Connectivity Endpoint | $/hour              | Azure: waived indefinitely. AWS/GCP: ativo    |
| Public Connectivity           | $/GB                | Per GB data processed                          |
| Data Egress                   | $/GB                | Inter-AZ, inter-region, internet, cross-cloud |

Preços específicos: link "Databricks Data Transfer Pricing" leva a docs por cloud (não foi extraído nessa página). TBD se necessário.

## 21. Storage (Databricks Default Storage) — `/product/pricing/storage`

**View: Premium / AWS / default**

| SKU                       | Preço  | Unidade |
| ------------------------- | ------ | ------- |
| Default Storage           | 0.023  | $/DSU   |

DSU conversion:

| Operation               | Azure                       | AWS                           | GCP                           |
| ----------------------- | --------------------------- | ----------------------------- | ----------------------------- |
| Stored Data             | 1 DSU / GB·month            | 1 DSU / GB·month              | 1 DSU / GB·month              |
| Tier 1 Operations       | 0.3535 DSU / 1000 ops (Write) | 0.2174 DSU / 1000 ops (PUT/COPY/POST/LIST) | 0.2174 DSU / 1000 ops (Class A) |
| Tier 2 Operations       | 0.0226 DSU / 1000 ops (Read) | 0.0174 DSU / 1000 ops (GET/SELECT) | 0.0174 DSU / 1000 ops (Class B) |

Nova unidade: **DSU** (Databricks Storage Unit). 1 GB·month armazenado = 1 DSU = $0.023.

## 22. Clean Rooms — `/product/pricing/clean-rooms`

**Sem preço próprio** — cobrança via SKUs existentes:
- DBUs compute → **"Jobs Serverless Compute"** (AWS/GCP) ou **"Automated Serverless Compute"** (Azure)
- Storage → **"Databricks Storage"** SKU

Customers pagam consumo de Databricks resources from their Clean Rooms.

## 23. View Sharing — `/product/pricing/view-sharing`

**View: Premium / AWS / default**

| Cenário                                          | $/DBU   | Bills                                             |
| ------------------------------------------------ | ------- | ------------------------------------------------- |
| Recipients in same account                       | 0       | No incremental charge                             |
| Recipients in diff. account + Serverless Compute | 0       | No incremental charge                             |
| Recipients in diff. account + Classic Compute    | 0.75    | "All-Purpose Serverless" ou "Interactive Server." |
| Databricks → Open Sharing (non-DB user)          | 0.75    | "All-Purpose Serverless" ou "Interactive Server." |

## 24. Delta Share from SAP BDC — `/product/pricing/delta-share-sap-business-data-cloud`

**NO CHARGE** — gratuito.
- Data Sharing (BDC → Databricks): free
- Compute for data processing: no incremental charge sobre workload nativo

## 25. Beta Products — `/product/pricing/beta-products`

**Sem SKU/preço próprio** — beta products usam SKUs existentes:
- **Lakehouse Monitoring for GenAI**: cobrado via Serverless Workflows (compute) + Agent Evaluation (AI judges)

Beta products: sem SLA, não recomendado pra produção.

---

## Sumário cross-SKU de unidades de cobrança

| Unidade        | SKUs que usam                                                                                |
| -------------- | -------------------------------------------------------------------------------------------- |
| `$/DBU`        | Maioria — Jobs, DLT, SQL, All-Purpose, Apps, Model Serving, AI Functions, Managed Services, AI Runtime, Model Training |
| `$/CU·h`       | Lakebase Compute                                                                              |
| `$/GB·month`   | Lakebase Storage                                                                              |
| `$/GB`         | Zerobus Ingest, AI Gateway Inference Tables / Usage Tracking                                  |
| `$/M tokens`   | Foundation Pay-Per-Token, AI Gateway Guardrails, Agent Evaluation                             |
| `$/hour/unit`  | Foundation Provisioned Throughput, Batch Inference, Vector Search Compute                     |
| `$/Answer`     | Agent Bricks Knowledge Assistant                                                              |
| `$/question`   | Agent Evaluation Synthetic Data                                                               |
| `$/DSU`        | Default Storage (1 DSU = 1 GB·month armazenado ou X operations conforme tier)                |
| `% Product Spend` | Enhanced Security and Compliance add-on (15%)                                              |
| `FREE`         | Delta Share from SAP BDC, View Sharing entre same account, View Sharing via Serverless        |

---

## Notas sobre tier mapping (confirmado em TODAS as 24 páginas com tier toggle)

- AWS/GCP: **Premium** e **Enterprise** existem oficialmente.
- Azure Databricks: **só Premium oficialmente**. "The Premium tier on Azure Databricks corresponds to the Enterprise tier on AWS and GCP".
- **Standard tier não existe oficialmente em lugar nenhum** — não foi mostrado em nenhuma das 25 páginas. Catalog YAML atual está errado nesse campo.

## Promoções com expiry date capturadas

| SKU                              | Promo  | Expiry        |
| -------------------------------- | ------ | ------------- |
| Lakebase Autoscaling / Always-On | 50%off | 2027-01-31    |
| Zerobus Ingest                   | 50%off | 2026-09-01    |
| Agent Bricks Knowledge Assistant | 50%off | 2026-06-30    |
| Agent Bricks Supervisor Agent    | 50%off | 2026-06-30    |
| AI Parse Document                | 50%off | 2026-06-30    |
| AI Extract                       | 50%off | 2026-06-30    |
| AI Classify                      | 50%off | 2026-06-30    |
| Data Quality Monitoring          | 50%off | 2026-08-01    |

Engine YAML precisa suportar `promo_until: <date>` opcional pra preço efetivo vs preço listado.

## Photon factor por SKU (heterogêneo)

| SKU base                    | Photon DBU rate factor |
| --------------------------- | ---------------------- |
| Jobs Classic                | 2.9X                   |
| DLT Classic                 | 2.9X                   |
| All-Purpose Classic         | 2.0X                   |
| Jobs Serverless             | auto-on (não toggle)   |
| DLT Serverless              | auto-on (não toggle)   |
| All-Purpose Serverless      | auto-on (não toggle)   |

---

**Captura concluída em 2026-05-28.** 25/25 sub-páginas processadas. Todos os preços extraídos são "Premium / AWS / default region" salvo indicação em contrário. Enterprise é tipicamente similar ou ligeiramente superior por SKU — confirmação detalhada exige toggle adicional por página (TODO follow-up se houver gap específico).

