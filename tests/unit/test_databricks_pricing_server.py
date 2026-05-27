"""
Tests do MCP databricks_pricing server.

Testa as 9 tools chamando-as como funções Python diretamente (não como MCP
protocol — isso seria integration test).
"""

from __future__ import annotations

import json

import pytest

from data_agents.mcp_servers.databricks_pricing import server


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _parse(response: str) -> dict:
    """Parse JSON envelope retornado pelas tools."""
    return json.loads(response)


# ─── Diagnostics ─────────────────────────────────────────────────────────────


class TestDiagnostics:
    def test_diagnostics_returns_ok_status(self):
        # FastMCP tools são wrapped — acessa via .fn ou chama diretamente
        result = server.databricks_pricing_diagnostics()
        data = _parse(result)
        assert "data" in data
        assert data["data"]["status"] == "ok"
        assert "catalogs_loaded" in data["data"]
        assert "azure" in data["data"]["catalogs_loaded"]
        assert "aws" in data["data"]["catalogs_loaded"]

    def test_diagnostics_smoke_canonical_matches(self):
        result = server.databricks_pricing_diagnostics()
        data = _parse(result)
        smoke = data["data"]["smoke_test_canonical"]
        # Jobs Premium 4w Standard_DS4_v2 8h × 22d on-demand brazilsouth = $726.88
        assert smoke["actual_monthly_usd"] == pytest.approx(726.88, abs=0.5)
        assert smoke["match"] is True


# ─── get_dbu_rate ────────────────────────────────────────────────────────────


class TestGetDBURate:
    def test_jobs_premium_no_photon_azure_returns_020(self):
        result = server.databricks_pricing_get_dbu_rate(
            compute_type="jobs_compute",
            tier="premium",
            photon=False,
            cloud="azure",
        )
        data = _parse(result)
        assert data["data"]["dbu_rate_per_hour_usd"] == 0.20

    def test_jobs_standard_aws_returns_010(self):
        result = server.databricks_pricing_get_dbu_rate(
            compute_type="jobs_compute",
            tier="standard",
            photon=False,
            cloud="aws",
        )
        data = _parse(result)
        assert data["data"]["dbu_rate_per_hour_usd"] == 0.10

    def test_serverless_compute_returns_base_per_dbu(self):
        result = server.databricks_pricing_get_dbu_rate(
            compute_type="serverless_compute",
            cloud="azure",
        )
        data = _parse(result)
        assert data["data"]["dbu_rate_per_hour_usd"] == 0.95

    def test_unknown_compute_returns_error(self):
        result = server.databricks_pricing_get_dbu_rate(
            compute_type="invalid_xyz",
            cloud="azure",
        )
        data = _parse(result)
        assert data.get("error") is True

    def test_uses_default_cloud_when_none(self):
        # Default = azure (DATABRICKS_PRICING_DEFAULT_CLOUD)
        result = server.databricks_pricing_get_dbu_rate(
            compute_type="jobs_compute",
            tier="premium",
            photon=False,
        )
        data = _parse(result)
        assert data["data"]["cloud"] == "azure"


# ─── get_instance_price ──────────────────────────────────────────────────────


class TestGetInstancePrice:
    def test_azure_standard_ds4_v2_brazilsouth(self):
        result = server.databricks_pricing_get_instance_price(
            instance_sku="Standard_DS4_v2",
            region="brazilsouth",
            cloud="azure",
        )
        data = _parse(result)
        assert data["data"]["price_usd_per_hour"] == pytest.approx(0.526, abs=0.01)
        assert data["data"]["dbu_per_hour"] == 1.5
        assert data["data"]["is_mock"] is True

    def test_aws_m5_xlarge_us_east(self):
        result = server.databricks_pricing_get_instance_price(
            instance_sku="m5.xlarge",
            region="us-east-1",
            cloud="aws",
        )
        data = _parse(result)
        assert data["data"]["price_usd_per_hour"] == pytest.approx(0.192, abs=0.001)

    def test_unknown_sku_returns_error(self):
        result = server.databricks_pricing_get_instance_price(
            instance_sku="z99.megalarge",
            region="us-east-1",
            cloud="aws",
        )
        data = _parse(result)
        assert data.get("error") is True


