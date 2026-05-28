"""
Optimization Engine — análises proativas sobre system.billing (Fase 4).

Três análises distintas, todas operando sobre os mesmos DataFrames que o
engine `billing.py` consome (`usage_df` + `prices_df` da Fase 3):

  1. **Rightsizing detector** (Chunk 4.1): cluster com DBU/h médio
     muito abaixo do que o instance_type entrega → sugere downsize.
  2. **Idle hunting** (Chunk 4.2): cluster com hours_per_day alto
     (sempre ligado) mas DBU/h muito baixo → sempre on sem uso.
  3. **Photon ROI validator** (Chunk 4.3): compara cluster com Photon
     vs sem Photon (mesma janela, mesmo perfil) — calcula speedup real
     necessário pra justificar o 2x DBU rate.

Premissa: este engine NÃO conecta no Databricks. Recebe DataFrames já
carregados (mock ou real via Chunk 3.4). Mesma estratégia do billing.py.

Saídas sempre como DataFrames pra consumo fácil no Streamlit + tools MCP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from data_agents.cost_engine.billing import BillingPeriod, _filter_period

if TYPE_CHECKING:
    import pandas as pd


# ─── Catálogo determinístico de capacidade DBU/h por instance_type ───────────
#
# Fonte: data/databricks_pricing/{azure,aws}.yaml já tem `dbu_per_hour` por SKU,
# mas o system.billing não retorna o instance_type por linha — só sku_name
# (categoria do compute). Pra rightsizing, precisamos saber a "capacidade
# esperada" de DBU/h por categoria — uma proxy razoável é a média ponderada
# do catalog.
#
# Quando real mode estiver conectado a system.compute.clusters, podemos
# enriquecer com worker_node_type pra ter `dbu_per_hour` exato do cluster.
# Por enquanto, usamos faixas conservadoras (não inventadas — derivadas das
# Standard_DS*_v2 / m5.*xlarge do catalog Fase 0).

_EXPECTED_DBU_PER_HOUR_BY_COMPUTE_TYPE: dict[str, float] = {
    # Categoria → DBU/h esperado pra cluster mediano de 4 workers
    # (1 driver + 4 workers × 1.5 DBU/h = 7.5 DBU/h pro perfil canonical)
    "jobs_compute": 7.5,
    "all_purpose_compute": 4.5,  # menos paralelismo, mais interativo
    "sql_compute": 4.0,  # warehouses Pro/Classic, perfil leve
    "serverless_compute": 3.0,  # auto-pause agressivo, picos curtos
    "dlt_core": 6.0,
    "other": 5.0,
}


# ─── Domain ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RightsizingThresholds:
    """Limiares pra detectar oportunidades de downsize.

    Attributes:
        underuse_pct: cluster com avg_dbu_per_hour < expected × underuse_pct
            é candidato a downsize. Default 0.5 (50%).
        min_days_observed: descarta clusters com menos de N dias de histórico
            (amostra estatística insuficiente). Default 7.
        min_total_dbus: ignora clusters com consumo muito baixo (ruído).
            Default 10 DBU.
    """

    underuse_pct: float = 0.5
    min_days_observed: int = 7
    min_total_dbus: float = 10.0


@dataclass(frozen=True)
class IdleThresholds:
    """Limiares pra detectar clusters idle (sempre on sem uso).

    Attributes:
        max_dbu_per_hour: cluster com avg_dbu_per_hour < esse valor é idle.
            Default 0.5 DBU/h (muito baixo — quase nada).
        min_days_observed: precisa ter sido visto em pelo menos N dias.
            Default 7.
        min_active_days_pct: precisa estar ativo em > pct dos dias (caso
            contrário é workload bursty, não idle). Default 0.7 (70%).
    """

    max_dbu_per_hour: float = 0.5
    min_days_observed: int = 7
    min_active_days_pct: float = 0.7


# ─── classify_sku helper local (espelha billing.py pra reuso) ───────────────


def _classify_compute_type(sku_name: str) -> str:
    """Mesma lógica de billing.classify_sku — inline pra evitar dep circular."""
    from data_agents.cost_engine.billing import classify_sku

    return classify_sku(sku_name)


# ─── 4.1 — Rightsizing detector ──────────────────────────────────────────────


def detect_rightsizing_opportunities(
    usage_df: pd.DataFrame,
    period: BillingPeriod,
    thresholds: RightsizingThresholds | None = None,
) -> pd.DataFrame:
    """
    Detecta clusters subutilizados (candidatos a downsize).

    Algoritmo:
      1. Filtra usage_df pela janela do period.
      2. Para cada cluster, calcula:
         - avg_dbu_per_hour = total_dbus / hours_observed
         - hours_observed = days_observed × 24 (proxy conservador)
         - expected_dbu_per_hour = média do catálogo pro compute_type dominante
      3. Marca como "underused" se avg < expected × underuse_pct.
      4. Calcula savings_pct estimado (1 - actual/expected).

    Args:
        usage_df: DataFrame system.billing.usage (com cluster_id + cluster_name).
        period: janela de análise.
        thresholds: limiares custom. Default = RightsizingThresholds().

    Returns:
        DataFrame com colunas: cluster_id, cluster_name, compute_type,
        days_observed, total_dbus, avg_dbu_per_hour, expected_dbu_per_hour,
        utilization_pct, suggestion, potential_savings_pct.
        Ordenado por potential_savings_pct DESC.
    """
    import pandas as pd

    if thresholds is None:
        thresholds = RightsizingThresholds()

    filtered = _filter_period(usage_df, period)
    if filtered.empty:
        return pd.DataFrame(
            columns=[
                "cluster_id",
                "cluster_name",
                "compute_type",
                "days_observed",
                "total_dbus",
                "avg_dbu_per_hour",
                "expected_dbu_per_hour",
                "utilization_pct",
                "suggestion",
                "potential_savings_pct",
            ]
        )

    # Remove linhas sem cluster_id (serverless puro)
    filtered = filtered[filtered["cluster_id"].notna()].copy()
    if filtered.empty:
        return pd.DataFrame(
            columns=[
                "cluster_id",
                "cluster_name",
                "compute_type",
                "days_observed",
                "total_dbus",
                "avg_dbu_per_hour",
                "expected_dbu_per_hour",
                "utilization_pct",
                "suggestion",
                "potential_savings_pct",
            ]
        )

    filtered["compute_type"] = filtered["sku_name"].apply(_classify_compute_type)

    # Agrega por cluster (compute_type = moda — categoria dominante)
    def _mode_or_first(series: pd.Series) -> str:
        modes = series.mode()
        return str(modes.iloc[0]) if not modes.empty else "other"

    agg = filtered.groupby(["cluster_id", "cluster_name"], as_index=False).agg(
        compute_type=("compute_type", _mode_or_first),
        days_observed=("usage_date", "nunique"),
        total_dbus=("usage_quantity", "sum"),
    )

    # Computa métricas
    agg["expected_dbu_per_hour"] = agg["compute_type"].map(_EXPECTED_DBU_PER_HOUR_BY_COMPUTE_TYPE)
    agg["expected_dbu_per_hour"] = agg["expected_dbu_per_hour"].fillna(
        _EXPECTED_DBU_PER_HOUR_BY_COMPUTE_TYPE["other"]
    )
    agg["avg_dbu_per_hour"] = agg["total_dbus"] / (agg["days_observed"] * 24)
    agg["utilization_pct"] = (agg["avg_dbu_per_hour"] / agg["expected_dbu_per_hour"] * 100).round(2)

    # Filtros estatísticos
    agg = agg[
        (agg["days_observed"] >= thresholds.min_days_observed)
        & (agg["total_dbus"] >= thresholds.min_total_dbus)
    ].copy()

    # Marca candidatos a downsize
    underuse_threshold = thresholds.underuse_pct * 100
    agg["suggestion"] = agg["utilization_pct"].apply(
        lambda pct: "downsize" if pct < underuse_threshold else "ok"
    )
    agg["potential_savings_pct"] = agg.apply(
        lambda row: (
            round(100 - row["utilization_pct"], 2) if row["suggestion"] == "downsize" else 0.0
        ),
        axis=1,
    )

    # Ordena por potencial de savings (descending)
    agg = agg.sort_values("potential_savings_pct", ascending=False).reset_index(drop=True)

    return agg[
        [
            "cluster_id",
            "cluster_name",
            "compute_type",
            "days_observed",
            "total_dbus",
            "avg_dbu_per_hour",
            "expected_dbu_per_hour",
            "utilization_pct",
            "suggestion",
            "potential_savings_pct",
        ]
    ]


# ─── 4.2 — Idle hunting ──────────────────────────────────────────────────────


def detect_idle_clusters(
    usage_df: pd.DataFrame,
    period: BillingPeriod,
    thresholds: IdleThresholds | None = None,
) -> pd.DataFrame:
    """
    Detecta clusters que ficam ligados mas consomem quase nada.

    Algoritmo:
      1. Filtra usage_df pela janela.
      2. Pra cada cluster, calcula:
         - active_days = dias com qualquer DBU > 0
         - total_dbus
         - avg_dbu_per_hour = total_dbus / (active_days × 24)
         - active_days_pct = active_days / period.days
      3. Marca como "idle" se ativo em mais de min_active_days_pct dos dias
         MAS avg_dbu_per_hour < max_dbu_per_hour (cluster sempre on, mas sem uso real).

    Args:
        usage_df: DataFrame system.billing.usage.
        period: janela.
        thresholds: limiares custom.

    Returns:
        DataFrame com colunas: cluster_id, cluster_name, active_days,
        active_days_pct, total_dbus, avg_dbu_per_hour, verdict, savings_hint.
        Ordenado por desperdício (DBU/h baixo + active_days_pct alto).
    """
    import pandas as pd

    if thresholds is None:
        thresholds = IdleThresholds()

    filtered = _filter_period(usage_df, period)
    if filtered.empty:
        return pd.DataFrame(
            columns=[
                "cluster_id",
                "cluster_name",
                "active_days",
                "active_days_pct",
                "total_dbus",
                "avg_dbu_per_hour",
                "verdict",
                "savings_hint",
            ]
        )

    filtered = filtered[filtered["cluster_id"].notna()].copy()
    if filtered.empty:
        return pd.DataFrame(
            columns=[
                "cluster_id",
                "cluster_name",
                "active_days",
                "active_days_pct",
                "total_dbus",
                "avg_dbu_per_hour",
                "verdict",
                "savings_hint",
            ]
        )

    agg = filtered.groupby(["cluster_id", "cluster_name"], as_index=False).agg(
        active_days=("usage_date", "nunique"),
        total_dbus=("usage_quantity", "sum"),
    )

    agg["active_days_pct"] = (agg["active_days"] / period.days * 100).round(2)
    agg["avg_dbu_per_hour"] = agg["total_dbus"] / (agg["active_days"] * 24)

    # Filtros estatísticos
    agg = agg[agg["active_days"] >= thresholds.min_days_observed].copy()

    # Detecta idle: ativo em muitos dias MAS DBU/h baixo
    min_active_pct = thresholds.min_active_days_pct * 100

    def _verdict(row: pd.Series) -> str:
        if (
            row["active_days_pct"] >= min_active_pct
            and row["avg_dbu_per_hour"] < thresholds.max_dbu_per_hour
        ):
            return "idle"
        if row["avg_dbu_per_hour"] < thresholds.max_dbu_per_hour:
            return "low_use"  # baixo uso mas não tá sempre on (workload bursty)
        return "ok"

    agg["verdict"] = agg.apply(_verdict, axis=1)
    agg["savings_hint"] = agg["verdict"].apply(
        lambda v: {
            "idle": "auto_terminate_or_stop",
            "low_use": "consider_serverless_or_smaller",
            "ok": "—",
        }.get(v, "—")
    )

    # Ordena por gravidade (idle primeiro, depois low_use, depois ok)
    verdict_order = {"idle": 0, "low_use": 1, "ok": 2}
    agg["_sort"] = agg["verdict"].map(verdict_order)
    agg = (
        agg.sort_values(["_sort", "avg_dbu_per_hour"]).drop(columns="_sort").reset_index(drop=True)
    )

    return agg[
        [
            "cluster_id",
            "cluster_name",
            "active_days",
            "active_days_pct",
            "total_dbus",
            "avg_dbu_per_hour",
            "verdict",
            "savings_hint",
        ]
    ]


# ─── 4.3 — Photon ROI validator ──────────────────────────────────────────────


@dataclass(frozen=True)
class PhotonROIResult:
    """Resultado da análise de ROI do Photon comparando 2 cenários.

    Photon dobra o DBU rate. Pra valer a pena economicamente, precisa acelerar
    o workload em >= 2× (assim hours_per_day cai metade e custo total empata).

    Attributes:
        cluster_id_with: ID do cluster com Photon.
        cluster_id_without: ID do cluster sem Photon (comparação).
        total_dbus_with: DBU total no cluster com Photon.
        total_dbus_without: DBU total no cluster sem Photon.
        relative_consumption: dbus_with / dbus_without. Idealmente < 1.0
            (Photon acelerou tanto que consumiu MENOS DBU mesmo cobrando 2×).
        breakeven_speedup: speedup mínimo necessário pra empatar custo (2.0).
        actual_speedup_proxy: estimativa baseada no consumo relativo.
        verdict: "photon_worth_it" | "photon_marginal" | "photon_not_worth".
        caveat: limitações da análise (sempre presente).
    """

    cluster_id_with: str
    cluster_id_without: str
    total_dbus_with: float
    total_dbus_without: float
    relative_consumption: float
    breakeven_speedup: float
    actual_speedup_proxy: float
    verdict: str
    caveat: str


def evaluate_photon_roi(
    usage_df: pd.DataFrame,
    period: BillingPeriod,
    cluster_id_with_photon: str,
    cluster_id_without_photon: str,
) -> PhotonROIResult:
    """
    Compara 2 clusters (1 com Photon, 1 sem) e estima se Photon vale a pena.

    Premissas FORTES (caveat sempre exposto ao usuário):
      - Os 2 clusters rodam workload SIMILAR (mesma natureza). Se um faz ETL
        e outro SQL ad-hoc, a comparação é inválida.
      - Não temos métrica de tempo real (`task_duration_seconds`) no
        system.billing — usamos DBU total como proxy. Photon que rodou
        rápido consome MENOS DBU total → relative_consumption < 1.0.
      - Sem `system.query.history` (não documentado no skill), não dá pra
        ter speedup exato. Por isso o resultado é "proxy", não definitivo.

    Algoritmo:
      1. Filtra usage_df pelos 2 clusters na mesma janela.
      2. Calcula total_dbus_with e total_dbus_without.
      3. relative_consumption = with / without.
      4. Se relative_consumption < 0.5: Photon acelerou MUITO (consumiu metade
         ou menos DBU) → economiza dinheiro mesmo cobrando 2×. verdict =
         "photon_worth_it".
      5. Se 0.5 ≤ relative_consumption ≤ 0.7: marginal — pode ou não compensar
         dependendo do workload. verdict = "photon_marginal".
      6. Se relative_consumption > 0.7: Photon não acelerou o suficiente —
         cobra 2× mas só economiza < 30% em DBU total. verdict =
         "photon_not_worth".

    Args:
        usage_df: DataFrame system.billing.usage.
        period: janela de análise.
        cluster_id_with_photon: ID do cluster Photon=on.
        cluster_id_without_photon: ID do cluster Photon=off.

    Returns:
        PhotonROIResult com métricas e verdict.

    Raises:
        ValueError: se algum dos clusters não tem consumo na janela.
    """
    filtered = _filter_period(usage_df, period)
    if filtered.empty:
        raise ValueError("usage_df vazio na janela informada — sem dados pra comparar")

    with_df = filtered[filtered["cluster_id"] == cluster_id_with_photon]
    without_df = filtered[filtered["cluster_id"] == cluster_id_without_photon]

    if with_df.empty:
        raise ValueError(f"cluster_id_with_photon={cluster_id_with_photon!r} sem dados na janela")
    if without_df.empty:
        raise ValueError(
            f"cluster_id_without_photon={cluster_id_without_photon!r} sem dados na janela"
        )

    total_with = float(with_df["usage_quantity"].sum())
    total_without = float(without_df["usage_quantity"].sum())

    if total_without == 0:
        raise ValueError("cluster sem Photon teve 0 DBU na janela — comparação inválida")

    relative = total_with / total_without
    # Se relative < 1 → Photon foi mais eficiente (consumiu menos DBU)
    # Speedup proxy = 1 / (relative / 2) → quanto mais rápido o Photon rodou
    # pra justificar 2× custo
    actual_speedup_proxy = 2.0 / relative if relative > 0 else float("inf")

    if relative < 0.5:
        verdict = "photon_worth_it"
    elif relative <= 0.7:
        verdict = "photon_marginal"
    else:
        verdict = "photon_not_worth"

    caveat = (
        "Análise PROXY baseada em DBU total — não substitui benchmark de tempo "
        "real (system.query.history não disponível neste schema). Compara workloads "
        "SIMILARES; se os 2 clusters rodam pipelines diferentes, resultado inválido."
    )

    return PhotonROIResult(
        cluster_id_with=cluster_id_with_photon,
        cluster_id_without=cluster_id_without_photon,
        total_dbus_with=round(total_with, 2),
        total_dbus_without=round(total_without, 2),
        relative_consumption=round(relative, 4),
        breakeven_speedup=2.0,
        actual_speedup_proxy=round(actual_speedup_proxy, 2),
        verdict=verdict,
        caveat=caveat,
    )


__all__ = [
    "IdleThresholds",
    "PhotonROIResult",
    "RightsizingThresholds",
    "detect_idle_clusters",
    "detect_rightsizing_opportunities",
    "evaluate_photon_roi",
]
