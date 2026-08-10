# Concept — Official pricing sources for Azure infra

> URLs oficiais Microsoft para cada componente de infra. Use como referência de
> citação nos relatórios (seção Sources). A fonte programática é sempre a Azure
> Retail Prices API; estas páginas são a documentação humana equivalente.

| Componente | URL oficial |
|---|---|
| Azure Retail Prices API | https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices |
| NAT Gateway | https://azure.microsoft.com/pricing/details/azure-nat-gateway/ |
| IP Addresses | https://azure.microsoft.com/pricing/details/ip-addresses/ |
| Private Link (Private Endpoint) | https://azure.microsoft.com/pricing/details/private-link/ |
| Virtual Network | https://azure.microsoft.com/pricing/details/virtual-network/ |
| Log Analytics / Monitor | https://azure.microsoft.com/pricing/details/monitor/ |
| Key Vault | https://azure.microsoft.com/pricing/details/key-vault/ |
| Azure Firewall | https://azure.microsoft.com/pricing/details/azure-firewall/ |
| Bandwidth (egress) | https://azure.microsoft.com/pricing/details/bandwidth/ |
| Defender for Cloud | https://azure.microsoft.com/pricing/details/defender-for-cloud/ |
| Azure Bastion | https://azure.microsoft.com/pricing/details/azure-bastion/ |
| DNS | https://azure.microsoft.com/pricing/details/dns/ |
| Storage / ADLS Gen2 | https://azure.microsoft.com/pricing/details/storage/data-lake/ |
| ExpressRoute | https://azure.microsoft.com/pricing/details/expressroute/ |

## Databricks reference architecture (para justificar o stack)

| Tópico | URL |
|---|---|
| Customer-managed VNet (VNet injection) | https://learn.microsoft.com/azure/databricks/security/network/classic/vnet-inject |
| Private Link (backend + frontend) | https://learn.microsoft.com/azure/databricks/security/network/classic/private-link |
| Secure cluster connectivity (no public IP) | https://learn.microsoft.com/azure/databricks/security/network/secure-cluster-connectivity |
| Diagnostic logging → Log Analytics | https://learn.microsoft.com/azure/databricks/admin/account-settings/audit-logs |

## Por que cada Private Endpoint existe (justificativa técnica)

Um workspace Databricks em VNet injection com Private Link tipicamente precisa de:
1. **Frontend PEP** — acesso privado dos usuários à web UI/REST API
2. **Backend PEP** — secure cluster connectivity (data plane → control plane)
3. **Control-plane relay PEP** — SCC relay
4. **ADLS raw PEP** — storage account da camada bronze
5. **ADLS curated PEP** — storage da camada silver/gold
6. **ADLS managed PEP** — DBFS root / managed tables
7. **Key Vault PEP** — secret scopes backed by Key Vault
8. **ACR PEP** — container registry para MLflow / custom images (se usado)

Daí o range 6-8 PEPs por ambiente. Ambientes que não usam ACR ou têm storage
consolidado ficam no low end (6).