# ─── list_instances + list_regions ───────────────────────────────────────────


class TestListing:
    def test_list_instances_brazilsouth_returns_sorted(self):
        result = server.databricks_pricing_list_instances(cloud="azure", region="brazilsouth")
        data = _parse(result)
        assert data["data"]["count"] > 0
        assert data["data"]["instances"] == sorted(data["data"]["instances"])
        assert "Standard_DS4_v2" in data["data"]["instances"]

    def test_list_regions_aws_has_us_east_1(self):
        result = server.databricks_pricing_list_regions(cloud="aws")
        data = _parse(result)
        assert "us-east-1" in data["data"]["regions"]
        assert "sa-east-1" in data["data"]["regions"]


# ─── calc_cluster_cost (canonical) ───────────────────────────────────────────


class TestCalcClusterCost:
    def test_canonical_scenario_returns_726(self):
        result = server.databricks_pricing_calc_cluster_cost(
            cloud="azure",
            compute_type="jobs_compute",
            tier="premium",
            photon=False,
            driver_instance="Standard_DS4_v2",
            worker_instance="Standard_DS4_v2",
            num_workers=4,
            hours_per_day=8.0,
            days_per_month=22,
            region="brazilsouth",
        )
        data = _parse(result)
        assert data["data"]["totals"]["monthly"] == pytest.approx(726.88, abs=0.5)

    def test_brl_conversion_via_fx_rate(self):
        result = server.databricks_pricing_calc_cluster_cost(
            cloud="azure",
            compute_type="jobs_compute",
            tier="premium",
            photon=False,
            driver_instance="Standard_DS4_v2",
            worker_instance="Standard_DS4_v2",
            num_workers=4,
            hours_per_day=8.0,
            days_per_month=22,
            region="brazilsouth",
            currency="BRL",
            fx_rate=5.0,
        )
        data = _parse(result)
        # Monthly em BRL = 726.88 * 5 = 3634.40
        assert data["data"]["totals"]["monthly"] == pytest.approx(3634.40, abs=1.0)
        assert data["data"]["currency"] == "BRL"


# ─── compare_payg_vs_dbcu ────────────────────────────────────────────────────


class TestComparePAYGvsDBCU:
    def test_small_workload_no_savings(self):
        result = server.databricks_pricing_compare_payg_vs_dbcu(
            cloud="azure",
            compute_type="jobs_compute",
            tier="standard",
            photon=False,
            driver_instance="Standard_DS3_v2",
            worker_instance="Standard_DS3_v2",
            num_workers=1,
            hours_per_day=1.0,
            days_per_month=22,
            region="brazilsouth",
        )
        data = _parse(result)
        # Workload pequeno → sem DBCU savings
        assert data["data"]["savings_1y_annual"] == 0
        assert "Permaneça em Pay-as-you-go" in data["data"]["recommendation"]

    def test_large_workload_has_savings(self):
        result = server.databricks_pricing_compare_payg_vs_dbcu(
            cloud="azure",
            compute_type="jobs_compute",
            tier="premium",
            photon=True,
            driver_instance="Standard_E16ds_v4",
            worker_instance="Standard_E16ds_v4",
            num_workers=10,
            hours_per_day=24.0,
            days_per_month=30,
            region="brazilsouth",
        )
        data = _parse(result)
        assert data["data"]["savings_1y_annual"] > 0
        assert data["data"]["savings_3y_annual"] > data["data"]["savings_1y_annual"]
        assert "DBCU" in data["data"]["recommendation"]


# ─── currency_convert ────────────────────────────────────────────────────────


class TestCurrencyConvert:
    def test_usd_to_brl_default_5(self):
        result = server.databricks_pricing_currency_convert(
            amount_usd=100.0,
            target_currency="BRL",
            fx_rate=5.0,
        )
        data = _parse(result)
        assert data["data"]["amount_converted"] == 500.0
        assert data["data"]["fx_rate"] == 5.0

    def test_usd_to_usd_returns_same_amount(self):
        result = server.databricks_pricing_currency_convert(
            amount_usd=100.0,
            target_currency="USD",
        )
        data = _parse(result)
        assert data["data"]["amount_converted"] == 100.0
        assert data["data"]["fx_rate"] == 1.0


