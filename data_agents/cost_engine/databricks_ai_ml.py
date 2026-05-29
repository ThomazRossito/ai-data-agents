"""
AI/ML Cost Scenarios for Databricks — PR 5 (2026-05-28).

Engine para modelar custos de scenarios AI/ML específicos (LLM tokens, Vector Search,
Lakebase, Agent Bricks). Complementa o `databricks.py` (compute/DBU-based).

Cada scenario tem um dataclass + função `calculate_*_cost()` que:
  - É determinística (mesma entrada → mesma saída)
  - Não faz I/O (catalog YAML já passado como dict)
  - Aplica preço promocional automaticamente se hoje < promo_until
  - Retorna breakdown completo (auditable)

Cobertura inicial (PR 5):
  - LLMScenario: Foundation Model + Proprietary FM (OpenAI/Anthropic/Gemini)
    com 3 modos (Pay-Per-Token / Provisioned Throughput / Batch Inference)
  - VectorSearchScenario: Standard 2M / Storage Optimized 64M, compute + storage
  - LakebaseScenario: Autoscaling / Always-On compute + storage. Promo auto.
  - AgentBricksScenario: Knowledge Assistant ($/answer) + Supervisor Agent ($/DBU)

Uso típico:

    from data_agents.cost_engine import (
        load_databricks_catalog,
        LLMScenario,
        calculate_llm_cost,
    )

    catalog = load_databricks_catalog("aws")
    scenario = LLMScenario(
        cloud="aws",
        mode="pay_per_token",
        m_input_tokens=10.0,
        m_output_tokens=5.0,
    )
    result = calculate_llm_cost(scenario, catalog)
    # result["totals"]["monthly"] = ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

# Re-usar CloudName do módulo base
from data_agents.cost_engine.databricks import CloudName


# ─── Helpers ────────────────────────────────────────────────────────────────


def _is_promo_active(promo_until: str | None, today: date | None = None) -> bool:
    """True se hoje < promo_until (formato YYYY-MM-DD); False se expirado ou None."""
    if not promo_until:
        return False
    if today is None:
        today = date.today()
    try:
        promo_date = datetime.strptime(promo_until, "%Y-%m-%d").date()
        return today < promo_date
    except (ValueError, TypeError):
        return False


# ─── LLMScenario ────────────────────────────────────────────────────────────


LlmMode = Literal["pay_per_token", "provisioned_throughput", "batch_inference"]
LlmVendor = Literal[
    "foundation_open",  # Foundation Model Serving (Llama, Qwen, GPT OSS, embeddings)
    "openai",
    "anthropic",
    "gemini",
]


@dataclass
class LLMScenario:
    """Cenário de uso de LLM (Foundation Model ou Proprietary).

    Pay-Per-Token: cobra $/M tokens (input + output).
    Provisioned Throughput: cobra $/hour/PT unit.
    Batch Inference: cobra $/hour/throughput band.

    Para foundation_open + per-model DBU rates, use `model` (ex: "llama_3_3_70b").
    Para vendors proprietários, use `model` (ex: "gpt_5_5", "claude_4_opus").
    """

    cloud: CloudName
    mode: LlmMode
    vendor: LlmVendor = "foundation_open"
    model: str | None = None  # ex: "llama_3_3_70b", "gpt_5_5"

    # Pay-Per-Token inputs
    m_input_tokens: float = 0.0  # millions of input tokens
    m_output_tokens: float = 0.0
    m_cache_write_tokens: float = 0.0  # OpenAI only
    m_cache_read_tokens: float = 0.0  # OpenAI only

    # Provisioned Throughput inputs
    pt_units: int = 0
    pt_hours: float = 0.0
    pt_capacity_type: Literal["entry", "scaling"] = "scaling"

    # Batch Inference inputs
    batch_throughput_bands: int = 0
    batch_hours: float = 0.0

    # Geo / context flags
    in_geo: bool = False  # +~10% uplift over Global Short
    long_context: bool = False  # +~2x uplift (OpenAI long context)

    # Metadata
    scenario_id: str | None = None
    description: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


def calculate_llm_cost(scenario: LLMScenario, catalog: dict[str, Any]) -> dict[str, Any]:
    """Calcula custo mensal de scenario LLM.

    Args:
        scenario: LLMScenario com mode, vendor, model, e inputs do mode escolhido.
        catalog: dict do catalog YAML (load_databricks_catalog).

    Returns:
        Dict com totals + breakdown + inputs_resolved + warnings.

    Raises:
        ValueError: vendor/model/mode inválido.
        KeyError: modelo não está no catalog.
    """
    warnings: list[str] = []

    if scenario.vendor == "foundation_open":
        block = catalog.get("foundation_model_serving")
        if block is None:
            raise KeyError("foundation_model_serving block ausente no catalog. PR 3 adicionou.")
        result = _calc_foundation_open(scenario, block, warnings)
    else:
        block = catalog.get("proprietary_foundation_model_serving")
        if block is None:
            raise KeyError(
                "proprietary_foundation_model_serving block ausente no catalog. PR 3 adicionou."
            )
        result = _calc_proprietary(scenario, block, warnings)

    monthly = result["cost_usd"]
    return {
        "scenario_id": scenario.scenario_id,
        "scenario_description": scenario.description,
        "vendor": scenario.vendor,
        "model": scenario.model,
        "mode": scenario.mode,
        "cloud": scenario.cloud,
        "totals": {
            "monthly": round(monthly, 4),
            "annual": round(monthly * 12, 2),
        },
        "breakdown": result.get("breakdown", {}),
        "inputs_resolved": result.get("inputs_resolved", {}),
        "warnings": warnings,
    }


def _calc_foundation_open(
    scenario: LLMScenario, block: dict[str, Any], warnings: list[str]
) -> dict[str, Any]:
    """Foundation Model Serving (open source LLMs)."""
    if scenario.mode == "pay_per_token":
        ppt = block["pay_per_token"]
        input_cost = scenario.m_input_tokens * ppt["input_per_m_tokens_usd"]
        output_cost = scenario.m_output_tokens * ppt["output_per_m_tokens_usd"]
        return {
            "cost_usd": input_cost + output_cost,
            "breakdown": {
                "input_cost_usd": round(input_cost, 4),
                "output_cost_usd": round(output_cost, 4),
            },
            "inputs_resolved": {
                "input_rate_per_m": ppt["input_per_m_tokens_usd"],
                "output_rate_per_m": ppt["output_per_m_tokens_usd"],
            },
        }
    if scenario.mode == "provisioned_throughput":
        pt = block["provisioned_throughput"]
        cost = scenario.pt_units * scenario.pt_hours * pt["per_hour_per_pt_unit_usd"]
        return {
            "cost_usd": cost,
            "breakdown": {
                "pt_units": scenario.pt_units,
                "pt_hours": scenario.pt_hours,
                "per_hour_per_unit_usd": pt["per_hour_per_pt_unit_usd"],
            },
            "inputs_resolved": {"rate_per_hour_per_unit": pt["per_hour_per_pt_unit_usd"]},
        }
    if scenario.mode == "batch_inference":
        bi = block["batch_inference"]
        cost = (
            scenario.batch_throughput_bands
            * scenario.batch_hours
            * bi["per_hour_per_throughput_band_usd"]
        )
        return {
            "cost_usd": cost,
            "breakdown": {
                "throughput_bands": scenario.batch_throughput_bands,
                "hours": scenario.batch_hours,
                "per_hour_per_band_usd": bi["per_hour_per_throughput_band_usd"],
            },
            "inputs_resolved": {"rate_per_hour_per_band": bi["per_hour_per_throughput_band_usd"]},
        }
    raise ValueError(f"Mode {scenario.mode!r} desconhecido para foundation_open")


def _calc_proprietary(
    scenario: LLMScenario, block: dict[str, Any], warnings: list[str]
) -> dict[str, Any]:
    """Proprietary Foundation Model Serving (OpenAI/Anthropic/Gemini)."""
    vendors = block.get("vendors", {})
    vendor_data = vendors.get(scenario.vendor)
    if vendor_data is None:
        raise KeyError(f"Vendor {scenario.vendor!r} não está no catalog")

    models = vendor_data.get("models", {})
    if not models or scenario.model not in models:
        # Anthropic/Gemini ainda podem ser stubs (sem models populados)
        if "_todo" in vendor_data:
            warnings.append(
                f"Vendor {scenario.vendor!r} stub (não capturado ainda). "
                "Captura de DBU tables em PR 6. Cost retornado é zero."
            )
            return {
                "cost_usd": 0.0,
                "breakdown": {},
                "inputs_resolved": {"_vendor_stub": True},
            }
        raise KeyError(f"Model {scenario.model!r} não está em proprietary[{scenario.vendor}]")

    model_data = models[scenario.model]
    base_dbu_rate = block["base_per_dbu_pay_per_token"]
    if scenario.mode == "batch_inference":
        base_dbu_rate = block["base_per_dbu_batch"]

    # Uplift in-geo (~10%) and long context (~2x)
    uplift = 1.0
    if scenario.in_geo:
        uplift *= 1.10
    if scenario.long_context:
        uplift *= 2.0

    if scenario.mode == "pay_per_token":
        input_dbu = (model_data.get("input_dbu_per_m") or 0) * scenario.m_input_tokens
        output_dbu = (model_data.get("output_dbu_per_m") or 0) * scenario.m_output_tokens
        cache_w_dbu = (model_data.get("cache_write_dbu_per_m") or 0) * scenario.m_cache_write_tokens
        cache_r_dbu = (model_data.get("cache_read_dbu_per_m") or 0) * scenario.m_cache_read_tokens
        total_dbu = (input_dbu + output_dbu + cache_w_dbu + cache_r_dbu) * uplift
        cost = total_dbu * base_dbu_rate
        return {
            "cost_usd": cost,
            "breakdown": {
                "input_dbu": round(input_dbu * uplift, 4),
                "output_dbu": round(output_dbu * uplift, 4),
                "cache_write_dbu": round(cache_w_dbu * uplift, 4),
                "cache_read_dbu": round(cache_r_dbu * uplift, 4),
                "total_dbu": round(total_dbu, 4),
            },
            "inputs_resolved": {
                "base_per_dbu_usd": base_dbu_rate,
                "uplift_applied": uplift,
                "model_rates": model_data,
            },
        }
    if scenario.mode == "batch_inference":
        batch_dbu_per_h = model_data.get("batch_dbu_per_h")
        if batch_dbu_per_h is None:
            raise ValueError(
                f"Model {scenario.model!r} não suporta batch inference (batch_dbu_per_h=null)"
            )
        total_dbu = batch_dbu_per_h * scenario.batch_hours * uplift
        cost = total_dbu * base_dbu_rate
        return {
            "cost_usd": cost,
            "breakdown": {
                "batch_dbu_per_h": batch_dbu_per_h,
                "hours": scenario.batch_hours,
                "total_dbu": round(total_dbu, 4),
            },
            "inputs_resolved": {"base_per_dbu_usd": base_dbu_rate, "uplift_applied": uplift},
        }
    raise ValueError(
        f"Mode {scenario.mode!r} não suportado para proprietary vendors (use pay_per_token ou batch_inference)"
    )


# ─── VectorSearchScenario ───────────────────────────────────────────────────


VsTier = Literal["standard", "storage_optimized"]


@dataclass
class VectorSearchScenario:
    """Vector Search: Standard 2M / Storage Optimized 64M vectors per unit.

    Compute cobrado por hour × unit. Storage cobrado por GB·month (Standard tem
    30 GB free; Storage Optimized não tem free tier).
    """

    cloud: CloudName
    tier: VsTier
    num_units: int = 1
    hours_per_month: float = 720.0  # default 30 dias × 24h
    storage_gb: float = 0.0
    is_ap_region: bool = False  # +~25% uplift effective $/DBU

    scenario_id: str | None = None
    description: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


def calculate_vector_search_cost(
    scenario: VectorSearchScenario, catalog: dict[str, Any]
) -> dict[str, Any]:
    """Calcula custo Vector Search compute + storage."""
    block = catalog.get("vector_search_v2")
    if block is None:
        raise KeyError("vector_search_v2 block ausente. PR 3 adicionou.")

    tier_data = block["tiers"].get(scenario.tier)
    if tier_data is None:
        raise ValueError(f"Tier {scenario.tier!r} inválido (use 'standard' ou 'storage_optimized')")

    # Compute: $/h × units × hours/month
    compute_per_h = tier_data["compute_per_hour_usd"]
    compute_cost = scenario.num_units * scenario.hours_per_month * compute_per_h

    # Storage: GB × $/GB·mo, descontando free tier
    storage_per_gb_mo = tier_data["storage_per_gb_month_usd"]
    free_gb = tier_data.get("storage_free_gb", 0)
    billable_gb = max(0.0, scenario.storage_gb - free_gb)
    storage_cost = billable_gb * storage_per_gb_mo

    total = compute_cost + storage_cost

    return {
        "scenario_id": scenario.scenario_id,
        "tier": scenario.tier,
        "cloud": scenario.cloud,
        "totals": {
            "monthly": round(total, 2),
            "annual": round(total * 12, 2),
        },
        "breakdown": {
            "compute_usd": round(compute_cost, 2),
            "storage_usd": round(storage_cost, 2),
            "billable_gb": round(billable_gb, 2),
            "free_gb_excluded": free_gb,
        },
        "inputs_resolved": {
            "compute_per_hour_usd": compute_per_h,
            "storage_per_gb_month_usd": storage_per_gb_mo,
            "dbu_per_hour": tier_data.get("dbu_per_hour"),
            "vector_capacity_per_unit": tier_data.get("vector_capacity_per_unit"),
        },
        "warnings": [],
    }


# ─── LakebaseScenario ───────────────────────────────────────────────────────


LakebaseMode = Literal["autoscaling", "always_on"]


@dataclass
class LakebaseScenario:
    """Lakebase Postgres managed (Disponível só AWS + Azure)."""

    cloud: CloudName
    mode: LakebaseMode
    cu_hours: float = 0.0  # Capacity Unit Hours
    storage_gb_months: float = 0.0  # GB armazenado × meses
    use_promo_if_active: bool = True
    today_override: str | None = None  # YYYY-MM-DD pra testes

    scenario_id: str | None = None
    description: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


def calculate_lakebase_cost(scenario: LakebaseScenario, catalog: dict[str, Any]) -> dict[str, Any]:
    """Calcula custo Lakebase compute + storage. Aplica promo se ativa hoje."""
    block = catalog.get("lakebase")
    warnings: list[str] = []

    if block is None:
        # GCP intencionalmente não tem Lakebase
        warnings.append(f"Lakebase não disponível em {scenario.cloud}. Cost = 0.")
        return {
            "scenario_id": scenario.scenario_id,
            "cloud": scenario.cloud,
            "totals": {"monthly": 0.0, "annual": 0.0},
            "breakdown": {},
            "inputs_resolved": {"_lakebase_unavailable": True},
            "warnings": warnings,
        }

    available = block.get("available_clouds", [])
    if scenario.cloud not in available:
        warnings.append(
            f"Cloud {scenario.cloud!r} não suporta Lakebase oficialmente "
            f"(disponível em {available})"
        )

    # Determinar se promo ativa
    promo_until = block.get("promo_until")
    today_date = None
    if scenario.today_override:
        today_date = datetime.strptime(scenario.today_override, "%Y-%m-%d").date()
    promo_active = scenario.use_promo_if_active and _is_promo_active(promo_until, today_date)

    # Compute rate dependendo do mode + promo
    if scenario.mode == "autoscaling":
        rate_key = "autoscaling_per_cu_h_promo" if promo_active else "autoscaling_per_cu_h_list"
    else:  # always_on
        rate_key = "always_on_min_per_cu_h_promo" if promo_active else "always_on_min_per_cu_h_list"
    compute_rate = block[rate_key]
    compute_cost = scenario.cu_hours * compute_rate

    # Storage (sem promo)
    storage_rate = block["storage_per_gb_month"]
    storage_cost = scenario.storage_gb_months * storage_rate

    total = compute_cost + storage_cost

    if promo_active:
        warnings.append(f"Promo 50% off ativa (até {promo_until}). Preço list = 2× o cobrado.")

    return {
        "scenario_id": scenario.scenario_id,
        "cloud": scenario.cloud,
        "mode": scenario.mode,
        "totals": {
            "monthly": round(total, 2),
            "annual": round(total * 12, 2),
        },
        "breakdown": {
            "compute_usd": round(compute_cost, 2),
            "storage_usd": round(storage_cost, 2),
        },
        "inputs_resolved": {
            "compute_rate_per_cu_h": compute_rate,
            "storage_rate_per_gb_month": storage_rate,
            "promo_active": promo_active,
            "promo_until": promo_until,
        },
        "warnings": warnings,
    }


# ─── AgentBricksScenario ────────────────────────────────────────────────────


@dataclass
class AgentBricksScenario:
    """Agent Bricks: Knowledge Assistant ($/answer) + Supervisor Agent ($/DBU).

    sub_agent_costs_usd: passa-through de cobranças de sub-agents (cada um ao
    seu preço nativo). User calcula previamente e passa o total.
    """

    cloud: CloudName
    knowledge_assistant_answers: int = 0
    supervisor_dbu_hours: float = 0.0
    sub_agent_costs_usd: float = 0.0
    use_promo_if_active: bool = True
    today_override: str | None = None

    scenario_id: str | None = None
    description: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


def calculate_agent_bricks_cost(
    scenario: AgentBricksScenario, catalog: dict[str, Any]
) -> dict[str, Any]:
    """Calcula custo Agent Bricks. Aplica promo se ativa hoje."""
    block = catalog.get("agent_bricks")
    if block is None:
        raise KeyError("agent_bricks block ausente. PR 3 adicionou.")

    warnings: list[str] = []
    promo_until = block.get("promo_until")
    today_date = None
    if scenario.today_override:
        today_date = datetime.strptime(scenario.today_override, "%Y-%m-%d").date()
    promo_active = scenario.use_promo_if_active and _is_promo_active(promo_until, today_date)

    ka = block["knowledge_assistant"]
    sa = block["supervisor_agent"]

    ka_rate = ka["per_answer_promo_usd"] if promo_active else ka["per_answer_list_usd"]
    sa_rate = sa["per_dbu_promo"] if promo_active else sa["per_dbu_list"]

    ka_cost = scenario.knowledge_assistant_answers * ka_rate
    sa_cost = scenario.supervisor_dbu_hours * sa_rate
    sub_agent = scenario.sub_agent_costs_usd

    total = ka_cost + sa_cost + sub_agent

    if promo_active:
        warnings.append(f"Promo 50% off ativa (até {promo_until}). Preço list = 2× o cobrado.")

    return {
        "scenario_id": scenario.scenario_id,
        "cloud": scenario.cloud,
        "totals": {
            "monthly": round(total, 2),
            "annual": round(total * 12, 2),
        },
        "breakdown": {
            "knowledge_assistant_usd": round(ka_cost, 2),
            "supervisor_agent_usd": round(sa_cost, 2),
            "sub_agents_usd": round(sub_agent, 2),
        },
        "inputs_resolved": {
            "ka_rate_per_answer": ka_rate,
            "sa_rate_per_dbu": sa_rate,
            "promo_active": promo_active,
            "promo_until": promo_until,
        },
        "warnings": warnings,
    }
