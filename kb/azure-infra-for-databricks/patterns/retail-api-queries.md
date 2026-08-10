# Pattern — Azure Retail Prices API queries for Databricks infra

> Queries exatas para buscar cada recurso de infra em runtime. Todas usam a API
> pública `https://prices.azure.com/api/retail/prices` (sem auth). Substitua
> `<region>` pelo `armRegionName` (ex: `southeastasia`).

## Regra de ouro

O `$filter` OData é sensível. Meters de rede (NAT, Private Link, Peering, Bandwidth)
frequentemente têm `armRegionName='Global'` — nesse caso o preço é único e vale
para todas as regiões. Sempre inspecionar o campo `armRegionName` do resultado.

## Queries por serviço

### NAT Gateway
```
$filter=serviceName eq 'NAT Gateway'
```
Meters: `Standard Gateway` (resource-hour) + `Standard Data Processed` (per GB).
Armazenado como `armRegionName='Global'`.

### Public IP (Static Standard)
```
$filter=serviceName eq 'Virtual Network' and armRegionName eq '<region>'
```
Filtrar `productName='IP Addresses'`, meter `Standard IPv4 Static Public IP`.

### Private Endpoint
```
$filter=serviceName eq 'Virtual Network'
```
Filtrar `productName='Virtual Network Private Link'`, meters:
`Standard Private Endpoint` (per-hour), `Standard Data Processed` (per GB).
Global pricing.

### VNet Peering
```
$filter=serviceName eq 'Virtual Network'
```
Filtrar `productName='Virtual Network Peering'`, skuName `Intra-Region`
(ingress + egress).

### Log Analytics
```
$filter=serviceName eq 'Log Analytics' and armRegionName eq '<region>'
```
Meter moderno PAYG: `Analytics Logs Data Ingestion` (product `Analytics Logs`).
Retention: `Analytics Logs Data Retention`.

### Key Vault
```
$filter=serviceName eq 'Key Vault' and armRegionName eq '<region>'
```
Meters: `Standard Operations` (per 10K), `Certificate Renewal Request`.
Managed HSM: `Key Vault HSM Pool` / `Standard B1 Instance`.

### Azure Firewall
```
$filter=serviceName eq 'Azure Firewall' and armRegionName eq '<region>'
```
skuName `Standard`: `Standard Deployment` (per-hour) + `Standard Data Processed`.

### Bandwidth (egress)
```
$filter=serviceName eq 'Bandwidth'
```
Product `Rtn Preference: MGN` (default) ou `Bandwidth - Routing Preference: Internet`.
Primeiros 100 GB egress grátis; tier 100 GB-10 TB é o relevante.

### Defender for Cloud
```
$filter=serviceName eq 'Microsoft Defender for Cloud' and armRegionName eq '<region>'
```
Meters: Servers `Plan 2` (P2 Node, per-hour), SQL `Standard Node` (per instance/mo).

### Bastion
```
$filter=serviceName eq 'Azure Bastion' and armRegionName eq '<region>'
```
skuName `Standard`: host per-hour + outbound data.

### ADLS Gen2 transactions
```
$filter=serviceName eq 'Storage' and armRegionName eq '<region>'
```
Filtrar `productName` contendo `Data Lake Storage Gen2`, meters de
`Write Operations` e `Read Operations` (per 10K).

## Southeast Asia — snapshot verificado (2026-07, USD)

| Recurso | Meter | $ |
|---|---|---|
| NAT Gateway | resource-hour | 0.045 |
| NAT Gateway | data processed/GB | 0.045 |
| Public IP Static | per-hour | 0.005 |
| Private Endpoint | per-hour | 0.01 |
| Private Endpoint | data/GB (in+out) | 0.02 |
| VNet Peering | intra-region/GB (in+out) | 0.02 |
| Log Analytics | ingest/GB | 2.99 |
| Log Analytics | retention/GB/mo | 0.13 |
| Key Vault | 10K ops | 0.03 |
| Key Vault | cert renewal | 3.00 |
| Azure Firewall Std | deploy/h | 1.25 |
| Azure Firewall Std | data/GB | 0.016 |
| Defender Servers P2 | node/h | 0.02 |
| Defender SQL | instance/mo | 15.00 |
| Bastion Std | host/h | 0.192 |
| Bandwidth egress | 100GB-10TB /GB | 0.12 |
| DNS Private Zone | zone/mo | 0.50 |
| ADLS write | 10K ops | 0.0715 |
| ADLS read | 10K ops | 0.0057 |

> Re-verificar antes de commit final: preços mudam. Data desta captura: 2026-07.
