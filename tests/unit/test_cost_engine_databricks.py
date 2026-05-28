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


# ─── Regression: Serverless não deve cobrar instance_cost (reportado 2026-05-28) ──


class TestServerlessNoInstanceCost:
    """Bug reportado: cenário Serverless estava somando instance_cost de driver+workers,
    o que está errado conforme catalog YAML explicita 'Inclui infra Databricks-managed'.

    Fix em data_agents/cost_engine/databricks.py: zerar instance_cost quando
    compute_type ∈ {serverless_compute, sql_serverless}.
    """

    def test_serverless_compute_ignores_instance_cost(self):
        catalog = load_databricks_catalog("azure")
        # Cenário exato do bug report do user (Tab 1 → Serverless + DS12_v2)
        scenario = DatabricksScenario(
            cloud="azure",
            compute_type="serverless_compute",
            tier="premium",
            photon=False,
            driver_instance="Standard_DS12_v2",
            worker_instance="Standard_DS12_v2",
            num_workers=4,
            hours_per_day=2.5,
            days_per_month=22,
            region="brazilsouth",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.464,
            worker_instance_cost_per_hour_usd=0.464,
        )
        result = calculate_databricks_cost(scenario, catalog)

        # Instance cost deve ser ZERO em serverless
        assert result["breakdown_hourly_usd"]["instance_total"] == 0.0
        assert result["breakdown_hourly_usd"]["instance_driver"] == 0.0
        assert result["breakdown_hourly_usd"]["instance_workers"] == 0.0

        # Cluster total deve ser apenas DBU cost
        assert (
            result["breakdown_hourly_usd"]["cluster_total"]
            == result["breakdown_hourly_usd"]["dbu_total"]
        )

        # Warning explicativo deve estar presente
        assert any("serverless" in w.lower() for w in result["warnings"])

    def test_serverless_monthly_matches_dbu_only(self):
        """Serverless mensal = DBU_total/h × hours/dia × dias/mês (sem instance)."""
        catalog = load_databricks_catalog("azure")
        scenario = DatabricksScenario(
            cloud="azure",
            compute_type="serverless_compute",
            tier="premium",
            photon=False,
            driver_instance="Standard_DS12_v2",
            worker_instance="Standard_DS12_v2",
            num_workers=4,
            hours_per_day=2.5,
            days_per_month=22,
            region="brazilsouth",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.464,
            worker_instance_cost_per_hour_usd=0.464,
        )
        result = calculate_databricks_cost(scenario, catalog)

        # DBU rate serverless azure premium = $0.35/DBU·h
        # (PR 1 fix 2026-05-28: era $0.95 fictício, real Jobs Serverless = $0.35)
        # Fonte: https://www.databricks.com/product/pricing/lakeflow-jobs
        # Driver DS12_v2 = 1.5 DBU/h, 4 workers × 1.5 = 6.0 DBU/h
        # Total DBU/h = 7.5 × $0.35 = $2.625/h
        # Mensal = $2.625 × 2.5h × 22d = $144.375
        assert result["totals"]["monthly"] == pytest.approx(144.37, abs=0.5)

    def test_non_serverless_keeps_instance_cost(self):
        """Cenário Jobs Premium (não-serverless) DEVE manter instance_cost (regression check)."""
        catalog = load_databricks_catalog("azure")
        scenario = DatabricksScenario(
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
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.526,
            worker_instance_cost_per_hour_usd=0.526,
        )
        result = calculate_databricks_cost(scenario, catalog)

        # Canonical $726.88 deve ser preservado
        assert result["totals"]["monthly"] == pytest.approx(726.88, abs=0.5)
        assert result["breakdown_hourly_usd"]["instance_total"] > 0.0

    def test_serverless_with_zero_instance_cost_inputs_no_warning(self):
        """Quando user passa instance_cost=0.0 explicitamente, não deve gerar warning duplo."""
        catalog = load_databricks_catalog("azure")
        scenario = DatabricksScenario(
            cloud="azure",
            compute_type="serverless_compute",
            tier="premium",
            photon=False,
            driver_instance="Standard_DS4_v2",
            worker_instance="Standard_DS4_v2",
            num_workers=4,
            hours_per_day=8.0,
            days_per_month=22,
            region="brazilsouth",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.0,
            worker_instance_cost_per_hour_usd=0.0,
        )
        result = calculate_databricks_cost(scenario, catalog)
        # Não gera warning de instance_cost zerado se o user já passou 0
        assert not any("instance_cost zerado" in w for w in result["warnings"])
        assert result["breakdown_hourly_usd"]["instance_total"] == 0.0

    def test_sql_with_tier_serverless_also_zeros_instance_cost(self):
        """SQL Warehouse com tier=serverless é Databricks-managed (no catalog atual,
        a opção 'SQL Warehouse Serverless' é compute_type=sql + tier=serverless)."""
        catalog = load_databricks_catalog("azure")
        scenario = DatabricksScenario(
            cloud="azure",
            compute_type="sql",
            tier="serverless",
            photon=False,
            driver_instance="Standard_DS4_v2",
            worker_instance="Standard_DS4_v2",
            num_workers=2,
            hours_per_day=4.0,
            days_per_month=22,
            region="brazilsouth",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.526,
            worker_instance_cost_per_hour_usd=0.526,
        )
        result = calculate_databricks_cost(scenario, catalog)
        assert result["breakdown_hourly_usd"]["instance_total"] == 0.0
        assert any("serverless" in w.lower() for w in result["warnings"])

    def test_sql_with_tier_pro_keeps_instance_cost(self):
        """Regression: SQL Warehouse Pro (não-serverless) NÃO deve zerar instance_cost."""
        catalog = load_databricks_catalog("azure")
        scenario = DatabricksScenario(
            cloud="azure",
            compute_type="sql",
            tier="pro",
            photon=False,
            driver_instance="Standard_DS4_v2",
            worker_instance="Standard_DS4_v2",
            num_workers=2,
            hours_per_day=4.0,
            days_per_month=22,
            region="brazilsouth",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.526,
            worker_instance_cost_per_hour_usd=0.526,
        )
        result = calculate_databricks_cost(scenario, catalog)
        # SQL Pro tem instance (não é managed)
        assert result["breakdown_hourly_usd"]["instance_total"] > 0.0


