"""Testes do AI/ML cost engine (data_agents/cost_engine/databricks_ai_ml.py).

PR 5 (2026-05-28): scenarios específicos pra LLM (Foundation + Proprietary),
Vector Search, Lakebase, Agent Bricks.
"""

import pytest

from data_agents.cost_engine import (
    AgentBricksScenario,
    LakebaseScenario,
    LLMScenario,
    VectorSearchScenario,
    calculate_agent_bricks_cost,
    calculate_lakebase_cost,
    calculate_llm_cost,
    calculate_vector_search_cost,
    load_databricks_catalog,
)
from data_agents.cost_engine.databricks_ai_ml import _is_promo_active


# ── _is_promo_active helper ──────────────────────────────────────────────────


class TestIsPromoActive:
    def test_none_returns_false(self):
        assert _is_promo_active(None) is False

    def test_empty_string_returns_false(self):
        assert _is_promo_active("") is False

    def test_invalid_format_returns_false(self):
        assert _is_promo_active("not-a-date") is False

    def test_future_date_active(self):
        from datetime import date

        # promo termina amanhã
        from datetime import timedelta

        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        assert _is_promo_active(tomorrow) is True

    def test_past_date_inactive(self):
        assert _is_promo_active("2020-01-01") is False

    def test_with_today_override(self):
        # promo termina 2026-12-31; usando today=2026-06-01 → ativa
        assert _is_promo_active("2026-12-31", today=__import__("datetime").date(2026, 6, 1)) is True
        # usando today=2027-01-01 → expirada
        assert (
            _is_promo_active("2026-12-31", today=__import__("datetime").date(2027, 1, 1)) is False
        )


# ── LLMScenario: Foundation Model Serving (open) ────────────────────────────


class TestLLMFoundationPayPerToken:
    """Foundation Model Serving Pay-Per-Token: $0.50 input / $1.50 output per M tokens."""

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_simple_pay_per_token(self, cloud):
        cat = load_databricks_catalog(cloud)
        scenario = LLMScenario(
            cloud=cloud,
            mode="pay_per_token",
            vendor="foundation_open",
            m_input_tokens=10.0,
            m_output_tokens=5.0,
        )
        result = calculate_llm_cost(scenario, cat)
        # 10 × 0.50 + 5 × 1.50 = 5 + 7.5 = 12.5
        assert result["totals"]["monthly"] == pytest.approx(12.50, abs=0.01)

    def test_breakdown_separates_input_output(self):
        cat = load_databricks_catalog("aws")
        scenario = LLMScenario(
            cloud="aws", mode="pay_per_token", m_input_tokens=10.0, m_output_tokens=5.0
        )
        result = calculate_llm_cost(scenario, cat)
        assert result["breakdown"]["input_cost_usd"] == pytest.approx(5.00, abs=0.01)
        assert result["breakdown"]["output_cost_usd"] == pytest.approx(7.50, abs=0.01)


class TestLLMFoundationProvisionedThroughput:
    """Provisioned Throughput: $6.00/hour/PT unit."""

    def test_pt_calculates(self):
        cat = load_databricks_catalog("aws")
        scenario = LLMScenario(
            cloud="aws", mode="provisioned_throughput", pt_units=2, pt_hours=10.0
        )
        result = calculate_llm_cost(scenario, cat)
        # 2 × 10 × 6.00 = 120
        assert result["totals"]["monthly"] == pytest.approx(120.00, abs=0.01)


class TestLLMFoundationBatchInference:
    """Batch Inference: $6.00/hour/throughput band."""

    def test_batch_calculates(self):
        cat = load_databricks_catalog("aws")
        scenario = LLMScenario(
            cloud="aws", mode="batch_inference", batch_throughput_bands=3, batch_hours=4.0
        )
        result = calculate_llm_cost(scenario, cat)
        # 3 × 4 × 6.00 = 72
        assert result["totals"]["monthly"] == pytest.approx(72.00, abs=0.01)


# ── LLMScenario: Proprietary Foundation Model Serving ───────────────────────


