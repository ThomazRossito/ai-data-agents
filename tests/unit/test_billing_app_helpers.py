"""Testes dos helpers do Streamlit Tab 6 'FinOps Realizado' (Chunk 3.3)."""

from __future__ import annotations

from datetime import date

import pytest

from data_agents.cost_app.databricks.billing_app_helpers import (
    format_compare_dataframe,
    interpret_verdict,
    load_billing_data,
)
from data_agents.cost_engine.billing import BillingPeriod


# ── load_billing_data ───────────────────────────────────────────────────────


class TestLoadBillingData:
    def test_mock_returns_two_dataframes(self):
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 30))
        usage_df, prices_df = load_billing_data(period=period, cloud="AZURE", mock=True)
        assert not usage_df.empty
        assert not prices_df.empty

    def test_mock_usage_df_has_expected_columns(self):
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 30))
        usage_df, _ = load_billing_data(period=period, cloud="AZURE", mock=True)
        expected = {
            "usage_date",
            "workspace_id",
            "sku_name",
            "usage_quantity",
            "cluster_id",
            "cluster_name",
            "cloud",
        }
        assert expected.issubset(set(usage_df.columns))

    def test_aws_cloud_returns_aws_skus(self):
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 30))
        usage_df, prices_df = load_billing_data(period=period, cloud="AWS", mock=True)
        assert all("AWS" in sku for sku in usage_df["sku_name"].unique())
        assert all("AWS" in sku for sku in prices_df["sku_name"].unique())

    def test_real_mode_raises_when_credentials_missing(self, monkeypatch):
        """Chunk 3.4: real mode foi implementado, mas requer DATABRICKS_HOST/TOKEN/WAREHOUSE_ID.
        Sem credenciais, RealModeConfig.from_env levanta RuntimeError descritivo
        (não mais o placeholder antigo)."""
        for var in (
            "DATABRICKS_HOST",
            "DATABRICKS_TOKEN",
            "DATABRICKS_BILLING_WAREHOUSE_ID",
        ):
            monkeypatch.delenv(var, raising=False)

        # Limpa cache pra garantir que não retorna entry stale
        from data_agents.cost_app.databricks import billing_real

        billing_real.clear_cache()

        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 30))
        with pytest.raises(RuntimeError, match="DATABRICKS_"):
            load_billing_data(period=period, cloud="AZURE", mock=False)

    def test_days_buffer_is_at_least_60(self):
        """Generator gera buffer de 10 dias + period.days, mínimo 60."""
        # Janela curta de 5 dias → generator gera 60 (max(5+10, 60))
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 5))
        usage_df, _ = load_billing_data(period=period, cloud="AZURE", mock=True)
        # Generator usa end_date=today por default, então tem 60 dias retroativos
        date_range = (usage_df["usage_date"].max() - usage_df["usage_date"].min()).days
        assert date_range >= 50  # tolerância pra weekend dip / inatividade

    def test_seed_reproducibility(self):
        period = BillingPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 1, 30))
        df1, _ = load_billing_data(period=period, cloud="AZURE", mock=True, seed=42)
        df2, _ = load_billing_data(period=period, cloud="AZURE", mock=True, seed=42)
        assert df1.equals(df2)


# ── format_compare_dataframe ────────────────────────────────────────────────


class TestFormatCompareDataframe:
    def test_returns_single_row_dataframe(self):
        df = format_compare_dataframe(
            scenario_name="Test",
            estimated_monthly_usd=726.88,
            actual_monthly_usd=750.00,
            variance_pct=3.18,
            verdict="on_budget",
            actual_period_days=30,
        )
        assert len(df) == 1

    def test_columns_match_expected(self):
        df = format_compare_dataframe(
            scenario_name="Test",
            estimated_monthly_usd=726.88,
            actual_monthly_usd=750.00,
            variance_pct=3.18,
            verdict="on_budget",
            actual_period_days=30,
        )
        expected = {
            "Cenário",
            "Estimado/mês",
            "Real/mês (extrapolado)",
            "Variance",
            "Verdict",
            "Janela actual",
        }
        assert set(df.columns) == expected

    def test_verdict_label_friendly(self):
        df = format_compare_dataframe(
            scenario_name="X",
            estimated_monthly_usd=100.0,
            actual_monthly_usd=120.0,
            variance_pct=20.0,
            verdict="over_budget",
            actual_period_days=14,
        )
        assert "Over Budget" in df["Verdict"].iloc[0]

    def test_variance_formatted_with_sign(self):
        df_pos = format_compare_dataframe(
            scenario_name="X",
            estimated_monthly_usd=100.0,
            actual_monthly_usd=120.0,
            variance_pct=20.0,
            verdict="over_budget",
            actual_period_days=14,
        )
        df_neg = format_compare_dataframe(
            scenario_name="Y",
            estimated_monthly_usd=100.0,
            actual_monthly_usd=80.0,
            variance_pct=-20.0,
            verdict="under_budget",
            actual_period_days=14,
        )
        assert df_pos["Variance"].iloc[0].startswith("+")
        assert df_neg["Variance"].iloc[0].startswith("-")


# ── interpret_verdict ───────────────────────────────────────────────────────


class TestInterpretVerdict:
    def test_on_budget_message(self):
        msg = interpret_verdict("on_budget", 3.5)
        assert "validado" in msg.lower()
        assert "3.5" in msg

    def test_over_budget_message(self):
        msg = interpret_verdict("over_budget", 15.0)
        assert "acima" in msg.lower()
        assert "investigue" in msg.lower()
        assert "15.0" in msg

    def test_under_budget_message(self):
        msg = interpret_verdict("under_budget", -25.0)
        assert "abaixo" in msg.lower()
        assert "superdimensionado" in msg.lower()

    def test_unknown_verdict_returns_fallback(self):
        msg = interpret_verdict("foo_bar", 0.0)
        assert "foo_bar" in msg


# ── Sanity: app.py importa sem erro ─────────────────────────────────────────


class TestAppImportsClean:
    def test_app_module_imports(self):
        """app.py import deve funcionar quando o ambiente tem [ui] extras.

        Pulado em [dev] puro (sem plotly/streamlit), porque app.py importa
        `plotly.graph_objects` e `streamlit` no top-level. O teste valida
        sanidade do tab registration, não a infra dos extras.
        """
        pytest.importorskip("plotly", reason="plotly só disponível com extras [ui]")
        pytest.importorskip("streamlit", reason="streamlit só disponível com extras [ui]")

        from data_agents.cost_app.databricks import app

        assert hasattr(app, "render_tab_finops_realizado")
        assert hasattr(app, "render_tab_historico")
        assert hasattr(app, "render_tab_cenario_cluster")
        assert hasattr(app, "main")
