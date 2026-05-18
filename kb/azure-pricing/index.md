# Knowledge Base — Azure Pricing & Cost Calculation

> Conhecimento operacional para o agent **azure-cost-calculator**. Consultar SEMPRE antes de calcular cenários novos.

## 1. Fonte de Verdade

| Item | Valor |
|---|---|
| API oficial | `https://prices.azure.com/api/retail/prices` |
| API version | `2023-01-01-preview` |
| Authentication | Nenhuma (público) |
| Calculadora UI | `https://azure.microsoft.com/pricing/calculator/` |
| Rate currency | A mesma que a calculadora usa (Microsoft FX rate diário) |
| Horas/mês padrão | 730 (= 365.25 ÷ 12 × 24) — não usar 720 |

## 2. Regiões Azure (arm region name)

Slugs comuns (use sempre minúsculo, sem espaços):

| Geografia | Slug |
|---|---|
| Brasil | `brazilsouth`, `brazilsoutheast` |
| EUA leste | `eastus`, `eastus2`, `centralus`, `southcentralus` |
| EUA oeste | `westus`, `westus2`, `westus3`, `westcentralus` |
| Europa | `northeurope`, `westeurope`, `francecentral`, `germanywestcentral`, `uksouth` |
| Ásia-Pacífico | `eastasia`, `southeastasia`, `japaneast`, `australiaeast` |
| Global (não-regional) | `global` (use para Entra ID, DNS, etc.) |

> **Atenção:** preços variam ±30% entre regiões. Brazil South costuma ser ~15% mais caro que East US para a maioria dos PaaS. Comparar regiões pode ser decisão financeira relevante.

## 3. Serviços e Mapeamento de `serviceName` na API

Match exato (case-sensitive):

| Categoria | `serviceName` na API |
|---|---|
| Compute VMs | `Virtual Machines` |
| Functions | `Functions` |
| App Service | `Azure App Service` |
| Storage Account | `Storage` |
| Cosmos DB | `Azure Cosmos DB` |
| SQL Database | `SQL Database`, `SQL Managed Instance`, `SQL Server` |
| Key Vault | `Key Vault` |
| Monitor / Log Analytics | `Azure Monitor` |
| Application Insights | `Azure Monitor` (mesma família) |
| App Gateway | `Application Gateway` |
| Firewall | `Azure Firewall` |
| Bastion | `Azure Bastion` |
| VPN Gateway | `VPN Gateway` |
| Private Link | `Private Link` |
| AI Search | `Azure Cognitive Search` (nome legado na API!) |
| Azure OpenAI | `Azure OpenAI` |
| Cognitive Services (genérico) | `Cognitive Services` |
| Microsoft Fabric | `Microsoft Fabric` |
| Backup | `Backup` |
| Site Recovery | `Site Recovery` |
| Defender for Cloud | `Microsoft Defender for Cloud` |
| Sentinel | `Microsoft Sentinel` |
| Purview | `Microsoft Purview` |

> **Pegadinha:** `Azure AI Search` (nome marketing) vira `Azure Cognitive Search` na API. Se a tool não achar com o primeiro, tente o segundo.

## 4. Pricing Types

| `priceType` | Significado |
|---|---|
| `Consumption` | Pay-as-you-go (PAYG) — preço default |
| `Reservation` | Reserved Instance (combinado com `reservationTerm`) |
| `DevTestConsumption` | Tier de Dev/Test (descontado, exige Visual Studio license) |

E `reservationTerm`:
- `1 Year` — 1 ano de commit
- `3 Years` — 3 anos de commit

## 5. Unit of Measure — Como Calcular Mensal

Mapping do `unitOfMeasure` → multiplicador pra custo mensal:

| `unitOfMeasure` | Cálculo |
|---|---|
| `1 Hour` | `unit_price × 730 × quantity` |
| `1 Month` ou `1/Month` | `unit_price × quantity` |
| `1 GB-Month` | `unit_price × quantity` (qty em GB) |
| `1 GB` | `unit_price × quantity` (consumo único — geralmente egress) |
| `100 Operations` | `unit_price × (quantity ÷ 100)` |
| `1 Million Operations` | `unit_price × (quantity ÷ 1_000_000)` |
| `1 vCPU-Hour` | `unit_price × 730 × num_vcpus` |

> A tool `estimate_monthly_cost` aplica essa lógica automaticamente para "hour"; outras unidades retornam o `unit_price × quantity` direto.

## 6. Bundles e Inclusões (CRITICAL — sem isso o custo fica dobrado)