# ── PR 1 (2026-05-28): tier model alinhado com Databricks oficial ────────────


class TestTierValidation:
    """Audit 2026-05-28 (kb/databricks-pricing/extracted-prices-raw.md): tier 'standard'
    não consta em nenhuma das 25 sub-páginas de pricing oficiais Databricks.
    Em PR 1 levantamos warning; em PR 2 será erro.
    """

    def test_validate_tier_premium_is_official(self):
        from data_agents.cost_engine.databricks import validate_tier

        ok, warning = validate_tier("premium")
        assert ok is True
        assert warning is None

    def test_validate_tier_enterprise_is_official_aws(self):
        from data_agents.cost_engine.databricks import validate_tier

        ok, warning = validate_tier("enterprise", cloud="aws")
        assert ok is True
        assert warning is None

    def test_validate_tier_enterprise_on_azure_warns(self):
        """Azure não publica Enterprise — Azure Premium ≡ AWS/GCP Enterprise."""
        from data_agents.cost_engine.databricks import validate_tier

        ok, warning = validate_tier("enterprise", cloud="azure")
        # tier ainda é oficial (existe em AWS/GCP), mas merece warning de mapping
        assert ok is True
        assert warning is not None
        assert "Azure" in warning

    def test_validate_tier_standard_is_deprecated(self):
        from data_agents.cost_engine.databricks import validate_tier

        ok, warning = validate_tier("standard")
        assert ok is False
        assert warning is not None
        assert "DEPRECATED" in warning

    def test_validate_tier_unknown_value(self):
        from data_agents.cost_engine.databricks import validate_tier

        ok, warning = validate_tier("foobar")
        assert ok is False
        assert warning is not None
        assert "desconhecido" in warning.lower()

    def test_calculate_cost_with_tier_standard_emits_warning(self):
        """End-to-end: tier=standard em scenario produz warning no result."""
        scenario = DatabricksScenario(
            cloud="aws",
            compute_type="jobs_compute",
            tier="standard",
            photon=False,
            driver_instance="m5.xlarge",
            worker_instance="m5.xlarge",
            num_workers=1,
            hours_per_day=1,
            days_per_month=1,
            region="us-east-1",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.192,
            worker_instance_cost_per_hour_usd=0.192,
        )
        result = calculate_databricks_cost(scenario)
        assert any("DEPRECATED" in w for w in result["warnings"])

    def test_calculate_cost_with_tier_premium_no_deprecation_warning(self):
        """Regression check: tier=premium NÃO produz warning de deprecation."""
        scenario = DatabricksScenario(
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
            driver_instance_cost_per_hour_usd=0.192,
            worker_instance_cost_per_hour_usd=0.192,
        )
        result = calculate_databricks_cost(scenario)
        assert not any("DEPRECATED" in w for w in result["warnings"])


