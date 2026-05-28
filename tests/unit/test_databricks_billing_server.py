"""Tests do MCP databricks_billing server (Fase 3).

Testa as 5 tools chamando-as como funções Python diretamente (não como MCP
protocol — isso seria integration test). Cobertura cobre:
  - diagnostics: smoke test mock mode
  - get_dbu_usage_daily: filtros (period, workspace_id, cloud)
  - get_top_cost_clusters: limit, ordenação DESC
  - get_cost_by_compute_type: percentuais
  - compare_estimate_vs_actual: bridge com Fase 2 (requer scenario salvo)
  - Envelope JSON validation
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest


# ─── Setup ───────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def force_mock_mode(monkeypatch):
    """Garante mock mode em todos os testes (independente do .env do dev)."""
    monkeypatch.setenv("DATABRICKS_BILLING_MOCK_MODE", "true")


@pytest.fixture
def server():
    """Importa server depois do mock mode setado."""
    from data_agents.mcp_servers.databricks_billing import server as srv

    return srv


def _parse(response: str) -> dict:
    return json.loads(response)


def _last_7_days() -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=6)
    return str(start), str(end)


# ─── Diagnostics ─────────────────────────────────────────────────────────────


class TestDiagnostics:
    def test_diagnostics_returns_ok_in_mock_mode(self, server):
        result = server.databricks_billing_diagnostics()
        data = _parse(result)
        assert data["mock_mode"] is True
        assert data["data"]["smoke_test"]["status"] == "ok"
        assert data["data"]["engine_loaded"] is True

    def test_diagnostics_includes_mock_metadata(self, server):
        data = _parse(server.databricks_billing_diagnostics())
        meta = data["data"]["mock_metadata"]
        assert meta["is_mock"] is True
        assert "AZURE" in meta["clouds_supported"]
        assert "AWS" in meta["clouds_supported"]

    def test_diagnostics_smoke_returns_positive_dbus(self, server):
        """Mock gera dados — smoke test não pode retornar 0."""
        data = _parse(server.databricks_billing_diagnostics())
        smoke = data["data"]["smoke_test"]
        # Não exigimos quantidade exata (varia com data), só que existe consumo
        assert smoke["total_dbus_last_7d"] > 0
        assert smoke["unique_skus"] > 0


# ─── get_dbu_usage_daily ─────────────────────────────────────────────────────


class TestGetDBUUsageDaily:
    def test_returns_rows_for_last_7_days(self, server):
        start, end = _last_7_days()
        result = server.databricks_billing_get_dbu_usage_daily(start, end)
        data = _parse(result)
        assert data["data"]["count"] > 0
        assert data["data"]["total_dbus"] > 0
        assert data["data"]["period"]["days"] == 7

    def test_invalid_period_returns_error(self, server):
        # end < start → engine levanta ValueError
        result = server.databricks_billing_get_dbu_usage_daily(
            start_date="2026-01-10", end_date="2026-01-01"
        )
        data = _parse(result)
        assert data.get("error") is True

    def test_invalid_date_format_returns_error(self, server):
        result = server.databricks_billing_get_dbu_usage_daily(
            start_date="not-a-date", end_date="2026-01-01"
        )
        data = _parse(result)
        assert data.get("error") is True

    def test_period_metadata_preserved(self, server):
        start, end = _last_7_days()
        data = _parse(
            server.databricks_billing_get_dbu_usage_daily(
                start, end, workspace_id=1234567890123456, cloud="AZURE"
            )
        )
        assert data["data"]["period"]["start_date"] == start
        assert data["data"]["period"]["end_date"] == end
        assert data["data"]["period"]["workspace_id"] == 1234567890123456
        assert data["data"]["period"]["cloud"] == "AZURE"

    def test_aws_cloud_returns_aws_skus(self, server):
        start, end = _last_7_days()
        data = _parse(server.databricks_billing_get_dbu_usage_daily(start, end, cloud="AWS"))
        # Todas as linhas devem ter SKU AWS
        for row in data["data"]["rows"]:
            assert "AWS" in row["sku_name"]


# ─── get_top_cost_clusters ───────────────────────────────────────────────────


class TestGetTopCostClusters:
    def test_returns_at_most_limit(self, server):
        start, end = _last_7_days()
        data = _parse(server.databricks_billing_get_top_cost_clusters(start, end, limit=3))
        assert data["data"]["count"] <= 3
        assert data["data"]["limit"] == 3

    def test_rows_ordered_by_cost_desc(self, server):
        start, end = _last_7_days()
        data = _parse(server.databricks_billing_get_top_cost_clusters(start, end, limit=10))
        rows = data["data"]["rows"]
        if len(rows) >= 2:
            assert rows[0]["estimated_cost_usd"] >= rows[1]["estimated_cost_usd"]

    def test_each_row_has_required_fields(self, server):
        start, end = _last_7_days()
        data = _parse(server.databricks_billing_get_top_cost_clusters(start, end))
        for row in data["data"]["rows"]:
            assert "cluster_id" in row
            assert "cluster_name" in row
            assert "total_dbus" in row
            assert "estimated_cost_usd" in row


# ─── get_cost_by_compute_type ────────────────────────────────────────────────


class TestGetCostByComputeType:
    def test_percentages_sum_to_100(self, server):
        start, end = _last_7_days()
        data = _parse(server.databricks_billing_get_cost_by_compute_type(start, end))
        rows = data["data"]["rows"]
        if rows:
            total_dbus_pct = sum(r["dbus_pct"] for r in rows)
            total_cost_pct = sum(r["cost_pct"] for r in rows)
            assert total_dbus_pct == pytest.approx(100.0, abs=0.5)
            assert total_cost_pct == pytest.approx(100.0, abs=0.5)

    def test_includes_compute_type_classification(self, server):
        start, end = _last_7_days()
        data = _parse(server.databricks_billing_get_cost_by_compute_type(start, end))
        valid_types = {
            "jobs_compute",
            "all_purpose_compute",
            "sql_compute",
            "serverless_compute",
            "dlt_core",
            "other",
        }
        for row in data["data"]["rows"]:
            assert row["compute_type"] in valid_types


# ─── compare_estimate_vs_actual (bridge Fase 2 ↔ Fase 3) ────────────────────


class TestCompareEstimateVsActual:
    @pytest.fixture
    def tmp_scenarios_env(self, tmp_path, monkeypatch):
        """Isola outputs/cost-scenarios em tmp_path (mesma estratégia da Fase 2)."""
        scenarios_dir = tmp_path / "cost-scenarios"
        monkeypatch.setenv("COST_SCENARIOS_DIR", str(scenarios_dir))
        return scenarios_dir

    @pytest.fixture
    def saved_scenario_uuid(self, tmp_scenarios_env) -> str:
        """Cria um cenário canonical e retorna o UUID."""
        from data_agents.mcp_servers.databricks_pricing import server as pricing

        result = pricing.databricks_pricing_save_scenario(
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
            name="Test Bridge Scenario",
        )
        return _parse(result)["data"]["uuid"]

    def test_returns_variance_and_verdict(self, server, saved_scenario_uuid):
        end = date.today()
        start = end - timedelta(days=29)
        result = server.databricks_billing_compare_estimate_vs_actual(
            scenario_uuid=saved_scenario_uuid,
            start_date=str(start),
            end_date=str(end),
        )
        data = _parse(result)
        assert "variance_pct" in data["data"]
        assert "verdict" in data["data"]
        assert data["data"]["verdict"] in {"on_budget", "over_budget", "under_budget"}

    def test_estimated_matches_phase_2_canonical(self, server, saved_scenario_uuid):
        """Estimated_monthly deve casar com canonical $726.88 da Fase 0."""
        end = date.today()
        start = end - timedelta(days=29)
        data = _parse(
            server.databricks_billing_compare_estimate_vs_actual(
                scenario_uuid=saved_scenario_uuid,
                start_date=str(start),
                end_date=str(end),
            )
        )
        assert data["data"]["estimated_monthly_usd"] == pytest.approx(726.88, abs=0.5)

    def test_unknown_uuid_returns_error(self, server, tmp_scenarios_env):
        end = date.today()
        start = end - timedelta(days=6)
        result = server.databricks_billing_compare_estimate_vs_actual(
            scenario_uuid="nonexistent-uuid-1234",
            start_date=str(start),
            end_date=str(end),
        )
        data = _parse(result)
        assert data.get("error") is True
        assert "not found" in data["message"].lower()

    def test_cluster_filter_changes_actual(self, server, saved_scenario_uuid):
        """Filtrar por cluster_name reduz o actual_total_usd."""
        end = date.today()
        start = end - timedelta(days=29)

        unfiltered = _parse(
            server.databricks_billing_compare_estimate_vs_actual(
                scenario_uuid=saved_scenario_uuid,
                start_date=str(start),
                end_date=str(end),
            )
        )
        filtered = _parse(
            server.databricks_billing_compare_estimate_vs_actual(
                scenario_uuid=saved_scenario_uuid,
                start_date=str(start),
                end_date=str(end),
                cluster_name_filter="etl-bronze-prod",
            )
        )
        # Filtrado por 1 cluster deve ter actual <= unfiltered (todos os clusters)
        assert filtered["data"]["actual_monthly_usd"] <= unfiltered["data"]["actual_monthly_usd"]


# ─── Envelope validation ─────────────────────────────────────────────────────


class TestEnvelopeFormat:
    def test_all_tools_return_valid_json_with_envelope(self, server):
        """Todas as tools retornam JSON com timestamp + mock_mode."""
        start, end = _last_7_days()
        tools_to_test = [
            ("databricks_billing_diagnostics", {}),
            ("databricks_billing_get_dbu_usage_daily", {"start_date": start, "end_date": end}),
            (
                "databricks_billing_get_top_cost_clusters",
                {"start_date": start, "end_date": end},
            ),
            (
                "databricks_billing_get_cost_by_compute_type",
                {"start_date": start, "end_date": end},
            ),
        ]
        for tool_name, kwargs in tools_to_test:
            tool_func = getattr(server, tool_name)
            result = tool_func(**kwargs)
            data = json.loads(result)
            assert "timestamp" in data
            assert "mock_mode" in data
            assert data["mock_mode"] is True
            assert "data" in data
