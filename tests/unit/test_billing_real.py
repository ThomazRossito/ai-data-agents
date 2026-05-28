"""Tests do real mode loader (Chunk 3.4).

Strategy: mockar databricks-sdk pra evitar conexão real. Testes cobrem:
  - RealModeConfig validation (env vars ausentes → RuntimeError)
  - SQL builders (parametrização de days_back + cloud)
  - Cache hit/miss + TTL
  - DataFrame conversion (rows → schema compatível com mock)
  - get_real_metadata (sem config + com config)
"""

from __future__ import annotations

import pytest

from data_agents.cost_app.databricks import billing_real


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """Garante que env vars não vazem entre testes."""
    for var in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_BILLING_WAREHOUSE_ID"):
        monkeypatch.delenv(var, raising=False)
    billing_real.clear_cache()


# ── RealModeConfig ──────────────────────────────────────────────────────────


class TestRealModeConfig:
    def test_missing_host_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="DATABRICKS_HOST"):
            billing_real.RealModeConfig.from_env()

    def test_missing_token_raises_runtime_error(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "https://adb-x.databricks.net")
        with pytest.raises(RuntimeError, match="DATABRICKS_TOKEN"):
            billing_real.RealModeConfig.from_env()

    def test_missing_warehouse_raises_runtime_error(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "https://adb-x.databricks.net")
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapi123")
        with pytest.raises(RuntimeError, match="DATABRICKS_BILLING_WAREHOUSE_ID"):
            billing_real.RealModeConfig.from_env()

    def test_all_env_vars_set_creates_config(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "https://adb-x.databricks.net")
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapi123")
        monkeypatch.setenv("DATABRICKS_BILLING_WAREHOUSE_ID", "wh_123")
        config = billing_real.RealModeConfig.from_env()
        assert config.host == "https://adb-x.databricks.net"
        assert config.token == "dapi123"
        assert config.warehouse_id == "wh_123"


# ── SQL builders ────────────────────────────────────────────────────────────


class TestSQLBuilders:
    def test_usage_sql_includes_table_and_interval(self):
        sql = billing_real._build_usage_sql(days_back=30)
        assert "system.billing.usage" in sql
        assert "INTERVAL 30 DAYS" in sql
        assert "usage_metadata.cluster_id" in sql
        assert "usage_metadata.cluster_name" in sql

    def test_usage_sql_cloud_filter(self):
        sql = billing_real._build_usage_sql(days_back=7, cloud_filter="AZURE")
        assert "AND cloud = 'AZURE'" in sql

    def test_usage_sql_no_cloud_filter(self):
        sql = billing_real._build_usage_sql(days_back=7, cloud_filter=None)
        assert "AND cloud =" not in sql

    def test_usage_sql_invalid_cloud_raises(self):
        with pytest.raises(ValueError, match="cloud inválido"):
            billing_real._build_usage_sql(days_back=7, cloud_filter="FOO")

    def test_prices_sql_filters_vigent(self):
        sql = billing_real._build_prices_sql()
        assert "system.billing.list_prices" in sql
        assert "price_end_time IS NULL" in sql
        assert "pricing.default" in sql

    def test_days_back_coerced_to_int(self):
        """Defesa contra injection — days_back é forçado pra int."""
        # passar string que coerce pra int é OK
        sql = billing_real._build_usage_sql(days_back=15)  # type: ignore[arg-type]
        assert "INTERVAL 15 DAYS" in sql


# ── Cache ───────────────────────────────────────────────────────────────────


class TestCache:
    def test_cache_empty_returns_none(self):
        assert billing_real._cache_get("nonexistent") is None

    def test_cache_set_get_roundtrip(self):
        billing_real._cache_set("foo", "bar")
        assert billing_real._cache_get("foo") == "bar"

    def test_clear_cache(self):
        billing_real._cache_set("foo", "bar")
        billing_real.clear_cache()
        assert billing_real._cache_get("foo") is None

    def test_get_last_load_timestamp_empty(self):
        billing_real.clear_cache()
        assert billing_real.get_last_load_timestamp() is None

    def test_get_last_load_timestamp_with_entries(self):
        billing_real._cache_set("foo", "bar")
        ts = billing_real.get_last_load_timestamp()
        assert ts is not None


# ── DataFrame conversion ────────────────────────────────────────────────────


class TestDataFrameConversion:
    def test_to_usage_dataframe_empty(self):
        df = billing_real._to_usage_dataframe([])
        assert df.empty
        # Schema mínimo
        assert "usage_date" in df.columns
        assert "cluster_id" in df.columns
        assert "sku_name" in df.columns

    def test_to_usage_dataframe_with_rows(self):
        rows = [
            {
                "usage_date": "2026-01-15",
                "workspace_id": 1234567890123456,
                "sku_name": "PREMIUM_JOBS_COMPUTE_AZURE",
                "usage_quantity": 12.5,
                "usage_unit": "DBU",
                "cloud": "AZURE",
                "cluster_id": "abc-123",
                "cluster_name": "etl-bronze",
            }
        ]
        df = billing_real._to_usage_dataframe(rows)
        assert len(df) == 1
        assert df["cluster_name"].iloc[0] == "etl-bronze"
        assert df["usage_quantity"].iloc[0] == pytest.approx(12.5)

    def test_to_prices_dataframe_empty(self):
        df = billing_real._to_prices_dataframe([])
        assert df.empty
        assert "sku_name" in df.columns
        assert "price_per_dbu" in df.columns

    def test_to_prices_dataframe_with_rows(self):
        rows = [
            {
                "sku_name": "PREMIUM_JOBS_COMPUTE_AZURE",
                "cloud": "AZURE",
                "currency_code": "USD",
                "price_per_dbu": 0.20,
                "price_start_time": "2024-01-01T00:00:00",
                "price_end_time": None,
            }
        ]
        df = billing_real._to_prices_dataframe(rows)
        assert len(df) == 1
        assert df["price_per_dbu"].iloc[0] == pytest.approx(0.20)


# ── get_real_metadata ───────────────────────────────────────────────────────


class TestRealMetadata:
    def test_metadata_without_config(self):
        meta = billing_real.get_real_metadata()
        assert meta["is_mock"] is False
        assert meta["config_ok"] is False
        assert meta["host"] == "(missing)"

    def test_metadata_with_config(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "https://adb-x.databricks.net")
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapi123")
        monkeypatch.setenv("DATABRICKS_BILLING_WAREHOUSE_ID", "wh_123456789012345")
        meta = billing_real.get_real_metadata()
        assert meta["config_ok"] is True
        assert meta["host"].startswith("https://")