# ── PR 1 (2026-05-28): Serverless rate corrigido ($0.95 → $0.35) ────────────


class TestServerlessRateCorrection:
    """Audit 2026-05-28: serverless_compute.base_per_dbu era $0.95 (fictício).
    Real Jobs Serverless: $0.35/DBU (https://www.databricks.com/product/pricing/lakeflow-jobs).
    PR 2 vai sub-tipar pra DLT $0.35, SQL $0.70, All-Purpose $0.75.
    """

    def test_azure_serverless_rate_is_0_35(self):
        catalog = load_databricks_catalog("azure")
        rate = catalog["dbu_rates_per_hour"]["serverless_compute"]["base_per_dbu"]
        assert rate == 0.35

    def test_aws_serverless_rate_is_0_35(self):
        catalog = load_databricks_catalog("aws")
        rate = catalog["dbu_rates_per_hour"]["serverless_compute"]["base_per_dbu"]
        assert rate == 0.35


# ── PR 2 (2026-05-28): Serverless sub-types + GCP + Lakebase ────────────────


class TestServerlessSubTypes:
    """Audit 2026-05-28: Databricks publica 4 sub-types de Serverless oficial,
    cada um com rate distinta. PR 2 adiciona como compute_type separados:
        - jobs_serverless         → $0.35/DBU (lakeflow-jobs)
        - dlt_serverless          → $0.35/DBU (lakeflow-spark-declarative-pipelines)
        - sql_serverless          → $0.70/DBU (databricks-sql; existe como sql.serverless)
        - all_purpose_serverless  → $0.75/DBU (datascience-ml)
    """

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_jobs_serverless_rate_is_0_35(self, cloud):
        catalog = load_databricks_catalog(cloud)
        rate = catalog["dbu_rates_per_hour"]["jobs_serverless"]["base_per_dbu"]
        assert rate == 0.35

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_dlt_serverless_rate_is_0_35(self, cloud):
        catalog = load_databricks_catalog(cloud)
        rate = catalog["dbu_rates_per_hour"]["dlt_serverless"]["base_per_dbu"]
        assert rate == 0.35

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_all_purpose_serverless_rate_is_0_75(self, cloud):
        catalog = load_databricks_catalog(cloud)
        rate = catalog["dbu_rates_per_hour"]["all_purpose_serverless"]["base_per_dbu"]
        assert rate == 0.75

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_serverless_compute_marked_deprecated(self, cloud):
        catalog = load_databricks_catalog(cloud)
        sc = catalog["dbu_rates_per_hour"]["serverless_compute"]
        # PyYAML pode carregar `_deprecated: true` como bool ou str dependendo
        # da versão/safe_load config. Aceita ambas — semântica é "marcado deprecated".
        deprecated_val = sc.get("_deprecated")
        assert deprecated_val in (True, "true", "True"), (
            f"_deprecated esperado True/true, got {deprecated_val!r}"
        )
        assert sc.get("_deprecated_note")  # tem nota de migration

    def test_jobs_serverless_zeroes_instance_cost(self):
        """End-to-end: jobs_serverless deve zerar instance cost (Databricks-managed)."""
        scenario = DatabricksScenario(
            cloud="aws",
            compute_type="jobs_serverless",
            tier="premium",
            photon=False,
            driver_instance="m5.xlarge",
            worker_instance="m5.xlarge",
            num_workers=2,
            hours_per_day=4,
            days_per_month=22,
            region="us-east-1",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.192,
            worker_instance_cost_per_hour_usd=0.192,
        )
        result = calculate_databricks_cost(scenario)
        assert result["breakdown_hourly_usd"]["instance_total"] == 0.0
        assert result["inputs_resolved"]["dbu_rate_per_hour_usd"] == 0.35

    def test_all_purpose_serverless_zeroes_instance_cost(self):
        """End-to-end: all_purpose_serverless também é Databricks-managed."""
        scenario = DatabricksScenario(
            cloud="aws",
            compute_type="all_purpose_serverless",
            tier="premium",
            photon=False,
            driver_instance="m5.xlarge",
            worker_instance="m5.xlarge",
            num_workers=2,
            hours_per_day=8,
            days_per_month=22,
            region="us-east-1",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.192,
            worker_instance_cost_per_hour_usd=0.192,
        )
        result = calculate_databricks_cost(scenario)
        assert result["breakdown_hourly_usd"]["instance_total"] == 0.0
        assert result["inputs_resolved"]["dbu_rate_per_hour_usd"] == 0.75
        # monthly = 0.75 × 3 DBU/h (1 driver + 2 workers × 1 DBU) × 8h × 22d
        assert result["totals"]["monthly"] == pytest.approx(396.0, abs=1.0)


