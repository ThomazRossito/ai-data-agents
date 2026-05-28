"""Tests do cost_engine/optimization.py (Fase 4 — análises proativas).

Cobre:
  - detect_rightsizing_opportunities: detecção de underuse + filtros estatísticos
  - detect_idle_clusters: distinção idle vs low_use vs ok
  - evaluate_photon_roi: 3 verdicts + edge cases (cluster sem dados)
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from data_agents.cost_app.databricks.billing_mock import generate_mock_usage_df
from data_agents.cost_engine.billing import BillingPeriod
from data_agents.cost_engine.optimization import (
    IdleThresholds,
    PhotonROIResult,
    RightsizingThresholds,
    detect_idle_clusters,
    detect_rightsizing_opportunities,
    evaluate_photon_roi,
)


@pytest.fixture
def usage_df_30d() -> pd.DataFrame:
    return generate_mock_usage_df(days=30, cloud="AZURE", seed=42)


@pytest.fixture
def period_30d(usage_df_30d: pd.DataFrame) -> BillingPeriod:
    end = usage_df_30d["usage_date"].max()
    return BillingPeriod(start_date=end - timedelta(days=29), end_date=end)


# ── Thresholds dataclasses ──────────────────────────────────────────────────


class TestThresholds:
    def test_rightsizing_defaults(self):
        t = RightsizingThresholds()
        assert t.underuse_pct == 0.5
        assert t.min_days_observed == 7
        assert t.min_total_dbus == 10.0

    def test_idle_defaults(self):
        t = IdleThresholds()
        assert t.max_dbu_per_hour == 0.5
        assert t.min_days_observed == 7
        assert t.min_active_days_pct == 0.7

    def test_thresholds_frozen(self):
        """Dataclasses devem ser imutáveis."""
        t = RightsizingThresholds()
        with pytest.raises((AttributeError, Exception)):
            t.underuse_pct = 0.9  # type: ignore[misc]


# ── detect_rightsizing_opportunities ────────────────────────────────────────


class TestRightsizing:
    def test_returns_expected_columns(self, usage_df_30d, period_30d):
        result = detect_rightsizing_opportunities(usage_df_30d, period_30d)
        expected_cols = {
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
        }
        assert expected_cols == set(result.columns)

    def test_ordered_by_savings_desc(self, usage_df_30d, period_30d):
        result = detect_rightsizing_opportunities(usage_df_30d, period_30d)
        if len(result) >= 2:
            assert (
                result["potential_savings_pct"].iloc[0] >= result["potential_savings_pct"].iloc[1]
            )

    def test_empty_df_returns_empty_with_schema(self):
        empty = pd.DataFrame(
            columns=["usage_date", "sku_name", "usage_quantity", "cluster_id", "cluster_name"]
        )
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 30))
        result = detect_rightsizing_opportunities(empty, period)
        assert result.empty
        assert "suggestion" in result.columns

    def test_min_days_filter_excludes_recent_clusters(self, usage_df_30d, period_30d):
        # Threshold alto exclui todos
        result_strict = detect_rightsizing_opportunities(
            usage_df_30d, period_30d, RightsizingThresholds(min_days_observed=999)
        )
        assert result_strict.empty

    def test_min_total_dbus_filter(self, usage_df_30d, period_30d):
        result_loose = detect_rightsizing_opportunities(
            usage_df_30d, period_30d, RightsizingThresholds(min_total_dbus=0.0)
        )
        result_strict = detect_rightsizing_opportunities(
            usage_df_30d, period_30d, RightsizingThresholds(min_total_dbus=99999.0)
        )
        assert len(result_loose) >= len(result_strict)

    def test_underuse_pct_affects_suggestion_count(self, usage_df_30d, period_30d):
        # Mais permissivo (10%): menos downsize
        result_strict = detect_rightsizing_opportunities(
            usage_df_30d, period_30d, RightsizingThresholds(underuse_pct=0.10)
        )
        # Mais agressivo (90%): mais downsize
        result_loose = detect_rightsizing_opportunities(
            usage_df_30d, period_30d, RightsizingThresholds(underuse_pct=0.90)
        )
        downsize_strict = int((result_strict["suggestion"] == "downsize").sum())
        downsize_loose = int((result_loose["suggestion"] == "downsize").sum())
        assert downsize_loose >= downsize_strict

    def test_utilization_pct_bounded(self, usage_df_30d, period_30d):
        result = detect_rightsizing_opportunities(usage_df_30d, period_30d)
        if not result.empty:
            assert (result["utilization_pct"] >= 0).all()


# ── detect_idle_clusters ────────────────────────────────────────────────────


class TestIdleHunting:
    def test_returns_expected_columns(self, usage_df_30d, period_30d):
        result = detect_idle_clusters(usage_df_30d, period_30d)
        expected_cols = {
            "cluster_id",
            "cluster_name",
            "active_days",
            "active_days_pct",
            "total_dbus",
            "avg_dbu_per_hour",
            "verdict",
            "savings_hint",
        }
        assert expected_cols == set(result.columns)

    def test_verdict_values(self, usage_df_30d, period_30d):
        result = detect_idle_clusters(usage_df_30d, period_30d)
        valid_verdicts = {"idle", "low_use", "ok"}
        if not result.empty:
            assert set(result["verdict"]).issubset(valid_verdicts)

    def test_threshold_zero_dbus_makes_all_idle(self, usage_df_30d, period_30d):
        # Threshold infinito: tudo vira idle/low_use (nenhum ok)
        result = detect_idle_clusters(
            usage_df_30d,
            period_30d,
            IdleThresholds(max_dbu_per_hour=999.0, min_active_days_pct=0.0),
        )
        if not result.empty:
            assert (result["verdict"] != "ok").all()

    def test_threshold_high_min_active_days_excludes_bursty(self, usage_df_30d, period_30d):
        # Workload bursty (active_days_pct baixo) NÃO é idle, é low_use
        result = detect_idle_clusters(
            usage_df_30d,
            period_30d,
            IdleThresholds(max_dbu_per_hour=10.0, min_active_days_pct=0.99),
        )
        # Nenhum cluster do mock fica ativo 99% dos dias (intermitência ~40%)
        idle_count = int((result["verdict"] == "idle").sum()) if not result.empty else 0
        assert idle_count == 0

    def test_savings_hint_consistent_with_verdict(self, usage_df_30d, period_30d):
        result = detect_idle_clusters(usage_df_30d, period_30d)
        if not result.empty:
            for _, row in result.iterrows():
                if row["verdict"] == "idle":
                    assert row["savings_hint"] == "auto_terminate_or_stop"
                elif row["verdict"] == "low_use":
                    assert row["savings_hint"] == "consider_serverless_or_smaller"
                else:
                    assert row["savings_hint"] == "—"


# ── evaluate_photon_roi ─────────────────────────────────────────────────────


class TestPhotonROI:
    def _two_clusters_df(self, ratio: float) -> pd.DataFrame:
        """Cria DataFrame com 2 clusters onde ratio = with/without."""
        # Cluster B (sem Photon): 100 DBU/dia × 30 dias = 3000 DBU
        # Cluster A (com Photon): ratio × 3000 = total_dbus_with
        rows = []
        for day_offset in range(30):
            d = date(2026, 1, 1) + timedelta(days=day_offset)
            rows.append(
                {
                    "usage_date": d,
                    "workspace_id": 1,
                    "sku_name": "PREMIUM_JOBS_COMPUTE_AZURE",
                    "usage_quantity": 100.0 * ratio,
                    "usage_unit": "DBU",
                    "cloud": "AZURE",
                    "cluster_id": "cluster_A_photon",
                    "cluster_name": "cluster-photon",
                }
            )
            rows.append(
                {
                    "usage_date": d,
                    "workspace_id": 1,
                    "sku_name": "PREMIUM_JOBS_COMPUTE_AZURE",
                    "usage_quantity": 100.0,
                    "usage_unit": "DBU",
                    "cloud": "AZURE",
                    "cluster_id": "cluster_B_baseline",
                    "cluster_name": "cluster-baseline",
                }
            )
        return pd.DataFrame(rows)

    def test_worth_it_when_ratio_below_05(self):
        df = self._two_clusters_df(ratio=0.4)
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 30))
        result = evaluate_photon_roi(df, period, "cluster_A_photon", "cluster_B_baseline")
        assert isinstance(result, PhotonROIResult)
        assert result.verdict == "photon_worth_it"
        assert result.relative_consumption == pytest.approx(0.4, abs=0.01)

    def test_marginal_when_ratio_between_05_and_07(self):
        df = self._two_clusters_df(ratio=0.6)
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 30))
        result = evaluate_photon_roi(df, period, "cluster_A_photon", "cluster_B_baseline")
        assert result.verdict == "photon_marginal"

    def test_not_worth_when_ratio_above_07(self):
        df = self._two_clusters_df(ratio=0.9)
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 30))
        result = evaluate_photon_roi(df, period, "cluster_A_photon", "cluster_B_baseline")
        assert result.verdict == "photon_not_worth"

    def test_caveat_always_present(self):
        df = self._two_clusters_df(ratio=0.5)
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 30))
        result = evaluate_photon_roi(df, period, "cluster_A_photon", "cluster_B_baseline")
        assert "PROXY" in result.caveat
        assert "system.query.history" in result.caveat

    def test_unknown_with_cluster_raises(self, usage_df_30d, period_30d):
        with pytest.raises(ValueError, match="cluster_id_with_photon"):
            evaluate_photon_roi(usage_df_30d, period_30d, "fake_cluster", "any_other")

    def test_unknown_without_cluster_raises(self, usage_df_30d, period_30d):
        # Pega um cluster real do mock pra ser o "with"
        real_id = usage_df_30d["cluster_id"].dropna().iloc[0]
        with pytest.raises(ValueError, match="cluster_id_without_photon"):
            evaluate_photon_roi(usage_df_30d, period_30d, str(real_id), "fake_cluster")

    def test_actual_speedup_proxy_positive(self):
        df = self._two_clusters_df(ratio=0.5)
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 30))
        result = evaluate_photon_roi(df, period, "cluster_A_photon", "cluster_B_baseline")
        assert result.actual_speedup_proxy > 0
        assert result.breakeven_speedup == 2.0

    def test_zero_consumption_without_raises(self):
        # Cria df onde cluster sem Photon teve 0 DBU
        df = pd.DataFrame(
            [
                {
                    "usage_date": date(2026, 1, 1),
                    "workspace_id": 1,
                    "sku_name": "PREMIUM_JOBS_COMPUTE_AZURE",
                    "usage_quantity": 10.0,
                    "cloud": "AZURE",
                    "cluster_id": "cluster_A",
                    "cluster_name": "A",
                },
                # Cluster B aparece mas com quantity 0
                {
                    "usage_date": date(2026, 1, 1),
                    "workspace_id": 1,
                    "sku_name": "PREMIUM_JOBS_COMPUTE_AZURE",
                    "usage_quantity": 0.0,
                    "cloud": "AZURE",
                    "cluster_id": "cluster_B",
                    "cluster_name": "B",
                },
            ]
        )
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 1))
        with pytest.raises(ValueError, match="0 DBU"):
            evaluate_photon_roi(df, period, "cluster_A", "cluster_B")
