"""Testes do package data_agents/cost_app/databricks/ (instance_prices + scenarios)."""

import json

import pytest

from data_agents.cost_app.databricks.instance_prices import (
    get_instance_price_usd_per_hour,
    get_mock_metadata,
    list_instances_for_region,
    list_regions_for_cloud,
)
from data_agents.cost_app.databricks.scenarios import (
    delete_scenario,
    list_saved_scenarios,
    load_scenario,
    save_scenario,
)
from data_agents.cost_engine.databricks import DatabricksScenario


# ── Instance prices mock ─────────────────────────────────────────────────────


class TestInstancePrices:
    def test_get_azure_brazilsouth_known_sku(self):
        price = get_instance_price_usd_per_hour("azure", "brazilsouth", "Standard_DS4_v2")
        assert isinstance(price, float)
        assert price > 0
        # BR South tem premium ~25-30% vs us-east → DS4_v2 ~ 0.526
        assert 0.5 < price < 0.6

    def test_get_aws_us_east_known_sku(self):
        price = get_instance_price_usd_per_hour("aws", "us-east-1", "m5.xlarge")
        assert isinstance(price, float)
        assert price > 0
        # m5.xlarge us-east-1 ~ 0.192
        assert 0.18 < price < 0.20

    def test_sao_paulo_premium_vs_us_east(self):
        """São Paulo deve ser ~50% mais caro que us-east pra mesmo SKU."""
        m5xl_us = get_instance_price_usd_per_hour("aws", "us-east-1", "m5.xlarge")
        m5xl_br = get_instance_price_usd_per_hour("aws", "sa-east-1", "m5.xlarge")
        assert m5xl_br > m5xl_us * 1.3  # pelo menos 30% mais caro
        assert m5xl_br < m5xl_us * 2.0  # mas não 2x

    def test_brazil_south_premium_vs_us_east_azure(self):
        """Brazil South deve ser ~25% mais caro que us-east pra Azure."""
        ds4_us = get_instance_price_usd_per_hour("azure", "eastus", "Standard_DS4_v2")
        ds4_br = get_instance_price_usd_per_hour("azure", "brazilsouth", "Standard_DS4_v2")
        assert ds4_br > ds4_us * 1.1
        assert ds4_br < ds4_us * 1.5

    def test_unknown_cloud_raises(self):
        with pytest.raises(ValueError, match="Cloud desconhecida"):
            get_instance_price_usd_per_hour("gcp", "us-central1", "n2-standard-4")  # type: ignore[arg-type]

    def test_unknown_region_raises(self):
        with pytest.raises(KeyError, match="Region"):
            get_instance_price_usd_per_hour("azure", "mars-central1", "Standard_DS4_v2")

    def test_unknown_sku_raises(self):
        with pytest.raises(KeyError, match="Instance SKU"):
            get_instance_price_usd_per_hour("aws", "us-east-1", "z9.megalarge")

    def test_list_instances_for_region_returns_sorted(self):
        skus = list_instances_for_region("azure", "brazilsouth")
        assert len(skus) > 0
        assert skus == sorted(skus)

    def test_list_regions_for_cloud(self):
        azure_regions = list_regions_for_cloud("azure")
        aws_regions = list_regions_for_cloud("aws")
        assert "brazilsouth" in azure_regions
        assert "eastus" in azure_regions
        assert "sa-east-1" in aws_regions
        assert "us-east-1" in aws_regions

    def test_mock_metadata_flags_as_mock(self):
        meta = get_mock_metadata()
        assert meta["is_mock"] is True
        assert "last_updated" in meta
        assert meta["azure_regions_count"] > 0
        assert meta["aws_regions_count"] > 0


# ── Scenarios persistence ───────────────────────────────────────────────────


@pytest.fixture
def tmp_scenarios_dir(tmp_path, monkeypatch):
    """Isola scenarios em diretório temporário pra não poluir outputs/."""
    scenarios_dir = tmp_path / "cost-scenarios"
    monkeypatch.setenv("COST_SCENARIOS_DIR", str(scenarios_dir))
    return scenarios_dir