class TestLLMProprietaryOpenAI:
    """OpenAI GPT 5.x family. Base = $0.07/DBU. Per-model DBU rates."""

    def test_gpt_5_5_pay_per_token(self):
        cat = load_databricks_catalog("aws")
        scenario = LLMScenario(
            cloud="aws",
            mode="pay_per_token",
            vendor="openai",
            model="gpt_5_5",
            m_input_tokens=1.0,
            m_output_tokens=0.1,
        )
        result = calculate_llm_cost(scenario, cat)
        # (71.429 × 1.0 + 428.571 × 0.1) DBU × $0.07/DBU = (71.429 + 42.857) × 0.07 = 8.000
        assert result["totals"]["monthly"] == pytest.approx(8.00, abs=0.01)

    def test_in_geo_uplift_applied(self):
        cat = load_databricks_catalog("aws")
        baseline = LLMScenario(
            cloud="aws",
            mode="pay_per_token",
            vendor="openai",
            model="gpt_5_5",
            m_input_tokens=1.0,
            in_geo=False,
        )
        with_uplift = LLMScenario(
            cloud="aws",
            mode="pay_per_token",
            vendor="openai",
            model="gpt_5_5",
            m_input_tokens=1.0,
            in_geo=True,
        )
        r1 = calculate_llm_cost(baseline, cat)
        r2 = calculate_llm_cost(with_uplift, cat)
        # in_geo aplica ~10% uplift
        assert r2["totals"]["monthly"] == pytest.approx(r1["totals"]["monthly"] * 1.10, abs=0.01)

    def test_long_context_doubles(self):
        cat = load_databricks_catalog("aws")
        baseline = LLMScenario(
            cloud="aws", mode="pay_per_token", vendor="openai", model="gpt_5", m_input_tokens=1.0
        )
        long_ctx = LLMScenario(
            cloud="aws",
            mode="pay_per_token",
            vendor="openai",
            model="gpt_5",
            m_input_tokens=1.0,
            long_context=True,
        )
        r1 = calculate_llm_cost(baseline, cat)
        r2 = calculate_llm_cost(long_ctx, cat)
        # long_context: ~2x uplift
        assert r2["totals"]["monthly"] == pytest.approx(r1["totals"]["monthly"] * 2.0, abs=0.01)

    def test_batch_inference_via_openai(self):
        cat = load_databricks_catalog("aws")
        scenario = LLMScenario(
            cloud="aws",
            mode="batch_inference",
            vendor="openai",
            model="gpt_5_5",
            batch_hours=2.0,
        )
        result = calculate_llm_cost(scenario, cat)
        # gpt_5_5 batch = 214.286 DBU/h × 2h × $0.07 = 30.00
        assert result["totals"]["monthly"] == pytest.approx(30.00, abs=0.01)


class TestLLMProprietaryAnthropic:
    """PR 6 (2026-05-28): Anthropic capturado via Chrome MCP. 6 modelos.
    Rates Global Short context. Base $0.07/DBU.
    """

    def test_claude_opus_4_5_pay_per_token(self):
        cat = load_databricks_catalog("aws")
        scenario = LLMScenario(
            cloud="aws",
            mode="pay_per_token",
            vendor="anthropic",
            model="claude_opus_4_5_to_4_7",
            m_input_tokens=1.0,
            m_output_tokens=0.1,
        )
        result = calculate_llm_cost(scenario, cat)
        # (71.429 × 1.0 + 357.143 × 0.1) DBU × $0.07/DBU = (71.429 + 35.714) × 0.07 = 7.50
        assert result["totals"]["monthly"] == pytest.approx(7.50, abs=0.01)

    def test_claude_haiku_4_5_cheap(self):
        """Haiku é o mais barato — Claude Haiku 4.5 input = 14.286 DBU/M."""
        cat = load_databricks_catalog("aws")
        scenario = LLMScenario(
            cloud="aws",
            mode="pay_per_token",
            vendor="anthropic",
            model="claude_haiku_4_5",
            m_input_tokens=1.0,
        )
        result = calculate_llm_cost(scenario, cat)
        # 14.286 × 1.0 × 0.07 = 1.00
        assert result["totals"]["monthly"] == pytest.approx(1.00, abs=0.01)

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_anthropic_six_models_loaded(self, cloud):
        cat = load_databricks_catalog(cloud)
        models = cat["proprietary_foundation_model_serving"]["vendors"]["anthropic"]["models"]
        assert len(models) == 6
        # Modelos esperados
        expected = {
            "claude_opus_4_8",
            "claude_opus_4_5_to_4_7",
            "claude_opus_4_to_4_1",
            "claude_sonnet_4_5_to_4_6",
            "claude_sonnet_4",
            "claude_haiku_4_5",
        }
        assert set(models.keys()) == expected

    def test_claude_opus_4_8_batch_coming_soon(self):
        """Claude Opus 4.8 batch_dbu_per_h é null (Coming soon)."""
        cat = load_databricks_catalog("aws")
        m = cat["proprietary_foundation_model_serving"]["vendors"]["anthropic"]["models"]
        assert m["claude_opus_4_8"]["batch_dbu_per_h"] is None


