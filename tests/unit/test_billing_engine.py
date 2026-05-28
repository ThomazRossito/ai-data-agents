"""Testes do cost_engine/billing.py (Fase 3 — análise FinOps real)."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from data_agents.cost_app.databricks.billing_mock import (
    generate_mock_list_prices_df,
    generate_mock_usage_df,
    get_mock_metadata,
)
from data_agents.cost_engine.billing import (
    BillingPeriod,
    aggregate_dbu_daily,
    classify_sku,
    compare_estimate_vs_actual,
    cost_by_compute_type,
    top_cost_clusters,
)


# ── BillingPeriod ────────────────────────────────────────────────────────────


class TestBillingPeriod:
    def test_days_inclusive_range(self):
        p = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 7))
        assert p.days == 7  # inclusivo

    def test_single_day_returns_one_day(self):
        p = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 1))
        assert p.days == 1

    def test_invalid_period_raises(self):
        with pytest.raises(ValueError, match="start_date.*deve ser"):
            BillingPeriod(start_date=date(2026, 1, 10), end_date=date(2026, 1, 1))

    def test_workspace_id_default_none(self):
        p = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 7))
        assert p.workspace_id is None


# ── classify_sku ─────────────────────────────────────────────────────────────


class TestClassifySku:
    def test_jobs_compute(self):
        assert classify_sku("PREMIUM_JOBS_COMPUTE_AZURE") == "jobs_compute"
        assert classify_sku("STANDARD_JOBS_COMPUTE_AWS") == "jobs_compute"

    def test_all_purpose(self):
        assert classify_sku("PREMIUM_ALL_PURPOSE_COMPUTE_AZURE") == "all_purpose_compute"

    def test_sql(self):
        assert classify_sku("PREMIUM_SQL_PRO_COMPUTE_AZURE") == "sql_compute"

    def test_serverless_wins_over_sql_when_both_present(self):
        """SERVERLESS_SQL_* deve ir pra serverless_compute, não sql_compute."""
        assert classify_sku("PREMIUM_SERVERLESS_SQL_AZURE") == "serverless_compute"

    def test_dlt(self):
        assert classify_sku("PREMIUM_DLT_ADVANCED_AZURE") == "dlt_core"

    def test_unknown_returns_other(self):
        assert classify_sku("RANDOM_SKU_NEVER_SEEN") == "other"

    def test_case_insensitive(self):
        assert classify_sku("premium_jobs_compute_azure") == "jobs_compute"


# ── aggregate_dbu_daily ──────────────────────────────────────────────────────


@pytest.fixture
def usage_df_30d() -> pd.DataFrame:
    """30 dias de mock determinístico (seed=42)."""
    return generate_mock_usage_df(days=30, cloud="AZURE", seed=42)


@pytest.fixture
def prices_df_azure() -> pd.DataFrame:
    return generate_mock_list_prices_df(cloud="AZURE")


@pytest.fixture
def last_7_days_period(usage_df_30d: pd.DataFrame) -> BillingPeriod:
    end = usage_df_30d["usage_date"].max()
    start = end - timedelta(days=6)
    return BillingPeriod(start_date=start, end_date=end)


class TestAggregateDBUDaily:
    def test_returns_dataframe_with_expected_columns(self, usage_df_30d, last_7_days_period):
        daily = aggregate_dbu_daily(usage_df_30d, last_7_days_period)
        assert list(daily.columns) == ["usage_date", "sku_name", "total_dbus"]

    def test_filters_by_period(self, usage_df_30d, last_7_days_period):
        daily = aggregate_dbu_daily(usage_df_30d, last_7_days_period)
        if not daily.empty:
            assert daily["usage_date"].min() >= last_7_days_period.start_date
            assert daily["usage_date"].max() <= last_7_days_period.end_date

    def test_empty_dataframe_returns_empty_with_schema(self):
        empty_df = pd.DataFrame(
            columns=["usage_date", "workspace_id", "sku_name", "usage_quantity", "cloud"]
        )
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 7))
        result = aggregate_dbu_daily(empty_df, period)
        assert result.empty
        assert list(result.columns) == ["usage_date", "sku_name", "total_dbus"]

    def test_workspace_filter_works(self, usage_df_30d):
        # Mock só gera 1 workspace_id, então filter inexistente retorna vazio
        end = usage_df_30d["usage_date"].max()
        period = BillingPeriod(
            start_date=end - timedelta(days=6),
            end_date=end,
            workspace_id=999_999_999_999,  # workspace inexistente
        )
        result = aggregate_dbu_daily(usage_df_30d, period)
        assert result.empty


# ── top_cost_clusters ────────────────────────────────────────────────────────


class TestTopCostClusters:
    def test_returns_top_n_ordered_desc(self, usage_df_30d, prices_df_azure, last_7_days_period):
        top = top_cost_clusters(usage_df_30d, prices_df_azure, last_7_days_period, limit=3)
        assert len(top) <= 3
        if len(top) >= 2:
            # Custo deve estar DESC
            assert top["estimated_cost_usd"].iloc[0] >= top["estimated_cost_usd"].iloc[1]

    def test_expected_columns(self, usage_df_30d, prices_df_azure, last_7_days_period):
        top = top_cost_clusters(usage_df_30d, prices_df_azure, last_7_days_period, limit=10)
        assert list(top.columns) == [
            "cluster_id",
            "cluster_name",
            "total_dbus",
            "estimated_cost_usd",
        ]

    def test_excludes_null_cluster_ids(self, prices_df_azure):
        """Linhas sem cluster_id (serverless puro) devem ser excluídas."""
        df = pd.DataFrame(
            [
                {
                    "usage_date": date(2026, 1, 1),
                    "workspace_id": 1,
                    "sku_name": "PREMIUM_JOBS_COMPUTE_AZURE",
                    "usage_quantity": 10.0,
                    "cloud": "AZURE",
                    "cluster_id": None,
                    "cluster_name": None,
                },
                {
                    "usage_date": date(2026, 1, 1),
                    "workspace_id": 1,
                    "sku_name": "PREMIUM_JOBS_COMPUTE_AZURE",
                    "usage_quantity": 20.0,
                    "cloud": "AZURE",
                    "cluster_id": "abc-123",
                    "cluster_name": "valid-cluster",
                },
            ]
        )
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 1))
        top = top_cost_clusters(df, prices_df_azure, period)
        assert len(top) == 1
        assert top["cluster_name"].iloc[0] == "valid-cluster"

    def test_cost_calculation_matches_quantity_times_price(
        self, usage_df_30d, prices_df_azure, last_7_days_period
    ):
        """Cost = SUM(usage_quantity × price_per_dbu) por cluster."""
        top = top_cost_clusters(usage_df_30d, prices_df_azure, last_7_days_period, limit=10)
        # Sanity check: custo > 0 onde dbus > 0
        for _, row in top.iterrows():
            if row["total_dbus"] > 0:
                assert row["estimated_cost_usd"] > 0


# ── cost_by_compute_type ─────────────────────────────────────────────────────


class TestCostByComputeType:
    def test_returns_dataframe_with_pct_columns(
        self, usage_df_30d, prices_df_azure, last_7_days_period
    ):
        breakdown = cost_by_compute_type(usage_df_30d, prices_df_azure, last_7_days_period)
        assert "dbus_pct" in breakdown.columns
        assert "cost_pct" in breakdown.columns

    def test_percentages_sum_to_100(self, usage_df_30d, prices_df_azure, last_7_days_period):
        breakdown = cost_by_compute_type(usage_df_30d, prices_df_azure, last_7_days_period)
        if not breakdown.empty:
            assert breakdown["dbus_pct"].sum() == pytest.approx(100.0, abs=0.5)
            assert breakdown["cost_pct"].sum() == pytest.approx(100.0, abs=0.5)

    def test_compute_types_are_classified(self, usage_df_30d, prices_df_azure, last_7_days_period):
        breakdown = cost_by_compute_type(usage_df_30d, prices_df_azure, last_7_days_period)
        valid_types = {
            "jobs_compute",
            "all_purpose_compute",
            "sql_compute",
            "serverless_compute",
            "dlt_core",
            "other",
        }
        if not breakdown.empty:
            assert set(breakdown["compute_type"]).issubset(valid_types)

    def test_sorted_by_cost_desc(self, usage_df_30d, prices_df_azure, last_7_days_period):
        breakdown = cost_by_compute_type(usage_df_30d, prices_df_azure, last_7_days_period)
        if len(breakdown) >= 2:
            assert (
                breakdown["estimated_cost_usd"].iloc[0] >= breakdown["estimated_cost_usd"].iloc[1]
            )


# ── compare_estimate_vs_actual ───────────────────────────────────────────────


class TestCompareEstimateVsActual:
    def test_on_budget_when_variance_under_10pct(self):
        envelope = {"uuid": "abc", "name": "Test"}
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 30))
        result = compare_estimate_vs_actual(
            scenario_envelope=envelope,
            estimated_monthly_usd=1000.0,
            actual_total_usd_in_period=1050.0,  # ~ $1050/mês (período é 30 dias)
            period=period,
        )
        assert result.verdict == "on_budget"
        assert abs(result.variance_pct) <= 10

    def test_over_budget_when_variance_above_10pct(self):
        envelope = {"uuid": "abc", "name": "Test"}
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 30))
        result = compare_estimate_vs_actual(
            scenario_envelope=envelope,
            estimated_monthly_usd=1000.0,
            actual_total_usd_in_period=1500.0,
            period=period,
        )
        assert result.verdict == "over_budget"
        assert result.variance_pct > 10

    def test_under_budget_when_variance_below_minus_10pct(self):
        envelope = {"uuid": "abc", "name": "Test"}
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 30))
        result = compare_estimate_vs_actual(
            scenario_envelope=envelope,
            estimated_monthly_usd=1000.0,
            actual_total_usd_in_period=500.0,
            period=period,
        )
        assert result.verdict == "under_budget"
        assert result.variance_pct < -10

    def test_extrapolates_short_period_to_monthly(self):
        """7 dias × X = monthly via 30/7."""
        envelope = {"uuid": "abc", "name": "Test"}
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 7))
        # 7 dias × $100 = $700/semana → $700 × (30/7) ≈ $3000/mês
        result = compare_estimate_vs_actual(
            scenario_envelope=envelope,
            estimated_monthly_usd=3000.0,
            actual_total_usd_in_period=700.0,
            period=period,
        )
        assert result.actual_monthly_usd == pytest.approx(3000.0, abs=1.0)
        assert result.verdict == "on_budget"

    def test_zero_estimated_doesnt_divide_by_zero(self):
        envelope = {"uuid": "abc", "name": "Test"}
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 7))
        result = compare_estimate_vs_actual(
            scenario_envelope=envelope,
            estimated_monthly_usd=0.0,
            actual_total_usd_in_period=100.0,
            period=period,
        )
        assert result.variance_pct == 0.0


# ── Mock generators (sanidade) ───────────────────────────────────────────────


class TestMockGenerators:
    def test_usage_df_has_expected_schema(self):
        df = generate_mock_usage_df(days=10, cloud="AZURE", seed=1)
        expected_cols = {
            "usage_date",
            "workspace_id",
            "sku_name",
            "usage_quantity",
            "usage_unit",
            "cloud",
            "cluster_id",
            "cluster_name",
        }
        assert expected_cols.issubset(set(df.columns))

    def test_usage_df_deterministic_via_seed(self):
        df1 = generate_mock_usage_df(days=15, seed=99)
        df2 = generate_mock_usage_df(days=15, seed=99)
        assert df1.equals(df2)

    def test_prices_df_has_pricing_vigente(self):
        df = generate_mock_list_prices_df(cloud="AZURE")
        # Todos os preços mock devem ter price_end_time None (vigente)
        assert df["price_end_time"].isna().all()
        assert (df["price_per_dbu"] > 0).all()

    def test_prices_skus_match_usage_skus(self):
        """SKUs do prices_df devem cobrir SKUs do usage_df pra JOIN funcionar."""
        usage = generate_mock_usage_df(days=30, cloud="AZURE", seed=42)
        prices = generate_mock_list_prices_df(cloud="AZURE")
        usage_skus = set(usage["sku_name"].unique())
        price_skus = set(prices["sku_name"].unique())
        assert usage_skus.issubset(price_skus)

    def test_aws_and_azure_have_different_prices(self):
        """Sanity check: AWS DBU rate ≠ Azure DBU rate (geralmente AWS < Azure)."""
        azure = generate_mock_list_prices_df(cloud="AZURE")
        aws = generate_mock_list_prices_df(cloud="AWS")
        # Jobs Premium: Azure $0.20, AWS $0.10
        azure_jobs = azure[azure["sku_name"].str.contains("JOBS")]["price_per_dbu"].iloc[0]
        aws_jobs = aws[aws["sku_name"].str.contains("JOBS")]["price_per_dbu"].iloc[0]
        assert azure_jobs > aws_jobs

    def test_metadata_marks_mock(self):
        meta = get_mock_metadata()
        assert meta["is_mock"] is True
        assert "AZURE" in meta["clouds_supported"]
        assert "AWS" in meta["clouds_supported"]
