# Databricks Pricing Catalog — Schema Documentation

## Visão geral

Catalogs YAML versionados com **DBU rates**, **instance mappings**, **DBCU
commit discounts**, **spot estimates**, **storage** e **networking** para
**Azure Databricks** e **AWS Databricks**.

Consumidor primário: `data_agents/cost_engine/databricks.py`.

## Arquivos

| Path | Cloud |
|------|-------|
| `azure.yaml` | Azure Databricks |
| `aws.yaml` | AWS Databricks |

(GCP fora de escopo no MVP — adicionar quando demanda surgir.)

## Schema (alto nível)

```yaml
schema_version: "1.0.0"           # SemVer; bump quando schema mudar
cloud: azure | aws
last_updated: "YYYY-MM-DD"
last_verified_against_source: "YYYY-MM-DD"
source_url: "..."
notes: "..."

regions:
  - id: <stable-id>               # usado em código
    display_name: <label>
    azure_region_code: ...        # OU aws_region_code

dbu_rates_per_hour:
  <compute_type>:
    <tier>:
      no_photon: <USD/DBU·h>
      photon: <USD/DBU·h>

instance_dbu_map:
  <instance_sku>:
    dbu_per_hour: <float>
    vcpu: <int>
    ram_gb: <int>
    # campos opcionais: gpu, gpu_type, disk_gb

dbcu_commit_discounts:
  - tier_min_usd_year: <int>
    tier_max_usd_year: <int|null>
    discount_pct_1y: <int>
    discount_pct_3y: <int>

spot_discounts:
  <region_id>:
    avg_discount_pct: <int>
    interrupt_rate_hourly: <string>

storage:
  ... (cloud-specific)

networking:
  ... (cloud-specific)

reserved_instance_discounts:
  reserved_1y_no_upfront_pct: <int>
  reserved_1y_all_upfront_pct: <int>
  reserved_3y_no_upfront_pct: <int>
  reserved_3y_all_upfront_pct: <int>

photon_modeling:
  dbu_consumption_multiplier: <float>
  typical_speedup_factor: <float>
  break_even_speedup: <float>
  not_recommended_for: [...]
```

## Validação

Antes de usar em produção, valide o catalog contra a fonte:

```bash
python scripts/validate_databricks_pricing.py --cloud azure
python scripts/validate_databricks_pricing.py --cloud aws
```

O validator compara DBU rates contra `https://www.databricks.com/product/pricing`
e abre PR se detectar divergência. (Skeleton em Fase 0.2 — implementação
completa na Fase 0.3.)

## Como atualizar

**Manual quarterly** (recomendado):
1. Acessar https://www.databricks.com/product/pricing
2. Comparar DBU rates da seção pricing
3. Editar YAML correspondente
4. Bumpar `last_updated` e `last_verified_against_source`
5. Rodar `pytest tests/unit/test_cost_engine_databricks.py -v` (valida que cenários conhecidos ainda batem)
6. Commit + PR

**Híbrido (futuro)**: scraper roda mensalmente via GitHub Action e abre PR automático
com diff. Você aprova manualmente. Ver `scripts/refresh_databricks_pricing.py`.

## Convenções

- **Todos os valores em USD** (conversão de moeda no engine, não no catalog)
- **Discounts em percentual inteiro** (ex: `15` = 15%, não `0.15`)
- **Custos em USD com decimais** (ex: `0.40` USD/DBU·hora)
- **null em `tier_max_usd_year`** = "sem limite superior" (último tier)

## Caveats importantes

1. **Reference pricing PAYG (retail)** — não cobre descontos EA, MCA, CSP ou contratos custom
2. **Spot pricing é estimativa** — variabilidade real depende de demanda em real-time
3. **Photon dobra DBU consumption** mas geralmente reduz wall-clock — engine modela isso
4. **DBCU commit tiers são típicos** — desconto real é negociado caso-a-caso
5. **Instance prices vêm de runtime** (Azure Retail Prices API / AWS Pricing API) — catalog só tem o DBU multiplier
