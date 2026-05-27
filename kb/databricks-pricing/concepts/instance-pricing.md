---
concept: instance-pricing
domain: databricks-pricing
updated_at: 2026-05-27
---

# Instance Pricing — Mock (Fase 1) e Roadmap

## Estado atual: mock catalog

Os instance prices (USD/h por SKU × region) estão **mockados** em `data_agents/cost_app/databricks/instance_prices.py`. Cobre:

**Azure (3 regions):**
- `brazilsouth` — canonical pro Brasil
- `eastus` — referência US
- `westeurope` — referência EU

**AWS (5 regions):**
- `us-east-1` — referência canonical
- `us-west-2` — Oregon
- `eu-west-1` — Ireland
- `ap-southeast-1` — Singapore
- `sa-east-1` — São Paulo

Cada region tem ~6-7 SKUs cobertos (DS-series, E-series, F-series no Azure; m5/r5/c5 no AWS).

## Por que mock?

A integração com **Azure Retail Prices API** + **AWS Pricing API** envolve:

1. **Azure Retail Prices API** (`https://prices.azure.com/api/retail/prices`)
   - Público, sem auth — mas filtragem por SKU é não-trivial (precisa de `armSkuName`, region slug, meter)
   - **Já temos integração** no `azure-cost-calculator` (`azure_pricing_*` MCP)
   - Para Databricks, precisa fazer match entre Databricks instance type e Azure VM SKU exato
   - **Roadmap:** Fase 2 do cost calculator (chunk pós-MVP)

2. **AWS Pricing API** (`https://api.pricing.us-east-1.amazonaws.com`)
   - Requer AWS credentials (mesmo que readonly)
   - JSON enorme — precisa de cache/filter pre-fetch
   - **Roadmap:** Fase 2+

Até lá: mock cobre os 95% dos casos de cotação que o agente recebe em PoC/pré-venda.

## Quando o SKU/region do usuário NÃO está no mock

O agente DEVE:

1. Chamar `databricks_pricing_list_instances(cloud, region)` pra listar opções no catalog
2. Se a region não estiver no mock, chamar `databricks_pricing_list_regions(cloud)`
3. Apresentar as opções ao usuário e pedir clarificação
4. **NUNCA inventar preço.** Se nada equivalente existir, dizer "SKU/region não disponível no mock catalog atual (Fase 1) — pedir cotação real à Databricks Account Team ou Azure/AWS Pricing Calculator".

## Premissas do mock

| Premissa | Valor |
|---|---|
| Pricing modelo | On-demand (não Spot, não RI) |
| Currency | USD |
| Update frequency | Manual — última atualização: 2026-05 |
| Source | Aproximações public-facing Azure/AWS pricing (não auditável vs preços reais negociados) |

## Roadmap pós-MVP

| Fase | Item |
|---|---|
| Fase 1 (MVP — atual) | Mock 3 regions Azure + 5 AWS, hand-curated |
| Fase 2 (pós-MVP) | Integração com Azure Retail API (já temos infra do `azure-cost-calculator`) |
| Fase 3 | Integração com AWS Pricing API |
| Fase 4 | Spot pricing dinâmico via Azure/AWS Spot APIs |
| Fase 5 | RI pricing dinâmico (1y/3y) |
| Fase 6 | Negotiated pricing override por cliente (`output/prj_<cliente>/pricing_override.yaml`) |

## DBU per hour — está no catalog ou no instance_prices?

**Resposta:** está no `instance_prices.py` junto com o `usd_per_hour`, como atributo do SKU:

```python
{
    "Standard_DS4_v2": {
        "usd_per_hour": 0.526,
        "dbu_per_hour": 1.5,
        "vcpu": 8,
        "memory_gb": 28,
        "is_mock": True,
    }
}
```

Esse `dbu_per_hour` é independente do `dbu_rate_per_hour_usd` (que está no catalog YAML). A multiplicação acontece no engine:

```
DBU cost/hora = num_instances × dbu_per_hour × dbu_rate_per_hour_usd
```

## Discount flags no scenario

O `DatabricksScenario` aceita 2 flags de desconto sobre o **instance cost**:

- `use_spot: bool` — aplica `discount_pct_spot` (catalog YAML)
- `use_reserved: bool` — aplica `discount_pct_ri` (catalog YAML)

Defaults: ambos `False`. NÃO confundir com DBCU — DBCU é desconto sobre o **DBU cost**, Spot/RI é sobre o **instance cost**.

## Onde isso é codificado

- Mock instance prices: `data_agents/cost_app/databricks/instance_prices.py`
- Catalog YAML (descontos Spot/RI): `data/databricks_pricing/{azure,aws}.yaml`
- Engine: `data_agents.cost_engine.databricks.calculate_databricks_cost(scenario)`
- MCP tool: `databricks_pricing_get_instance_price(...)` retorna `is_mock=True` no payload
