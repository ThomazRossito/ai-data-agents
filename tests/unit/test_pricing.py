"""
Testes para utils/pricing.py — recálculo de custo dos modelos Moonshot Kimi.

Cobre a reformulação que:
  - resolve a tabela de preço pelo MODELO REAL (K2.6 / K2.7-code / K3), com
    casamento por substring e fallback para K2.6;
  - extrai tokens de model_usage (camelCase) OU usage (snake_case) OU attrs,
    sem deixar um model_usage presente-mas-zero bloquear o fallback;
  - converte o custo do SDK (preço Sonnet) pelo ratio de input quando não há
    tokens no ResultMessage;
  - calcula o inflation_factor (quanto o SDK superestimou).
"""

from __future__ import annotations

import types

from data_agents.utils.pricing import (
    PRICING_KIMI_K2_6,
    PRICING_KIMI_K2_7_CODE,
    PRICING_KIMI_K3,
    CostBreakdown,
    _first_int,
    _real_model,
    _resolve_pricing,
    _safe_float_attr,
    _safe_int_attr,
    _safe_int_dict,
    _safe_str_attr,
    _tokens_from_message,
    compute_cost_from_tokens,
    real_cost_from_message,
    recompute_cost_from_message,
)


def _msg(**kw):
    """Simula um ResultMessage do SDK (atributos arbitrários)."""
    return types.SimpleNamespace(**kw)


# ─── _resolve_pricing ────────────────────────────────────────────────────────


def test_resolve_pricing_k26():
    assert _resolve_pricing("kimi-k2.6") is PRICING_KIMI_K2_6


def test_resolve_pricing_k3_with_date_suffix():
    # casamento por substring tolera sufixo de data
    assert _resolve_pricing("kimi-k3-20260716") is PRICING_KIMI_K3


def test_resolve_pricing_k27_code():
    assert _resolve_pricing("kimi-k2.7-code") is PRICING_KIMI_K2_7_CODE


def test_resolve_pricing_k25_maps_to_k26_table():
    assert _resolve_pricing("kimi-k2.5") is PRICING_KIMI_K2_6


def test_resolve_pricing_unknown_falls_back_k26():
    assert _resolve_pricing("gpt-9-turbo") is PRICING_KIMI_K2_6


def test_resolve_pricing_none_falls_back_k26():
    assert _resolve_pricing(None) is PRICING_KIMI_K2_6


# ─── compute_cost_from_tokens ────────────────────────────────────────────────


def test_compute_cost_k3_explicit_pricing():
    # 1M input @ $3 + 1M output @ $15 = $18
    c = compute_cost_from_tokens(1_000_000, 1_000_000, pricing=PRICING_KIMI_K3)
    assert c == round(3.0 + 15.0, 6)


def test_compute_cost_resolves_by_model():
    c = compute_cost_from_tokens(1_000_000, 0, model="kimi-k2.6")
    assert c == round(0.55, 6)


def test_compute_cost_with_cache_read():
    c = compute_cost_from_tokens(0, 0, cache_read_tokens=1_000_000, pricing=PRICING_KIMI_K2_6)
    assert c == round(0.055, 6)


def test_compute_cost_zero():
    assert compute_cost_from_tokens(0, 0) == 0.0


# ─── _first_int ──────────────────────────────────────────────────────────────


def test_first_int_snake_case():
    assert _first_int({"input_tokens": 5}, ("input_tokens", "inputTokens")) == 5


def test_first_int_camel_case():
    assert _first_int({"inputTokens": 7}, ("input_tokens", "inputTokens")) == 7


def test_first_int_missing_returns_zero():
    assert _first_int({}, ("a", "b")) == 0


def test_first_int_invalid_returns_zero():
    assert _first_int({"a": "not-an-int"}, ("a",)) == 0


# ─── _tokens_from_message ────────────────────────────────────────────────────


def test_tokens_from_model_usage_camel():
    msg = _msg(
        model_usage={"m": {"inputTokens": 100, "outputTokens": 50, "cacheReadInputTokens": 10}}
    )
    assert _tokens_from_message(msg) == (100, 50, 10)


def test_tokens_sums_multiple_model_usage_entries():
    msg = _msg(
        model_usage={
            "sup": {"inputTokens": 100, "outputTokens": 50},
            "sub": {"inputTokens": 20, "outputTokens": 5},
        }
    )
    assert _tokens_from_message(msg) == (120, 55, 0)


def test_tokens_from_usage_snake_when_model_usage_absent():
    msg = _msg(usage={"input_tokens": 30, "output_tokens": 20, "cache_read_input_tokens": 5})
    assert _tokens_from_message(msg) == (30, 20, 5)


def test_tokens_model_usage_zero_falls_back_to_usage():
    # regressão: model_usage presente mas zerado NÃO pode bloquear o fallback
    msg = _msg(
        model_usage={"m": {"inputTokens": 0, "outputTokens": 0}},
        usage={"input_tokens": 42, "output_tokens": 9},
    )
    assert _tokens_from_message(msg) == (42, 9, 0)