# ─── save_scenario (bridge Agent → App) ──────────────────────────────────────


class TestSaveScenario:
    @pytest.fixture
    def tmp_scenarios_env(self, tmp_path, monkeypatch):
        """Isola outputs/cost-scenarios em tmp_path."""
        scenarios_dir = tmp_path / "cost-scenarios"
        monkeypatch.setenv("COST_SCENARIOS_DIR", str(scenarios_dir))
        return scenarios_dir

    def test_save_returns_uuid_and_app_url(self, tmp_scenarios_env):
        result = server.databricks_pricing_save_scenario(
            cloud="azure",
            compute_type="jobs_compute",
            tier="premium",
            photon=False,
            driver_instance="Standard_DS4_v2",
            worker_instance="Standard_DS4_v2",
            num_workers=4,
            hours_per_day=8.0,
            days_per_month=22,
            region="brazilsouth",
            name="ETL Bronze produção",
            description="Pipeline noturno",
        )
        data = _parse(result)
        assert "uuid" in data["data"]
        assert len(data["data"]["uuid"]) == 36  # UUID v4
        assert data["data"]["app_url"] == "http://localhost:8514"
        assert "ETL Bronze produção" in data["data"]["next_step"]

    def test_save_file_created_with_source_agent(self, tmp_scenarios_env):
        result = server.databricks_pricing_save_scenario(
            cloud="azure",
            compute_type="jobs_compute",
            tier="premium",
            photon=False,
            driver_instance="Standard_DS4_v2",
            worker_instance="Standard_DS4_v2",
            num_workers=4,
            hours_per_day=8.0,
            days_per_month=22,
            region="brazilsouth",
            name="Test",
        )
        data = _parse(result)
        uuid = data["data"]["uuid"]
        # Lê o arquivo persistido
        filepath = tmp_scenarios_env / f"{uuid}.json"
        assert filepath.exists()
        with open(filepath) as f:
            envelope = json.load(f)
        assert envelope["source"] == "agent"
        assert envelope["scenario"]["cloud"] == "azure"


# ─── Validações gerais de envelope ───────────────────────────────────────────


class TestEnvelopeFormat:
    def test_all_tools_return_json(self):
        """Toda tool deve retornar string JSON parseável."""
        # Pula tools que requerem state externo (save_scenario) — testados separado
        tools_to_test = [
            ("databricks_pricing_diagnostics", {}),
            ("databricks_pricing_list_regions", {"cloud": "azure"}),
            (
                "databricks_pricing_list_instances",
                {"cloud": "azure", "region": "brazilsouth"},
            ),
        ]
        for tool_name, kwargs in tools_to_test:
            tool_func = getattr(server, tool_name)
            result = tool_func(**kwargs)
            # Não deve crashar no parse
            data = json.loads(result)
            assert "timestamp" in data


# ─── Bridge App → Agent (Chunk 2.3) ──────────────────────────────────────────


