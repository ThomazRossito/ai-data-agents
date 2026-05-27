"""Testes do cost engine Databricks (data_agents/cost_engine/databricks.py).

Cobertura:
  - Carga de catalog (azure + aws)
  - Cálculo determinístico (mesma entrada → mesma saída)
  - Cenários canônicos com valores conhecidos
  - Resolução de DBU rates por compute_type/tier/photon
  - Aplicação de spot/reserved discounts
  - DBCU commit savings progressivos
  - Photon speedup warnings
  - Conversão de moeda
"""

import pytest

from data_agents.cost_engine import (
    DatabricksScenario,
    calculate_databricks_cost,
    load_databricks_catalog,
)


# ── Catalog loading ──────────────────────────────────────────────────────────


class TestCatalogLoading:
    def test_load_azure_catalog(self):
        catalog = load_databricks_catalog("azure")
        assert catalog["cloud"] == "azure"
        assert catalog["schema_version"].startswith("1.")
        assert "dbu_rates_per_hour" in catalog
        assert "instance_dbu_map" in catalog

    def test_load_aws_catalog(self):
        catalog = load_databricks_catalog("aws")
        assert catalog["cloud"] == "aws"
        assert catalog["schema_version"].startswith("1.")
        assert "dbu_rates_per_hour" in catalog
        assert "instance_dbu_map" in catalog

    def test_catalogs_have_brazil_region(self):
        azure = load_databricks_catalog("azure")
        aws = load_databricks_catalog("aws")
        azure_regions = [r["id"] for r in azure["regions"]]
        aws_regions = [r["id"] for r in aws["regions"]]
        assert "brazilsouth" in azure_regions
        assert "sa-east-1" in aws_regions

    def test_catalog_has_dbcu_commit_tiers(self):
        catalog = load_databricks_catalog("azure")
        tiers = catalog["dbcu_commit_discounts"]
        # Pelo menos 4 tiers (0-10k, 10k-100k, 100k-500k, 500k+)
        assert len(tiers) >= 4
        # Primeiro tier sem desconto
        assert tiers[0]["discount_pct_1y"] == 0


# ── Cenário canônico: Jobs Compute Premium + Photon, Brazil South ────────────


class TestCanonicalScenarios:
    @pytest.fixture
    def basic_scenario_azure(self) -> DatabricksScenario:
        return DatabricksScenario(
            cloud="azure",
            compute_type="jobs_compute",
            tier="premium",
            photon=False,
            driver_instance="Standard_DS4_v2",  # 1.5 DBU/h
            worker_instance="Standard_DS4_v2",  # 1.5 DBU/h
            num_workers=4,
            hours_per_day=8,
            days_per_month=22,
            region="brazilsouth",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.526,  # Standard_DS4_v2 BR South aproximado
            worker_instance_cost_per_hour_usd=0.526,
        )

    def test_calculate_returns_required_keys(self, basic_scenario_azure):
        result = calculate_databricks_cost(basic_scenario_azure)
        assert "totals" in result
        assert "monthly" in result["totals"]
        assert "annual" in result["totals"]
        assert "tco_36m" in result["totals"]
        assert "breakdown_hourly_usd" in result
        assert "inputs_resolved" in result
        assert "commit_savings" in result
        assert "source" in result

    def test_dbu_rate_jobs_premium_no_photon_azure(self, basic_scenario_azure):
        """Premium Jobs sem Photon Azure = $0.20/DBU·h."""
        result = calculate_databricks_cost(basic_scenario_azure)
        assert result["inputs_resolved"]["dbu_rate_per_hour_usd"] == 0.20

    def test_effective_workers_no_autoscale(self, basic_scenario_azure):
        """Sem autoscale, effective_workers == num_workers."""
        result = calculate_databricks_cost(basic_scenario_azure)
        assert result["inputs_resolved"]["effective_workers"] == 4.0

    def test_hours_per_month_calculation(self, basic_scenario_azure):
        result = calculate_databricks_cost(basic_scenario_azure)
        assert result["inputs_resolved"]["hours_per_month"] == 176  # 8*22

    def test_dbu_cost_hourly_correct(self, basic_scenario_azure):
        """
        Driver: 1.5 DBU/h × $0.20 = $0.30/h
        Workers: 4 × 1.5 DBU/h × $0.20 = $1.20/h
        Total DBU hourly = $1.50/h
        """
        result = calculate_databricks_cost(basic_scenario_azure)
        assert result["breakdown_hourly_usd"]["dbu_driver"] == 0.3
        assert result["breakdown_hourly_usd"]["dbu_workers"] == 1.2
        assert result["breakdown_hourly_usd"]["dbu_total"] == 1.5

    def test_instance_cost_no_discount_on_demand(self, basic_scenario_azure):
        """
        On-demand: sem desconto, instance cost = base.
        Driver: $0.526/h, Workers: 4 × $0.526 = $2.104/h
        Total: $2.63/h
        """
        result = calculate_databricks_cost(basic_scenario_azure)
        assert result["breakdown_hourly_usd"]["instance_driver"] == pytest.approx(0.526)
        assert result["breakdown_hourly_usd"]["instance_workers"] == pytest.approx(2.104, abs=0.001)
        assert result["breakdown_hourly_usd"]["instance_total"] == pytest.approx(2.63, abs=0.001)
        assert result["inputs_resolved"]["instance_discount_pct_applied"] == 0

    def test_monthly_total_correct(self, basic_scenario_azure):
        """
        Cluster hourly = DBU ($1.50) + Instance ($2.63) = $4.13/h
        Monthly = $4.13 × 176h = $726.88
        """
        result = calculate_databricks_cost(basic_scenario_azure)
        assert result["totals"]["monthly"] == pytest.approx(726.88, abs=0.5)


