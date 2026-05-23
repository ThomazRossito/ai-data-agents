"""
Pricing — Cálculo de custo correto para Moonshot Kimi K2.6.

O claude-agent-sdk calcula `total_cost_usd` internamente assumindo preços da
Anthropic Sonnet ($3/M input, $15/M output). Como o projeto está apontando
para a Moonshot via endpoint compatível, o valor reportado pelo SDK é
inflado em ~5x. Este módulo recalcula o custo a partir dos tokens reais
usando a tabela de preços oficial da Moonshot.

Tabela de preços — Moonshot Kimi K2.6 (abr/2026):
  - Input regular:    $0.55 / 1M tokens
  - Output:           $2.65 / 1M tokens
  - Cache hit (read): $0.055 / 1M tokens (10% do input regular)

Uso:
    from data_agents.utils.pricing import recompute_cost_from_message

    # Após receber um ResultMessage do claude-agent-sdk:
    real_cost = recompute_cost_from_message(message)

Referências:
  - https://platform.moonshot.ai/docs/pricing
  - Pricing observado em platform.moonshot.ai/console/pay
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("data_agents.pricing")


# ─── Tabela de preços (USD por 1M tokens) ────────────────────────────────────

#: Preços oficiais da Moonshot para a família Kimi K2.6.
#: Atualize aqui se a Moonshot publicar nova tabela.
PRICING_KIMI_K2_6: dict[str, float] = {
    "input_per_mtok": 0.55,
    "output_per_mtok": 2.65,
    "cache_read_per_mtok": 0.055,  # 10% do input regular (estimativa conservadora)
}

#: Modelos suportados por este recálculo. Para outros modelos, devolvemos o
#: cost reportado pelo SDK sem modificação.
SUPPORTED_MODELS: set[str] = {
    "kimi-k2.6",
    "kimi-k2.5",  # mesma faixa de preço aproximada
}


# ─── Estrutura de resultado ──────────────────────────────────────────────────


@dataclass
class CostBreakdown:
    """Detalhamento do cálculo de custo."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_input_usd: float
    cost_output_usd: float
    cost_cache_read_usd: float
    total_cost_usd: float
    sdk_reported_cost_usd: float | None  # o que o SDK disse (Anthropic prices)
    inflation_factor: float | None  # quanto o SDK superestimou

    def __str__(self) -> str:
        return (
            f"in={self.input_tokens:,} out={self.output_tokens:,} "
            f"cache={self.cache_read_tokens:,} → ${self.total_cost_usd:.5f}"
        )


# ─── Funções públicas ────────────────────────────────────────────────────────


def compute_cost_from_tokens(
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    pricing: dict[str, float] | None = None,
) -> float:
    """
    Calcula o custo em USD a partir dos contadores de token.

    Args:
        input_tokens: Tokens de input regulares (sem cache hit).
        output_tokens: Tokens gerados pelo modelo.
        cache_read_tokens: Tokens lidos do cache (preço reduzido).
        pricing: Tabela alternativa de preços. Padrão: PRICING_KIMI_K2_6.

    Returns:
        Custo total em USD.
    """
    p = pricing or PRICING_KIMI_K2_6
    cost = (
        (input_tokens / 1_000_000) * p["input_per_mtok"]
        + (output_tokens / 1_000_000) * p["output_per_mtok"]
        + (cache_read_tokens / 1_000_000) * p["cache_read_per_mtok"]
    )
    return round(cost, 6)