class TestGcpCatalog:
    """PR 2 (2026-05-28): gcp.yaml scaffold criado. Estrutura paralela a aws.yaml.
    Pricing derivado via paridade /product/sku-groups + Google Cloud Calculator spot-checks.
    """

    def test_gcp_catalog_loads(self):
        catalog = load_databricks_catalog("gcp")
        assert catalog["cloud"] == "gcp"
        assert catalog["schema_version"].startswith("1.")

    def test_gcp_has_premium_and_enterprise_tiers(self):
        """AWS/GCP têm Premium e Enterprise (Azure só Premium = AWS/GCP Enterprise)."""
        catalog = load_databricks_catalog("gcp")
        ap = catalog["dbu_rates_per_hour"]["all_purpose_compute"]
        assert "premium" in ap
        assert "enterprise" in ap

    def test_gcp_has_brazil_region(self):
        catalog = load_databricks_catalog("gcp")
        regions = [r["id"] for r in catalog["regions"]]
        assert "southamerica-east1" in regions

    def test_gcp_does_not_have_lakebase(self):
        """Lakebase oficialmente disponível só AWS + Azure (não GCP)."""
        catalog = load_databricks_catalog("gcp")
        assert "lakebase" not in catalog

    def test_gcp_has_lakeflow_connect(self):
        catalog = load_databricks_catalog("gcp")
        assert "lakeflow_connect" in catalog

    def test_gcp_scenario_resolves(self):
        """Smoke: cenário GCP padrão calcula custo sem erros."""
        scenario = DatabricksScenario(
            cloud="gcp",
            compute_type="jobs_compute",
            tier="premium",
            photon=False,
            driver_instance="n2-standard-4",
            worker_instance="n2-standard-4",
            num_workers=2,
            hours_per_day=8,
            days_per_month=22,
            region="us-central1",
            instance_pricing_model="on_demand",
            driver_instance_cost_per_hour_usd=0.1942,
            worker_instance_cost_per_hour_usd=0.1942,
        )
        result = calculate_databricks_cost(scenario)
        assert result["totals"]["monthly"] > 0
        # GCP Premium Jobs = $0.15/DBU per aws.yaml-derived paridade
        assert result["inputs_resolved"]["dbu_rate_per_hour_usd"] == 0.15