def test_tokens_from_attrs_fallback():
    msg = _msg(input_tokens=11, output_tokens=22, cache_read_input_tokens=3)
    assert _tokens_from_message(msg) == (11, 22, 3)


# ─── _real_model ─────────────────────────────────────────────────────────────


def test_real_model_explicit_wins():
    assert _real_model(_msg(), model="kimi-k3") == "kimi-k3"


def test_real_model_non_claude_attr():
    assert _real_model(_msg(model="kimi-k2.6")) == "kimi-k2.6"


def test_real_model_claude_label_uses_settings(monkeypatch):
    from data_agents.config.settings import settings

    monkeypatch.setattr(settings, "default_model", "kimi-k3-test")
    # rótulo Anthropic do SDK deve ser ignorado → usa settings.default_model
    assert _real_model(_msg(model="claude-sonnet-4-6")) == "kimi-k3-test"


def test_real_model_no_attr_uses_settings(monkeypatch):
    from data_agents.config.settings import settings

    monkeypatch.setattr(settings, "default_model", "kimi-foo")
    assert _real_model(_msg()) == "kimi-foo"


# ─── recompute_cost_from_message ─────────────────────────────────────────────


def test_recompute_with_tokens_k3():
    msg = _msg(
        model_usage={"m": {"inputTokens": 1_000_000, "outputTokens": 1_000_000}},
        total_cost_usd=None,
    )
    cb = recompute_cost_from_message(msg, model="kimi-k3")
    assert isinstance(cb, CostBreakdown)
    assert cb.input_tokens == 1_000_000
    assert cb.output_tokens == 1_000_000
    assert cb.total_cost_usd == round(3.0 + 15.0, 6)
    assert cb.inflation_factor is None  # sem custo do SDK


def test_recompute_with_tokens_k26_and_inflation():
    # SDK reportou custo (preço Sonnet); custo real vem dos tokens; inflation = sdk/real
    msg = _msg(
        model_usage={"m": {"inputTokens": 1_000_000, "outputTokens": 0}},
        total_cost_usd=3.0,
    )
    cb = recompute_cost_from_message(msg, model="kimi-k2.6")
    assert cb.total_cost_usd == round(0.55, 6)
    assert cb.sdk_reported_cost_usd == 3.0
    assert cb.inflation_factor == round(3.0 / 0.55, 2)


def test_recompute_no_tokens_converts_sdk_cost():
    # sem tokens, mas com custo do SDK → conversão pelo ratio de input (K2.6: 0.55/3.0)
    msg = _msg(total_cost_usd=3.0)
    cb = recompute_cost_from_message(msg, model="kimi-k2.6")
    assert cb.input_tokens == 0
    assert cb.total_cost_usd == round(3.0 * (0.55 / 3.0), 6)


def test_recompute_no_tokens_no_cost_is_zero():
    msg = _msg(total_cost_usd=None)
    cb = recompute_cost_from_message(msg, model="kimi-k2.6")
    assert cb.total_cost_usd == 0.0
    assert cb.inflation_factor is None


def test_real_cost_from_message_returns_float():
    msg = _msg(
        model_usage={"m": {"inputTokens": 1_000_000, "outputTokens": 0}},
        total_cost_usd=None,
    )
    v = real_cost_from_message(msg, model="kimi-k2.6")
    assert isinstance(v, float)
    assert v == round(0.55, 6)


# ─── CostBreakdown ───────────────────────────────────────────────────────────


def test_cost_breakdown_str():
    cb = CostBreakdown(1000, 500, 100, 0.1, 0.2, 0.01, 0.31, 1.0, 3.2)
    s = str(cb)
    assert "in=1,000" in s
    assert "out=500" in s
    assert "0.31000" in s


# ─── helpers seguros ─────────────────────────────────────────────────────────


def test_safe_int_attr():
    assert _safe_int_attr(_msg(x=5), "x", 0) == 5
    assert _safe_int_attr(_msg(), "x", 7) == 7
    assert _safe_int_attr(_msg(x="bad"), "x", 9) == 9


def test_safe_float_attr():
    assert _safe_float_attr(_msg(x=1.5), "x", None) == 1.5
    assert _safe_float_attr(_msg(), "x", None) is None
    assert _safe_float_attr(_msg(x="bad"), "x", 2.0) == 2.0


def test_safe_str_attr():
    assert _safe_str_attr(_msg(x=5), "x", None) == "5"
    assert _safe_str_attr(_msg(), "x", "d") == "d"


def test_safe_int_dict():
    assert _safe_int_dict({"x": 5}, "x", 0) == 5
    assert _safe_int_dict({}, "x", 3) == 3
    assert _safe_int_dict({"x": "bad"}, "x", 4) == 4