class TestLLMProprietaryGemini:
    """PR 6 (2026-05-28): Gemini capturado via Chrome MCP. 7 modelos.
    Gemini tem PROMO 20% OFF até 2026-06-30 — preços no YAML são LIST.
    """

    def test_gemini_3_5_flash_pay_per_token(self):
        cat = load_databricks_catalog("aws")
        scenario = LLMScenario(
            cloud="aws",
            mode="pay_per_token",
            vendor="gemini",
            model="gemini_3_5_flash",
            m_input_tokens=10.0,
            m_output_tokens=5.0,
        )
        result = calculate_llm_cost(scenario, cat)
        # (26.786 × 10 + 160.714 × 5) × 0.07 = (267.86 + 803.57) × 0.07 = 75.00
        assert result["totals"]["monthly"] == pytest.approx(75.00, abs=0.01)

    def test_gemini_2_5_flash_lite_cheapest(self):
        """Flash Lite tem o menor DBU rate da série Gemini."""
        cat = load_databricks_catalog("aws")
        scenario = LLMScenario(
            cloud="aws",
            mode="pay_per_token",
            vendor="gemini",
            model="gemini_2_5_flash_lite",
            m_input_tokens=1.0,
        )
        result = calculate_llm_cost(scenario, cat)
        # 1.786 × 1.0 × 0.07 = 0.125
        assert result["totals"]["monthly"] == pytest.approx(0.125, abs=0.001)

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_gemini_seven_models_loaded(self, cloud):
        cat = load_databricks_catalog(cloud)
        models = cat["proprietary_foundation_model_serving"]["vendors"]["gemini"]["models"]
        assert len(models) == 7

    @pytest.mark.parametrize("cloud", ["azure", "aws", "gcp"])
    def test_gemini_has_20pct_promo(self, cloud):
        """Gemini tem promo 20% off (diferente de Anthropic e OpenAI)."""
        cat = load_databricks_catalog(cloud)
        gem = cat["proprietary_foundation_model_serving"]["vendors"]["gemini"]
        assert gem["promo_until"] == "2026-06-30"
        assert gem["promo_discount_pct"] == 20

    def test_gemini_2_5_flash_lite_no_batch(self):
        """Gemini 2.5 Flash Lite não tem batch (null)."""
        cat = load_databricks_catalog("aws")
        m = cat["proprietary_foundation_model_serving"]["vendors"]["gemini"]["models"]
        assert m["gemini_2_5_flash_lite"]["batch_dbu_per_h"] is None


class TestLLMProprietaryNoLongerStubs:
    """PR 6 (2026-05-28): regressão — Anthropic + Gemini agora têm modelos populados.
    Antes (PR 5) levantavam warning 'stub'; agora calculam custo real.
    """

    @pytest.mark.parametrize("vendor", ["anthropic", "gemini"])
    def test_no_stub_warning_when_model_valid(self, vendor):
        cat = load_databricks_catalog("aws")
        model = "claude_haiku_4_5" if vendor == "anthropic" else "gemini_2_5_flash"
        scenario = LLMScenario(
            cloud="aws",
            mode="pay_per_token",
            vendor=vendor,
            model=model,
            m_input_tokens=1.0,
        )
        result = calculate_llm_cost(scenario, cat)
        # Não deve haver warning de stub (modelos agora populados)
        assert not any("stub" in w.lower() for w in result["warnings"])
        # E o custo deve ser > 0 (PR 5 retornava 0)
        assert result["totals"]["monthly"] > 0


# ── VectorSearchScenario ────────────────────────────────────────────────────


class TestVectorSearch:
    def test_standard_tier_with_free_storage(self):
        """Standard 1 unit × 720h + 50 GB; 30 GB free → 20 GB billable."""
        cat = load_databricks_catalog("aws")
        scenario = VectorSearchScenario(
            cloud="aws", tier="standard", num_units=1, hours_per_month=720, storage_gb=50.0
        )
        result = calculate_vector_search_cost(scenario, cat)
        # Compute: 1 × 720 × 0.28 = 201.60
        # Storage: (50-30) × 0.230 = 4.60
        # Total: 206.20
        assert result["totals"]["monthly"] == pytest.approx(206.20, abs=0.01)
        assert result["breakdown"]["billable_gb"] == 20.0

    def test_standard_under_free_tier(self):
        """Storage 20 GB ≤ 30 GB free → billable = 0."""
        cat = load_databricks_catalog("aws")
        scenario = VectorSearchScenario(
            cloud="aws", tier="standard", num_units=1, hours_per_month=720, storage_gb=20.0
        )
        result = calculate_vector_search_cost(scenario, cat)
        assert result["breakdown"]["billable_gb"] == 0.0
        assert result["breakdown"]["storage_usd"] == 0.0

    def test_storage_optimized_no_free_tier(self):
        """Storage Optimized não tem free tier."""
        cat = load_databricks_catalog("aws")
        scenario = VectorSearchScenario(
            cloud="aws",
            tier="storage_optimized",
            num_units=2,
            hours_per_month=720,
            storage_gb=100.0,
        )
        result = calculate_vector_search_cost(scenario, cat)
        # Compute: 2 × 720 × 1.28 = 1843.20
        # Storage: 100 × 0.046 = 4.60 (sem free tier)
        # Total: 1847.80
        assert result["totals"]["monthly"] == pytest.approx(1847.80, abs=0.01)