class TestLakebaseSchema:
    """PR 2 (2026-05-28): Lakebase block parses corretamente no YAML.
    Engine ainda não calcula Lakebase (TODO PR 3) — só carrega a estrutura.
    """

    @pytest.mark.parametrize("cloud", ["azure", "aws"])
    def test_lakebase_block_present(self, cloud):
        catalog = load_databricks_catalog(cloud)
        assert "lakebase" in catalog
        lb = catalog["lakebase"]
        assert lb["cost_unit"] == "cu_h"
        assert lb["promo_until"]  # tem data
        assert lb["autoscaling_per_cu_h_promo"] == 0.092
        assert lb["always_on_min_per_cu_h_promo"] == 0.069
        assert lb["storage_per_gb_month"] == 0.345

    @pytest.mark.parametrize("cloud", ["azure", "aws"])
    def test_lakebase_promo_below_list_price(self, cloud):
        """Sanidade: preço promocional deve ser menor que list price."""
        catalog = load_databricks_catalog(cloud)
        lb = catalog["lakebase"]
        assert lb["autoscaling_per_cu_h_promo"] < lb["autoscaling_per_cu_h_list"]
        assert lb["always_on_min_per_cu_h_promo"] < lb["always_on_min_per_cu_h_list"]


class TestLakeflowConnectSchema:
    """PR 2 (2026-05-28): Lakeflow Connect block parses no YAML em todas 3 clouds."""

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_lakeflow_connect_block_present(self, cloud):
        catalog = load_databricks_catalog(cloud)
        assert "lakeflow_connect" in catalog
        lfc = catalog["lakeflow_connect"]
        assert "managed_connectors" in lfc
        assert "zerobus_ingest" in lfc

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_managed_connectors_have_free_tier(self, cloud):
        catalog = load_databricks_catalog(cloud)
        mc = catalog["lakeflow_connect"]["managed_connectors"]
        assert mc["base_per_dbu"] == 0.35
        assert mc["free_tier_dbu_per_workspace_per_day"] == 100

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_zerobus_has_promo_period(self, cloud):
        catalog = load_databricks_catalog(cloud)
        zb = catalog["lakeflow_connect"]["zerobus_ingest"]
        assert zb["promo_until"] == "2026-09-01"
        assert zb["per_gb_promo"] < zb["per_gb_list"]


# ── PR 3 (2026-05-28): AI/ML SKUs completos ─────────────────────────────────


class TestAiMlSkusPresent:
    """PR 3: 10 novos blocos AI/ML adicionados nos 3 catalogs.
    Engine ainda não modela (display-only no Tab 8 Catálogo); PR 4 vai adicionar
    scenario types específicos (LLMScenario, VectorSearchScenario, etc.).
    """

    AI_ML_BLOCKS = (
        "model_serving",
        "foundation_model_serving",
        "proprietary_foundation_model_serving",
        "vector_search_v2",
        "ai_functions",
        "ai_gateway",
        "agent_bricks",
        "agent_evaluation",
        "model_training",
        "ai_runtime",
    )

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    @pytest.mark.parametrize("block", AI_ML_BLOCKS)
    def test_block_present_in_catalog(self, cloud, block):
        catalog = load_databricks_catalog(cloud)
        assert block in catalog, f"{cloud}: missing top-level block {block!r}"


class TestModelServing:
    """Model Serving CPU + GPU. Mesma rate $0.07/DBU; GPU diferenciação por DBU/h."""

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_cpu_and_gpu_rates_equal(self, cloud):
        catalog = load_databricks_catalog(cloud)
        ms = catalog["model_serving"]
        assert ms["cpu_per_dbu"] == 0.070
        assert ms["gpu_per_dbu"] == 0.070

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_gpu_instance_dbu_rates(self, cloud):
        """Tabela DBU/h por GPU size confirmada via Chrome MCP."""
        catalog = load_databricks_catalog(cloud)
        gpu = catalog["model_serving"]["gpu_instances"]
        assert gpu["small"]["dbu_per_hour"] == 10.48  # T4
        assert gpu["medium"]["dbu_per_hour"] == 20.00  # A10G x1
        assert gpu["large_8x_80"]["dbu_per_hour"] == 628.00  # A100 80GB x8


