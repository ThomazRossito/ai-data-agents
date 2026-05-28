"""
Real-mode loader de instance prices via Azure Retail Prices API + AWS Pricing API.

Substitui o mock estático em `instance_prices.py` por queries reais quando
o user habilita `DATABRICKS_INSTANCE_PRICES_MODE=real` no `.env`.

Estratégia:
  - Azure: Azure Retail Prices API (pública, sem auth) — reusa lógica do
    azure_pricing MCP. Cache TTL 1h.
  - AWS: AWS Pricing API via boto3 (requer AWS credentials no .env).
    Cache TTL 1h.
  - Fallback automático pro mock quando API falha (network, auth, region
    não suportada).

Sem credenciais → fallback transparente pro mock (não quebra UI). UI mostra
banner indicando modo ativo (mock vs real) + source URL + timestamp.

Schema retornado idêntico ao mock pra preservar engine compatibility.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("instance_prices_real")


# ─── Constantes ──────────────────────────────────────────────────────────────


_AZURE_RETAIL_API = "https://prices.azure.com/api/retail/prices"
_AZURE_API_VERSION = "2023-01-01-preview"
_CACHE_TTL_SECONDS = 3600  # 1h

# Cache em memória por (cloud, region, sku) → (timestamp, price_per_hour_usd)
_PRICE_CACHE: dict[str, tuple[float, float]] = {}


def clear_cache() -> None:
    """Limpa cache. Útil em testes e quando user pede refresh manual."""
    _PRICE_CACHE.clear()


def _now() -> float:
    return time.time()


def _cache_get(key: str) -> float | None:
    entry = _PRICE_CACHE.get(key)
    if entry is None:
        return None
    ts, price = entry
    if _now() - ts > _CACHE_TTL_SECONDS:
        del _PRICE_CACHE[key]
        return None
    return price


def _cache_set(key: str, price: float) -> None:
    _PRICE_CACHE[key] = (_now(), price)


# ─── Mode resolution ────────────────────────────────────────────────────────


def is_real_mode_enabled() -> bool:
    """True se DATABRICKS_INSTANCE_PRICES_MODE=real no env (default false)."""
    return os.environ.get("DATABRICKS_INSTANCE_PRICES_MODE", "mock").lower() == "real"


# ─── Azure Retail API integration ───────────────────────────────────────────


def fetch_azure_vm_price(
    region: str,
    sku_name: str,
    currency: str = "USD",
    timeout_seconds: float = 10.0,
) -> float | None:
    """
    Busca preço VM Azure Linux on-demand via Retail API.

    Args:
        region: arm region name (ex: "brazilsouth", "eastus", "westeurope").
        sku_name: armSkuName exato (ex: "Standard_DS4_v2").
        currency: 3-letter code (USD, BRL).
        timeout_seconds: timeout HTTP (default 10s).

    Returns:
        USD por hora (float) ou None se não encontrado / API falhou.
        Sempre retorna Linux (descarta Windows que inclui licença).

    Raises:
        Nenhuma — falhas são logadas e retornam None pra triggerar fallback.
    """
    cache_key = f"azure::{region.lower()}::{sku_name}::{currency.upper()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        import requests
    except ImportError:
        logger.warning("requests não disponível — usando mock fallback")
        return None

    try:
        # Filtra:
        # - serviceName='Virtual Machines'
        # - armRegionName=<region>
        # - armSkuName=<sku>
        # - priceType='Consumption' (on-demand)
        # - productName NÃO contém "Windows" (queremos Linux)
        # API não suporta NOT contains — filtramos no client após receber.
        filter_expr = (
            f"serviceName eq 'Virtual Machines' "
            f"and armRegionName eq '{region.lower()}' "
            f"and armSkuName eq '{sku_name}' "
            f"and priceType eq 'Consumption'"
        )

        params = {
            "api-version": _AZURE_API_VERSION,
            "currencyCode": currency.upper(),
            "$filter": filter_expr,
        }

        resp = requests.get(_AZURE_RETAIL_API, params=params, timeout=timeout_seconds)
        resp.raise_for_status()
        payload = resp.json()
        items = payload.get("Items", [])

        if not items:
            logger.info("azure VM price not found: %s/%s", region, sku_name)
            return None

        # Filtra Linux (descarta Windows + Low Priority + Spot — queremos on-demand padrão)
        linux_items = [
            item
            for item in items
            if "Windows" not in item.get("productName", "")
            and "Low Priority" not in item.get("skuName", "")
            and "Spot" not in item.get("skuName", "")
        ]

        if not linux_items:
            logger.info(
                "azure VM Linux on-demand not found: %s/%s (had %d Windows/Spot)",
                region,
                sku_name,
                len(items),
            )
            return None

        # Pega o primeiro on-demand Linux — retailPrice é USD/hour por default
        # (a API retorna unitOfMeasure="1 Hour" pra VMs)
        price = float(linux_items[0]["retailPrice"])
        _cache_set(cache_key, price)
        return price

    except (KeyError, ValueError, IndexError) as exc:
        logger.warning("malformed Azure API response for %s/%s: %s", region, sku_name, exc)
        return None
    except Exception as exc:
        # Network errors, timeouts, etc — log + fallback transparente
        logger.warning("azure VM price fetch failed for %s/%s: %s", region, sku_name, exc)
        return None


# ─── AWS Pricing API integration ────────────────────────────────────────────


def fetch_aws_ec2_price(
    region: str,
    instance_type: str,
    operating_system: str = "Linux",
    timeout_seconds: float = 15.0,
) -> float | None:
    """
    Busca preço EC2 AWS on-demand via AWS Pricing API.

    Args:
        region: AWS region name (ex: "us-east-1", "sa-east-1").
        instance_type: EC2 instance type (ex: "m5.xlarge").
        operating_system: "Linux" | "Windows" (default Linux).
        timeout_seconds: timeout HTTP.

    Returns:
        USD por hora (float) ou None se não encontrado / API falhou.

    Notas:
        - AWS Pricing API é hospedada em us-east-1 e ap-south-1 apenas
          (independente da region do EC2 que está sendo consultado).
        - Requer AWS credentials (AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY
          no .env, ou ~/.aws/credentials).
        - Returns None se boto3 não instalado ou credenciais ausentes
          (triggers fallback pro mock).
    """
    cache_key = f"aws::{region.lower()}::{instance_type}::{operating_system.lower()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
    except ImportError:
        logger.warning("boto3 não disponível — usando mock fallback (AWS)")
        return None

    try:
        # AWS Pricing API tem mapping de region codes pra nomes "humanos"
        # (ex: us-east-1 → "US East (N. Virginia)"). Cobre os principais.
        region_to_location = {
            "us-east-1": "US East (N. Virginia)",
            "us-east-2": "US East (Ohio)",
            "us-west-1": "US West (N. California)",
            "us-west-2": "US West (Oregon)",
            "eu-west-1": "EU (Ireland)",
            "eu-central-1": "EU (Frankfurt)",
            "ap-southeast-1": "Asia Pacific (Singapore)",
            "ap-southeast-2": "Asia Pacific (Sydney)",
            "ap-northeast-1": "Asia Pacific (Tokyo)",
            "sa-east-1": "South America (Sao Paulo)",
        }

        location = region_to_location.get(region.lower())
        if location is None:
            logger.warning("AWS region não mapeada: %s", region)
            return None

        # boto3 Pricing client SEMPRE roda em us-east-1 ou ap-south-1
        client = boto3.client(
            "pricing",
            region_name="us-east-1",
            config=__import__("botocore.client", fromlist=["Config"]).Config(
                connect_timeout=timeout_seconds, read_timeout=timeout_seconds
            ),
        )

        filters = [
            {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
            {"Type": "TERM_MATCH", "Field": "location", "Value": location},
            {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": operating_system},
            {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
            {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
            {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
        ]

        response = client.get_products(
            ServiceCode="AmazonEC2",
            Filters=filters,
            MaxResults=10,
        )

        price_list = response.get("PriceList", [])
        if not price_list:
            logger.info("aws EC2 price not found: %s/%s", region, instance_type)
            return None

        # PriceList retorna strings JSON com estrutura complexa
        import json as _json

        for item_str in price_list:
            item = _json.loads(item_str)
            terms = item.get("terms", {}).get("OnDemand", {})
            for term in terms.values():
                price_dimensions = term.get("priceDimensions", {})
                for dim in price_dimensions.values():
                    unit = dim.get("unit", "")
                    if unit == "Hrs":
                        usd_str = dim.get("pricePerUnit", {}).get("USD")
                        if usd_str:
                            price = float(usd_str)
                            _cache_set(cache_key, price)
                            return price

        logger.info("aws EC2 on-demand price not parseable: %s/%s", region, instance_type)
        return None

    except NoCredentialsError:
        logger.warning(
            "AWS credentials não configuradas — usando mock fallback. "
            "Configure AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY no .env."
        )
        return None
    except (ClientError, BotoCoreError) as exc:
        logger.warning("AWS Pricing API error para %s/%s: %s", region, instance_type, exc)
        return None
    except Exception as exc:
        logger.warning("aws EC2 price fetch failed for %s/%s: %s", region, instance_type, exc)
        return None


# ─── Public API: get_real_price com fallback ─────────────────────────────────


def get_instance_price_real_or_mock(
    cloud: str,
    region: str,
    sku_name: str,
    mock_fallback_fn,
) -> tuple[float, str]:
    """
    Tenta buscar preço real via API; fallback pro mock se falhar.

    Args:
        cloud: "azure" | "aws".
        region: region name.
        sku_name: SKU/instance type.
        mock_fallback_fn: callable(cloud, region, sku) -> float. Chamado se API
            falhar ou modo real estiver desabilitado.

    Returns:
        Tupla (price_usd_per_hour, source) onde source é "real_api" | "mock".
    """
    if not is_real_mode_enabled():
        return mock_fallback_fn(cloud, region, sku_name), "mock"

    real_price: float | None = None
    if cloud.lower() == "azure":
        real_price = fetch_azure_vm_price(region, sku_name)
    elif cloud.lower() == "aws":
        real_price = fetch_aws_ec2_price(region, sku_name)

    if real_price is not None and real_price > 0:
        return real_price, "real_api"

    # Fallback pro mock se API falhou ou retornou inválido
    logger.info("Real API falhou pra %s/%s/%s — fallback pro mock", cloud, region, sku_name)
    return mock_fallback_fn(cloud, region, sku_name), "mock_fallback"


def get_pricing_metadata() -> dict[str, Any]:
    """Retorna metadata pra UI mostrar source + status do real mode."""
    return {
        "mode": "real" if is_real_mode_enabled() else "mock",
        "azure_source_url": _AZURE_RETAIL_API,
        "aws_source": "AWS Pricing API (boto3 — requer credenciais)",
        "cache_ttl_seconds": _CACHE_TTL_SECONDS,
        "cache_entries": len(_PRICE_CACHE),
        "last_refresh_iso": (
            datetime.fromtimestamp(
                max(v[0] for v in _PRICE_CACHE.values()), tz=timezone.utc
            ).isoformat()
            if _PRICE_CACHE
            else None
        ),
        "boto3_available": _has_boto3(),
        "requests_available": _has_requests(),
    }


def _has_requests() -> bool:
    try:
        import requests  # noqa: F401

        return True
    except ImportError:
        return False


def _has_boto3() -> bool:
    try:
        import boto3  # noqa: F401

        return True
    except ImportError:
        return False


__all__ = [
    "clear_cache",
    "fetch_aws_ec2_price",
    "fetch_azure_vm_price",
    "get_instance_price_real_or_mock",
    "get_pricing_metadata",
    "is_real_mode_enabled",
]