Quando um SKU **inclui** sub-recursos, NÃO adicionar separadamente:

| SKU principal | Inclui (não cobrar à parte) |
|---|---|
| **Azure AI Search Standard S1** | 25 GB de storage + 12 search units com semantic ranker |
| **Azure AI Search Standard S2** | 100 GB de storage + 36 search units |
| **Azure AI Search Standard S3** | 200 GB de storage + 36 search units |
| **Microsoft Fabric F2/F4/F8…** | Power BI Premium capacity (NÃO comprar Power BI Pro por user) |
| **Microsoft Fabric F-SKU** | OneLake storage até 10× capacity units em GB |
| **App Service Premium** | SSL certificate + custom domain |
| **Cosmos DB Provisioned (RU)** | Storage até 25 GB grátis incluso na RU |
| **Application Gateway WAF v2** | WAF rules + TLS termination |
| **Azure Firewall** | DNS proxy + IDPS (Premium) |
| **Key Vault Premium** | HSM-backed keys + soft-delete + purge protection |

> Sempre que aparecer um destes SKUs no input, validar com o usuário ou nas instructions se ele já não está esperando o bundle.

## 7. Reservations vs Savings Plans

**Reservations (RI):**
- Commit a um SKU específico (ex: `Standard_D4s_v3` em East US)
- 1 ano: ~30% desconto vs PAYG
- 3 anos: ~50-60% desconto vs PAYG
- Pra: VMs, Cosmos DB Provisioned, SQL DB, App Service, Synapse
- Quebrar contrato: penalidade ou cancelamento parcial

**Savings Plans:**
- Commit a um valor $/hora (flexível entre SKUs de compute)
- 1 ano: ~20% desconto
- 3 anos: ~40% desconto
- Pra: compute (VMs, AKS, ACI, Functions Premium)
- Mais flexível que RI mas menor desconto

**Regra:** se workload é previsível e SKU é fixo → RI. Se workload é variável → Savings Plan.

## 8. Currency Conversion

A Microsoft atualiza os preços em outras currencies diariamente, mas **não é taxa de câmbio real-time** — é uma taxa aplicada pela Microsoft pra mês. Pequenas variações vs Banco Central são esperadas (0.1-0.5%).

**O agent deve sempre:**
1. Buscar preço na currency do usuário diretamente (não converter do USD)
2. Se conversão for necessária, usar `azure_pricing_currency_convert` (derivado de SKU de referência)
3. Exibir rate usado pro usuário poder auditar

## 9. EA / MCA Negotiated Pricing

A Retail Prices API mostra **preços públicos**. Empresas grandes (corporativas, FAANG, governo) normalmente têm:
- **EA (Enterprise Agreement)**: contrato anual com descontos negociados (típico 5-30%)
- **MCA (Microsoft Customer Agreement)**: contrato direto Microsoft

> Se usuário menciona "temos contrato com Microsoft", aplicar discount % informado por ele sobre o retail. Sem informação, assumir retail e mencionar o caveat.

Para preço EA exato, exportar o "Price Sheet" do portal Azure (Cost Management → Pricing → Download).

## 10. Casos Especiais

### 10.1 Marketplace third-party
SKUs do Marketplace (Oracle, SAP, Cloudera, etc.) NÃO estão na Retail Prices API standard. Endpoint diferente: `https://prices.azure.com/api/retail/prices?$filter=serviceFamily eq 'Marketplace'`. **Documentar como limitação** ao usuário.

### 10.2 Spot pricing
VMs Spot têm preço flutuante por segundo. A API retorna preço "Low Priority" como aproximação, mas valor real varia. Documentar como "preço médio".

### 10.3 Outbound bandwidth (egress)
Cobrança escalonada (free tier de 100GB/mês outbound, depois faixas). A API retorna preço da primeira faixa — pra cenários high-egress, calcular faixas manualmente.

### 10.4 Cross-region replication
Cosmos DB / SQL DB / Storage GRS: réplica em segunda região cobra storage 2× + bandwidth de replicação. Tool `estimate_monthly_cost` precisa receber explicitamente o resource secundário.

## 11. Padrão de Output (Reportagem para usuário)

Sempre incluir no final do relatório:

```
**Fonte:** Azure Retail Prices API
**Consultado em:** 2026-05-15T14:30:00Z (UTC)
**Link calculadora oficial:** <URL gerada por generate_calculator_url>
**Caveats:**
  - Preços retail públicos; descontos EA/MCA NÃO inclusos.
  - Currency rate: Microsoft FX (atualizado periodicamente).
  - Bundle pricing: <listar quais bundles foram aplicados>
```

