"""Testes do real-mode DBU rate loader (data_agents/cost_app/databricks/pricing_real.py).

PR 8 (2026-05-28): system.billing.list_prices via Databricks SDK.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from data_agents.cost_app.databricks import pricing_real


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """Isola env vars + limpa cache entre testes."""
    monkeypatch.delenv("DATABRICKS_PRICING_MODE", raising=False)
    pricing_real.clear_cache()


# ── is_real_pricing_mode_enabled ────────────────────────────────────────────


class TestRealPricingModeFlag:
    def test_default_is_disabled(self):
        assert pricing_real.is_real_pricing_mode_enabled() is False

    def test_real_explicit(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_PRICING_MODE", "real")
        assert pricing_real.is_real_pricing_mode_enabled() is True

    def test_real_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_PRICING_MODE", "REAL")
        assert pricing_real.is_real_pricing_mode_enabled() is True

    def test_unknown_value_is_disabled(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_PRICING_MODE", "weird")
        assert pricing_real.is_real_pricing_mode_enabled() is False


# ── Cache ───────────────────────────────────────────────────────────────────


class TestCache:
    def test_empty_returns_none(self):
        assert pricing_real._cache_get("nonexistent") is None

    def test_set_get_roundtrip(self):
        pricing_real._cache_set("foo", 0.95)
        assert pricing_real._cache_get("foo") == 0.95

    def test_clear_cache(self):
        pricing_real._cache_set("foo", 0.95)
        pricing_real.clear_cache()
        assert pricing_real._cache_get("foo") is None

    def test_expired_entry_returns_none(self):
        old_ts = time.time() - 7200  # 2h atrás (TTL é 1h)
        pricing_real._PRICE_CACHE["expired"] = (old_ts, 0.95)
        assert pricing_real._cache_get("expired") is None


# ── _build_list_prices_sql ──────────────────────────────────────────────────


class TestBuildListPricesSql:
    def test_valid_sku_cloud_returns_sql(self):
        sql = pricing_real._build_list_prices_sql("STANDARD_ALL_PURPOSE_COMPUTE", "aws")
        assert "system.billing.list_prices" in sql
        assert "STANDARD_ALL_PURPOSE_COMPUTE" in sql
        assert "AWS" in sql
        assert "LIMIT 1" in sql

    def test_cloud_case_insensitive_uppercased(self):
        sql = pricing_real._build_list_prices_sql("FOO", "azure")
        assert "AZURE" in sql

    def test_invalid_cloud_raises(self):
        with pytest.raises(ValueError, match="cloud inválido"):
            pricing_real._build_list_prices_sql("FOO", "alibaba")

    def test_sku_with_injection_chars_raises(self):
        """SQL injection defense — caracteres especiais no sku_name rejeitados."""
        with pytest.raises(ValueError, match="sku_name contém caracteres inválidos"):
            pricing_real._build_list_prices_sql("FOO'; DROP TABLE--", "aws")


# ── fetch_dbu_rate_real ─────────────────────────────────────────────────────


class TestFetchDbuRateReal:
    def test_returns_none_when_billing_real_not_importable(self, monkeypatch):
        """Simula billing_real ausente — fallback transparente."""
        import sys

        # Bloquear billing_real specifically
        monkeypatch.setitem(sys.modules, "data_agents.cost_app.databricks.billing_real", None)
        result = pricing_real.fetch_dbu_rate_real("ANY_SKU", "aws")
        assert result is None

    def test_returns_none_when_credentials_missing(self, monkeypatch):
        """Sem DATABRICKS_HOST/TOKEN, RealModeConfig.from_env() raises."""
        monkeypatch.delenv("DATABRICKS_HOST", raising=False)
        monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
        monkeypatch.delenv("DATABRICKS_BILLING_WAREHOUSE_ID", raising=False)
        result = pricing_real.fetch_dbu_rate_real("ANY_SKU", "aws")
        assert result is None

    def test_returns_price_when_sql_succeeds(self, monkeypatch):
        """Mock _execute_sql retornando uma row — deve retornar o price_default."""
        monkeypatch.setenv("DATABRICKS_HOST", "https://test.databricks.net")
        monkeypatch.setenv("DATABRICKS_TOKEN", "fake_token")
        monkeypatch.setenv("DATABRICKS_BILLING_WAREHOUSE_ID", "fake_warehouse")

        mock_rows = [{"sku_name": "TEST_SKU", "cloud": "AWS", "price_default": 0.42}]
        with patch(
            "data_agents.cost_app.databricks.billing_real._execute_sql",
            return_value=mock_rows,
        ):
            result = pricing_real.fetch_dbu_rate_real("TEST_SKU", "aws")
            assert result == pytest.approx(0.42)

    def test_returns_none_when_no_rows(self, monkeypatch):
        """SKU não encontrado em system.billing.list_prices → None."""
        monkeypatch.setenv("DATABRICKS_HOST", "https://test.databricks.net")
        monkeypatch.setenv("DATABRICKS_TOKEN", "fake_token")
        monkeypatch.setenv("DATABRICKS_BILLING_WAREHOUSE_ID", "fake_warehouse")

        with patch(
            "data_agents.cost_app.databricks.billing_real._execute_sql",
            return_value=[],
        ):
            result = pricing_real.fetch_dbu_rate_real("MISSING_SKU", "aws")
            assert result is None

    def test_returns_none_when_sql_raises(self, monkeypatch):
        """Qualquer exception em _execute_sql cai no fallback (None)."""
        monkeypatch.setenv("DATABRICKS_HOST", "https://test.databricks.net")
        monkeypatch.setenv("DATABRICKS_TOKEN", "fake_token")
        monkeypatch.setenv("DATABRICKS_BILLING_WAREHOUSE_ID", "fake_warehouse")

        with patch(
            "data_agents.cost_app.databricks.billing_real._execute_sql",
            side_effect=RuntimeError("warehouse paused"),
        ):
            result = pricing_real.fetch_dbu_rate_real("ANY_SKU", "aws")
            assert result is None

    def test_uses_cache_on_second_call(self, monkeypatch):
        """Segunda chamada não invoca _execute_sql (cache hit)."""
        monkeypatch.setenv("DATABRICKS_HOST", "https://test.databricks.net")
        monkeypatch.setenv("DATABRICKS_TOKEN", "fake_token")
        monkeypatch.setenv("DATABRICKS_BILLING_WAREHOUSE_ID", "fake_warehouse")

        mock_rows = [{"price_default": 0.55}]
        with patch(
            "data_agents.cost_app.databricks.billing_real._execute_sql",
            return_value=mock_rows,
        ) as mock_exec:
            pricing_real.fetch_dbu_rate_real("CACHED_SKU", "aws")
            pricing_real.fetch_dbu_rate_real("CACHED_SKU", "aws")
            assert mock_exec.call_count == 1


# ── get_dbu_rate_real_or_fallback ───────────────────────────────────────────


class TestGetDbuRateRealOrFallback:
    def _fallback_fn(self, value: float | None = 0.20):
        """Cria thunk que retorna value (default 0.20)."""

        def thunk() -> float | None:
            return value

        return thunk

    def test_mock_mode_returns_yaml(self):
        """DATABRICKS_PRICING_MODE não setado → usa fallback diretamente."""
        price, source = pricing_real.get_dbu_rate_real_or_fallback(
            "ANY_SKU", "aws", self._fallback_fn(0.20)
        )
        assert price == 0.20
        assert source == "yaml"

    def test_mock_mode_unavailable_when_fallback_returns_none(self):
        price, source = pricing_real.get_dbu_rate_real_or_fallback(
            "ANY_SKU", "aws", self._fallback_fn(None)
        )
        assert price is None
        assert source == "unavailable"

    def test_real_mode_returns_real_when_api_succeeds(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_PRICING_MODE", "real")
        with patch.object(pricing_real, "fetch_dbu_rate_real", return_value=0.42):
            price, source = pricing_real.get_dbu_rate_real_or_fallback(
                "ANY_SKU", "aws", self._fallback_fn(0.20)
            )
            assert price == 0.42
            assert source == "real_api"

    def test_real_mode_falls_back_when_api_returns_none(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_PRICING_MODE", "real")
        with patch.object(pricing_real, "fetch_dbu_rate_real", return_value=None):
            price, source = pricing_real.get_dbu_rate_real_or_fallback(
                "ANY_SKU", "aws", self._fallback_fn(0.20)
            )
            assert price == 0.20
            assert source == "yaml_fallback"


# ── Metadata ────────────────────────────────────────────────────────────────


class TestPricingRealMetadata:
    def test_metadata_when_disabled(self):
        meta = pricing_real.get_pricing_real_metadata()
        assert meta["real_mode_enabled"] is False
        assert meta["source_table"] == "system.billing.list_prices"
        assert "DATABRICKS_HOST" in str(meta["requires_env_vars"])

    def test_metadata_when_enabled(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_PRICING_MODE", "real")
        meta = pricing_real.get_pricing_real_metadata()
        assert meta["real_mode_enabled"] is True

    def test_metadata_cache_count(self):
        pricing_real._cache_set("foo", 0.1)
        pricing_real._cache_set("bar", 0.2)
        meta = pricing_real.get_pricing_real_metadata()
        assert meta["cache_entries"] == 2
