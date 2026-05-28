"""Tests do instance_prices_real (Sub-chunks 1 + 3).

Cobre:
  - is_real_mode_enabled: env var detection
  - Cache TTL (set/get/expiry)
  - fetch_azure_vm_price: mock requests, fallback quando API falha
  - fetch_aws_ec2_price: mock boto3, fallback quando sem credenciais
  - get_instance_price_real_or_mock: fallback transparente
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from data_agents.cost_app.databricks import instance_prices_real


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """Isola env vars + limpa cache entre testes."""
    monkeypatch.delenv("DATABRICKS_INSTANCE_PRICES_MODE", raising=False)
    instance_prices_real.clear_cache()


# ── is_real_mode_enabled ────────────────────────────────────────────────────


class TestRealModeFlag:
    def test_default_is_mock(self):
        assert instance_prices_real.is_real_mode_enabled() is False

    def test_real_explicit(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_INSTANCE_PRICES_MODE", "real")
        assert instance_prices_real.is_real_mode_enabled() is True

    def test_real_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_INSTANCE_PRICES_MODE", "REAL")
        assert instance_prices_real.is_real_mode_enabled() is True

    def test_unknown_value_is_mock(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_INSTANCE_PRICES_MODE", "weird")
        assert instance_prices_real.is_real_mode_enabled() is False


# ── Cache ───────────────────────────────────────────────────────────────────


class TestCache:
    def test_empty_returns_none(self):
        assert instance_prices_real._cache_get("nonexistent") is None

    def test_set_get_roundtrip(self):
        instance_prices_real._cache_set("foo", 1.5)
        assert instance_prices_real._cache_get("foo") == 1.5

    def test_clear_cache(self):
        instance_prices_real._cache_set("foo", 1.5)
        instance_prices_real.clear_cache()
        assert instance_prices_real._cache_get("foo") is None

    def test_expired_entry_returns_none(self, monkeypatch):
        # Set entry com timestamp antigo (1h+ atrás)
        old_ts = time.time() - 7200  # 2h atrás
        instance_prices_real._PRICE_CACHE["expired"] = (old_ts, 1.5)
        assert instance_prices_real._cache_get("expired") is None


# ── fetch_azure_vm_price ────────────────────────────────────────────────────


class TestFetchAzureVMPrice:
    def test_returns_none_when_api_returns_empty(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"Items": []}
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            result = instance_prices_real.fetch_azure_vm_price("brazilsouth", "Standard_DS4_v2")
            assert result is None

    def test_returns_price_from_first_linux_item(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Items": [
                {
                    "armSkuName": "Standard_DS4_v2",
                    "productName": "Virtual Machines DS Series",
                    "skuName": "Standard_DS4_v2",
                    "retailPrice": 0.526,
                    "unitOfMeasure": "1 Hour",
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            result = instance_prices_real.fetch_azure_vm_price("brazilsouth", "Standard_DS4_v2")
            assert result == pytest.approx(0.526)

    def test_filters_out_windows(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Items": [
                {
                    "armSkuName": "Standard_DS4_v2",
                    "productName": "Virtual Machines DS Series Windows",
                    "skuName": "Standard_DS4_v2",
                    "retailPrice": 1.234,  # Windows: deve ser ignorado
                },
                {
                    "armSkuName": "Standard_DS4_v2",
                    "productName": "Virtual Machines DS Series",  # Linux
                    "skuName": "Standard_DS4_v2",
                    "retailPrice": 0.526,
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            result = instance_prices_real.fetch_azure_vm_price("brazilsouth", "Standard_DS4_v2")
            assert result == pytest.approx(0.526)  # Pegou o Linux, não o Windows

    def test_filters_out_spot_and_low_priority(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Items": [
                {
                    "armSkuName": "Standard_DS4_v2",
                    "productName": "Virtual Machines DS Series",
                    "skuName": "Standard_DS4_v2 Spot",
                    "retailPrice": 0.05,  # Spot: deve ser ignorado
                },
                {
                    "armSkuName": "Standard_DS4_v2",
                    "productName": "Virtual Machines DS Series",
                    "skuName": "Standard_DS4_v2 Low Priority",
                    "retailPrice": 0.10,  # Low Priority: deve ser ignorado
                },
                {
                    "armSkuName": "Standard_DS4_v2",
                    "productName": "Virtual Machines DS Series",
                    "skuName": "Standard_DS4_v2",
                    "retailPrice": 0.526,  # On-demand normal
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            result = instance_prices_real.fetch_azure_vm_price("brazilsouth", "Standard_DS4_v2")
            assert result == pytest.approx(0.526)

    def test_returns_none_when_network_fails(self):
        with patch("requests.get", side_effect=ConnectionError("No network")):
            result = instance_prices_real.fetch_azure_vm_price("brazilsouth", "Standard_DS4_v2")
            assert result is None

    def test_uses_cache_on_second_call(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Items": [
                {
                    "armSkuName": "Standard_DS4_v2",
                    "productName": "Virtual Machines DS Series",
                    "skuName": "Standard_DS4_v2",
                    "retailPrice": 0.526,
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            instance_prices_real.fetch_azure_vm_price("brazilsouth", "Standard_DS4_v2")
            instance_prices_real.fetch_azure_vm_price("brazilsouth", "Standard_DS4_v2")
            # Segunda chamada deve vir do cache (não nova request)
            assert mock_get.call_count == 1


# ── fetch_aws_ec2_price ─────────────────────────────────────────────────────


class TestFetchAWSEC2Price:
    def test_returns_none_when_boto3_not_installed(self, monkeypatch):
        """Simula boto3 ausente — fallback transparente.

        Fix em PR 1 (2026-05-28): versão anterior usava sys.meta_path.insert
        com _Blocker custom, mas falhava quando boto3 já estava cacheado em
        sys.modules por outros tests do session (vazava preço real $0.192).

        Mecanismo atual: setar sys.modules['boto3'] = None força o próximo
        `import boto3` a levantar ImportError imediatamente
        ('import of boto3 halted; None in sys.modules'). monkeypatch.setitem
        garante teardown automático.
        """
        import sys

        # None em sys.modules → próximo `import boto3` levanta ImportError direto
        monkeypatch.setitem(sys.modules, "boto3", None)
        monkeypatch.setitem(sys.modules, "botocore", None)
        monkeypatch.setitem(sys.modules, "botocore.exceptions", None)

        # Garante cache limpo (fixture isola_env já chama clear_cache, mas
        # explicit é seguro contra interferência cross-test)
        instance_prices_real.clear_cache()

        result = instance_prices_real.fetch_aws_ec2_price("us-east-1", "m5.xlarge")
        assert result is None

    def test_returns_none_for_unknown_region(self):
        """Region não mapeada → None."""
        # Tenta boto3; se disponível, vai cair no early-return de region desconhecida
        try:
            import boto3  # noqa: F401
        except ImportError:
            pytest.skip("boto3 não disponível — pula teste")

        result = instance_prices_real.fetch_aws_ec2_price("xx-unknown-99", "m5.xlarge")
        assert result is None


# ── get_instance_price_real_or_mock ─────────────────────────────────────────


class TestGetRealOrMock:
    def _mock_fn(self, cloud, region, sku):
        """Mock fallback que retorna sempre 0.526."""
        return 0.526

    def test_mock_mode_returns_mock(self):
        # DATABRICKS_INSTANCE_PRICES_MODE não setado (default mock)
        price, source = instance_prices_real.get_instance_price_real_or_mock(
            cloud="azure",
            region="brazilsouth",
            sku_name="Standard_DS4_v2",
            mock_fallback_fn=self._mock_fn,
        )
        assert price == 0.526
        assert source == "mock"

    def test_real_mode_falls_back_to_mock_on_failure(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_INSTANCE_PRICES_MODE", "real")
        with patch.object(instance_prices_real, "fetch_azure_vm_price", return_value=None):
            price, source = instance_prices_real.get_instance_price_real_or_mock(
                cloud="azure",
                region="brazilsouth",
                sku_name="Standard_DS4_v2",
                mock_fallback_fn=self._mock_fn,
            )
            assert price == 0.526
            assert source == "mock_fallback"

    def test_real_mode_returns_api_price_when_available(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_INSTANCE_PRICES_MODE", "real")
        with patch.object(instance_prices_real, "fetch_azure_vm_price", return_value=0.789):
            price, source = instance_prices_real.get_instance_price_real_or_mock(
                cloud="azure",
                region="brazilsouth",
                sku_name="Standard_DS4_v2",
                mock_fallback_fn=self._mock_fn,
            )
            assert price == 0.789
            assert source == "real_api"


# ── get_pricing_metadata ────────────────────────────────────────────────────


class TestPricingMetadata:
    def test_metadata_in_mock_mode(self):
        meta = instance_prices_real.get_pricing_metadata()
        assert meta["mode"] == "mock"
        assert "azure_source_url" in meta
        assert "aws_source" in meta
        assert "cache_ttl_seconds" in meta

    def test_metadata_in_real_mode(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_INSTANCE_PRICES_MODE", "real")
        meta = instance_prices_real.get_pricing_metadata()
        assert meta["mode"] == "real"


# ── Integration: instance_prices.get_instance_price_usd_per_hour ────────────


class TestPublicAPIIntegration:
    """Garante que get_instance_price_usd_per_hour() continua funcionando
    em modo mock (zero regression do bugfix Serverless)."""

    def test_mock_mode_canonical_price(self):
        from data_agents.cost_app.databricks.instance_prices import (
            get_instance_price_usd_per_hour,
        )

        price = get_instance_price_usd_per_hour("azure", "brazilsouth", "Standard_DS4_v2")
        assert price == pytest.approx(0.526)

    def test_unknown_sku_raises_keyerror(self):
        from data_agents.cost_app.databricks.instance_prices import (
            get_instance_price_usd_per_hour,
        )

        with pytest.raises(KeyError):
            get_instance_price_usd_per_hour("azure", "brazilsouth", "FakeSku_X99")