# ── Spot pricing aplica desconto só no instance, não no DBU ──────────────────


class TestSpotPricing:
    def test_spot_applies_discount_to_instance_only(self):
        scenario = DatabricksScenario(
            cloud="aws",
            compute_type="jobs_compute",
            tier="standard",
            photon=False,
            driver_instance="m5.xlarge",
            worker_instance="m5.xlarge",
            num_workers=2,
            hours_per_day=24,
            days_per_month=30,
            region="us-east-1",
            instance_pricing_model="spot",
            driver_instance_cost_per_hour_usd=0.192,
            worker_instance_cost_per_hour_usd=0.192,
        )
        result = calculate_databricks_cost(scenario)
        # AWS us-east-1 spot discount = 80%
        assert result["inputs_resolved"]["instance_discount_pct_applied"] == 80
        # Instance after discount: $0.192 * 3 * 0.20 = $0.1152/h
        assert result["breakdown_hourly_usd"]["instance_total"] == pytest.approx(0.1152, abs=0.001)
        # DBU rate (Jobs Standard AWS) = $0.10/DBU·h, NÃO afetado
        assert result["inputs_resolved"]["dbu_rate_per_hour_usd"] == 0.10


# ── Reserved Instance aplica desconto no instance ────────────────────────────


class TestReservedInstance:
    def test_reserved_3y_no_upfront_aws(self):
        scenario = DatabricksScenario(
            cloud="aws",
            compute_type="all_purpose_compute",
            tier="premium",
            photon=False,
            driver_instance="m5.2xlarge",
            worker_instance="m5.2xlarge",
            num_workers=1,
            hours_per_day=1,
            days_per_month=1,
            region="us-east-1",
            instance_pricing_model="reserved_3y",
            driver_instance_cost_per_hour_usd=1.00,
            worker_instance_cost_per_hour_usd=1.00,
        )
        result = calculate_databricks_cost(scenario)
        # reserved_3y_no_upfront_pct AWS = 45
        assert result["inputs_resolved"]["instance_discount_pct_applied"] == 45


# ── Photon warning quando speedup < break_even ───────────────────────────────


class TestPhotonWarnings:
    def test_photon_low_speedup_emits_warning(self):
        scenario = DatabricksScenario(
            cloud="azure",
            compute_type="jobs_compute",
            tier="premium",
            photon=True,
            driver_instance="Standard_DS4_v2",
            worker_instance="Standard_DS4_v2",
            num_workers=2,
            hours_per_day=1,
            days_per_month=1,
            region="brazilsouth",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.526,
            worker_instance_cost_per_hour_usd=0.526,
            photon_speedup_factor=1.5,  # < break_even 2.0
        )
        result = calculate_databricks_cost(scenario)
        assert any("Photon" in w for w in result["warnings"])

    def test_photon_high_speedup_no_warning(self):
        scenario = DatabricksScenario(
            cloud="azure",
            compute_type="jobs_compute",
            tier="premium",
            photon=True,
            driver_instance="Standard_DS4_v2",
            worker_instance="Standard_DS4_v2",
            num_workers=2,
            hours_per_day=1,
            days_per_month=1,
            region="brazilsouth",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.526,
            worker_instance_cost_per_hour_usd=0.526,
            photon_speedup_factor=3.0,  # > break_even
        )
        result = calculate_databricks_cost(scenario)
        assert not any("Photon" in w for w in result["warnings"])


# ── DBCU commit savings progressivos ─────────────────────────────────────────