## 12. Skills Operacionais Associadas

- `skills/finops/azure-pricing/SKILL.md` — playbook detalhado de uso do MCP em cenários comuns
- `skills/patterns/cost-modeling/SKILL.md` — modelagem de TCO 36 meses, projeções de uso

## 13. Heurísticas de Padrão de Arquitetura (USAR pra construir cenários)

> ⚠️ **Esta seção é CRÍTICA.** Define como o agent escolhe SKUs/tiers a partir de descrição em linguagem natural. Sem aplicar essas heurísticas, o agent vai sobre-estimar ou sub-estimar custos drasticamente.

### 13.1 Disambiguation de termos ambíguos

| Termo do usuário | Significa |
|---|---|
| **"Foundry"** (sem qualificador) | **SEMPRE Azure AI Foundry** (plataforma Microsoft). NUNCA Palantir Foundry. |
| **"Palantir Foundry"** (explícito) | Plataforma da Palantir — third-party Marketplace, fora do escopo da Retail API |
| "OpenAI" | Tokens de modelos OpenAI (gpt-*, embedding-*) deployados via Foundry → cobrados sob `serviceName: Azure OpenAI` |
| "AI Search" / "Cognitive Search" / "Foundry IQ" | `serviceName: Azure Cognitive Search` na API |
| "Fabric" | `serviceName: Microsoft Fabric` |

### 13.2 Detecção de padrão de arquitetura

O agent escolhe entre 3 cenários-base:

**→ Enterprise Full** (~15 recursos, $2.500-$3.500/mês baseline) quando o usuário menciona:
- "produção", "enterprise", "corporativo", "completo"
- "compliance", "LGPD", "SOX", "auditoria"
- "Network Hub", "Firewall", "Bastion", "WAF"
- "Defender", "Sentinel", "Purview"
- "DR", "disaster recovery", "multi-region"
- Combinação Foundry + AI Search + Fabric + Network + Security

**→ Simple PoC** (3-5 recursos, $300-$500/mês) quando o usuário menciona:
- "PoC", "prova de conceito", "MVP", "validação"
- "simples", "básico", "teste"
- Lista curta de recursos (1-3 serviços)

**→ Construção custom** quando o usuário lista recursos específicos que não casam com padrão acima.

### 13.3 Escala de SKUs por volume (CRÍTICO — não sobre-escalar)

#### Foundry tokens (gpt-4.1-mini)

| Volume queries/dia | Tokens/mês total | Split input:output |
|---|---|---|
| 100-500 | 5-25M | 70% in / 30% out |
| 500-1.000 | 50-105M | 75% in / 25% out |
| 1.000-5.000 | 100-525M | 75% in / 25% out |
| 5.000-50.000 | 500M-5B | 80% in / 20% out |

Cálculo: `queries × 30 dias × ~3500 tokens/query` (RAG médio com chunks)

#### Microsoft Fabric tier (NÃO escalar agressivamente!)

| Volume Spark workload | Tier sugerido | $/mês |
|---|---|---|
| **Light** (read-only dashboards, < 1.000 queries/dia) | **F2** com pause/resume | ~$78 ativo |
| **Medium** (ETL diário + dashboards, 1.000-5.000 queries/dia) | **F4** | $525 |
| **Heavy** (ETL contínuo + ML, 5.000-20.000 queries/dia) | **F8** | $1.050 |
| **Very heavy** (multi-workspace, 20.000+ queries/dia) | **F16** | $2.100 |
| **Petabyte-scale** (raríssimo, casos massivos) | F32+ | $4.200+ |

> ⚠️ **F64 ($13.000/mês) é overkill em 99% dos casos.** Só sugerir se cliente já indicar workload Petabyte-scale explícito.

#### Azure AI Search tier

| Volume queries/dia | Tier | Inclui | $/mês |
|---|---|---|---|
| < 100 (PoC) | Basic | 2 GB, sem semantic ranker | $75 |
| 100-5.000 | **Standard S1** | 25 GB + semantic ranker | $324 (brazilsouth) |
| 5.000-50.000 | Standard S2 | 100 GB + semantic ranker | $1.300 |
| 50.000+ | Standard S3 ou Storage Optimized | 200 GB+ | $2.000+ |

#### Sentinel ingest

| Tamanho organização | Volume ingest/mês | $/mês (PAYG) |
|---|---|---|
| Pequena (< 100 users) | 10-50 GB | $20-100 |
| Média (100-1.000 users) | 100-300 GB | $200-600 |
| Grande (1.000+ users) | 500 GB+ | $1.000+ |

