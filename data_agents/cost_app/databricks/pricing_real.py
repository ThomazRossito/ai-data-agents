"""
Real-mode DBU rate loader via `system.billing.list_prices` (PR 8, 2026-05-28).

Substitui rates estáticos do catalog YAML por queries ao vivo contra Unity
Catalog system table `system.billing.list_prices`. Cache TTL 1h. Fallback
transparente pra função `fallback_fn` (tipicamente leitura do YAML) quando
real-mode desabilitado, credenciais ausentes ou API falha.

Estratégia:
  - Habilitado via env var `DATABRICKS_PRICING_MODE=real` (default: mock/yaml)
  - Re-usa DATABRICKS_HOST + TOKEN + BILLING_WAREHOUSE_ID do billing_real.py
  - Query SQL contra system.billing.list_prices (workspace deve ter UC + system
    schemas habilitados)
  - Retorna `pricing.default` (preço list) — preço promocional fica como TODO
    (campo `pricing.promotional.default` pode ser exposto em iteração futura)
  - Cache em memória por (cloud, sku_name) → (timestamp, price)
  - Fallback transparente pro mock/YAML quando DATABRICKS_PRICING_MODE != real
    ou credenciais ausentes ou API falha

Tabela: https://docs.databricks.com/aws/en/admin/system-tables/pricing
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable

logger = logging.getLogger("databricks_pricing.real")


# ─── Constantes ──────────────────────────────────────────────────────────────


_CACHE_TTL_SECONDS = 3600  # 1h — pricing muda raramente
_DEFAULT_TIMEOUT_SECONDS = 30

# Cache em memória: (cloud, sku) → (timestamp, price_usd_per_unit)
_PRICE_CACHE: dict[str, tuple[float, float]] = {}


def clear_cache() -> None:
    """Limpa cache. Útil em testes e quando user pede refresh manual."""
    _PRICE_CACHE.clear()


def is_real_pricing_mode_enabled() -> bool:
    """True se env var `DATABRICKS_PRICING_MODE=real` está setado.

    Mantém pareamento com `instance_prices_real.is_real_mode_enabled()` mas usa
    var diferente porque escopo é distinto (rates de DBU/SKU, não VM/EC2 price).
    """
    return os.environ.get("DATABRICKS_PRICING_MODE", "").strip().lower() == "real"


def _cache_get(key: str) -> float | None:
    entry = _PRICE_CACHE.get(key)
    if entry is None:
        return None
    ts, price = entry
    if time.time() - ts > _CACHE_TTL_SECONDS:
        del _PRICE_CACHE[key]
        return None
    return price


def _cache_set(key: str, price: float) -> None:
    _PRICE_CACHE[key] = (time.time(), price)


# ─── SQL ─────────────────────────────────────────────────────────────────────


def _build_list_prices_sql(sku_name: str, cloud: str) -> str:
    """SQL pra fetch o preço mais recente de um SKU em uma cloud.

    system.billing.list_prices contém histórico — pegamos o registro mais
    recente cujo price_start_time <= now AND (price_end_time IS NULL OR price_end_time > now).

    sku_name e cloud são parametrizados — validados antes de inserir na string.
    """
    # Defensive: filtra caracteres especiais (sku_name e cloud devem vir de
    # nosso código, não user input direto, mas paranoia justifica).
    sku_clean = "".join(c for c in sku_name if c.isalnum() or c in ("_", "-"))
    cloud_clean = cloud.upper()
    if cloud_clean not in ("AWS", "AZURE", "GCP"):
        raise ValueError(f"cloud inválido: {cloud!r}")
    if sku_clean != sku_name:
        raise ValueError(f"sku_name contém caracteres inválidos: {sku_name!r}")

    return f"""
SELECT
    sku_name,
    cloud,
    currency_code,
    usage_unit,
    CAST(pricing.default AS DOUBLE) AS price_default,
    price_start_time
FROM system.billing.list_prices
WHERE sku_name = '{sku_clean}'
  AND cloud = '{cloud_clean}'
  AND price_start_time <= current_timestamp()
  AND (price_end_time IS NULL OR price_end_time > current_timestamp())