class TestBridgeListLoadDeleteSearch:
    """Testes das 4 novas tools MCP do Chunk 2.3 (list/load/delete/search)."""

    @pytest.fixture
    def tmp_scenarios_env(self, tmp_path, monkeypatch):
        """Isola outputs/cost-scenarios em tmp_path."""
        scenarios_dir = tmp_path / "cost-scenarios"
        monkeypatch.setenv("COST_SCENARIOS_DIR", str(scenarios_dir))
        return scenarios_dir

    def _save_canonical(self, name: str = "Canonical") -> str:
        """Helper: salva via tool save_scenario (source=agent)."""
        result = server.databricks_pricing_save_scenario(
            cloud="azure",
            compute_type="jobs_compute",
            tier="premium",
            photon=False,
            driver_instance="Standard_DS4_v2",
            worker_instance="Standard_DS4_v2",
            num_workers=4,
            hours_per_day=8.0,
            days_per_month=22,
            region="brazilsouth",
            name=name,
        )
        return _parse(result)["data"]["uuid"]

    def test_list_scenarios_empty_returns_zero(self, tmp_scenarios_env):
        result = server.databricks_pricing_list_scenarios()
        data = _parse(result)
        assert data["data"]["count"] == 0
        assert data["data"]["scenarios"] == []

    def test_list_scenarios_returns_metadata(self, tmp_scenarios_env):
        self._save_canonical("ETL-1")
        self._save_canonical("ETL-2")
        result = server.databricks_pricing_list_scenarios()
        data = _parse(result)
        assert data["data"]["count"] == 2
        names = {s["name"] for s in data["data"]["scenarios"]}
        assert names == {"ETL-1", "ETL-2"}
        # Não vaza filepath (campo interno)
        assert all("filepath" not in s for s in data["data"]["scenarios"])

    def test_list_scenarios_filter_source(self, tmp_scenarios_env):
        self._save_canonical("FromAgent")
        # Salva um manual direto via API pra simular
        from data_agents.cost_app.databricks.scenarios import save_scenario
        from data_agents.cost_engine.databricks import DatabricksScenario

        manual_scenario = DatabricksScenario(
            cloud="azure",
            compute_type="jobs_compute",
            tier="premium",
            photon=False,
            driver_instance="Standard_DS4_v2",
            worker_instance="Standard_DS4_v2",
            num_workers=4,
            hours_per_day=8,
            days_per_month=22,
            region="brazilsouth",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.526,
            worker_instance_cost_per_hour_usd=0.526,
        )
        save_scenario(manual_scenario, name="FromManual", source="manual")

        result = server.databricks_pricing_list_scenarios(filter_source="agent")
        data = _parse(result)
        assert data["data"]["count"] == 1
        assert data["data"]["scenarios"][0]["name"] == "FromAgent"

    def test_load_scenario_returns_full_envelope(self, tmp_scenarios_env):
        scenario_uuid = self._save_canonical("ToLoad")
        result = server.databricks_pricing_load_scenario(scenario_uuid)
        data = _parse(result)
        assert data["data"]["uuid"] == scenario_uuid
        assert data["data"]["name"] == "ToLoad"
        assert data["data"]["source"] == "agent"
        assert data["data"]["parent_uuid"] is None
        assert "scenario" in data["data"]
        assert data["data"]["scenario"]["cloud"] == "azure"
        assert data["data"]["scenario"]["num_workers"] == 4

    def test_load_scenario_unknown_uuid_returns_error(self, tmp_scenarios_env):
        result = server.databricks_pricing_load_scenario("nonexistent-uuid-1234")
        data = _parse(result)
        assert data.get("error") is True

    def test_delete_scenario_removes_file(self, tmp_scenarios_env):
        scenario_uuid = self._save_canonical("ToDelete")
        result = server.databricks_pricing_delete_scenario(scenario_uuid)
        data = _parse(result)
        assert data["data"]["deleted"] is True
        # Lista subsequente confirma remoção
        list_result = _parse(server.databricks_pricing_list_scenarios())
        assert list_result["data"]["count"] == 0

    def test_delete_unknown_uuid_is_idempotent(self, tmp_scenarios_env):
        result = server.databricks_pricing_delete_scenario("nonexistent-uuid")
        data = _parse(result)
        assert data["data"]["deleted"] is False  # idempotente

    def test_search_finds_by_name_substring(self, tmp_scenarios_env):
        self._save_canonical("ETL Bronze produção")
        self._save_canonical("ETL Silver staging")
        self._save_canonical("Pipeline alfa")

        result = server.databricks_pricing_search_scenarios("ETL")
        data = _parse(result)
        assert data["data"]["count"] == 2
        names = {s["name"] for s in data["data"]["scenarios"]}
        assert names == {"ETL Bronze produção", "ETL Silver staging"}

    def test_search_respects_limit(self, tmp_scenarios_env):
        for i in range(5):
            self._save_canonical(f"ETL-{i}")
        result = server.databricks_pricing_search_scenarios("ETL", limit=2)
        data = _parse(result)
        assert data["data"]["count"] == 2
        assert data["data"]["limit"] == 2
