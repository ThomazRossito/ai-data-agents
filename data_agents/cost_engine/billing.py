"""
Billing Engine — análise FinOps de workloads Databricks em produção.

Diferente do `databricks.py` (Fase 0 — cotação determinística baseada em catalog
YAML), este módulo processa dados REAIS de consumo Databricks expostos pela
tabela `system.billing.usage` do Unity Catalog.

Schema oficial de `system.billing.usage` (verificado em
skills/databricks/databricks-unity-catalog/5-system-tables.md):

  Column            Type      Description
  ----------------- --------- --------------------------------------------
  usage_date        DATE      Data do consumo
  workspace_id      BIGINT    ID do workspace
  sku_name          STRING    SKU consumido (ex: "PREMIUM_JOBS_COMPUTE_AZURE")
  usage_quantity    DECIMAL   Quantidade consumida
  usage_unit        STRING    Unidade (sempre "DBU" pra DBUs)
  cloud             STRING    "AZURE" | "AWS" | "GCP"
  usage_metadata    MAP       Inclui cluster_id, cluster_name, job_id, etc

Schema oficial de `system.billing.list_prices`:

  Column            Type      Description
  ----------------- --------- --------------------------------------------
  sku_name          STRING    SKU (chave com usage)
  cloud             STRING    Cloud (chave com usage)
  currency_code     STRING    "USD"
  pricing           STRUCT    Estrutura com pricing.default (USD/DBU)
  price_start_time  TIMESTAMP Início de vigência
  price_end_time    TIMESTAMP Fim de vigência (NULL = vigente)

Este engine **não conecta no Databricks** — recebe DataFrames já carregados.
Quem chama é responsável por:
  (a) Buscar via SQL real (com databricks-sdk + warehouse), OU
  (b) Buscar do mock (billing_mock.py — útil pra dev/test)

Pattern de SKU → compute_type (verificado no skill `5-system-tables.md`):
  - "%ALL_PURPOSE%"  → all_purpose_compute
  - "%JOBS%"         → jobs_compute
  - "%SQL%"          → sql_compute
  - "%SERVERLESS%"   → serverless_compute
  - else             → "other"

Convenção: todas as funções retornam pandas DataFrames pra ficar fácil
consumir em Streamlit (Plotly aceita DataFrame direto) e em tools MCP
(que serializam pra JSON).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


# ─── Domain ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BillingPeriod:
    """Janela de análise.

    Args:
        start_date: data inicial inclusiva.
        end_date: data final inclusiva.
        workspace_id: filtro opcional (None = todos os workspaces).
    """

    start_date: date
    end_date: date
    workspace_id: int | None = None

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise ValueError(
                f"start_date ({self.start_date}) deve ser <= end_date ({self.end_date})"
            )

    @property
    def days(self) -> int:
        """Número de dias na janela (inclusivo)."""
        return (self.end_date - self.start_date).days + 1


# SKU pattern → compute_type. Ordem importa: SERVERLESS antes de SQL/JOBS porque
# alguns SKUs contêm múltiplas keywords (ex: "SERVERLESS_SQL_*").
_SKU_PATTERNS: tuple[tuple[str, str], ...] = (
    ("SERVERLESS", "serverless_compute"),
    ("ALL_PURPOSE", "all_purpose_compute"),
    ("JOBS", "jobs_compute"),
    ("SQL", "sql_compute"),
    ("DLT", "dlt_core"),
)


def classify_sku(sku_name: str) -> str:
    """Classifica um SKU em compute_type segundo pattern matching no nome.

    Args:
        sku_name: SKU do system.billing.usage (ex: "PREMIUM_JOBS_COMPUTE_AZURE").

    Returns:
        Compute type: "jobs_compute", "all_purpose_compute", "sql_compute",
        "serverless_compute", "dlt_core" ou "other".
    """
    sku_upper = sku_name.upper()
    for pattern, compute_type in _SKU_PATTERNS:
        if pattern in sku_upper:
            return compute_type
    return "other"


# ─── Aggregation primitives ─────────────────────────────────────────────────


def _filter_period(df: pd.DataFrame, period: BillingPeriod) -> pd.DataFrame:
    """Filtra DataFrame pela janela do BillingPeriod.

    Espera coluna 'usage_date' como date/datetime e (opcionalmente) 'workspace_id'.
    """
    mask = (df["usage_date"] >= period.start_date) & (df["usage_date"] <= period.end_date)
    if period.workspace_id is not None and "workspace_id" in df.columns:
        mask &= df["workspace_id"] == period.workspace_id
    return df.loc[mask].copy()


def aggregate_dbu_daily(
    usage_df: pd.DataFrame,
    period: BillingPeriod,
) -> pd.DataFrame:
    """Agrega DBU consumido por dia × sku_name.

    Args:
        usage_df: DataFrame com schema system.billing.usage.
        period: janela de análise.

    Returns:
        DataFrame com colunas [usage_date, sku_name, total_dbus] ordenado por
        usage_date ASC, total_dbus DESC.
    """
    import pandas as pd

    filtered = _filter_period(usage_df, period)
    if filtered.empty:
        return pd.DataFrame(columns=["usage_date", "sku_name", "total_dbus"])

    agg = (
        filtered.groupby(["usage_date", "sku_name"], as_index=False)["usage_quantity"]
        .sum()
        .rename(columns={"usage_quantity": "total_dbus"})
        .sort_values(["usage_date", "total_dbus"], ascending=[True, False])
        .reset_index(drop=True)
    )
    return agg


def top_cost_clusters(
    usage_df: pd.DataFrame,
    prices_df: pd.DataFrame,
    period: BillingPeriod,
    limit: int = 10,
) -> pd.DataFrame:
    """Top N clusters por custo $ na janela (JOIN com list_prices).

    Args:
        usage_df: schema system.billing.usage. Coluna 'cluster_id' DEVE estar
            extraída de usage_metadata pelo caller (ex: via SQL ou mock).
        prices_df: schema system.billing.list_prices. Coluna 'price_per_dbu'
            DEVE estar extraída de pricing.default pelo caller.
        period: janela.
        limit: top N (default 10).

    Returns:
        DataFrame com colunas [cluster_id, cluster_name, total_dbus,
        estimated_cost_usd] ordenado por estimated_cost_usd DESC.
        Linhas com cluster_id NULL são removidas (são consumos sem cluster
        atribuído — DLT/serverless geralmente).
    """
    import pandas as pd

    filtered = _filter_period(usage_df, period)
    if filtered.empty:
        return pd.DataFrame(
            columns=["cluster_id", "cluster_name", "total_dbus", "estimated_cost_usd"]
        )

    # Remove linhas sem cluster_id (serverless, DLT compartilhado, etc)
    filtered = filtered[filtered["cluster_id"].notna()].copy()
    if filtered.empty:
        return pd.DataFrame(
            columns=["cluster_id", "cluster_name", "total_dbus", "estimated_cost_usd"]
        )

    # JOIN com prices: usa price_end_time IS NULL pra pegar vigente
    current_prices = prices_df[prices_df["price_end_time"].isna()][
        ["sku_name", "cloud", "price_per_dbu"]
    ]

    joined = filtered.merge(current_prices, on=["sku_name", "cloud"], how="left")
    joined["estimated_cost_usd"] = joined["usage_quantity"] * joined["price_per_dbu"]

    agg = (
        joined.groupby(["cluster_id", "cluster_name"], as_index=False)
        .agg(total_dbus=("usage_quantity", "sum"), estimated_cost_usd=("estimated_cost_usd", "sum"))
        .sort_values("estimated_cost_usd", ascending=False)
        .head(limit)
        .reset_index(drop=True)
    )
    return agg


def cost_by_compute_type(
    usage_df: pd.DataFrame,
    prices_df: pd.DataFrame,
    period: BillingPeriod,
) -> pd.DataFrame:
    """Breakdown DBU + custo $ por compute_type (jobs/all_purpose/sql/serverless).

    Aplica classify_sku() pra mapear sku_name → compute_type, depois agrega.

    Args:
        usage_df: schema system.billing.usage.
        prices_df: schema system.billing.list_prices com price_per_dbu extraído.
        period: janela.

    Returns:
        DataFrame com colunas [compute_type, total_dbus, estimated_cost_usd,
        dbus_pct, cost_pct] ordenado por estimated_cost_usd DESC.
    """
    import pandas as pd

    filtered = _filter_period(usage_df, period)
    if filtered.empty:
        return pd.DataFrame(
            columns=[
                "compute_type",
                "total_dbus",
                "estimated_cost_usd",
                "dbus_pct",
                "cost_pct",
            ]
        )

    current_prices = prices_df[prices_df["price_end_time"].isna()][
        ["sku_name", "cloud", "price_per_dbu"]
    ]
    joined = filtered.merge(current_prices, on=["sku_name", "cloud"], how="left")
    joined["compute_type"] = joined["sku_name"].apply(classify_sku)
    joined["estimated_cost_usd"] = joined["usage_quantity"] * joined["price_per_dbu"]

    agg = (
        joined.groupby("compute_type", as_index=False)
        .agg(total_dbus=("usage_quantity", "sum"), estimated_cost_usd=("estimated_cost_usd", "sum"))
        .sort_values("estimated_cost_usd", ascending=False)
        .reset_index(drop=True)
    )

    total_dbus = agg["total_dbus"].sum()
    total_cost = agg["estimated_cost_usd"].sum()
    agg["dbus_pct"] = (agg["total_dbus"] / total_dbus * 100).round(2) if total_dbus > 0 else 0.0
    agg["cost_pct"] = (
        (agg["estimated_cost_usd"] / total_cost * 100).round(2) if total_cost > 0 else 0.0
    )

    return agg


# ─── Bridge Fase 2 ↔ Fase 3 (estimate vs actual) ────────────────────────────


@dataclass(frozen=True)
class EstimateVsActual:
    """Resultado da comparação cenário estimado (Fase 2) vs realizado (Fase 3).

    Attributes:
        scenario_uuid: UUID do cenário (Fase 2).
        scenario_name: nome do cenário display.
        estimated_monthly_usd: custo estimado pelo cost_engine.databricks.
        actual_monthly_usd: custo realizado extrapolado da janela.
        actual_period_days: dias na janela analisada.
        variance_pct: (actual - estimate) / estimate * 100. Positivo = gastou
            mais do que previsto.
        verdict: "on_budget" (|variance| <= 10%) | "over_budget" (variance > 10%)
            | "under_budget" (variance < -10%).
    """

    scenario_uuid: str
    scenario_name: str
    estimated_monthly_usd: float
    actual_monthly_usd: float
    actual_period_days: int
    variance_pct: float
    verdict: str


def compare_estimate_vs_actual(
    scenario_envelope: dict,
    estimated_monthly_usd: float,
    actual_total_usd_in_period: float,
    period: BillingPeriod,
) -> EstimateVsActual:
    """Compara um cenário estimado (Fase 2) com o consumo realizado (Fase 3).

    O caller é responsável por:
      1. Carregar o scenario_envelope via scenarios.load_envelope(uuid)
      2. Calcular estimated_monthly_usd via cost_engine.databricks.calculate_databricks_cost
      3. Calcular actual_total_usd_in_period via top_cost_clusters ou
         cost_by_compute_type filtrando pelo cluster/SKU do cenário

    Args:
        scenario_envelope: dict retornado por scenarios.load_envelope.
            Espera chaves 'uuid', 'name'.
        estimated_monthly_usd: custo mensal estimado do scenario_envelope
            calculado pelo cost_engine.databricks.
        actual_total_usd_in_period: custo total realizado na janela `period`.
        period: janela de análise (define dias pra extrapolar pro mensal).

    Returns:
        EstimateVsActual com variance_pct + verdict.
    """
    days_in_period = period.days
    # Extrapola actual pro mensal (assume distribuição uniforme nos dias).
    # Premissa: o user analisa períodos relativamente uniformes (não mistura
    # 1 semana de pico + 3 semanas de idle).
    actual_monthly_usd = actual_total_usd_in_period * (30 / days_in_period)

    if estimated_monthly_usd <= 0:
        variance_pct = 0.0
    else:
        variance_pct = (actual_monthly_usd - estimated_monthly_usd) / estimated_monthly_usd * 100

    if abs(variance_pct) <= 10:
        verdict = "on_budget"
    elif variance_pct > 10:
        verdict = "over_budget"
    else:
        verdict = "under_budget"

    return EstimateVsActual(
        scenario_uuid=scenario_envelope.get("uuid", "?"),
        scenario_name=scenario_envelope.get("name", "?"),
        estimated_monthly_usd=round(estimated_monthly_usd, 2),
        actual_monthly_usd=round(actual_monthly_usd, 2),
        actual_period_days=days_in_period,
        variance_pct=round(variance_pct, 2),
        verdict=verdict,
    )
