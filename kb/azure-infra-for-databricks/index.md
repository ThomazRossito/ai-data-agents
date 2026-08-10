---
domain: azure-infra-for-databricks
updated_at: 2026-07-22
agents: [azure-cost-calculator, databricks-cost-calculator]
source: "Azure Retail Prices API (armRegionName-scoped) + CI&T greenfield reference patterns"
---

# Knowledge Base — Azure Infra for Databricks (Greenfield)

> **Por que este KB existe:** num deploy Databricks greenfield (do zero), a camada
> de infraestrutura Azure que HOSPEDA o Databricks — vNet, NAT Gateway, Private
> Endpoints, Log Analytics, Key Vault, Firewall, Defender — **não é Databricks** e
> historicamente ficava fora da estimativa de custo. Num caso enterprise real
> essa camada representa **35-45% do custo total**. Este KB dá o sizing de
> referência para não deixar esse custo invisível.

## 1. Fonte de Verdade

| Item | Valor |
|---|---|
| API oficial | `https://prices.azure.com/api/retail/prices?$filter=serviceName eq '<svc>' and armRegionName eq '<region>'` |
| Modo de consumo | Runtime via MCP `azure_pricing` (real) — NUNCA hardcode sem verificar data |
| Regiões verificadas | `southeastasia` (Singapore), 2026-07 |
| Owner do sizing | CI&T FinOps reference (yellow = revisar com cliente) |

## 2. Regra de ativação

Acione este KB sempre que:
- A descrição do usuário menciona **"greenfield", "do zero", "implementação nova", "N ambientes"**
- O `azure-cost-calculator` for chamado para modelar a infra de suporte a um workload Databricks
- O workflow `WF-06 Greenfield` estiver rodando

## 3. Enterprise Reference Stack — por ambiente

Base para **1 workspace Databricks**. Repetir por ambiente (PROD, DEV, UAT, Sandbox).
Preços = Azure Retail Prices API, `southeastasia`, 2026-07 (USD).

### 3.1 Networking

| Recurso | Qty/env | Meter | $ unit | Sizing default |
|---|---|---|---|---|
| NAT Gateway | 1 | Resource-hour | $0.045/h | 24×7 = 730h |
| NAT Gateway | 1 | Data processed | $0.045/GB | 500 GB (dev) a 2 TB (PROD)/mo |
| Static Public IP | 2 | Per-hour | $0.005/h | 1 for NAT + 1 reserved |
| Private Endpoint | 6-8 | Per-hour | $0.01/h | frontend, backend, control-plane, 3× ADLS, KV, ACR |
| Private Endpoint | 6-8 | Data processed | $0.02/GB (in+out) | ~200 GB/PEP/mo |
| VNet Peering | 1 | Intra-region in+out | $0.02/GB | 50-100 GB/mo (hub-spoke) |
| Private DNS zone | 5 | Per zone/mo | $0.50 | privatelink.dfs/.blob/.databricks/.vault/.file |

### 3.2 Observability & Security

| Recurso | Qty/env | Meter | $ unit | Sizing default |
|---|---|---|---|---|
| Log Analytics ingest | 1 | GB ingested | $2.99/GB | 100-300 GB/mo (compliance-grade); 20-50 GB (minimal) |
| Log Analytics retention | 1 | GB/mo beyond 31d | $0.13/GB | 12mo = ingest × 12 |
| Key Vault ops | 1 | 10K ops | $0.03 | ~100K ops/mo |
| Key Vault certs | 1 | per renewal | $3.00 | 2-4 certs/mo |
| Defender for Servers P2 | opt | per node × hour | $0.02/h | enable if compliance-grade |
| Defender for SQL | opt | per instance/mo | $15.00 | if Lakebase/Postgres in scope |
| ADLS Gen2 write tx | 1 | 10K ops | $0.0715 | ~2.5M ops/mo (Delta writes) |
| ADLS Gen2 read tx | 1 | 10K ops | $0.0057 | ~50M ops/mo (queries/scans) |

### 3.3 Shared services (uma vez, não por env)

| Recurso | Meter | $ unit | Quando habilitar |
|---|---|---|---|
| Azure Firewall Standard | Deployment/hour | $1.25/h (~$912/mo) | Se NÃO houver firewall central no landing zone |
| Azure Firewall Standard | Data processed | $0.016/GB | Junto do deployment |
| Azure Bastion Standard | Per-hour | $0.192/h (~$140/mo) | Se precisa jump box para admin |
| Egress to internet | GB (100GB-10TB) | $0.12/GB | Power BI externo, exports, SaaS |
| ExpressRoute Gateway | Per-hour | $0.19/h (Azure-side) | Circuit precificado separado pelo provedor |

## 4. Sizing por ambiente (não-prod escala variable, não fixed)

Recursos **fixed** (NAT, PEPs, KV, DNS) NÃO escalam down entre ambientes — cada
workspace precisa do seu stack. Recursos **variable** (log ingest, egress, tx)
escalam com o workload.

| Env | % variable vs PROD | Notas |
|---|---|---|
| PROD | 100% | 200 GB Log/mo, 2 TB egress via NAT |
| Non-prod DEV | 30-50% | 60-100 GB Log/mo, 500 GB egress |
| Non-prod UAT | 30-50% | como DEV |
| Sandbox | 10-30% | 20-50 GB Log/mo, 200 GB egress; Bastion opcional off |

## 5. Ordem de grandeza (sanity check)

Para 4 ambientes greenfield enterprise em `southeastasia`, com Firewall + Defender
+ Bastion habilitados, a camada Azure Infra fica tipicamente em **$5.500-6.500/mo**
(~40% de um total de ~$14k/mo quando somado ao Databricks compute + storage).

Se a estimativa de Azure Infra vier **abaixo de ~$3.000/mo para 4 ambientes
enterprise**, provavelmente está faltando: Firewall, Defender, log ingest realista
(≥100 GB/env), ou PEPs suficientes (≥6/env). Revisar antes de entregar.

## 6. Otimizações típicas (para responder "como reduzir?")

| Estratégia | Economia | Trade-off |
|---|---|---|
| Hub-spoke com NAT+Firewall compartilhado | -30% infra | Requer landing zone maduro |
| Log Analytics DCR filtering (drop verbose) | -40% Log Analytics | Perde alguns audit trails |
| Azure Firewall Basic vs Standard | -$693/mo | Perde TLS inspection, Threat Intel |
| Log retention 6mo vs 12mo | -50% retention | Compliance risk se exige 12mo |
| Non-prod sem Defender for Servers | -$116/mo | Perde compliance parity com PROD |

## 7. O que NÃO modelar (evitar superestimar)

- Tráfego Databricks ↔ ADLS Gen2 na MESMA região = **grátis** (não cobrar)
- Ingress de dados para o Azure = **grátis**
- Azure Private Link endpoint hours no Azure Databricks first-party: alguns
  charges são waived — confirmar em `data_transfer.private_connectivity_per_hour`
  (billed_azure: false no catalog)

## 8. Fontes

Ver `patterns/retail-api-queries.md` para as queries exatas por serviço.
Todas as URLs oficiais Microsoft em `concepts/pricing-sources.md`.