class TestFoundationModelServing:
    """Foundation Model Serving: 3 modes + 12 modelos com per-model DBU rates."""

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_pay_per_token_rates(self, cloud):
        catalog = load_databricks_catalog(cloud)
        ppt = catalog["foundation_model_serving"]["pay_per_token"]
        assert ppt["input_per_m_tokens_usd"] == 0.50
        assert ppt["output_per_m_tokens_usd"] == 1.50

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_provisioned_throughput_rate(self, cloud):
        catalog = load_databricks_catalog(cloud)
        pt = catalog["foundation_model_serving"]["provisioned_throughput"]
        assert pt["per_hour_per_pt_unit_usd"] == 6.00

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_llama_3_3_70b_dbu_rates(self, cloud):
        """Llama 3.3 70B é flagship — DBU rates confirmados via Chrome MCP."""
        catalog = load_databricks_catalog(cloud)
        models = catalog["foundation_model_serving"]["per_model_dbu_rates"]
        m = models["llama_3_3_70b"]
        assert m["input_dbu_per_m"] == 7.143
        assert m["output_dbu_per_m"] == 21.429
        assert m["entry_pt_dbu_h"] == 85.714
        assert m["scaling_pt_dbu_h"] == 342.857

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_has_12_models(self, cloud):
        catalog = load_databricks_catalog(cloud)
        models = catalog["foundation_model_serving"]["per_model_dbu_rates"]
        # 12 modelos extraídos da página oficial
        assert len(models) == 12


class TestProprietaryFoundationModelServing:
    """Proprietary FM: OpenAI/Anthropic/Gemini. $0.07/DBU base + per-model DBU."""

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_base_rate(self, cloud):
        catalog = load_databricks_catalog(cloud)
        pfms = catalog["proprietary_foundation_model_serving"]
        assert pfms["base_per_dbu_pay_per_token"] == 0.07
        assert pfms["base_per_dbu_batch"] == 0.07

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_openai_gpt_5_5_dbu_rates(self, cloud):
        """GPT 5.5 Global Short context — rates oficiais."""
        catalog = load_databricks_catalog(cloud)
        openai = catalog["proprietary_foundation_model_serving"]["vendors"]["openai"]["models"]
        gpt55 = openai["gpt_5_5"]
        assert gpt55["input_dbu_per_m"] == 71.429
        assert gpt55["output_dbu_per_m"] == 428.571
        assert gpt55["batch_dbu_per_h"] == 214.286

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_three_vendors_present(self, cloud):
        catalog = load_databricks_catalog(cloud)
        vendors = catalog["proprietary_foundation_model_serving"]["vendors"]
        assert "openai" in vendors
        assert "anthropic" in vendors
        assert "gemini" in vendors


class TestVectorSearchV2:
    """Vector Search refactor: 2 tiers (Standard 2M + Storage Optimized 64M)."""

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_standard_tier(self, cloud):
        catalog = load_databricks_catalog(cloud)
        std = catalog["vector_search_v2"]["tiers"]["standard"]
        assert std["compute_per_hour_usd"] == 0.28
        assert std["storage_per_gb_month_usd"] == 0.230
        assert std["vector_capacity_per_unit"] == 2_000_000
        assert std["dbu_per_hour"] == 4.00

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_storage_optimized_tier(self, cloud):
        catalog = load_databricks_catalog(cloud)
        opt = catalog["vector_search_v2"]["tiers"]["storage_optimized"]
        assert opt["compute_per_hour_usd"] == 1.28
        assert opt["storage_per_gb_month_usd"] == 0.046
        assert opt["vector_capacity_per_unit"] == 64_000_000
        assert opt["dbu_per_hour"] == 18.286