# ── LakebaseScenario ────────────────────────────────────────────────────────


class TestLakebase:
    def test_autoscaling_with_promo_active(self):
        """Promo $0.092/CU·h ativa até 2027-01-31."""
        cat = load_databricks_catalog("aws")
        scenario = LakebaseScenario(
            cloud="aws",
            mode="autoscaling",
            cu_hours=100.0,
            storage_gb_months=10.0,
            today_override="2026-06-01",  # antes do promo_until
        )
        result = calculate_lakebase_cost(scenario, cat)
        # Compute: 100 × 0.092 = 9.20
        # Storage: 10 × 0.345 = 3.45
        # Total: 12.65
        assert result["totals"]["monthly"] == pytest.approx(12.65, abs=0.01)
        assert result["inputs_resolved"]["promo_active"] is True

    def test_autoscaling_with_promo_expired(self):
        """Após 2027-01-31, preço list = 2× promo."""
        cat = load_databricks_catalog("aws")
        scenario = LakebaseScenario(
            cloud="aws",
            mode="autoscaling",
            cu_hours=100.0,
            storage_gb_months=10.0,
            today_override="2028-01-01",
        )
        result = calculate_lakebase_cost(scenario, cat)
        # Compute list: 100 × 0.184 = 18.40
        # Storage: 10 × 0.345 = 3.45
        # Total: 21.85
        assert result["totals"]["monthly"] == pytest.approx(21.85, abs=0.01)
        assert result["inputs_resolved"]["promo_active"] is False

    def test_always_on_mode(self):
        cat = load_databricks_catalog("aws")
        scenario = LakebaseScenario(
            cloud="aws",
            mode="always_on",
            cu_hours=720.0,  # 1 mês inteiro always-on
            today_override="2026-06-01",
        )
        result = calculate_lakebase_cost(scenario, cat)
        # Promo: 720 × 0.069 = 49.68
        assert result["totals"]["monthly"] == pytest.approx(49.68, abs=0.01)

    def test_gcp_returns_zero_with_warning(self):
        """Lakebase não disponível em GCP."""
        cat = load_databricks_catalog("gcp")
        scenario = LakebaseScenario(cloud="gcp", mode="autoscaling", cu_hours=100.0)
        result = calculate_lakebase_cost(scenario, cat)
        assert result["totals"]["monthly"] == 0.0
        assert any("não disponível" in w.lower() for w in result["warnings"])


# ── AgentBricksScenario ─────────────────────────────────────────────────────


class TestAgentBricks:
    def test_promo_active(self):
        """Promo 50% off até 2026-06-30."""
        cat = load_databricks_catalog("aws")
        scenario = AgentBricksScenario(
            cloud="aws",
            knowledge_assistant_answers=100,
            supervisor_dbu_hours=5.0,
            today_override="2026-06-01",
        )
        result = calculate_agent_bricks_cost(scenario, cat)
        # KA promo: 100 × 0.150 = 15.00
        # SA promo: 5 × 0.070 = 0.35
        # Total: 15.35
        assert result["totals"]["monthly"] == pytest.approx(15.35, abs=0.01)
        assert result["inputs_resolved"]["promo_active"] is True

    def test_promo_expired(self):
        cat = load_databricks_catalog("aws")
        scenario = AgentBricksScenario(
            cloud="aws",
            knowledge_assistant_answers=100,
            supervisor_dbu_hours=5.0,
            today_override="2027-01-01",
        )
        result = calculate_agent_bricks_cost(scenario, cat)
        # KA list: 100 × 0.300 = 30.00
        # SA list: 5 × 0.140 = 0.70
        # Total: 30.70
        assert result["totals"]["monthly"] == pytest.approx(30.70, abs=0.01)

    def test_sub_agent_passthrough(self):
        """sub_agent_costs_usd é passa-through (somado ao total)."""
        cat = load_databricks_catalog("aws")
        scenario = AgentBricksScenario(
            cloud="aws",
            knowledge_assistant_answers=10,
            sub_agent_costs_usd=50.0,
            today_override="2026-06-01",
        )
        result = calculate_agent_bricks_cost(scenario, cat)
        # KA: 10 × 0.150 = 1.50
        # Sub-agents: 50.0
        # Total: 51.50
        assert result["totals"]["monthly"] == pytest.approx(51.50, abs=0.01)
        assert result["breakdown"]["sub_agents_usd"] == 50.0
