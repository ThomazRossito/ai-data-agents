"""
Tests for mcp_servers/azure_pricing/server.py

Cobertura:
  - Imports e estrutura do server (sem fazer chamadas reais à API)
  - Helpers (_now_iso, _default_*, _hours_per_month)
  - Tools com mock de requests
  - Validação de filter_expression OData
  - Cache em memória funciona
  - Diagnostics retorna estrutura esperada

Marker `requires_network` é aplicado aos testes que de fato chamam a API
pública — pulam por default; rodar com `pytest -m requires_network` pra
fazer hit real.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_retail_response():
    """Mock de resposta da Azure Retail Prices API."""
    return {
        "Items": [
            {
                "currencyCode": "USD",
                "tierMinimumUnits": 0.0,
                "retailPrice": 0.0208,
                "unitPrice": 0.0208,
                "armRegionName": "brazilsouth",
                "location": "BR South",
                "effectiveStartDate": "2024-01-01T00:00:00Z",
                "meterId": "abc-123",
                "meterName": "LRS Data Stored",
                "productId": "DZH318Z0BPR3",
                "skuId": "DZH318Z0BPR3/000C",
                "productName": "Standard Page Blob",
                "skuName": "Standard_LRS",
                "serviceName": "Storage",
                "serviceId": "DZH317F1HKN0",
                "serviceFamily": "Storage",
                "unitOfMeasure": "1 GB/Month",
                "type": "Consumption",
                "isPrimaryMeterRegion": True,
                "armSkuName": "Standard_LRS",
            }
        ],
        "NextPageLink": None,
        "Count": 1,
    }


@pytest.fixture
def mock_hour_based_response():
    """Mock de SKU cobrado por hora (ex: VMs, AI Search)."""
    return {
        "Items": [
            {
                "currencyCode": "USD",
                "retailPrice": 0.34247,
                "unitPrice": 0.34247,
                "armRegionName": "brazilsouth",
                "meterName": "S1 Search Unit Hour",
                "productName": "Azure Cognitive Search Standard",
                "skuName": "S1",
                "serviceName": "Azure Cognitive Search",
                "unitOfMeasure": "1 Hour",
                "type": "Consumption",
            }
        ],
        "NextPageLink": None,
    }


# ─── Imports & Estrutura ─────────────────────────────────────────────────────


class TestImports:
    def test_server_module_importable(self):
        """server.py deve importar sem erros."""
        from data_agents.mcp_servers.azure_pricing import server

        assert hasattr(server, "mcp")
        assert hasattr(server, "main")

    def test_server_config_importable(self):
        """server_config.py deve importar e expor as constantes."""
        from data_agents.mcp_servers.azure_pricing.server_config import (
            AZURE_PRICING_MCP_READONLY_TOOLS,
            AZURE_PRICING_MCP_TOOLS,
            get_azure_pricing_mcp_config,
        )

        assert isinstance(AZURE_PRICING_MCP_TOOLS, list)
        assert isinstance(AZURE_PRICING_MCP_READONLY_TOOLS, list)
        assert callable(get_azure_pricing_mcp_config)

    def test_all_tools_use_correct_prefix(self):
        """Tools devem seguir convenção mcp__azure_pricing__*."""
        from data_agents.mcp_servers.azure_pricing.server_config import AZURE_PRICING_MCP_TOOLS

        for tool in AZURE_PRICING_MCP_TOOLS:
            assert tool.startswith("mcp__azure_pricing__"), (
                f"Tool {tool} não segue convenção mcp__<server>__<tool>"
            )

    def test_readonly_is_subset_of_full(self):
        """Tools readonly devem ser subset das tools completas."""
        from data_agents.mcp_servers.azure_pricing.server_config import (
            AZURE_PRICING_MCP_READONLY_TOOLS,
            AZURE_PRICING_MCP_TOOLS,
        )

        assert set(AZURE_PRICING_MCP_READONLY_TOOLS).issubset(set(AZURE_PRICING_MCP_TOOLS))


# ─── Helpers Internos ────────────────────────────────────────────────────────


class TestHelpers:
    def test_default_region(self):
        from data_agents.mcp_servers.azure_pricing.server import _default_region

        # Default fallback se env não setado
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AZURE_PRICING_DEFAULT_REGION", None)
            assert _default_region() == "brazilsouth"

    def test_default_currency(self):
        from data_agents.mcp_servers.azure_pricing.server import _default_currency

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AZURE_PRICING_DEFAULT_CURRENCY", None)
            assert _default_currency() == "USD"

    def test_hours_per_month(self):
        from data_agents.mcp_servers.azure_pricing.server import _hours_per_month

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AZURE_PRICING_HOURS_PER_MONTH", None)
            assert _hours_per_month() == 730.0

    def test_hours_per_month_invalid_falls_back(self):
        from data_agents.mcp_servers.azure_pricing.server import _hours_per_month

        with patch.dict(os.environ, {"AZURE_PRICING_HOURS_PER_MONTH": "abc"}):
            assert _hours_per_month() == 730.0

    def test_now_iso_format(self):
        from data_agents.mcp_servers.azure_pricing.server import _now_iso

        ts = _now_iso()
        # Formato esperado: YYYY-MM-DDTHH:MM:SSZ
        assert len(ts) == 20
        assert ts.endswith("Z")
        assert "T" in ts


# ─── Tools (com mock de requests) ────────────────────────────────────────────


class TestTools:
    def test_diagnostics_returns_status(self, mock_retail_response):
        from data_agents.mcp_servers.azure_pricing import server

        # Limpa cache pra garantir hit no mock
        server._PRICE_CACHE.clear()

        with patch("data_agents.mcp_servers.azure_pricing.server.requests") as mock_req:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_retail_response
            mock_response.raise_for_status = MagicMock()
            mock_req.get.return_value = mock_response

            result = server.azure_pricing_diagnostics()
            data = json.loads(result)

        assert data["status"] == "ok"
        assert data["api_endpoint"] == "https://prices.azure.com/api/retail/prices"
        assert "defaults" in data
        assert "timestamp" in data

    def test_get_retail_price_builds_correct_filter(self, mock_retail_response):
        from data_agents.mcp_servers.azure_pricing import server

        server._PRICE_CACHE.clear()

        with patch("data_agents.mcp_servers.azure_pricing.server.requests") as mock_req:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_retail_response
            mock_response.raise_for_status = MagicMock()
            mock_req.get.return_value = mock_response

            result = server.azure_pricing_get_retail_price(
                service_name="Storage",
                region="brazilsouth",
                sku_name="Standard_LRS",
            )
            data = json.loads(result)

        assert data["items_count"] == 1
        # Verificar que filter foi montado com todos os critérios
        filter_expr = data["query"]["filter_expression"]
        assert "serviceName eq 'Storage'" in filter_expr
        assert "armRegionName eq 'brazilsouth'" in filter_expr
        assert "skuName eq 'Standard_LRS'" in filter_expr
        assert "priceType eq 'Consumption'" in filter_expr

    def test_estimate_monthly_cost_hour_based_uses_730(self, mock_hour_based_response):
        """Recurso cobrado por hora deve ser × 730 pra mensal."""
        from data_agents.mcp_servers.azure_pricing import server

        server._PRICE_CACHE.clear()

        with patch("data_agents.mcp_servers.azure_pricing.server.requests") as mock_req:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_hour_based_response
            mock_response.raise_for_status = MagicMock()
            mock_req.get.return_value = mock_response

            resources = json.dumps(
                [
                    {
                        "label": "AI Search S1",
                        "service_name": "Azure Cognitive Search",
                        "sku_name": "S1",
                        "region": "brazilsouth",
                        "quantity": 1,
                    }
                ]
            )
            result = server.azure_pricing_estimate_monthly_cost(resources_json=resources)
            data = json.loads(result)

        assert data["summary"]["matched_count"] == 1
        # 0.34247 × 730 × 1 ≈ 250
        item = data["breakdown"][0]
        assert item["match_found"] is True
        expected = 0.34247 * 730 * 1
        assert abs(item["monthly_cost"] - expected) < 0.5

    def test_estimate_monthly_cost_invalid_json(self):
        from data_agents.mcp_servers.azure_pricing import server

        result = server.azure_pricing_estimate_monthly_cost(resources_json="not valid json")
        data = json.loads(result)
        assert "error" in data

    def test_estimate_monthly_cost_not_a_list(self):
        from data_agents.mcp_servers.azure_pricing import server

        result = server.azure_pricing_estimate_monthly_cost(resources_json='{"not": "a list"}')
        data = json.loads(result)
        assert "error" in data

    def test_estimate_monthly_cost_unmatched(self):
        """Resource sem match deve aparecer em warnings."""
        from data_agents.mcp_servers.azure_pricing import server

        server._PRICE_CACHE.clear()

        with patch("data_agents.mcp_servers.azure_pricing.server.requests") as mock_req:
            mock_response = MagicMock()
            mock_response.json.return_value = {"Items": [], "NextPageLink": None}
            mock_response.raise_for_status = MagicMock()
            mock_req.get.return_value = mock_response

            resources = json.dumps(
                [
                    {
                        "label": "fake service",
                        "service_name": "NonExistentService",
                        "region": "brazilsouth",
                    }
                ]
            )
            result = server.azure_pricing_estimate_monthly_cost(resources_json=resources)
            data = json.loads(result)

        assert data["summary"]["unmatched_count"] == 1
        assert len(data["warnings"]) > 0

    def test_currency_convert_same_currency_returns_amount(self):
        from data_agents.mcp_servers.azure_pricing import server

        result = server.azure_pricing_currency_convert(
            amount=100.0, from_currency="USD", to_currency="USD"
        )
        data = json.loads(result)
        assert data["amount_original"] == 100.0
        assert data["amount_converted"] == 100.0
        assert data["exchange_rate"] == 1.0

    def test_list_regions_returns_structured_data(self):
        from data_agents.mcp_servers.azure_pricing import server

        result = server.azure_pricing_list_regions()
        data = json.loads(result)

        assert "regions_by_geography" in data
        assert "Brazil" in data["regions_by_geography"]
        assert "brazilsouth" in data["regions_by_geography"]["Brazil"]
        assert data["total_regions"] > 30

    def test_savings_plan_calc_recommends_overcommitted_low_usage(self):
        from data_agents.mcp_servers.azure_pricing import server

        result = server.azure_pricing_savings_plan_calc(
            hourly_commitment_usd=10.0,
            actual_usage_hours=100,  # bem menos que 730
            term_years=1,
        )
        data = json.loads(result)
        assert data["recommendation"] == "overcommitted"

    def test_savings_plan_calc_recommends_good_fit_high_usage(self):
        from data_agents.mcp_servers.azure_pricing import server

        result = server.azure_pricing_savings_plan_calc(
            hourly_commitment_usd=10.0,
            actual_usage_hours=720,  # quase 100% das 730
            term_years=3,
        )
        data = json.loads(result)
        assert data["recommendation"] == "good_fit"

    def test_generate_calculator_url_returns_links(self):
        from data_agents.mcp_servers.azure_pricing import server

        resources = json.dumps([{"label": "AI Search", "service_name": "Azure AI Search"}])
        result = server.azure_pricing_generate_calculator_url(resources_json=resources)
        data = json.loads(result)

        assert "calculator_base_url" in data
        assert "azure.microsoft.com" in data["calculator_base_url"]
        assert len(data["resources_to_add_manually"]) == 1

    def test_generate_calculator_url_invalid_json(self):
        from data_agents.mcp_servers.azure_pricing import server

        result = server.azure_pricing_generate_calculator_url(resources_json="invalid")
        data = json.loads(result)
        assert "error" in data


# ─── Cache Behavior ──────────────────────────────────────────────────────────


class TestCache:
    def test_cache_hit_avoids_second_api_call(self, mock_retail_response):
        """Segunda chamada idêntica não deve fazer HTTP."""
        from data_agents.mcp_servers.azure_pricing import server

        server._PRICE_CACHE.clear()

        with patch("data_agents.mcp_servers.azure_pricing.server.requests") as mock_req:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_retail_response
            mock_response.raise_for_status = MagicMock()
            mock_req.get.return_value = mock_response

            # 1ª chamada — hit na API
            server._query_retail_api("serviceName eq 'Storage'")
            assert mock_req.get.call_count == 1

            # 2ª chamada idêntica — cache hit, sem nova chamada
            server._query_retail_api("serviceName eq 'Storage'")
            assert mock_req.get.call_count == 1  # ainda 1, não 2


# ─── Integration smoke (REAL network, opcional) ──────────────────────────────


@pytest.mark.requires_network
@pytest.mark.skipif(
    "AZURE_PRICING_RUN_REAL_API" not in __import__("os").environ,
    reason="TestRealAPI bate na Azure Retail Prices API real — habilite com AZURE_PRICING_RUN_REAL_API=1",
)
class TestRealAPI:
    """Testes que fazem hit real na Azure Retail Prices API. Skipped por default.

    Por que skip por default mesmo com @requires_network:
    - O endpoint às vezes retorna 'Connection aborted / RemoteDisconnected' por
      throttling momentâneo, gerando flakes em CI/dev local.
    - O teste é informativo (não cobre lógica do projeto, só sanidade da API).
    - Para rodar manualmente: `AZURE_PRICING_RUN_REAL_API=1 pytest -k TestRealAPI`.
    """

    def test_real_api_returns_storage_price(self):
        from data_agents.mcp_servers.azure_pricing import server

        server._PRICE_CACHE.clear()
        result = server._query_retail_api(
            "serviceName eq 'Storage' and armRegionName eq 'eastus' and skuName eq 'Standard_LRS'",
            max_results=1,
        )
        assert isinstance(result, list)
        if result:
            assert "retailPrice" in result[0]
            assert "serviceName" in result[0]


# ─── Config & Registration ───────────────────────────────────────────────────


class TestConfigRegistration:
    def test_registered_in_all_mcp_configs(self):
        from data_agents.config.mcp_servers import ALL_MCP_CONFIGS

        assert "azure_pricing" in ALL_MCP_CONFIGS
        assert callable(ALL_MCP_CONFIGS["azure_pricing"])

    def test_in_always_active_mcps(self):
        """azure_pricing não precisa de credenciais — deve estar always-active."""
        from data_agents.config.mcp_servers import ALWAYS_ACTIVE_MCPS

        assert "azure_pricing" in ALWAYS_ACTIVE_MCPS

    def test_aliases_in_loader(self):
        from data_agents.agents.loader import MCP_TOOL_SETS

        assert "azure_pricing_all" in MCP_TOOL_SETS
        assert "azure_pricing_readonly" in MCP_TOOL_SETS
        assert len(MCP_TOOL_SETS["azure_pricing_all"]) > 0

    def test_command_registered(self):
        """Slash command /cost-azure deve estar registrado em commands.yaml."""
        from pathlib import Path

        import yaml

        # Phase 7: tests/unit/X.py — repo root é 2 níveis acima; commands.yaml
        # está em data_agents/config/.
        repo_root = Path(__file__).parent.parent.parent
        commands_path = repo_root / "data_agents" / "config" / "commands.yaml"
        with open(commands_path) as f:
            data = yaml.safe_load(f)

        assert "cost-azure" in data["commands"]
        assert data["commands"]["cost-azure"]["agent"] == "azure-cost-calculator"

    def test_agent_registry_file_exists(self):
        from pathlib import Path

        # Phase 7: registry vive em data_agents/agents/registry/.
        repo_root = Path(__file__).parent.parent.parent
        path = repo_root / "data_agents" / "agents" / "registry" / "azure-cost-calculator.md"
        assert path.exists()
        content = path.read_text()
        assert "name: azure-cost-calculator" in content
        assert "azure_pricing" in content