class TestAiFunctions:
    """AI Functions: Parse + Extract + Classify, todos $0.07/DBU promo."""

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_all_three_functions_present(self, cloud):
        catalog = load_databricks_catalog(cloud)
        aif = catalog["ai_functions"]
        assert "ai_parse_document" in aif
        assert "ai_extract" in aif
        assert "ai_classify" in aif

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_promo_below_list_price(self, cloud):
        catalog = load_databricks_catalog(cloud)
        aif = catalog["ai_functions"]
        assert aif["ai_parse_document"]["per_dbu_promo"] == 0.070
        assert aif["ai_parse_document"]["per_dbu_list"] == 0.140
        assert aif["promo_until"] == "2026-06-30"


class TestAiGateway:
    """AI Gateway: Guardrails ($/M tok), Inference Tables + Usage Tracking ($/GB)."""

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_guardrails_rate(self, cloud):
        catalog = load_databricks_catalog(cloud)
        assert catalog["ai_gateway"]["ai_guardrails"]["per_m_tokens_usd"] == 1.50

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_inference_tables_rate(self, cloud):
        catalog = load_databricks_catalog(cloud)
        assert catalog["ai_gateway"]["inference_tables"]["per_gb_usd"] == 0.50

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_usage_tracking_rate(self, cloud):
        catalog = load_databricks_catalog(cloud)
        assert catalog["ai_gateway"]["usage_tracking"]["per_gb_usd"] == 0.100


class TestAgentBricks:
    """Agent Bricks: Knowledge Assistant ($/Answer) + Supervisor Agent ($/DBU)."""

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_knowledge_assistant_promo(self, cloud):
        catalog = load_databricks_catalog(cloud)
        ka = catalog["agent_bricks"]["knowledge_assistant"]
        assert ka["per_answer_promo_usd"] == 0.150
        assert ka["per_answer_list_usd"] == 0.300

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_supervisor_agent_promo(self, cloud):
        catalog = load_databricks_catalog(cloud)
        sa = catalog["agent_bricks"]["supervisor_agent"]
        assert sa["per_dbu_promo"] == 0.070


class TestAgentEvaluation:
    """Agent Evaluation (MLflow): tokens + synthetic questions."""

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_token_rates(self, cloud):
        catalog = load_databricks_catalog(cloud)
        ae = catalog["agent_evaluation"]
        assert ae["input_per_m_tokens_usd"] == 0.15
        assert ae["output_per_m_tokens_usd"] == 0.60
        assert ae["synthetic_data"]["per_question_usd"] == 0.35


class TestFoundationModelTraining:
    """Foundation Model Training: fine-tuning + forecasting, todos $0.65/DBU."""

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_training_rates(self, cloud):
        catalog = load_databricks_catalog(cloud)
        mt = catalog["model_training"]
        assert mt["fine_tuning_per_dbu_usd"] == 0.65
        assert mt["forecasting_per_dbu_usd"] == 0.65

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_llama_estimates_present(self, cloud):
        catalog = load_databricks_catalog(cloud)
        est = catalog["model_training"]["fine_tuning_dbu_estimates"]
        # Llama 3.3 70B: 225 DBU pra 10M words, 11000 DBU pra 500M words
        assert est["llama_3_3_70b"]["dbu_10m_words"] == 225
        assert est["llama_3_3_70b"]["dbu_500m_words"] == 11000


class TestAiRuntime:
    """AI Runtime: A10 + H100 GPUs on-demand. Disponível só AWS + Azure."""

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_gpu_rates(self, cloud):
        catalog = load_databricks_catalog(cloud)
        ait = catalog["ai_runtime"]
        assert ait["a10_on_demand_per_dbu_usd"] == 2.50
        assert ait["h100_on_demand_per_dbu_usd"] == 7.00

    @pytest.mark.parametrize("cloud,available", [("azure", True), ("aws", True), ("gcp", False)])
    def test_availability_matches_official(self, cloud, available):
        catalog = load_databricks_catalog(cloud)
        ai_rt = catalog["ai_runtime"]
        is_available = cloud in ai_rt.get("available_clouds", [])
        assert is_available == available, (
            f"{cloud} AI Runtime availability expected {available}, got {is_available}"
        )