@pytest.fixture
def example_scenario() -> DatabricksScenario:
    return DatabricksScenario(
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


class TestScenarioPersistence:
    def test_save_returns_uuid_and_creates_file(self, tmp_scenarios_dir, example_scenario):
        scenario_uuid = save_scenario(example_scenario, name="Test Scenario", description="Test")
        assert isinstance(scenario_uuid, str)
        assert len(scenario_uuid) == 36  # UUID v4
        expected_file = tmp_scenarios_dir / f"{scenario_uuid}.json"
        assert expected_file.exists()

    def test_save_envelope_has_required_metadata(self, tmp_scenarios_dir, example_scenario):
        scenario_uuid = save_scenario(
            example_scenario, name="ETL Bronze", description="Pipeline diário"
        )
        path = tmp_scenarios_dir / f"{scenario_uuid}.json"
        with open(path) as f:
            envelope = json.load(f)
        assert envelope["uuid"] == scenario_uuid
        assert envelope["name"] == "ETL Bronze"
        assert envelope["description"] == "Pipeline diário"
        assert envelope["source"] == "manual"
        assert "created_at" in envelope
        assert envelope["schema_version"] == "1.0.0"
        assert envelope["scenario"]["cloud"] == "azure"

    def test_load_reconstructs_scenario(self, tmp_scenarios_dir, example_scenario):
        scenario_uuid = save_scenario(example_scenario, name="Test")
        loaded = load_scenario(scenario_uuid)
        assert loaded.cloud == example_scenario.cloud
        assert loaded.compute_type == example_scenario.compute_type
        assert loaded.num_workers == example_scenario.num_workers
        assert loaded.driver_instance == example_scenario.driver_instance

    def test_load_unknown_uuid_raises(self, tmp_scenarios_dir):
        with pytest.raises(FileNotFoundError):
            load_scenario("nonexistent-uuid-1234")

    def test_list_saved_scenarios_empty(self, tmp_scenarios_dir):
        entries = list_saved_scenarios()
        assert entries == []

    def test_list_saved_scenarios_returns_metadata(self, tmp_scenarios_dir, example_scenario):
        save_scenario(example_scenario, name="A", source="manual")
        save_scenario(example_scenario, name="B", source="agent")
        entries = list_saved_scenarios()
        assert len(entries) == 2
        names = {e["name"] for e in entries}
        assert names == {"A", "B"}
        sources = {e["source"] for e in entries}
        assert sources == {"manual", "agent"}

    def test_list_sorted_desc_by_created_at(self, tmp_scenarios_dir, example_scenario):
        import time

        uuid_a = save_scenario(example_scenario, name="A")
        time.sleep(0.01)
        uuid_b = save_scenario(example_scenario, name="B")
        entries = list_saved_scenarios()
        # B foi criado depois → deve aparecer primeiro
        assert entries[0]["uuid"] == uuid_b
        assert entries[1]["uuid"] == uuid_a

    def test_delete_removes_file(self, tmp_scenarios_dir, example_scenario):
        scenario_uuid = save_scenario(example_scenario, name="Test")
        assert delete_scenario(scenario_uuid) is True
        path = tmp_scenarios_dir / f"{scenario_uuid}.json"
        assert not path.exists()

    def test_delete_nonexistent_returns_false(self, tmp_scenarios_dir):
        assert delete_scenario("nonexistent-uuid") is False

    def test_corrupt_file_is_skipped_in_list(self, tmp_scenarios_dir):
        # Cria arquivo corrupto
        corrupt = tmp_scenarios_dir
        corrupt.mkdir(parents=True, exist_ok=True)
        (corrupt / "broken.json").write_text("{ not valid json")
        entries = list_saved_scenarios()
        assert entries == []  # ignora silenciosamente

    def test_save_with_source_agent(self, tmp_scenarios_dir, example_scenario):
        """Cenário marcado como vindo do agent (preparação Fase 2)."""
        scenario_uuid = save_scenario(example_scenario, name="From Agent", source="agent")
        loaded_entry = next(e for e in list_saved_scenarios() if e["uuid"] == scenario_uuid)
        assert loaded_entry["source"] == "agent"
