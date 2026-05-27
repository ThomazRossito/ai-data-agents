"""
Databricks Pricing — MCP Server Customizado.

Expõe o calculation engine determinístico (data_agents.cost_engine.databricks)
+ pricing catalogs YAML (data/databricks_pricing/{azure,aws}.yaml) como tools
consumíveis por agents.

Tools disponíveis (9):
  - databricks_pricing_diagnostics          — smoke test
  - databricks_pricing_get_dbu_rate         — DBU rate lookup
  - databricks_pricing_get_instance_price   — instance USD/h
  - databricks_pricing_list_instances       — instances disponíveis por region
  - databricks_pricing_list_regions         — regions disponíveis por cloud
  - databricks_pricing_calc_cluster_cost    — custo total (driver+workers+DBU)
  - databricks_pricing_compare_payg_vs_dbcu — comparação completa com breakeven
  - databricks_pricing_currency_convert     — USD↔BRL
  - databricks_pricing_save_scenario        — persiste cenário pra App carregar

Configuração no .env (todos opcionais — defaults sensatos):

  DATABRICKS_PRICING_DEFAULT_CLOUD=azure         # azure | aws
  DATABRICKS_PRICING_DEFAULT_REGION=brazilsouth  # brazilsouth | us-east-1 | etc
  DATABRICKS_PRICING_DEFAULT_CURRENCY=USD        # USD | BRL
  DATABRICKS_PRICING_FX_USD_BRL=5.0              # default fx rate

Autenticação: nenhuma (catalog estático + sem APIs externas em runtime)
Dependências: pyyaml (catalog), engine via data_agents.cost_engine

Comando entry point: databricks-pricing-mcp (declarado em pyproject.toml)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from data_agents.cost_app.databricks.instance_prices import (
    get_instance_price_usd_per_hour,
    list_instances_for_region,
    list_regions_for_cloud,
)
from data_agents.cost_app.databricks.scenarios import save_scenario
from data_agents.cost_engine.databricks import (
    DatabricksScenario,
    calculate_databricks_cost,
    load_databricks_catalog,
)

logger = logging.getLogger("databricks_pricing_mcp")

# ─── FastMCP Server ─────────────────────────────────────────────────────────

mcp = FastMCP("databricks-pricing")


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _default_cloud() -> str:
    return os.environ.get("DATABRICKS_PRICING_DEFAULT_CLOUD", "azure")


def _default_region() -> str:
    return os.environ.get("DATABRICKS_PRICING_DEFAULT_REGION", "brazilsouth")


def _default_currency() -> str:
    return os.environ.get("DATABRICKS_PRICING_DEFAULT_CURRENCY", "USD")


def _default_fx_rate() -> float:
    try:
        return float(os.environ.get("DATABRICKS_PRICING_FX_USD_BRL", "5.0"))
    except (ValueError, TypeError):
        return 5.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _envelope(payload: dict, **extras: object) -> str:
    """Envolve resposta com metadata pra auditabilidade."""
    return json.dumps(
        {
            "timestamp": _now_iso(),
            "source": "data_agents.cost_engine.databricks",
            **extras,
            "data": payload,
        },
        indent=2,
        ensure_ascii=False,
        default=str,
    )


def _error(msg: str, **context: object) -> str:
    """Resposta de erro padronizada."""
    return json.dumps(
        {
            "timestamp": _now_iso(),
            "error": True,
            "message": msg,
            **context,
        },
        indent=2,
        ensure_ascii=False,
    )


# ─── Tools ────────────────────────────────────────────────────────────────────


@mcp.tool()
def databricks_pricing_diagnostics() -> str:
    """
    Smoke test do MCP server. Valida que: (1) catalogs YAML carregam,
    (2) engine consegue calcular cenário canônico, (3) defaults estão ok.

    Returns:
        JSON com status + defaults + amostra (cenário Jobs Premium 4w 8h x 22d).
    """
    try:
        # Carrega ambos os catalogs
        azure_catalog = load_databricks_catalog("azure")
        aws_catalog = load_databricks_catalog("aws")

        # Cenário canônico — bate com smoke test da Fase 0
        scenario = DatabricksScenario(
            cloud="azure",
            compute_type="jobs_compute",
            tier="premium",
            photon=False,
            driver_instance="Standard_DS4_v2",
            worker_instance="Standard_DS4_v2",
            num_workers=4,
            hours_per_day=8,
            days_per_month=22,
            region="brazilsouth",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.526,
            worker_instance_cost_per_hour_usd=0.526,
        )
        result = calculate_databricks_cost(scenario, azure_catalog)

        return _envelope(
            {
                "status": "ok",
                "defaults": {
                    "cloud": _default_cloud(),
                    "region": _default_region(),
                    "currency": _default_currency(),
                    "fx_usd_brl": _default_fx_rate(),
                },
                "catalogs_loaded": {
                    "azure": {
                        "schema_version": azure_catalog["schema_version"],
                        "last_updated": azure_catalog["last_updated"],
                        "compute_types": len(azure_catalog["dbu_rates_per_hour"]),
                        "instances": len(azure_catalog["instance_dbu_map"]),
                    },
                    "aws": {
                        "schema_version": aws_catalog["schema_version"],
                        "last_updated": aws_catalog["last_updated"],
                        "compute_types": len(aws_catalog["dbu_rates_per_hour"]),
                        "instances": len(aws_catalog["instance_dbu_map"]),
                    },
                },
                "smoke_test_canonical": {
                    "scenario": (
                        "Jobs Premium 4 workers Standard_DS4_v2 8h × 22d Brazil South on-demand"
                    ),
                    "expected_monthly_usd": 726.88,
                    "actual_monthly_usd": result["totals"]["monthly"],
                    "match": abs(result["totals"]["monthly"] - 726.88) < 0.5,
                },
            }
        )
    except Exception as exc:
        logger.exception("Diagnostics falhou")
        return _error(f"Diagnostics failed: {exc}")


@mcp.tool()
def databricks_pricing_get_dbu_rate(
    compute_type: str,
    tier: str = "premium",
    photon: bool = False,
    cloud: str | None = None,
) -> str:
    """
    Retorna o DBU rate (USD/DBU·hora) pra um compute_type específico.

    Args:
        compute_type: all_purpose_compute | jobs_compute | delta_live_tables |
                      sql | serverless_compute | model_serving | vector_search |
                      mosaic_agent
        tier: standard | premium | enterprise (varia por compute_type)
        photon: True se Photon habilitado (afeta apenas all_purpose e jobs)
        cloud: azure | aws. Default vem de DATABRICKS_PRICING_DEFAULT_CLOUD

    Returns:
        JSON com dbu_rate, compute_type, tier, photon, source.
    """
    cloud = cloud or _default_cloud()
    try:
        catalog = load_databricks_catalog(cloud)  # type: ignore[arg-type]
        rates = catalog["dbu_rates_per_hour"]

        if compute_type not in rates:
            return _error(
                f"compute_type {compute_type!r} não encontrado",
                cloud=cloud,
                available=list(rates.keys()),
            )

        compute_rates = rates[compute_type]

        # Estruturas diferentes — espelha lógica do _resolve_dbu_rate
        if compute_type == "serverless_compute":
            rate = float(compute_rates["base_per_dbu"])
        elif compute_type in ("delta_live_tables", "sql"):
            chosen = tier if tier in compute_rates else "pro"
            rate = float(compute_rates[chosen])
        elif compute_type == "model_serving":
            rate = float(compute_rates["cpu_per_dbu"])
        elif compute_type == "vector_search":
            rate = float(compute_rates["storage_endpoint_per_hour"])
        elif compute_type == "mosaic_agent":
            rate = float(compute_rates["serverless_per_dbu"])
        else:
            # all_purpose_compute, jobs_compute
            tier_data = compute_rates.get(tier)
            if tier_data is None:
                return _error(
                    f"Tier {tier!r} não disponível para {compute_type!r}",
                    cloud=cloud,
                    available=list(compute_rates.keys()),
                )
            photon_key = "photon" if photon else "no_photon"
            rate = float(tier_data[photon_key])

        return _envelope(
            {
                "cloud": cloud,
                "compute_type": compute_type,
                "tier": tier,
                "photon": photon,
                "dbu_rate_per_hour_usd": rate,
            },
            catalog_version=catalog.get("schema_version"),
            catalog_last_updated=catalog.get("last_updated"),
        )
    except Exception as exc:
        logger.exception("get_dbu_rate falhou")
        return _error(f"get_dbu_rate failed: {exc}")


@mcp.tool()
def databricks_pricing_get_instance_price(
    instance_sku: str,
    region: str | None = None,
    cloud: str | None = None,
) -> str:
    """
    Retorna preço USD/hora on-demand pra um instance SKU específico.

    ⚠️ Valores estimados (mock estático). Pra produção, próxima evolução
    consulta Azure Retail Prices API / AWS Pricing API em runtime.

    Args:
        instance_sku: SKU completo (ex: "Standard_DS4_v2", "m5.xlarge")
        region: Region id (default DATABRICKS_PRICING_DEFAULT_REGION)
        cloud: azure | aws. Default DATABRICKS_PRICING_DEFAULT_CLOUD

    Returns:
        JSON com price_usd_per_hour, sku, region, cloud, dbu_per_hour.
    """
    cloud = cloud or _default_cloud()
    region = region or _default_region()
    try:
        price = get_instance_price_usd_per_hour(cloud, region, instance_sku)  # type: ignore[arg-type]

        # Catalog tem DBU multiplier
        catalog = load_databricks_catalog(cloud)  # type: ignore[arg-type]
        inst_data = catalog["instance_dbu_map"].get(instance_sku, {})

        return _envelope(
            {
                "instance_sku": instance_sku,
                "cloud": cloud,
                "region": region,
                "price_usd_per_hour": price,
                "dbu_per_hour": inst_data.get("dbu_per_hour"),
                "vcpu": inst_data.get("vcpu"),
                "ram_gb": inst_data.get("ram_gb"),
                "gpu": inst_data.get("gpu"),
                "is_mock": True,
                "mock_warning": (
                    "Valores são estimativas estáticas. "
                    "Confirmar contra Azure Retail Prices API / AWS Pricing API "
                    "antes de uso em produção."
                ),
            }
        )
    except (KeyError, ValueError) as exc:
        return _error(str(exc), cloud=cloud, region=region, instance_sku=instance_sku)
    except Exception as exc:
        logger.exception("get_instance_price falhou")
        return _error(f"get_instance_price failed: {exc}")


@mcp.tool()
def databricks_pricing_list_instances(
    cloud: str | None = None,
    region: str | None = None,
) -> str:
    """
    Lista todos os instance SKUs disponíveis pra cloud + region.

    Returns:
        JSON com lista ordenada de SKUs.
    """
    cloud = cloud or _default_cloud()
    region = region or _default_region()
    try:
        skus = list_instances_for_region(cloud, region)  # type: ignore[arg-type]
        return _envelope(
            {
                "cloud": cloud,
                "region": region,
                "count": len(skus),
                "instances": skus,
            }
        )
    except Exception as exc:
        logger.exception("list_instances falhou")
        return _error(f"list_instances failed: {exc}")


@mcp.tool()
def databricks_pricing_list_regions(cloud: str | None = None) -> str:
    """Lista regions disponíveis pra cloud."""
    cloud = cloud or _default_cloud()
    try:
        regions = list_regions_for_cloud(cloud)  # type: ignore[arg-type]
        return _envelope(
            {
                "cloud": cloud,
                "count": len(regions),
                "regions": regions,
            }
        )
    except Exception as exc:
        logger.exception("list_regions falhou")
        return _error(f"list_regions failed: {exc}")


@mcp.tool()
def databricks_pricing_calc_cluster_cost(
    cloud: str,
    compute_type: str,
    tier: str,
    photon: bool,
    driver_instance: str,
    worker_instance: str,
    num_workers: int,
    hours_per_day: float,
    days_per_month: int,
    region: str,
    instance_pricing_model: str = "on_demand",
    autoscale_avg_workers_pct: float = 100.0,
    currency: str | None = None,
    fx_rate: float | None = None,
    photon_speedup_factor: float | None = None,
) -> str:
    """
    Calcula custo total mensal de um cluster Databricks completo.

    Args:
        cloud: azure | aws
        compute_type: jobs_compute | all_purpose_compute | etc.
        tier: standard | premium | enterprise (varia por compute_type)
        photon: True se Photon habilitado
        driver_instance: SKU do driver (ex: "Standard_DS4_v2")
        worker_instance: SKU dos workers (geralmente igual ao driver)
        num_workers: quantos workers (não conta driver)
        hours_per_day: 1.0-24.0
        days_per_month: 1-31
        region: region id (brazilsouth, us-east-1, etc.)
        instance_pricing_model: on_demand | spot | reserved_1y | reserved_3y
        autoscale_avg_workers_pct: 0-100, % médio do max em autoscale
        currency: USD | BRL (default = DATABRICKS_PRICING_DEFAULT_CURRENCY)
        fx_rate: cotação USD→BRL (default = DATABRICKS_PRICING_FX_USD_BRL)
        photon_speedup_factor: 1.0-10.0, default 2.5 se Photon=True

    Returns:
        JSON com totals (monthly/annual/tco_36m), breakdown_hourly,
        inputs_resolved, commit_savings, warnings, source.
    """
    currency = currency or _default_currency()
    fx = fx_rate if fx_rate is not None else (_default_fx_rate() if currency == "BRL" else 1.0)

    try:
        # Resolve instance prices
        driver_price = get_instance_price_usd_per_hour(cloud, region, driver_instance)  # type: ignore[arg-type]
        worker_price = get_instance_price_usd_per_hour(cloud, region, worker_instance)  # type: ignore[arg-type]

        scenario = DatabricksScenario(
            cloud=cloud,  # type: ignore[arg-type]
            compute_type=compute_type,  # type: ignore[arg-type]
            tier=tier,  # type: ignore[arg-type]
            photon=photon,
            driver_instance=driver_instance,
            worker_instance=worker_instance,
            num_workers=num_workers,
            hours_per_day=hours_per_day,
            days_per_month=days_per_month,
            region=region,
            instance_pricing_model=instance_pricing_model,  # type: ignore[arg-type]
            driver_instance_cost_per_hour_usd=driver_price,
            worker_instance_cost_per_hour_usd=worker_price,
            autoscale_avg_workers_pct=autoscale_avg_workers_pct,
            photon_speedup_factor=photon_speedup_factor,
            currency_conversion_rate=fx,
            currency_label=currency,
        )
        result = calculate_databricks_cost(scenario)
        return _envelope(result, scenario_input=scenario.__dict__)
    except (KeyError, ValueError) as exc:
        return _error(str(exc), inputs={"cloud": cloud, "compute_type": compute_type})
    except Exception as exc:
        logger.exception("calc_cluster_cost falhou")
        return _error(f"calc_cluster_cost failed: {exc}")


@mcp.tool()
def databricks_pricing_compare_payg_vs_dbcu(
    cloud: str,
    compute_type: str,
    tier: str,
    photon: bool,
    driver_instance: str,
    worker_instance: str,
    num_workers: int,
    hours_per_day: float,
    days_per_month: int,
    region: str,
    instance_pricing_model: str = "on_demand",
    currency: str | None = None,
    fx_rate: float | None = None,
) -> str:
    """
    Compara Pay-as-you-go vs DBCU Commit 1y vs 3y pro cenário.

    Returns:
        JSON com monthly_payg/dbcu_1y/dbcu_3y, savings, breakeven_month,
        recomendação contextual.
    """
    from data_agents.cost_app.databricks.comparisons import compute_comparison

    currency = currency or _default_currency()
    fx = fx_rate if fx_rate is not None else (_default_fx_rate() if currency == "BRL" else 1.0)

    try:
        driver_price = get_instance_price_usd_per_hour(cloud, region, driver_instance)  # type: ignore[arg-type]
        worker_price = get_instance_price_usd_per_hour(cloud, region, worker_instance)  # type: ignore[arg-type]

        scenario = DatabricksScenario(
            cloud=cloud,  # type: ignore[arg-type]
            compute_type=compute_type,  # type: ignore[arg-type]
            tier=tier,  # type: ignore[arg-type]
            photon=photon,
            driver_instance=driver_instance,
            worker_instance=worker_instance,
            num_workers=num_workers,
            hours_per_day=hours_per_day,
            days_per_month=days_per_month,
            region=region,
            instance_pricing_model=instance_pricing_model,  # type: ignore[arg-type]
            driver_instance_cost_per_hour_usd=driver_price,
            worker_instance_cost_per_hour_usd=worker_price,
            currency_conversion_rate=fx,
            currency_label=currency,
        )
        comparison = compute_comparison(scenario)

        return _envelope(
            {
                "currency": comparison.currency,
                "monthly_payg": comparison.monthly_payg,
                "monthly_dbcu_1y": comparison.monthly_dbcu_1y,
                "monthly_dbcu_3y": comparison.monthly_dbcu_3y,
                "savings_1y_annual": comparison.savings_1y_annual,
                "savings_3y_annual": comparison.savings_3y_annual,
                "savings_1y_pct": comparison.savings_1y_pct,
                "savings_3y_pct": comparison.savings_3y_pct,
                "breakeven_month_1y": comparison.breakeven_month_1y,
                "breakeven_month_3y": comparison.breakeven_month_3y,
                "recommendation": comparison.recommendation,
                # Não retorna cumulative_36m por padrão (poluiria output) — disponível via App
            }
        )
    except (KeyError, ValueError) as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.exception("compare_payg_vs_dbcu falhou")
        return _error(f"compare_payg_vs_dbcu failed: {exc}")


@mcp.tool()
def databricks_pricing_currency_convert(
    amount_usd: float,
    target_currency: str = "BRL",
    fx_rate: float | None = None,
) -> str:
    """
    Converte USD pra outra moeda.

    Args:
        amount_usd: valor em USD
        target_currency: "BRL" (default) ou "USD" (no-op)
        fx_rate: cotação USD→target. Default DATABRICKS_PRICING_FX_USD_BRL.

    Returns:
        JSON com converted amount.
    """
    if target_currency == "USD":
        return _envelope({"amount_usd": amount_usd, "amount_converted": amount_usd, "fx_rate": 1.0})

    rate = fx_rate if fx_rate is not None else _default_fx_rate()
    converted = round(amount_usd * rate, 2)

    return _envelope(
        {
            "amount_usd": amount_usd,
            "amount_converted": converted,
            "target_currency": target_currency,
            "fx_rate": rate,
        }
    )


@mcp.tool()
def databricks_pricing_save_scenario(
    cloud: str,
    compute_type: str,
    tier: str,
    photon: bool,
    driver_instance: str,
    worker_instance: str,
    num_workers: int,
    hours_per_day: float,
    days_per_month: int,
    region: str,
    name: str,
    description: str = "",
    instance_pricing_model: str = "on_demand",
    autoscale_avg_workers_pct: float = 100.0,
    currency: str | None = None,
    fx_rate: float | None = None,
    photon_speedup_factor: float | None = None,
) -> str:
    """
    Persiste cenário Databricks como JSON em outputs/cost-scenarios/<uuid>.json
    pra que o Streamlit App carregue via dropdown (Tab 1 → 'Carregar Cenário').

    Bridge Agent → App: agent constrói cenário conversacionalmente, persiste
    aqui, e responde ao usuário com UUID + link clicável pro App em :8514.

    Args:
        ... (mesmos do calc_cluster_cost)
        name: nome curto display (ex: "ETL Bronze produção")
        description: descrição opcional

    Returns:
        JSON com uuid + filepath + URL sugerida pro App.
    """
    currency = currency or _default_currency()
    fx = fx_rate if fx_rate is not None else (_default_fx_rate() if currency == "BRL" else 1.0)

    try:
        driver_price = get_instance_price_usd_per_hour(cloud, region, driver_instance)  # type: ignore[arg-type]
        worker_price = get_instance_price_usd_per_hour(cloud, region, worker_instance)  # type: ignore[arg-type]

        scenario = DatabricksScenario(
            cloud=cloud,  # type: ignore[arg-type]
            compute_type=compute_type,  # type: ignore[arg-type]
            tier=tier,  # type: ignore[arg-type]
            photon=photon,
            driver_instance=driver_instance,
            worker_instance=worker_instance,
            num_workers=num_workers,
            hours_per_day=hours_per_day,
            days_per_month=days_per_month,
            region=region,
            instance_pricing_model=instance_pricing_model,  # type: ignore[arg-type]
            driver_instance_cost_per_hour_usd=driver_price,
            worker_instance_cost_per_hour_usd=worker_price,
            autoscale_avg_workers_pct=autoscale_avg_workers_pct,
            photon_speedup_factor=photon_speedup_factor,
            currency_conversion_rate=fx,
            currency_label=currency,
        )

        scenario_uuid = save_scenario(
            scenario,
            name=name,
            description=description,
            source="agent",
        )

        return _envelope(
            {
                "uuid": scenario_uuid,
                "name": name,
                "filepath": f"outputs/cost-scenarios/{scenario_uuid}.json",
                "app_url": "http://localhost:8514",
                "next_step": (
                    f"Abrir http://localhost:8514 → Sidebar → Cenários Salvos → "
                    f"selecionar '{name}' → Carregar"
                ),
            }
        )
    except (KeyError, ValueError) as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.exception("save_scenario falhou")
        return _error(f"save_scenario failed: {exc}")


# ─── Entry point ─────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point pro stdio server."""
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()
