"""
Calculation engine determinístico para Databricks Cost (AWS + Azure).

Princípios:
  - Função pura: mesma entrada → mesma saída, sem side effects
  - Sem I/O em runtime (catalog YAML lido uma vez via load_databricks_catalog)
  - Sem chamada de API externa (instance prices vêm do consumidor — MCP wrappa)
  - Sem dependência de cloud SDK
  - Auditável: cada cálculo expõe breakdown completo no output

Modelo de custo (formula central):

    cluster_cost_hour = (
        num_workers * worker_dbu_h * dbu_rate
        + driver_dbu_h * dbu_rate
        + (num_workers * worker_instance_cost_h + driver_instance_cost_h)
    )

Onde:
  - dbu_rate vem de dbu_rates_per_hour[compute_type][tier][photon_state]
  - <node>_dbu_h vem de instance_dbu_map[<sku>].dbu_per_hour
  - instance_cost_h vem do consumidor (não está no catalog — varia por região
    e modelo de pricing on-demand/spot/reserved)

Uso típico:

    from data_agents.cost_engine import (
        DatabricksScenario,
        calculate_databricks_cost,
        load_databricks_catalog,
    )

    catalog = load_databricks_catalog("azure")
    scenario = DatabricksScenario(
        cloud="azure",
        compute_type="jobs_compute",
        tier="premium",
        photon=True,
        driver_instance="Standard_DS4_v2",
        worker_instance="Standard_DS4_v2",
        num_workers=4,
        hours_per_day=8,
        days_per_month=22,
        region="brazilsouth",
        instance_pricing_model="on_demand",
        # consumer fornece instance prices via API:
        driver_instance_cost_per_hour_usd=0.526,
        worker_instance_cost_per_hour_usd=0.526,
    )
    result = calculate_databricks_cost(scenario, catalog)
    # result["total_monthly_usd"] = ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml


# Aliases pra clarity
# PR 2 (2026-05-28): + "gcp" cloud + 3 serverless sub-types.
CloudName = Literal["azure", "aws", "gcp"]
ComputeType = Literal[
    "all_purpose_compute",
    "jobs_compute",
    "serverless_compute",  # alias DEPRECATED — use sub-types abaixo
    "jobs_serverless",  # PR 2: $0.35/DBU oficial Jobs Serverless
    "dlt_serverless",  # PR 2: $0.35/DBU oficial DLT Serverless
    "all_purpose_serverless",  # PR 2: $0.75/DBU oficial All-Purpose Serverless
    "delta_live_tables",
    "sql",
    "model_serving",
    "vector_search",
    "mosaic_agent",
]
# PR 1 (auditoria 2026-05-28): tier model alinhado com Databricks oficial.
# `standard` é DEPRECATED — não consta em nenhuma das 25 sub-páginas de pricing
# oficiais (kb/databricks-pricing/extracted-prices-raw.md). PR 2 vai removê-lo.
#
# Mapping confirmado em https://www.databricks.com/product/pricing/* (todas as 25 páginas):
#   "The Premium tier on Azure Databricks corresponds to the Enterprise tier on AWS and GCP"
#
# Implicação prática:
#   - Azure só publica "Premium" oficialmente (= Enterprise em AWS/GCP).
#   - AWS/GCP publicam Premium e Enterprise.
#   - O catalog YAML ainda tem "standard" pra back-compat até PR 2.
#
# Helper validate_tier() abaixo emite warning quando "standard" é usado.
Tier = str  # ampliado pra str em PR 1; volta a Literal["premium", "enterprise"] em PR 2
OFFICIAL_TIERS: tuple[str, ...] = ("premium", "enterprise")
DEPRECATED_TIERS: tuple[str, ...] = ("standard",)
PricingModel = Literal["on_demand", "spot", "reserved_1y", "reserved_3y"]


def validate_tier(tier: str, cloud: CloudName | None = None) -> tuple[bool, str | None]:
    """Valida tier contra hierarquia oficial Databricks.

    Returns:
        (is_official, warning_message_or_None)

    Regras:
        - "premium" e "enterprise" são OFICIAIS (sempre válidos)
        - "standard" é DEPRECATED — válido pra back-compat, mas emite warning
        - Qualquer outro valor é UNKNOWN — válido (engine lê do YAML), warning leve

    Para cloud="azure", também avisa que Azure só publica "premium" oficialmente.
    """
    tier_normalized = tier.lower().strip()

    if tier_normalized in OFFICIAL_TIERS:
        if cloud == "azure" and tier_normalized == "enterprise":
            return True, (
                "Azure Databricks não publica tier 'enterprise' oficialmente — "
                "Azure 'premium' corresponde a AWS/GCP 'enterprise'. "
                "Catalog YAML pode aceitar 'enterprise' como alias para 'premium' no Azure."
            )
        return True, None

    if tier_normalized in DEPRECATED_TIERS:
        return False, (
            f"Tier {tier!r} é DEPRECATED — não consta nas 25 páginas oficiais de pricing "
            f"Databricks (verificado 2026-05-28). Use 'premium' ou 'enterprise'. "
            f"Suporte será removido em PR 2."
        )

    return False, f"Tier {tier!r} desconhecido. Esperado: 'premium' ou 'enterprise'."


# Onde vivem os catalogs YAML
_CATALOG_DIR = Path(__file__).parent.parent.parent / "data" / "databricks_pricing"


@dataclass
class DatabricksScenario:
    """
    Descreve um cenário de cluster/workload Databricks pra cálculo de custo.

    Campos obrigatórios:
        cloud: "azure" ou "aws"
        compute_type: tipo de compute (jobs_compute, all_purpose_compute, etc.)
        tier: "standard", "premium" ou "enterprise"
        photon: True se Photon está habilitado
        driver_instance: SKU do driver (ex: "Standard_DS4_v2" ou "m5.xlarge")
        worker_instance: SKU do worker (mesmo formato que driver)
        num_workers: quantos worker nodes (não conta o driver)
        hours_per_day: horas que o cluster fica ativo por dia
        days_per_month: dias por mês (típico: 22 working days)
        region: id da região do catalog (ex: "brazilsouth", "us-east-1")
        instance_pricing_model: "on_demand" | "spot" | "reserved_1y" | "reserved_3y"
        driver_instance_cost_per_hour_usd: vem do consumidor (API cloud)
        worker_instance_cost_per_hour_usd: idem

    Campos opcionais (defaults sensatos):
        autoscale_avg_workers_pct: se cluster faz autoscale, % médio do max.
            Ex: max_workers=8 com autoscale_avg=50 → custo calculado com 4 workers.
            Default: 100 (sem autoscaling — usa num_workers como média).
        dbcu_commit_pct: desconto DBCU contratual (sobrescreve auto-tier).
            Se None, calcula a partir de cluster_annual_dbu_usd.
        photon_speedup_factor: speedup real observado (override do default 2.5).
        currency_conversion_rate: se != 1.0, converte total pra outra moeda.
        currency_label: label da moeda final ("USD", "BRL", etc.).
    """

    cloud: CloudName
    compute_type: ComputeType
    tier: Tier
    photon: bool
    driver_instance: str
    worker_instance: str
    num_workers: int
    hours_per_day: float
    days_per_month: int
    region: str
    instance_pricing_model: PricingModel
    driver_instance_cost_per_hour_usd: float
    worker_instance_cost_per_hour_usd: float

    # Opcionais com defaults
    autoscale_avg_workers_pct: float = 100.0
    dbcu_commit_pct: float | None = None
    photon_speedup_factor: float | None = None
    currency_conversion_rate: float = 1.0
    currency_label: str = "USD"

    # Metadata (auditável)
    scenario_id: str | None = None
    description: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


def load_databricks_catalog(cloud: CloudName) -> dict[str, Any]:
    """
    Carrega o catalog YAML pra uma cloud específica.

    Args:
        cloud: "azure" ou "aws"

    Returns:
        Dict com schema completo do catalog.

    Raises:
        FileNotFoundError: se YAML não existir.
        ValueError: se schema_version não for compatível.
    """
    catalog_path = _CATALOG_DIR / f"{cloud}.yaml"
    if not catalog_path.exists():
        raise FileNotFoundError(f"Catalog Databricks pricing não encontrado: {catalog_path}")

    with open(catalog_path, encoding="utf-8") as f:
        catalog: dict[str, Any] = yaml.safe_load(f)

    schema_version = catalog.get("schema_version", "0.0.0")
    major = int(schema_version.split(".")[0])
    if major != 1:
        raise ValueError(f"Schema incompatível: {schema_version}. Esperado major version 1.")

    return catalog


def _resolve_dbu_rate(catalog: dict[str, Any], scenario: DatabricksScenario) -> float:
    """Resolve DBU rate (USD/DBU·hora) do catalog para o cenário."""
    rates = catalog["dbu_rates_per_hour"]
    compute = rates.get(scenario.compute_type)
    if compute is None:
        raise ValueError(
            f"Compute type desconhecido: {scenario.compute_type}. Suportados: {list(rates.keys())}"
        )

    # serverless_compute, delta_live_tables, sql, model_serving, vector_search
    # têm estruturas diferentes — tratamento especial:
    # PR 2 (2026-05-28): + jobs_serverless / dlt_serverless / all_purpose_serverless
    # — todos seguem mesmo schema `base_per_dbu` do legacy `serverless_compute`.
    if scenario.compute_type in (
        "serverless_compute",
        "jobs_serverless",
        "dlt_serverless",
        "all_purpose_serverless",
    ):
        return float(compute["base_per_dbu"])
    if scenario.compute_type == "delta_live_tables":
        # tier maps to product line (core/pro/advanced)
        # mas usamos tier do scenario; default = "pro"
        dlt_tier = scenario.tier if scenario.tier in compute else "pro"
        return float(compute[dlt_tier])
    if scenario.compute_type == "sql":
        # tier maps to warehouse class (classic/pro/serverless)
        sql_tier = scenario.tier if scenario.tier in compute else "pro"
        return float(compute[sql_tier])
    if scenario.compute_type == "model_serving":
        # default CPU; pode evoluir pra GPU
        return float(compute["cpu_per_dbu"])
    if scenario.compute_type == "vector_search":
        return float(compute["storage_endpoint_per_hour"])
    if scenario.compute_type == "mosaic_agent":
        return float(compute["serverless_per_dbu"])

    # all_purpose_compute e jobs_compute têm tier + photon
    tier_data = compute.get(scenario.tier)
    if tier_data is None:
        raise ValueError(f"Tier {scenario.tier!r} não disponível para {scenario.compute_type!r}")

    photon_key = "photon" if scenario.photon else "no_photon"
    if photon_key not in tier_data:
        raise ValueError(
            f"Variante {photon_key!r} não disponível em {scenario.compute_type}.{scenario.tier}"
        )
    return float(tier_data[photon_key])


def _resolve_instance_dbu(catalog: dict[str, Any], instance_sku: str) -> float:
    """Resolve DBU/hora consumido por instance type."""
    inst_map = catalog["instance_dbu_map"]
    inst_data = inst_map.get(instance_sku)
    if inst_data is None:
        raise ValueError(
            f"Instance SKU {instance_sku!r} não está em {catalog['cloud']}.yaml. "
            f"Disponíveis: {list(inst_map.keys())[:5]}..."
        )
    return float(inst_data["dbu_per_hour"])


def _resolve_dbcu_discount_pct(
    catalog: dict[str, Any], annual_dbu_usd: float, commit_years: int
) -> float:
    """Resolve % de desconto DBCU baseado no tier de gasto anual + duração."""
    if commit_years not in (1, 3):
        return 0.0

    tiers = catalog["dbcu_commit_discounts"]
    pct_key = f"discount_pct_{commit_years}y"

    for tier_data in tiers:
        max_usd = tier_data["tier_max_usd_year"]
        if annual_dbu_usd >= tier_data["tier_min_usd_year"] and (
            max_usd is None or annual_dbu_usd < max_usd
        ):
            return float(tier_data[pct_key])

    return 0.0


def _apply_pricing_model_discount(
    catalog: dict[str, Any], scenario: DatabricksScenario, base_cost: float
) -> tuple[float, float]:
    """
    Aplica desconto do pricing model (on_demand/spot/reserved_*) no INSTANCE COST.
    NÃO afeta DBU cost.

    Returns: (cost_after_discount, discount_pct_applied)
    """
    if scenario.instance_pricing_model == "on_demand":
        return base_cost, 0.0

    if scenario.instance_pricing_model == "spot":
        spot_data = catalog.get("spot_discounts", {}).get(scenario.region)
        if spot_data is None:
            return base_cost, 0.0
        discount_pct = float(spot_data["avg_discount_pct"])
        return base_cost * (1 - discount_pct / 100), discount_pct

    if scenario.instance_pricing_model in ("reserved_1y", "reserved_3y"):
        years = 1 if scenario.instance_pricing_model == "reserved_1y" else 3
        # Default: no_upfront (mais comum)
        ri_discounts = catalog.get("reserved_instance_discounts", {})
        key = f"reserved_{years}y_no_upfront_pct"
        discount_pct = float(ri_discounts.get(key, 0))
        return base_cost * (1 - discount_pct / 100), discount_pct

    return base_cost, 0.0


def calculate_databricks_cost(
    scenario: DatabricksScenario,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Calcula custo total mensal de um cenário Databricks.

    Args:
        scenario: DatabricksScenario descrevendo cluster/workload.
        catalog: dict do catalog YAML. Se None, carrega via load_databricks_catalog.

    Returns:
        Dict com breakdown completo (auditável):
            {
                "scenario_id": ...,
                "cloud": ...,
                "currency": "USD" (ou conversão),
                "totals": {
                    "monthly": float,
                    "annual": float,
                    "tco_36m": float,
                },
                "breakdown_hourly_usd": {
                    "dbu_total": float,
                    "dbu_driver": float,
                    "dbu_workers": float,
                    "instance_total": float,
                    "instance_driver": float,
                    "instance_workers": float,
                    "cluster_total": float,
                },
                "inputs_resolved": {
                    "dbu_rate": float,
                    "driver_dbu_per_hour": float,
                    "worker_dbu_per_hour": float,
                    "effective_workers": float,  # após autoscale_avg
                    "hours_per_month": float,
                    "instance_discount_pct_applied": float,
                },
                "commit_savings": {
                    "annual_dbu_usd": float,
                    "dbcu_discount_pct": float,
                    "savings_1y_usd": float,
                    "savings_3y_usd": float,
                },
                "warnings": [...],
            }

    Raises:
        ValueError: scenario inválido ou compute/tier/instance não encontrado.
    """
    if catalog is None:
        catalog = load_databricks_catalog(scenario.cloud)
    if catalog["cloud"] != scenario.cloud:
        raise ValueError(
            f"Catalog é da cloud {catalog['cloud']!r} mas scenario é {scenario.cloud!r}"
        )

    warnings: list[str] = []

    # 0. Valida tier contra hierarquia oficial Databricks (PR 1, 2026-05-28)
    tier_ok, tier_warning = validate_tier(scenario.tier, cloud=scenario.cloud)
    if tier_warning:
        warnings.append(tier_warning)

    # 1. Resolve DBU rate (USD/DBU·h)
    dbu_rate = _resolve_dbu_rate(catalog, scenario)

    # 2. Resolve DBU por hora de cada node
    driver_dbu_h = _resolve_instance_dbu(catalog, scenario.driver_instance)
    worker_dbu_h = _resolve_instance_dbu(catalog, scenario.worker_instance)

    # 3. Autoscaling: ajusta workers efetivos
    effective_workers = scenario.num_workers * (scenario.autoscale_avg_workers_pct / 100)

    # 4. Hours per month
    hours_per_month = scenario.hours_per_day * scenario.days_per_month

    # 5. DBU cost (hourly e mensal)
    dbu_driver_hourly = driver_dbu_h * dbu_rate
    dbu_workers_hourly = effective_workers * worker_dbu_h * dbu_rate
    dbu_total_hourly = dbu_driver_hourly + dbu_workers_hourly

    # 6. Instance cost (hourly, antes do desconto pricing model)
    # IMPORTANTE: Serverless é Databricks-managed — o user paga só DBU,
    # sem instance cost separado (confirmado no catalog YAML "Inclui infra
    # Databricks-managed").
    # PR 2 (2026-05-28): expandido pra cobrir todos os sub-types serverless
    # oficiais (Databricks publica 4: Jobs/DLT/SQL/All-Purpose Serverless).
    _SERVERLESS_COMPUTE_TYPES = (
        "serverless_compute",  # legacy alias (deprecated)
        "sql_serverless",  # variante explícita
        "jobs_serverless",  # PR 2
        "dlt_serverless",  # PR 2
        "all_purpose_serverless",  # PR 2
    )
    _is_serverless = scenario.compute_type in _SERVERLESS_COMPUTE_TYPES or (
        scenario.compute_type == "sql" and scenario.tier == "serverless"
    )
    if _is_serverless:
        inst_driver_base = 0.0
        inst_workers_base = 0.0
        if (
            scenario.driver_instance_cost_per_hour_usd > 0
            or scenario.worker_instance_cost_per_hour_usd > 0
        ):
            tier_label = f"+tier={scenario.tier}" if scenario.compute_type == "sql" else ""
            warnings.append(
                f"compute_type={scenario.compute_type!r}{tier_label}: instance_cost zerado "
                "(serverless inclui infra Databricks-managed)"
            )
    else:
        inst_driver_base = scenario.driver_instance_cost_per_hour_usd
        inst_workers_base = effective_workers * scenario.worker_instance_cost_per_hour_usd
    inst_total_base = inst_driver_base + inst_workers_base

    # 7. Aplica desconto de pricing model (spot/reserved) só no instance
    inst_total_after_discount, instance_discount_pct = _apply_pricing_model_discount(
        catalog, scenario, inst_total_base
    )
    # Se aplicou, scala proporcionalmente driver/worker
    if inst_total_base > 0:
        scaling = inst_total_after_discount / inst_total_base
    else:
        scaling = 1.0
    inst_driver_hourly = inst_driver_base * scaling
    inst_workers_hourly = inst_workers_base * scaling

    # 8. Cluster total (hourly)
    cluster_hourly = dbu_total_hourly + inst_total_after_discount

    # 9. Monthly + Annual
    monthly_usd = cluster_hourly * hours_per_month
    annual_usd = monthly_usd * 12

    # 10. DBCU commit savings (calculado em cima do DBU cost anual)
    annual_dbu_usd = dbu_total_hourly * hours_per_month * 12
    if scenario.dbcu_commit_pct is not None:
        dbcu_pct = scenario.dbcu_commit_pct
        warnings.append(f"dbcu_commit_pct={dbcu_pct}% manual (override do auto-tier)")
    else:
        # Auto-tier baseado em gasto anual DBU
        # Tenta 1y e 3y; reporta os dois
        dbcu_pct = _resolve_dbcu_discount_pct(catalog, annual_dbu_usd, 1)

    savings_1y = annual_dbu_usd * (_resolve_dbcu_discount_pct(catalog, annual_dbu_usd, 1) / 100)
    savings_3y = annual_dbu_usd * (_resolve_dbcu_discount_pct(catalog, annual_dbu_usd, 3) / 100)

    # 11. Photon warning
    if scenario.photon:
        photon_model = catalog.get("photon_modeling", {})
        speedup = scenario.photon_speedup_factor or float(
            photon_model.get("typical_speedup_factor", 2.5)
        )
        break_even = float(photon_model.get("break_even_speedup", 2.0))
        if speedup < break_even:
            warnings.append(
                f"Photon ON com speedup={speedup}x < break_even={break_even}x — "
                f"custo final pode ser MAIOR. Considere desabilitar Photon."
            )

    # 12. Conversão de moeda (se aplicável)
    fx_rate = scenario.currency_conversion_rate
    if fx_rate != 1.0:
        warnings.append(f"Conversão de moeda aplicada: 1 USD = {fx_rate} {scenario.currency_label}")

    monthly_final = monthly_usd * fx_rate
    annual_final = annual_usd * fx_rate
    tco_36m_final = annual_final * 3

    return {
        "scenario_id": scenario.scenario_id,
        "scenario_description": scenario.description,
        "cloud": scenario.cloud,
        "currency": scenario.currency_label,
        "fx_rate_applied": fx_rate,
        "totals": {
            "monthly": round(monthly_final, 2),
            "annual": round(annual_final, 2),
            "tco_36m": round(tco_36m_final, 2),
        },
        "breakdown_hourly_usd": {
            "dbu_total": round(dbu_total_hourly, 4),
            "dbu_driver": round(dbu_driver_hourly, 4),
            "dbu_workers": round(dbu_workers_hourly, 4),
            "instance_total": round(inst_total_after_discount, 4),
            "instance_driver": round(inst_driver_hourly, 4),
            "instance_workers": round(inst_workers_hourly, 4),
            "cluster_total": round(cluster_hourly, 4),
        },
        "inputs_resolved": {
            "dbu_rate_per_hour_usd": dbu_rate,
            "driver_dbu_per_hour": driver_dbu_h,
            "worker_dbu_per_hour": worker_dbu_h,
            "effective_workers": effective_workers,
            "hours_per_month": hours_per_month,
            "instance_discount_pct_applied": instance_discount_pct,
        },
        "commit_savings": {
            "annual_dbu_usd": round(annual_dbu_usd, 2),
            "auto_dbcu_pct_1y": _resolve_dbcu_discount_pct(catalog, annual_dbu_usd, 1),
            "auto_dbcu_pct_3y": _resolve_dbcu_discount_pct(catalog, annual_dbu_usd, 3),
            "savings_1y_usd": round(savings_1y, 2),
            "savings_3y_usd": round(savings_3y, 2),
            "monthly_with_dbcu_1y": round((monthly_usd - (savings_1y / 12)) * fx_rate, 2),
            "monthly_with_dbcu_3y": round((monthly_usd - (savings_3y / 12)) * fx_rate, 2),
        },
        "source": {
            "catalog_version": catalog.get("schema_version"),
            "catalog_last_updated": catalog.get("last_updated"),
            "catalog_source_url": catalog.get("source_url"),
        },
        "warnings": warnings,
    }