#### Log Analytics ingest (analog ao Sentinel)

| Verbosidade | Volume/mês | $/mês |
|---|---|---|
| Light (warnings only) | 5-15 GB | $11-35 |
| Normal | 30-100 GB | $70-230 |
| Heavy debug | 200+ GB | $460+ |

### 13.4 Bundles e Inclusões (NÃO duplicar)

| SKU Principal | Inclui (não cobrar à parte) |
|---|---|
| **Azure AI Search Standard S1** | 25 GB storage + 12 search units + semantic ranker |
| **Azure AI Search Standard S2** | 100 GB storage + 36 search units |
| **Microsoft Fabric F-SKU** | Power BI Premium capacity (NÃO comprar PBI Pro por user) |
| **Microsoft Fabric F-SKU** | OneLake storage até 10× CU em GB (incluso) |
| **Cosmos DB Provisioned RU** | 25 GB storage incluso |
| **Application Gateway WAF v2** | WAF rules + TLS termination + DNS proxy |
| **Azure Firewall Premium** | IDPS + TLS inspection + DNS proxy |
| **Key Vault Premium** | HSM-backed keys + soft-delete + purge protection |
| **Foundry resource** | Custo base $0 — só tokens dos modelos |

### 13.5 Cobertura regional de Azure OpenAI (fallback automático)

Azure OpenAI tem cobertura regional **incompleta**. Em `brazilsouth`, muitos modelos não estão na Retail API. Quando isso acontece, a Microsoft cobra os tokens via **deployment region** (geralmente eastus2 ou westeurope):

| Região | Cobertura OpenAI |
|---|---|
| eastus, eastus2 | ✅ Completa |
| westeurope, northeurope, francecentral | ✅ Completa |
| brazilsouth | ⚠️ **Parcial** — usar fallback eastus2 |
| centralindia, uaenorth | ⚠️ Parcial |

O MCP `azure_pricing_estimate_monthly_cost` faz fallback automático para `eastus2 → eastus → westeurope` quando o serviço é Azure OpenAI/Cognitive Services. Sinaliza no output com flag `cross_region_pricing: true`.

### 13.6 Componentes fora da Retail API (mencionar mas não somar automaticamente)

| Componente | Custo típico | Como tratar |
|---|---|---|
| Microsoft Copilot Studio license | $200/mês/tenant | Listar como "Componente fora do escopo da Retail API — adicionar separadamente" |
| DDoS Protection Standard | $2.944/mês tenant-wide | Idem — geralmente compartilhado |
| Entra ID P2 | $0 (incluso M365 E5) | Não cobrar se cliente já tem |
| Private DNS Zones | ~$5/mês | Mínimo, mencionar |

### 13.7 Mapeamento `serviceName` (case-sensitive na API)

| Marketing name | `serviceName` na Retail API |
|---|---|
| Azure AI Search | `Azure Cognitive Search` (nome legado!) |
| Azure OpenAI (qualquer modelo) | `Azure OpenAI` |
| Microsoft Fabric | `Microsoft Fabric` |
| Cosmos DB | `Azure Cosmos DB` |
| Storage Account | `Storage` |
| Key Vault | `Key Vault` |
| Application Gateway | `Application Gateway` |
| Azure Firewall | `Azure Firewall` |
| Bastion | `Azure Bastion` |
| Log Analytics | `Azure Monitor` |
| Defender for Cloud | `Microsoft Defender for Cloud` |
| Sentinel | `Microsoft Sentinel` |

---

## 14. Patterns Suplementares (consulte via Read quando relevante)

Estes arquivos NÃO são injetados automaticamente, mas podem ser lidos pelo agent via Read tool quando o contexto exigir:

| Pattern | Quando consultar via Read |
|---|---|
| `kb/azure-pricing/patterns/bundle-skus.md` | Detalhamento de cada bundle, com tabelas exaustivas |
| `kb/azure-pricing/patterns/openai-foundry-billing.md` | Discovery-first pattern + product naming variations + PTU vs Standard |
| `kb/azure-pricing/templates/enterprise-full.json` | Template-base estruturado pra cenário enterprise-full |
| `kb/azure-pricing/templates/simple-poc.json` | Template-base estruturado pra cenário PoC |

## 13. Referências Externas

- [Azure Retail Prices API docs](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices)
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/)
- [Azure regions and pricing](https://azure.microsoft.com/regions/services/)
- [Reservation vs Savings Plan comparison](https://learn.microsoft.com/azure/cost-management-billing/reservations/save-compute-costs-reservations)