class TestDBCUCommitSavings:
    def test_small_workload_no_dbcu_discount(self):
        """Cenário com gasto anual < $10k → sem desconto DBCU."""
        scenario = DatabricksScenario(
            cloud="azure",
            compute_type="jobs_compute",
            tier="standard",
            photon=False,
            driver_instance="Standard_DS3_v2",
            worker_instance="Standard_DS3_v2",
            num_workers=1,
            hours_per_day=1,
            days_per_month=22,
            region="brazilsouth",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.10,
            worker_instance_cost_per_hour_usd=0.10,
        )
        result = calculate_databricks_cost(scenario)
        assert result["commit_savings"]["auto_dbcu_pct_1y"] == 0
        assert result["commit_savings"]["savings_1y_usd"] == 0

    def test_large_workload_gets_dbcu_discount(self):
        """Cenário grande (>$10k/year DBU) → desconto DBCU aplicável."""
        scenario = DatabricksScenario(
            cloud="azure",
            compute_type="jobs_compute",
            tier="premium",
            photon=True,
            driver_instance="Standard_E16ds_v4",
            worker_instance="Standard_E16ds_v4",
            num_workers=10,
            hours_per_day=24,
            days_per_month=30,
            region="brazilsouth",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=1.20,
            worker_instance_cost_per_hour_usd=1.20,
        )
        result = calculate_databricks_cost(scenario)
        # Esse cenário deve gerar gasto anual DBU bem acima de $10k
        assert result["commit_savings"]["annual_dbu_usd"] > 10000
        assert result["commit_savings"]["auto_dbcu_pct_1y"] >= 15


# ── Conversão de moeda ──────────────────────────────────────────────────────


class TestCurrencyConversion:
    def test_brl_conversion(self):
        scenario = DatabricksScenario(
            cloud="azure",
            compute_type="jobs_compute",
            tier="standard",
            photon=False,
            driver_instance="Standard_DS3_v2",
            worker_instance="Standard_DS3_v2",
            num_workers=1,
            hours_per_day=1,
            days_per_month=1,
            region="brazilsouth",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.10,
            worker_instance_cost_per_hour_usd=0.10,
            currency_conversion_rate=5.0,  # 1 USD = R$ 5,00
            currency_label="BRL",
        )
        result = calculate_databricks_cost(scenario)
        assert result["currency"] == "BRL"
        assert result["fx_rate_applied"] == 5.0
        # Verifica que conversão foi aplicada: totals devem ser 5x do baseline
        assert any("Conversão" in w for w in result["warnings"])


# ── Determinismo: mesma entrada → mesma saída ────────────────────────────────


class TestDeterminism:
    def test_same_scenario_returns_same_result(self):
        scenario = DatabricksScenario(
            cloud="azure",
            compute_type="jobs_compute",
            tier="premium",
            photon=False,
            driver_instance="Standard_DS4_v2",
            worker_instance="Standard_DS4_v2",
            num_workers=3,
            hours_per_day=10,
            days_per_month=22,
            region="brazilsouth",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.50,
            worker_instance_cost_per_hour_usd=0.50,
        )
        result1 = calculate_databricks_cost(scenario)
        result2 = calculate_databricks_cost(scenario)
        assert result1["totals"] == result2["totals"]
        assert result1["breakdown_hourly_usd"] == result2["breakdown_hourly_usd"]


# ── Validações de erro ───────────────────────────────────────────────────────


class TestValidation:
    def test_unknown_compute_type_raises(self):
        catalog = load_databricks_catalog("azure")
        scenario = DatabricksScenario(
            cloud="azure",
            compute_type="invalid_type",  # type: ignore[arg-type]
            tier="premium",
            photon=False,
            driver_instance="Standard_DS3_v2",
            worker_instance="Standard_DS3_v2",
            num_workers=1,
            hours_per_day=1,
            days_per_month=1,
            region="brazilsouth",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.10,
            worker_instance_cost_per_hour_usd=0.10,
        )
        with pytest.raises(ValueError, match="Compute type desconhecido"):
            calculate_databricks_cost(scenario, catalog)

    def test_unknown_instance_raises(self):
        scenario = DatabricksScenario(
            cloud="azure",
            compute_type="jobs_compute",
            tier="premium",
            photon=False,
            driver_instance="NonExistent_VM",
            worker_instance="Standard_DS3_v2",
            num_workers=1,
            hours_per_day=1,
            days_per_month=1,
            region="brazilsouth",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.10,
            worker_instance_cost_per_hour_usd=0.10,
        )
        with pytest.raises(ValueError, match="Instance SKU"):
            calculate_databricks_cost(scenario)

    def test_cloud_mismatch_raises(self):
        catalog_azure = load_databricks_catalog("azure")
        scenario_aws = DatabricksScenario(
            cloud="aws",
            compute_type="jobs_compute",
            tier="premium",
            photon=False,
            driver_instance="m5.xlarge",
            worker_instance="m5.xlarge",
            num_workers=1,
            hours_per_day=1,
            days_per_month=1,
            region="us-east-1",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.10,
            worker_instance_cost_per_hour_usd=0.10,
        )
        with pytest.raises(ValueError, match="Catalog é da cloud"):
            calculate_databricks_cost(scenario_aws, catalog_azure)
