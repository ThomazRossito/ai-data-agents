---
concept: multi-cloud
domain: databricks-pricing
updated_at: 2026-05-27
---

# Multi-cloud — Diferenças Azure vs AWS no modelo Databricks

## Modelo é o mesmo, números mudam

A fórmula `(DBU × DBU_rate) + (instance_hours × instance_price)` vale pra **azure e aws**. O que muda:

1. **DBU rate** é menor em AWS (geralmente metade do Azure pra mesmo `compute_type × tier × photon`)
2. **Instance prices** são similares (Azure DS-series ~ AWS m5-series em USD/h)
3. **DBU per hour** por instance type é tipicamente o mesmo (ex: DS4_v2 = m5.2xlarge = 1.5 DBU/h)

## Comparação direta — Jobs Premium sem Photon

| Parâmetro | Azure | AWS |
|---|---|---|
| DBU rate | $0.20/DBU·h | $0.10/DBU·h |
| Instance equivalente | Standard_DS4_v2 ($0.526/h) | m5.2xlarge ($0.384/h) |
| DBU/h por instance | 1.5 | 1.5 |
| **Cluster 4w × 8h × 22d** | $726.88/mês | ~$498.00/mês |

> AWS é tipicamente **30% mais barato** no canonical workload, mas isso varia por SKU/region.

## Quando escolher Azure?

✅ Cliente já no Azure (Fabric, Synapse, AD/Entra)
✅ Workspaces que precisam de Fabric Direct Lake integration
✅ Compliance LGPD com region `brazilsouth` específica
✅ Reservas Azure já existentes

## Quando escolher AWS?

✅ Cliente já na AWS (S3, Redshift, Glue)
✅ Custo é fator decisivo (geralmente AWS mais barato)
✅ Regions com latência crítica (us-east-1 é referência)
✅ Reservas AWS já existentes

## Cross-cloud comparison — quando o usuário pede

Se o usuário disser **"compara Azure e AWS pra esse workload"**:

1. Rodar `databricks_pricing_calc_cluster_cost(cloud="azure", ...)` com SKU Azure equivalente
2. Rodar `databricks_pricing_calc_cluster_cost(cloud="aws", ...)` com SKU AWS equivalente
3. Apresentar 2 colunas lado a lado no `cost_report.md`

**SKU equivalence (mock catalog Fase 1):**

| Azure SKU | AWS SKU equivalente | vCPU/Memory |
|---|---|---|
| Standard_DS3_v2 | m5.xlarge | 4 vCPU / 14-16 GB |
| Standard_DS4_v2 | m5.2xlarge | 8 vCPU / 28-32 GB |
| Standard_DS5_v2 | m5.4xlarge | 16 vCPU / 56-64 GB |
| Standard_E8ds_v4 | r5.2xlarge | 8 vCPU / 64 GB (memory-opt) |
| Standard_E16ds_v4 | r5.4xlarge | 16 vCPU / 128 GB (memory-opt) |
| Standard_F8s_v2 | c5.2xlarge (~) | 8 vCPU / 16-17 GB (compute-opt) |

> Esses mapeamentos são **aproximações**. Memory/CPU exatos podem variar 5-10%. Para validação cross-cloud séria, pedir SKU específico ao usuário em vez de mapear automaticamente.

## Regions cobertas no mock (Fase 1)

**Azure:**
- `brazilsouth` — region canonical pro Brasil
- `eastus` — referência US
- `westeurope` — referência EU

**AWS:**
- `us-east-1` — referência US (referência canonical)
- `us-west-2` — Oregon
- `eu-west-1` — Ireland
- `ap-southeast-1` — Singapore
- `sa-east-1` — São Paulo (Brasil)

Outras regions: listar via `databricks_pricing_list_regions(cloud)` e pedir cotação real.

## O que evitar

❌ **Mapear SKU cross-cloud sem confirmar** — Se o usuário disse "Standard_DS4_v2", não converte pra m5.2xlarge unilateralmente. Pergunte se quer comparar AWS e qual SKU AWS preferido.

❌ **Recomendar cross-cloud sem premissa de negócio** — Cliente que já é Azure-only não muda pra AWS por 30% de saving. Os custos de mudança (S3 vs ADLS, networking, training) são altíssimos.

❌ **Misturar Azure + AWS no mesmo cluster** — Databricks workspace é Azure OU AWS, nunca os dois. Cross-cloud comparison são 2 cenários separados.

## Onde isso é codificado

- Catalogs separados: `data/databricks_pricing/azure.yaml` e `data/databricks_pricing/aws.yaml`
- Engine: `load_databricks_catalog(cloud)` carrega o YAML correto
- Mock instance prices: `data_agents.cost_app.databricks.instance_prices` (mesma estrutura pros 2 clouds)
