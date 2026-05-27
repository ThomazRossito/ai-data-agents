---
concept: dbu-model
domain: databricks-pricing
updated_at: 2026-05-27
---

# DBU Model — Anatomia do DBU Rate

## O que é DBU?

**DBU (Databricks Unit)** é a unidade de cobrança da Databricks. Independe do cloud — é o "ticker" do consumo de processamento Databricks. Cada VM consome X DBUs por hora, e cada DBU custa Y USD dependendo de 4 fatores.

## Os 4 fatores que determinam o `dbu_rate_per_hour_usd`

```
dbu_rate = lookup(compute_type, tier, photon, cloud)
```

### 1. `compute_type` — categoria do workload

| Compute Type | Descrição | Cenário típico |
|---|---|---|
| `jobs_compute` | Batch jobs (scheduled) | ETL/ELT noturno, pipelines DLT |
| `all_purpose_compute` | Notebook interativo | Exploração, debug |
| `sql_compute` (também chamado de Pro/Classic) | SQL Warehouse | Dashboards BI, queries ad-hoc |
| `sql_pro` | SQL Warehouse Pro tier | SQL Pro com features advanced |
| `sql_serverless` | SQL Serverless | Auto-pause, sub-minute startup |
| `dlt_core` / `dlt_pro` / `dlt_advanced` | DLT (Delta Live Tables) | Pipelines declarativos |
| `serverless_compute` | Serverless compute geral | Notebooks/Jobs sem cluster próprio |

> **Default no agente:** `jobs_compute` (mais comum para batch ETL). Cite no output.

### 2. `tier` — Workspace pricing tier

| Tier | Quando | DBU rate |
|---|---|---|
| `standard` | Workspaces com features básicas | Mais barato |
| `premium` | Workspaces com Unity Catalog, ACLs, IP access list, Audit logs | ~1.5-2× standard |

> **Default no agente:** `premium` (workspaces enterprise modernos quase sempre são Premium — Unity Catalog requer Premium).

### 3. `photon` — Engine vetorizado

| Photon | Impacto no rate |
|---|---|
| `false` | Rate base |
| `true` | Rate × 2× (dobra) |

Photon é uma engine de execução vetorizada (C++) que acelera workloads SQL/agregação. **Custa o dobro mas pode acelerar 2-5×** em workloads adequados — não pra todo workload.

> **Default no agente:** `photon=false`. Cite no output ("Photon desativado por padrão; ative se quiser comparar").

Veja `photon-roi.md` para regra de bolso de quando vale.

### 4. `cloud` — Provider

| Cloud | DBU rate (jobs Premium sem Photon) |
|---|---|
| `azure` | $0.20 |
| `aws` | $0.10 |
| `gcp` (não suportado no catalog atual) | ~ similar a AWS |

AWS é geralmente ~50% mais barato em DBU rate (mas instance prices são similares ou maiores em algumas regiões).

## Tabela completa Azure — DBU rates por (compute_type × tier × photon)

| compute_type | std_no_photon | std_photon | prem_no_photon | prem_photon |
|---|---|---|---|---|
| jobs_compute | $0.10 | $0.20 | $0.20 | $0.40 |
| all_purpose_compute | $0.40 | $0.80 | $0.55 | $1.10 |
| sql_compute | n/a | n/a | $0.22 | $0.44 |
| sql_pro | n/a | n/a | $0.55 | n/a |
| sql_serverless | n/a | n/a | $0.70 | n/a |
| dlt_core | $0.20 | n/a | $0.36 | n/a |
| dlt_pro | n/a | n/a | $0.54 | n/a |
| dlt_advanced | n/a | n/a | $0.72 | n/a |
| serverless_compute | n/a | n/a | $0.95 | n/a |

## Tabela completa AWS — DBU rates

| compute_type | std_no_photon | std_photon | prem_no_photon | prem_photon |
|---|---|---|---|---|
| jobs_compute | $0.07 | $0.14 | $0.10 | $0.20 |
| all_purpose_compute | $0.40 | $0.80 | $0.55 | $1.10 |
| sql_compute | n/a | n/a | $0.22 | $0.44 |
| serverless_compute | n/a | n/a | $0.95 | n/a |

> Para lookup programático: `databricks_pricing_get_dbu_rate(compute_type, tier, photon, cloud)`.

## DBU per hour por instance — onde "consumo" entra

Cada VM/EC2 consome X DBUs/h (declarado no catalog). Ex:
- Azure `Standard_DS4_v2` = 1.5 DBU/h
- AWS `m5.2xlarge` = 1.5 DBU/h

Cluster com driver + 4 workers DS4_v2 = (1.5 + 4 × 1.5) = 7.5 DBU/h. Em 8h × 22d = 1.320 DBU/mês.

Custo DBU mensal = 1.320 × $0.20 = $264. Soma com instance cost (880h × $0.526 = $462.88) = **$726.88** (canonical).

## Onde isso é codificado no projeto

- Catalog YAML: `data/databricks_pricing/{azure,aws}.yaml`
- Engine: `data_agents/cost_engine/databricks.py` — função `calculate_databricks_cost(scenario)`
- MCP tool: `databricks_pricing_get_dbu_rate(...)` para lookup