ORDER BY price_start_time DESC
LIMIT 1
""".strip()


# ─── Fetch ───────────────────────────────────────────────────────────────────


def fetch_dbu_rate_real(sku_name: str, cloud: str) -> float | None:
    """Fetch o preço list (USD/usage_unit) de um SKU via system.billing.list_prices.

    Args:
        sku_name: nome do SKU oficial Databricks (ex: 'STANDARD_ALL_PURPOSE_COMPUTE',
            'PREMIUM_JOBS_COMPUTE_AWS'). Case sensitive.
        cloud: 'aws', 'azure', ou 'gcp' (case insensitive).

    Returns:
        Preço USD/usage_unit (DBU, TOKEN, GB-MONTH, ANSWER, ...) do registro mais
        recente, ou None se:
          - real-mode não habilitado (DATABRICKS_PRICING_MODE != real)
          - credenciais ausentes
          - SKU não encontrado em system.billing.list_prices
          - API/SQL falhou (network, auth, permissão, warehouse pausado)

    Fallback transparente: caller deve ter um `fallback_fn` que retorna
    o preço do YAML quando isso retorna None.
    """
    cache_key = f"{cloud.lower()}::{sku_name}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # Lazy import — billing_real define a config e o executor
    try:
        from data_agents.cost_app.databricks.billing_real import (
            RealModeConfig,
            _execute_sql,
        )
    except ImportError as exc:
        logger.warning("billing_real não disponível — usando fallback: %s", exc)
        return None

    try:
        config = RealModeConfig.from_env()
    except RuntimeError as exc:
        logger.info("credenciais ausentes — usando fallback: %s", exc)
        return None

    sql = _build_list_prices_sql(sku_name, cloud)
    try:
        rows = _execute_sql(config, sql)
    except Exception as exc:  # noqa: BLE001 — qualquer falha cai no fallback
        logger.warning("query system.billing.list_prices falhou: %s", exc)
        return None

    if not rows:
        logger.info(
            "SKU %r não encontrado em system.billing.list_prices (cloud=%s)", sku_name, cloud
        )
        return None

    price = rows[0].get("price_default")
    if price is None:
        return None

    try:
        price_float = float(price)
    except (TypeError, ValueError):
        return None

    _cache_set(cache_key, price_float)
    return price_float


# ─── Public API: get_dbu_rate_real_or_fallback ──────────────────────────────


def get_dbu_rate_real_or_fallback(
    sku_name: str,
    cloud: str,
    fallback_fn: Callable[[], float | None],
) -> tuple[float | None, str]:
    """Tenta real-mode; fallback transparente pro YAML.

    Args:
        sku_name: SKU oficial Databricks.
        cloud: 'aws', 'azure', 'gcp'.
        fallback_fn: thunk que retorna o preço do catalog YAML (ou None se
            o YAML também não tem o SKU). Mantém engine determinístico.

    Returns:
        (price, source) onde source ∈ {
            'real_api', 'yaml_fallback', 'unavailable'
        }.
    """
    if not is_real_pricing_mode_enabled():
        price = fallback_fn()
        return price, "yaml" if price is not None else "unavailable"

    real_price = fetch_dbu_rate_real(sku_name, cloud)
    if real_price is not None:
        return real_price, "real_api"

    # Real-mode habilitado mas API falhou — fallback transparente
    price = fallback_fn()
    return price, "yaml_fallback" if price is not None else "unavailable"


# ─── Metadata / introspection ────────────────────────────────────────────────


def get_pricing_real_metadata() -> dict[str, Any]:
    """Retorna estado do real-mode pra UI.

    Não toca nas APIs — só lê env vars + status do cache.
    """
    return {
        "real_mode_enabled": is_real_pricing_mode_enabled(),
        "env_var": "DATABRICKS_PRICING_MODE",
        "source_table": "system.billing.list_prices",
        "source_url": "https://docs.databricks.com/aws/en/admin/system-tables/pricing",
        "cache_ttl_seconds": _CACHE_TTL_SECONDS,
        "cache_entries": len(_PRICE_CACHE),
        "requires_env_vars": [
            "DATABRICKS_HOST",
            "DATABRICKS_TOKEN",
            "DATABRICKS_BILLING_WAREHOUSE_ID",
            "DATABRICKS_PRICING_MODE=real (pra habilitar)",
        ],
    }