def recompute_cost_from_message(message: Any) -> CostBreakdown:
    """
    Recalcula o custo de um ResultMessage do claude-agent-sdk usando
    os preços reais da Moonshot.

    O ResultMessage do claude-agent-sdk expõe `usage` como **dict**
    (não como objeto) — extraímos os tokens via dict access. Estrutura
    típica observada no SDK 0.1.48:

        usage = {
            'input_tokens': N,
            'output_tokens': N,
            'cache_read_input_tokens': N,
            'cache_creation_input_tokens': N,
            ...
        }

    Args:
        message: ResultMessage do claude-agent-sdk.

    Returns:
        CostBreakdown com o custo recalculado e detalhes.
    """
    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    cache_creation_tokens = 0

    # 1) Caminho principal: dict `usage` no ResultMessage do claude-agent-sdk
    usage = getattr(message, "usage", None)
    if isinstance(usage, dict):
        input_tokens = _safe_int_dict(usage, "input_tokens", 0)
        output_tokens = _safe_int_dict(usage, "output_tokens", 0)
        cache_read_tokens = _safe_int_dict(usage, "cache_read_input_tokens", 0)
        cache_creation_tokens = _safe_int_dict(usage, "cache_creation_input_tokens", 0)

    # 2) Fallback: model_usage (breakdown por modelo, formato {model: {tokens...}})
    if input_tokens == 0 and output_tokens == 0:
        model_usage = getattr(message, "model_usage", None)
        if isinstance(model_usage, dict):
            for _model_name, mu in model_usage.items():
                if isinstance(mu, dict):
                    input_tokens += _safe_int_dict(mu, "input_tokens", 0)
                    output_tokens += _safe_int_dict(mu, "output_tokens", 0)
                    cache_read_tokens += _safe_int_dict(mu, "cache_read_input_tokens", 0)
                    cache_creation_tokens += _safe_int_dict(mu, "cache_creation_input_tokens", 0)

    # 3) Fallback final: atributos diretos (defensivo, caso o SDK mude)
    if input_tokens == 0 and output_tokens == 0:
        input_tokens = _safe_int_attr(message, "input_tokens", 0)
        output_tokens = _safe_int_attr(message, "output_tokens", 0)
        cache_read_tokens = _safe_int_attr(message, "cache_read_input_tokens", 0)

    sdk_cost = _safe_float_attr(message, "total_cost_usd", None)

    real_cost = compute_cost_from_tokens(input_tokens, output_tokens, cache_read_tokens)

    inflation = None
    if sdk_cost and real_cost > 0:
        inflation = round(sdk_cost / real_cost, 2)

    return CostBreakdown(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cost_input_usd=round((input_tokens / 1_000_000) * PRICING_KIMI_K2_6["input_per_mtok"], 6),
        cost_output_usd=round(
            (output_tokens / 1_000_000) * PRICING_KIMI_K2_6["output_per_mtok"], 6
        ),
        cost_cache_read_usd=round(
            (cache_read_tokens / 1_000_000) * PRICING_KIMI_K2_6["cache_read_per_mtok"], 6
        ),
        total_cost_usd=real_cost,
        sdk_reported_cost_usd=sdk_cost,
        inflation_factor=inflation,
    )


def real_cost_from_message(message: Any) -> float:
    """
    Helper conveniente: retorna apenas o custo recalculado (float).

    Útil pra substituir `message.total_cost_usd` em chamadas existentes.
    Se o SDK não expor tokens, faz fallback para o valor original do SDK.
    """
    breakdown = recompute_cost_from_message(message)
    if breakdown.input_tokens == 0 and breakdown.output_tokens == 0:
        # Sem tokens — não podemos recalcular. Devolve o que o SDK disse.
        sdk_cost = _safe_float_attr(message, "total_cost_usd", 0.0)
        logger.debug("recompute_cost: sem tokens disponíveis, usando valor do SDK (%.6f)", sdk_cost)
        return sdk_cost
    return breakdown.total_cost_usd


# ─── Helpers internos ────────────────────────────────────────────────────────


def _safe_int_attr(obj: Any, attr: str, default: int) -> int:
    val = getattr(obj, attr, None)
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _safe_float_attr(obj: Any, attr: str, default: float | None) -> float | None:
    val = getattr(obj, attr, None)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int_dict(d: dict[str, Any], key: str, default: int) -> int:
    """Extrai um int de um dict de forma segura (None / str inválida → default)."""
    val = d.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default
