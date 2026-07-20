"""
Pricing — Cálculo de custo correto para os modelos Moonshot Kimi.

O claude-agent-sdk calcula `total_cost_usd` internamente assumindo preços da
Anthropic Sonnet ($3/M input, $15/M output). Como o projeto está apontando
para a Moonshot via endpoint compatível, o valor reportado pelo SDK não bate.
Este módulo recalcula o custo a partir dos tokens reais usando a tabela de
preços de CADA modelo — resolvida pelo nome do modelo (`model_usage`), pois uma
sessão pode misturar modelos (ex.: Supervisor kimi-k3 + sub-agentes kimi-k2.6).

Tabelas de preço (USD / 1M tokens; confira em platform.moonshot.ai/docs/pricing):
  - kimi-k2.6 / k2.5:  in $0.55  · out $2.65  · cache $0.055
  - kimi-k2.7-code:    in $0.95  · out $4.00  · cache $0.19
  - kimi-k3:           in $3.00  · out $15.00 · cache $0.19

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

#: Preços oficiais da Moonshot por modelo (USD / 1M tokens).
#: Atualize aqui se a Moonshot publicar nova tabela. Fonte: platform.moonshot.ai/docs/pricing.
PRICING_KIMI_K2_6: dict[str, float] = {
    "input_per_mtok": 0.55,
    "output_per_mtok": 2.65,
    "cache_read_per_mtok": 0.055,  # 10% do input regular (estimativa conservadora)
}

#: Kimi K2.7-Code (jun/2026) — coding-specialized. ⚠️ Confirmar valores na Moonshot.
PRICING_KIMI_K2_7_CODE: dict[str, float] = {
    "input_per_mtok": 0.95,
    "output_per_mtok": 4.00,
    "cache_read_per_mtok": 0.19,
}

#: Kimi K3 (jul/2026) — flagship 2.8T, thinking sempre-ligado. ~4-5x o K2.6.
#: ⚠️ Confirme os valores em platform.moonshot.ai/docs/pricing antes de confiar no budget.
PRICING_KIMI_K3: dict[str, float] = {
    "input_per_mtok": 3.00,
    "output_per_mtok": 15.00,
    "cache_read_per_mtok": 0.19,
}

#: Resolução nome-do-modelo → tabela. Chaves em minúsculo; casamento por substring
#: (o SDK pode reportar sufixos de data). Ordem: mais específico primeiro.
PRICING_BY_MODEL: dict[str, dict[str, float]] = {
    "kimi-k2.7-code": PRICING_KIMI_K2_7_CODE,
    "kimi-k3": PRICING_KIMI_K3,
    "kimi-k2.6": PRICING_KIMI_K2_6,
    "kimi-k2.5": PRICING_KIMI_K2_6,  # mesma faixa aproximada
}

#: Modelos com tabela de preço própria (para os demais, cai no fallback K2.6).
SUPPORTED_MODELS: set[str] = set(PRICING_BY_MODEL.keys())


def _resolve_pricing(model_name: str | None) -> dict[str, float]:
    """Resolve a tabela de preço pelo nome do modelo (fallback: K2.6)."""
    if model_name:
        m = model_name.lower()
        for key, table in PRICING_BY_MODEL.items():
            if key in m:
                return table
        logger.debug(
            "pricing: modelo '%s' sem tabela própria — usando K2.6 como fallback", model_name
        )
    return PRICING_KIMI_K2_6


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
    model: str | None = None,
) -> float:
    """
    Calcula o custo em USD a partir dos contadores de token.

    Args:
        input_tokens: Tokens de input regulares (sem cache hit).
        output_tokens: Tokens gerados pelo modelo.
        cache_read_tokens: Tokens lidos do cache (preço reduzido).
        pricing: Tabela alternativa de preços. Se None, resolve pela `model`.
        model: Nome do modelo, usado para resolver a tabela quando `pricing` é None.

    Returns:
        Custo total em USD.
    """
    p = pricing or _resolve_pricing(model)
    cost = (
        (input_tokens / 1_000_000) * p["input_per_mtok"]
        + (output_tokens / 1_000_000) * p["output_per_mtok"]
        + (cache_read_tokens / 1_000_000) * p["cache_read_per_mtok"]
    )
    return round(cost, 6)


# ─── Extração de tokens robusta ──────────────────────────────────────────────
#: O `usage` agregado usa Anthropic API (snake_case: input_tokens); o `model_usage`
#: (=`modelUsage` do CLI) usa camelCase (inputTokens). Aceitamos AMBOS.
_INPUT_KEYS = ("input_tokens", "inputTokens")
_OUTPUT_KEYS = ("output_tokens", "outputTokens")
_CACHE_KEYS = ("cache_read_input_tokens", "cacheReadInputTokens")

#: O SDK/CLI reporta total_cost_usd assumindo preço Anthropic Sonnet ($3/M input).
#: Usado só como ÚLTIMO recurso: converter o custo do SDK quando NÃO há tokens.
_SDK_REF_INPUT_PER_MTOK = 3.0


def _first_int(d: dict[str, Any], keys: tuple[str, ...]) -> int:
    for k in keys:
        v = d.get(k)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
    return 0


def _tokens_from_message(message: Any) -> tuple[int, int, int]:
    """(input, output, cache_read) — soma model_usage, senão usage, senão attrs.

    Tolera snake_case e camelCase. NÃO deixa um model_usage presente-mas-zero
    bloquear o fallback para `usage` (regressão do rewrite anterior).
    """
    in_t = out_t = ca_t = 0
    mu = getattr(message, "model_usage", None)
    if isinstance(mu, dict):
        for entry in mu.values():
            if isinstance(entry, dict):
                in_t += _first_int(entry, _INPUT_KEYS)
                out_t += _first_int(entry, _OUTPUT_KEYS)
                ca_t += _first_int(entry, _CACHE_KEYS)
    if in_t == 0 and out_t == 0:
        u = getattr(message, "usage", None)
        if isinstance(u, dict):
            in_t = _first_int(u, _INPUT_KEYS)
            out_t = _first_int(u, _OUTPUT_KEYS)
            ca_t = _first_int(u, _CACHE_KEYS)
    if in_t == 0 and out_t == 0:
        in_t = _safe_int_attr(message, "input_tokens", 0)
        out_t = _safe_int_attr(message, "output_tokens", 0)
        ca_t = _safe_int_attr(message, "cache_read_input_tokens", 0)
    return in_t, out_t, ca_t


def _real_model(message: Any, model: str | None = None) -> str:
    """Modelo REAL da execução. O ResultMessage do SDK NÃO tem `model`, e o
    `model_usage` traz rótulos Anthropic (claude-*) contra a Moonshot — então a
    fonte de verdade é o modelo configurado (`settings.default_model`)."""
    if model:
        return model
    m = _safe_str_attr(message, "model", None)
    if m and "claude" not in m.lower():  # ignora rótulos Anthropic do SDK
        return m
    try:
        from config.settings import settings

        return str(settings.default_model)
    except Exception:
        return "kimi-k2.6"


def recompute_cost_from_message(message: Any, model: str | None = None) -> CostBreakdown:
    """
    Recalcula o custo de um ResultMessage usando o preço do MODELO REAL configurado.

    Por que não confiar no `model_usage`: contra a Moonshot, o SDK rotula o uso com
    nomes Anthropic (claude-sonnet/haiku) e às vezes reporta 0 tokens. Então:
      1) extraímos tokens de model_usage/usage/attrs (snake OU camelCase);
      2) precificamos pelo modelo real (`model` explícito ou `settings.default_model`);
      3) se NÃO houver tokens, convertemos o custo do SDK (preço Sonnet) para o
         preço do modelo real pelo ratio de input (aproximação; p/ K3 ratio≈1.0).

    Sessões mistas (Supervisor + sub-agentes) são precificadas pelo modelo primário
    (conservador — o Supervisor domina o custo).
    """
    real_model = _real_model(message, model)
    p = _resolve_pricing(real_model)
    in_t, out_t, ca_t = _tokens_from_message(message)
    sdk_cost = _safe_float_attr(message, "total_cost_usd", None)

    if in_t or out_t or ca_t:
        cost_in = (in_t / 1_000_000) * p["input_per_mtok"]
        cost_out = (out_t / 1_000_000) * p["output_per_mtok"]
        cost_ca = (ca_t / 1_000_000) * p["cache_read_per_mtok"]
    elif sdk_cost:
        # Sem tokens no ResultMessage — converte o custo do SDK (preço Sonnet) para
        # o modelo real pelo ratio de input (input domina em runs agentic).
        ratio = p["input_per_mtok"] / _SDK_REF_INPUT_PER_MTOK
        cost_in, cost_out, cost_ca = sdk_cost * ratio, 0.0, 0.0
        logger.debug(
            "recompute_cost: sem tokens; custo SDK %.6f × %.3f (%s) = %.6f",
            sdk_cost, ratio, real_model, cost_in,
        )
    else:
        cost_in = cost_out = cost_ca = 0.0

    real_cost = round(cost_in + cost_out + cost_ca, 6)
    inflation = round(sdk_cost / real_cost, 2) if (sdk_cost and real_cost > 0) else None

    return CostBreakdown(
        input_tokens=in_t,
        output_tokens=out_t,
        cache_read_tokens=ca_t,
        cost_input_usd=round(cost_in, 6),
        cost_output_usd=round(cost_out, 6),
        cost_cache_read_usd=round(cost_ca, 6),
        total_cost_usd=real_cost,
        sdk_reported_cost_usd=sdk_cost,
        inflation_factor=inflation,
    )


def real_cost_from_message(message: Any, model: str | None = None) -> float:
    """Retorna só o custo recalculado (float). Agora sempre sensato: sem tokens, o
    recompute já converte o custo do SDK — não devolvemos mais o valor cru."""
    return recompute_cost_from_message(message, model).total_cost_usd


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


def _safe_str_attr(obj: Any, attr: str, default: str | None) -> str | None:
    val = getattr(obj, attr, None)
    if val is None:
        return default
    try:
        return str(val)
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
