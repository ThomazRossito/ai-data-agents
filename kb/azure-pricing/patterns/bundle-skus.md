# Pattern — Bundle SKUs (o que está incluído em cada serviço)

> Referência detalhada para o agent `azure-cost-calculator` evitar dupla cobrança de recursos que já vêm incluídos no tier principal.

## Azure AI Search

| Tier | Storage Incluído | Search Units | Semantic Ranker | Replicas | Custo/mês USD |
|---|---|---|---|---|---|
| Free | 50 MB | 3 índices | ❌ | ❌ | $0 (dev/test) |
| Basic | 2 GB | 1 SU | ❌ | até 3 | ~$75 |
| Standard S1 | 25 GB | 12 SU | ✅ (1k free queries/mês depois $4/1k) | até 12 | ~$250 |
| Standard S2 | 100 GB | 36 SU | ✅ | até 12 | ~$1.000 |
| Standard S3 | 200 GB | 36 SU | ✅ | até 12 | ~$2.000 |
| Storage Optimized L1 | 1 TB | 12 SU | ✅ | até 3 | ~$3.000 |
| Storage Optimized L2 | 2 TB | 24 SU | ✅ | até 3 | ~$6.000 |

> **Não cobrar Storage Account separado** quando AI Search S1+ está em uso (o índice + 25GB está incluído).

## Microsoft Fabric

| Tier | Capacity Units | OneLake Storage Incluso | Power BI | Custo/mês USD |
|---|---|---|---|---|
| F2 | 2 CU | Até 20 GB | Premium incluído | ~$262 |
| F4 | 4 CU | Até 40 GB | Premium incluído | ~$525 |
| F8 | 8 CU | Até 80 GB | Premium incluído | ~$1.050 |
| F16 | 16 CU | Até 160 GB | Premium incluído | ~$2.100 |
| F32 | 32 CU | Até 320 GB | Premium incluído | ~$4.200 |
| F64 | 64 CU | Até 640 GB | Premium incluído | ~$8.410 |

> **Não cobrar Power BI Pro por user separadamente** quando Fabric F-SKU está ativo.
> **OneLake storage** acima do incluído cobra ~$0.023/GB-month adicional.

## App Service

| Tier | SSL Cert | Custom Domain | Backup | VNet Integration |
|---|---|---|---|---|
| Free F1 | ❌ | ❌ | ❌ | ❌ |
| Basic B1 | ✅ (self-managed) | ✅ | ❌ | ❌ |
| Standard S1 | ✅ | ✅ | Manual | ✅ |
| Premium P1v3 | ✅ | ✅ | Auto | ✅ + Private Link |
| Isolated I1v2 | ✅ | ✅ | Auto | ✅ App Service Environment |

## Cosmos DB

| Mode | Storage Incluso | Outras inclusões |
|---|---|---|
| Provisioned (RU/s) | 25 GB grátis (depois $0.25/GB-month) | Backup periódico 8h grátis |
| Serverless | 1 GB grátis (depois $0.25/GB-month) | Backup periódico |
| Autoscale | Mesma do Provisioned | Continuous backup pago à parte ($0.20/GB-month) |

> Multi-region writes: cobra 2× RU/s + bandwidth de replicação.

## Application Gateway

| SKU | WAF | TLS | Auto-scale | DDoS Standard |
|---|---|---|---|---|
| Standard V2 | ❌ | ✅ | ✅ | Compatível (não incluso) |
| WAF V2 | ✅ (OWASP rules + custom) | ✅ | ✅ | Compatível (não incluso) |

> DDoS Protection Standard é tier separado ($2.944/mês, geralmente tenant-wide).

## Azure Firewall

| Tier | TLS Inspection | IDPS | DNS Proxy | Threat Intel |
|---|---|---|---|---|
| Standard | ❌ | ❌ | ✅ | Alert only |
| Premium | ✅ | ✅ | ✅ | Alert + Deny |

## Key Vault

| Tier | HSM-backed | Soft Delete | Purge Protection | Audit Logs |
|---|---|---|---|---|
| Standard | ❌ | ✅ | Opcional | ✅ (90 dias) |
| Premium | ✅ (FIPS 140-2 L3) | ✅ | Opcional | ✅ (90 dias) |

## Azure OpenAI / Foundry

Foundry **Basic Setup**: Cosmos DB + Storage + AI Search gerenciados internamente. Custo zero adicional.

Foundry **Standard Setup**: Cosmos DB + Storage + AI Search ficam na **sua subscription** (compliance) — esses custos são incrementais e devem ser somados ao Foundry tokens.

Modelos OpenAI (deployados via Foundry):
- **Standard PAYG**: pay-per-token, sem limite mas sem SLA throughput
- **PTU (Provisioned Throughput Units)**: reserva capacidade hora/mês, ~$50/PTU/hora (varia por modelo)

## VMs — sempre cobrar separado

VMs **não bundlam** storage/network. Adicionar separadamente:
- Disco OS (Standard SSD E10 ~128GB → ~$8/mês; Premium P10 → ~$20/mês)
- Bandwidth outbound (100 GB free, depois faixas)
- Public IP (Standard ~$3.65/mês)
- VNet Peering (~$0.01/GB processado)

---

## Anti-pattern: Duplicação Comum

❌ "AI Search Standard S1 + Storage Account 25GB" → DUPLO (S1 já inclui)
❌ "Fabric F2 + Power BI Pro 30 users" → DUPLO (F2 inclui PBI Premium)
❌ "Application Gateway WAF + WAF subscription" → DUPLO (WAF v2 já é WAF)
❌ "Cosmos DB Provisioned 400 RU + Storage 5GB" → DUPLO (até 25GB incluso)

✅ "AI Search Standard S1 (25GB index incluso)"
✅ "Fabric F2 (Power BI Premium incluso, sem PBI Pro adicional)"
✅ "Application Gateway WAF v2 (WAF rules + TLS incluso)"
