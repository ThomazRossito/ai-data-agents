"""
Databricks Billing — MCP Server Customizado (Fase 3).

Expõe `data_agents.cost_engine.billing` como 5 tools FastMCP. Permite que
agents analisem workloads Databricks em PRODUÇÃO via `system.billing.usage`
do Unity Catalog.

Tools disponíveis (5):
  - databricks_billing_diagnostics                  — smoke test (mock vs real)
  - databricks_billing_get_dbu_usage_daily          — DBU/dia × SKU na janela
  - databricks_billing_get_top_cost_clusters        — top N clusters por custo
  - databricks_billing_get_cost_by_compute_type     — breakdown por tipo
  - databricks_billing_compare_estimate_vs_actual   — bridge Fase 2 ↔ Fase 3

Modos:
  - DATABRICKS_BILLING_MOCK_MODE=true  (default): dados sintéticos (dev/test)
  - DATABRICKS_BILLING_MOCK_MODE=false: SQL real via databricks-sdk

Requer (modo real):
  - DATABRICKS_HOST + DATABRICKS_TOKEN
  - DATABRICKS_BILLING_WAREHOUSE_ID (warehouse pra rodar SQL)
  - Unity Catalog habilitado + workspace admin + SELECT em system.billing

Comando entry point: databricks-billing-mcp (declarado em pyproject.toml)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone

from mcp.server.fastmcp import FastMCP

from data_agents.cost_app.databricks.billing_mock import (
    generate_mock_list_prices_df,
    generate_mock_usage_df,
    get_mock_metadata,
)
from data_agents.cost_engine.billing import (
    BillingPeriod,
    aggregate_dbu_daily,
    compare_estimate_vs_actual,
    cost_by_compute_type,
    top_cost_clusters,
)

logger = logging.getLogger("databricks_billing_mcp")

# ─── FastMCP Server ─────────────────────────────────────────────────────────

mcp = FastMCP("databricks-billing")


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _is_mock_mode() -> bool:
    """Mock mode default = true. Só vira false com env explicito 'false'."""
    return os.environ.get("DATABRICKS_BILLING_MOCK_MODE", "true").lower() != "false"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _envelope(payload: dict, **extras: object) -> str:
    """Envolve resposta com metadata pra auditabilidade."""
    return json.dumps(
        {
            "timestamp": _now_iso(),
            "source": "data_agents.cost_engine.billing",
            "mock_mode": _is_mock_mode(),
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


def _parse_date(value: str | date) -> date:
    """Aceita 'YYYY-MM-DD' ou date object."""
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def _load_dataframes(cloud: str = "AZURE") -> tuple:
    """Carrega usage_df + prices_df do mock ou SQL real.

    Returns:
        (usage_df, prices_df) — pandas DataFrames.

    Raises:
        RuntimeError: se mock_mode=false e a integração real ainda não está
            implementada (Chunk 3.1 entrega só mock; real fica pra Chunk 3.x).
    """
    if _is_mock_mode():
        # Por padrão gera 60 dias de histórico — caller filtra pela janela depois
        usage_df = generate_mock_usage_df(days=60, cloud=cloud)
        prices_df = generate_mock_list_prices_df(cloud=cloud)
        return usage_df, prices_df

    # Real mode — placeholder pro Chunk 3.x. Por ora, falha cedo e claro.
    raise RuntimeError(
        "DATABRICKS_BILLING_MOCK_MODE=false ainda não suportado no Chunk 3.1. "
        "Integração com databricks-sdk + SQL real virá em chunk posterior. "
        "Use mock mode (DATABRICKS_BILLING_MOCK_MODE=true) por enquanto."
    )


# ─── Tools ───────────────────────────────────────────────────────────────────


@mcp.tool()
def databricks_billing_diagnostics() -> str:
    """
    Smoke test do MCP server: valida mock generator + engine + retorna metadata.

    Returns:
        JSON com mock_mode + sample (últimos 7 dias DBU total) + metadata.
    """
    try:
        usage_df, prices_df = _load_dataframes(cloud="AZURE")

        # Sample: total DBU últimos 7 dias
        if usage_df.empty:
            sample = {"status": "empty_dataset", "total_dbus_last_7d": 0}
        else:
            end = usage_df["usage_date"].max()
            start = end - timedelta(days=6)
            period = BillingPeriod(start_date=start, end_date=end)
            daily = aggregate_dbu_daily(usage_df, period)
            sample = {
                "status": "ok",
                "total_dbus_last_7d": float(daily["total_dbus"].sum()),
                "days_with_data": int(daily["usage_date"].nunique()) if not daily.empty else 0,
                "unique_skus": int(daily["sku_name"].nunique()) if not daily.empty else 0,
                "period_start": str(start),
                "period_end": str(end),
            }

        meta = get_mock_metadata() if _is_mock_mode() else {"is_mock": False}

        return _envelope(
            {
                "smoke_test": sample,
                "mock_metadata": meta,
                "engine_loaded": True,
            }
        )
    except Exception as exc:
        logger.exception("diagnostics falhou")
        return _error(f"diagnostics failed: {exc}")


@mcp.tool()
def databricks_billing_get_dbu_usage_daily(
    start_date: str,
    end_date: str,
    workspace_id: int | None = None,
    cloud: str = "AZURE",
) -> str:
    """
    Retorna DBU consumido por dia × sku_name na janela.

    Args:
        start_date: 'YYYY-MM-DD' inclusivo.
        end_date: 'YYYY-MM-DD' inclusivo.
        workspace_id: filtra por workspace (None = todos).
        cloud: "AZURE" ou "AWS" (default AZURE).

    Returns:
        JSON com data: count, period, rows (lista [usage_date, sku_name, total_dbus]).
    """
    try:
        usage_df, _ = _load_dataframes(cloud=cloud)
        period = BillingPeriod(
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
            workspace_id=workspace_id,
        )
        daily = aggregate_dbu_daily(usage_df, period)

        return _envelope(
            {
                "period": {
                    "start_date": str(period.start_date),
                    "end_date": str(period.end_date),
                    "days": period.days,
                    "workspace_id": workspace_id,
                    "cloud": cloud.upper(),
                },
                "count": len(daily),
                "total_dbus": float(daily["total_dbus"].sum()) if not daily.empty else 0.0,
                "rows": daily.to_dict(orient="records"),
            }
        )
    except ValueError as exc:
        return _error(f"Invalid period: {exc}")
    except Exception as exc:
        logger.exception("get_dbu_usage_daily falhou")
        return _error(f"get_dbu_usage_daily failed: {exc}")


@mcp.tool()
def databricks_billing_get_top_cost_clusters(
    start_date: str,
    end_date: str,
    limit: int = 10,
    workspace_id: int | None = None,
    cloud: str = "AZURE",
) -> str:
    """
    Top N clusters por custo $ na janela (JOIN com list_prices).

    Args:
        start_date: 'YYYY-MM-DD' inclusivo.
        end_date: 'YYYY-MM-DD' inclusivo.
        limit: top N (default 10).
        workspace_id: filtra por workspace (None = todos).
        cloud: "AZURE" ou "AWS" (default AZURE).

    Returns:
        JSON com data: count, period, rows (lista [cluster_id, cluster_name,
        total_dbus, estimated_cost_usd]).
    """
    try:
        usage_df, prices_df = _load_dataframes(cloud=cloud)
        period = BillingPeriod(
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
            workspace_id=workspace_id,
        )
        top = top_cost_clusters(usage_df, prices_df, period, limit=limit)

        return _envelope(
            {
                "period": {
                    "start_date": str(period.start_date),
                    "end_date": str(period.end_date),
                    "days": period.days,
                    "workspace_id": workspace_id,
                    "cloud": cloud.upper(),
                },
                "limit": limit,
                "count": len(top),
                "total_cost_usd": float(top["estimated_cost_usd"].sum()) if not top.empty else 0.0,
                "rows": top.to_dict(orient="records"),
            }
        )
    except ValueError as exc:
        return _error(f"Invalid period: {exc}")
    except Exception as exc:
        logger.exception("get_top_cost_clusters falhou")
        return _error(f"get_top_cost_clusters failed: {exc}")


@mcp.tool()
def databricks_billing_get_cost_by_compute_type(
    start_date: str,
    end_date: str,
    workspace_id: int | None = None,
    cloud: str = "AZURE",
) -> str:
    """
    Breakdown DBU + custo $ por compute_type na janela.

    Classifica cada SKU em jobs_compute, all_purpose_compute, sql_compute,
    serverless_compute, dlt_core ou 'other' via pattern matching.

    Args:
        start_date: 'YYYY-MM-DD' inclusivo.
        end_date: 'YYYY-MM-DD' inclusivo.
        workspace_id: filtra por workspace (None = todos).
        cloud: "AZURE" ou "AWS" (default AZURE).

    Returns:
        JSON com data: count, period, rows (lista [compute_type, total_dbus,
        estimated_cost_usd, dbus_pct, cost_pct]).
    """
    try:
        usage_df, prices_df = _load_dataframes(cloud=cloud)
        period = BillingPeriod(
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
            workspace_id=workspace_id,
        )
        breakdown = cost_by_compute_type(usage_df, prices_df, period)

        return _envelope(
            {
                "period": {
                    "start_date": str(period.start_date),
                    "end_date": str(period.end_date),
                    "days": period.days,
                    "workspace_id": workspace_id,
                    "cloud": cloud.upper(),
                },
                "count": len(breakdown),
                "total_dbus": float(breakdown["total_dbus"].sum()) if not breakdown.empty else 0.0,
                "total_cost_usd": float(breakdown["estimated_cost_usd"].sum())
                if not breakdown.empty
                else 0.0,
                "rows": breakdown.to_dict(orient="records"),
            }
        )
    except ValueError as exc:
        return _error(f"Invalid period: {exc}")
    except Exception as exc:
        logger.exception("get_cost_by_compute_type falhou")
        return _error(f"get_cost_by_compute_type failed: {exc}")


@mcp.tool()
def databricks_billing_compare_estimate_vs_actual(
    scenario_uuid: str,
    start_date: str,
    end_date: str,
    cluster_name_filter: str | None = None,
    workspace_id: int | None = None,
) -> str:
    """
    Bridge Fase 2 ↔ Fase 3: compara cenário estimado com consumo realizado.

    Carrega o cenário (Fase 2), calcula custo estimado mensal via engine
    Fase 0, busca consumo realizado na janela via system.billing, extrapola
    pro mensal, calcula variance %.

    Args:
        scenario_uuid: UUID do cenário salvo (Fase 2 — outputs/cost-scenarios/).
        start_date: 'YYYY-MM-DD' inclusivo (janela do consumo realizado).
        end_date: 'YYYY-MM-DD' inclusivo.
        cluster_name_filter: se informado, filtra usage só desse cluster.
            Útil quando o cenário descreve 1 workload específico (ex:
            "etl-bronze-prod"). None = todos os clusters somados.
        workspace_id: filtra por workspace (None = todos).

    Returns:
        JSON com estimated_monthly_usd, actual_monthly_usd, variance_pct,
        verdict (on_budget/over_budget/under_budget), period.
    """
    try:
        # 1. Carrega scenario envelope (Fase 2)
        from data_agents.cost_app.databricks.scenarios import load_envelope
        from data_agents.cost_engine.databricks import (
            DatabricksScenario,
            calculate_databricks_cost,
            load_databricks_catalog,
        )

        envelope = load_envelope(scenario_uuid)
        scenario_dict = envelope["scenario"]
        cloud = scenario_dict.get("cloud", "azure").upper()

        # 2. Calcula estimated_monthly_usd via Fase 0
        # Remove campos extras que DatabricksScenario não aceita
        valid_fields = {
            "cloud",
            "compute_type",
            "tier",
            "photon",
            "driver_instance",
            "worker_instance",
            "num_workers",
            "hours_per_day",
            "days_per_month",
            "region",
            "instance_pricing_model",
            "driver_instance_cost_per_hour_usd",
            "worker_instance_cost_per_hour_usd",
            "autoscale_avg_workers_pct",
            "photon_speedup_factor",
            "currency_conversion_rate",
            "currency_label",
            "scenario_id",
        }
        scenario_clean = {k: v for k, v in scenario_dict.items() if k in valid_fields}
        scenario = DatabricksScenario(**scenario_clean)
        catalog = load_databricks_catalog(scenario.cloud)
        result = calculate_databricks_cost(scenario, catalog)
        estimated_monthly = float(result["totals"]["monthly"])

        # 3. Busca actual via mock/real
        usage_df, prices_df = _load_dataframes(cloud=cloud)
        period = BillingPeriod(
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
            workspace_id=workspace_id,
        )

        # Filtra por cluster_name se informado
        if cluster_name_filter is not None:
            usage_df = usage_df[usage_df["cluster_name"] == cluster_name_filter].copy()

        breakdown = cost_by_compute_type(usage_df, prices_df, period)
        actual_total = float(breakdown["estimated_cost_usd"].sum()) if not breakdown.empty else 0.0

        # 4. Compute variance via engine
        comparison = compare_estimate_vs_actual(
            scenario_envelope=envelope,
            estimated_monthly_usd=estimated_monthly,
            actual_total_usd_in_period=actual_total,
            period=period,
        )

        return _envelope(
            {
                "scenario_uuid": comparison.scenario_uuid,
                "scenario_name": comparison.scenario_name,
                "estimated_monthly_usd": comparison.estimated_monthly_usd,
                "actual_monthly_usd": comparison.actual_monthly_usd,
                "actual_period_days": comparison.actual_period_days,
                "variance_pct": comparison.variance_pct,
                "verdict": comparison.verdict,
                "cluster_name_filter": cluster_name_filter,
                "period": {
                    "start_date": str(period.start_date),
                    "end_date": str(period.end_date),
                    "days": period.days,
                    "workspace_id": workspace_id,
                    "cloud": cloud,
                },
            }
        )
    except FileNotFoundError as exc:
        return _error(f"Scenario not found: {exc}")
    except ValueError as exc:
        return _error(f"Invalid input: {exc}")
    except Exception as exc:
        logger.exception("compare_estimate_vs_actual falhou")
        return _error(f"compare_estimate_vs_actual failed: {exc}")


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
