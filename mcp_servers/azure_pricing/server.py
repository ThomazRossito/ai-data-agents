"""
Azure Pricing — MCP Server Customizado.

Expõe a Azure Retail Prices API (https://prices.azure.com/api/retail/prices)
como conjunto de tools determinísticas. Os preços retornados casam 1:1 com
o Azure Pricing Calculator oficial para retail pricing (não inclui descontos
EA/MCA negociados — para esses cenários, alimentar price sheet via flag).

Configuração no .env (todos opcionais — têm defaults sensatos):

  AZURE_PRICING_DEFAULT_REGION=brazilsouth   # arm region name (ex: brazilsouth, eastus, westeurope)
  AZURE_PRICING_DEFAULT_CURRENCY=USD          # 3-letter code: USD, BRL, EUR, GBP, etc.
  AZURE_PRICING_HOURS_PER_MONTH=730           # padrão da calculadora oficial (365.25/12*24)

Autenticação: nenhuma (Retail Prices API é pública, sem rate limits abusivos)
Dependências: requests + stdlib

Comando entry point: azure-pricing-mcp (declarado em pyproject.toml)
"""

from __future__ import annotations

import json
import logging
import os
import time
import traceback
import urllib.parse
from datetime import datetime, timezone
from typing import Any

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("azure_pricing_mcp")

# ─── FastMCP Server ───────────────────────────────────────────────────────────

mcp = FastMCP("azure-pricing")

# ─── Constantes ──────────────────────────────────────────────────────────────

_RETAIL_PRICES_API = "https://prices.azure.com/api/retail/prices"
_PRICING_CALCULATOR_BASE = "https://azure.microsoft.com/pricing/calculator/"

# ─── Tabela determinística de fixed costs ────────────────────────────────────
# Serviços que TÊM custo fixo de deployment ALÉM do consumption.
# Valores baseados em preços Microsoft maio/2026. Atualização periódica recomendada.
# A Retail API frequentemente retorna apenas o consumption meter (ex: Firewall Data
# Processed $0.016/GB) sem expor o fixed cost de deployment, levando agentes a
# subestimar o custo total em milhares de dólares/mês. Este registro fecha esse gap.
_FIXED_COSTS_TABLE: dict[str, dict[str, dict[str, float | str]]] = {
    "Azure Firewall": {
        "Standard": {
            "label_suggestion": "Azure Firewall Standard - Deployment",
            "meter_name": "Standard Deployment",
            "price_usd_per_hour": 1.25,
            "monthly_usd_730h": 912.50,
        },
        "Premium": {
            "label_suggestion": "Azure Firewall Premium - Deployment",
            "meter_name": "Premium Deployment",
            "price_usd_per_hour": 1.75,
            "monthly_usd_730h": 1277.50,
        },
    },
    "VPN Gateway": {
        "VpnGw1": {
            "label_suggestion": "VPN Gateway VpnGw1 - Fixed",
            "meter_name": "VpnGw1",
            "price_usd_per_hour": 0.19,
            "monthly_usd_730h": 138.70,
        },
        "VpnGw2": {
            "label_suggestion": "VPN Gateway VpnGw2 - Fixed",
            "meter_name": "VpnGw2",
            "price_usd_per_hour": 0.49,
            "monthly_usd_730h": 357.70,
        },
        "VpnGw3": {
            "label_suggestion": "VPN Gateway VpnGw3 - Fixed",
            "meter_name": "VpnGw3",
            "price_usd_per_hour": 1.25,
            "monthly_usd_730h": 912.50,
        },
    },
    "Application Gateway": {
        "WAF_v2": {
            "label_suggestion": "Application Gateway WAF v2 - Fixed Cost",
            "meter_name": "Standard Fixed Cost",
            "price_usd_per_hour": 0.72,
            "monthly_usd_730h": 525.60,
        },
        "Standard_v2": {
            "label_suggestion": "Application Gateway v2 - Fixed Cost",
            "meter_name": "Standard Fixed Cost",
            "price_usd_per_hour": 0.36,
            "monthly_usd_730h": 262.80,
        },
    },
    "Azure Bastion": {
        "Basic": {
            "label_suggestion": "Azure Bastion Basic - Gateway",
            "meter_name": "Basic Gateway",
            "price_usd_per_hour": 0.19,
            "monthly_usd_730h": 138.70,
        },
        "Standard": {
            "label_suggestion": "Azure Bastion Standard - Gateway",
            "meter_name": "Standard Gateway",
            "price_usd_per_hour": 0.29,
            "monthly_usd_730h": 211.70,
        },
    },
}


def _lookup_fixed_cost_fallback(
    service: str | None, sku: str | None, meter: str | None
) -> dict[str, float | str] | None:
    """
    Retorna o registro de fixed cost da tabela determinística se o resource
    parece ser um deployment/fixed line conhecido. Usado como fallback quando
    a Retail API não retorna match (ex: Firewall Premium Deployment ausente
    do response da API em brazilsouth).

    Heurística: o resource é elegível se o service_name está na tabela E
    (o meter_name ou sku_name parecem indicar fixed cost — keywords:
    "deployment", "fixed cost", "gateway", "vpngw").
    """
    if not service:
        return None

    # Match por service_name (case-insensitive, prefix-match)
    service_lower = service.lower()
    matched_service = None
    for tabled_service in _FIXED_COSTS_TABLE.keys():
        if tabled_service.lower() in service_lower or service_lower in tabled_service.lower():
            matched_service = tabled_service
            break

    if not matched_service:
        return None

    # Verifica se este resource parece ser a linha de fixed cost
    fixed_keywords = {"deployment", "fixed cost", "gateway", "vpngw"}
    haystack = " ".join(filter(None, [str(meter or ""), str(sku or "")])).lower()
    is_fixed_line = any(kw in haystack for kw in fixed_keywords)

    if not is_fixed_line:
        return None

    # Resolve tier (preferência: sku_name; fallback: primeiro da tabela)
    tiers = _FIXED_COSTS_TABLE[matched_service]
    sku_lower = str(sku or "").lower()
    for tier_key, tier_info in tiers.items():
        if tier_key.lower() in sku_lower:
            return tier_info  # type: ignore[return-value]

    # Default: primeiro tier
    return next(iter(tiers.values()))  # type: ignore[return-value]


def _detect_fixed_cost_violations(resources: list[dict]) -> list[dict]:
    """
    Detecta resources que precisam de fixed cost mas só têm consumption.

    Heurística: se um resource menciona Azure Firewall/VPN Gateway/App Gateway/Bastion
    via service_name OU label OU sku_name, verifica se EXISTE outra entry no mesmo
    resources_json que cubra o fixed cost (via meter_name como "Deployment", "Gateway",
    "Fixed Cost", "VpnGw*").

    Retorna lista de violações com sugestão de linha a adicionar.
    """
    violations: list[dict] = []

    for service_name, tiers in _FIXED_COSTS_TABLE.items():
        # Resources que parecem ser DESSE serviço
        service_resources = [
            r for r in resources
            if service_name.lower() in str(r.get("service_name", "")).lower()
            or service_name.lower() in str(r.get("label", "")).lower()
        ]
        if not service_resources:
            continue

        # Existe alguma entry deste serviço com meter_name de fixed cost?
        fixed_meter_keywords = {"deployment", "fixed cost", "gateway", "vpngw"}
        has_fixed_line = any(
            any(kw in str(r.get("meter_name", "")).lower() for kw in fixed_meter_keywords)
            for r in service_resources
        )

        if has_fixed_line:
            continue  # OK, já tem fixed cost

        # Detecta o tier mais provável (do primeiro resource)
        tier_detected = None
        for r in service_resources:
            sku_lower = str(r.get("sku_name", "")).lower()
            label_lower = str(r.get("label", "")).lower()
            for tier_key in tiers.keys():
                if tier_key.lower() in sku_lower or tier_key.lower() in label_lower:
                    tier_detected = tier_key
                    break
            if tier_detected:
                break

        # Default: primeiro tier da tabela
        if not tier_detected:
            tier_detected = next(iter(tiers.keys()))

        tier_info = tiers[tier_detected]
        violations.append(
            {
                "service_name": service_name,
                "tier_detected": tier_detected,
                "issue": (
                    f"{service_name} está no breakdown apenas com consumption/data "
                    f"meter. Falta a linha de fixed cost de deployment."
                ),
                "missing_line_to_add": {
                    "service_name": service_name,
                    "label": tier_info["label_suggestion"],
                    "sku_name": tier_detected,
                    "meter_name": tier_info["meter_name"],
                    "region": service_resources[0].get("region", "brazilsouth"),
                    "quantity": 1,
                    "_fixed_price_reference_usd_per_hour": tier_info["price_usd_per_hour"],
                    "_expected_monthly_usd_730h": tier_info["monthly_usd_730h"],
                },
                "remediation": (
                    f"Use price_usd_per_hour=${tier_info['price_usd_per_hour']} "
                    f"se a API não retornar — esse valor vem da tabela determinística "
                    f"do MCP (KB §13.3, atualizada maio/2026)."
                ),
            }
        )

    return violations
_API_VERSION = "2023-01-01-preview"
_DEFAULT_TIMEOUT = 30
_MAX_PAGE_FOLLOW = 5  # quantas páginas da API seguir em listSkus (paginação OData)
_CACHE_TTL_S = 3600  # 1 hora de cache em memória pra evitar refetch durante sessão

# Cache em memória pra preços (válido durante o lifetime do processo MCP)
_PRICE_CACHE: dict[str, tuple[float, list[dict]]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_region() -> str:
    return os.environ.get("AZURE_PRICING_DEFAULT_REGION", "brazilsouth").strip().lower()


def _default_currency() -> str:
    return os.environ.get("AZURE_PRICING_DEFAULT_CURRENCY", "USD").strip().upper()


def _hours_per_month() -> float:
    raw = os.environ.get("AZURE_PRICING_HOURS_PER_MONTH", "730").strip()
    try:
        return float(raw)
    except ValueError:
        return 730.0


# ─── HTTP helper ──────────────────────────────────────────────────────────────


def _query_retail_api(
    filter_expr: str,
    currency: str | None = None,
    max_results: int = 50,
) -> list[dict]:
    """
    Chama a Azure Retail Prices API com OData $filter.

    Args:
        filter_expr: expressão OData (ex: "serviceName eq 'Azure OpenAI'
                     and armRegionName eq 'brazilsouth'")
        currency: 3-letter code (USD, BRL, etc.). Se None usa default.
        max_results: limite de itens (paginação automática até atingir)

    Returns:
        Lista de items da API (cada item é um SKU com preço unitário)
    """
    if not REQUESTS_AVAILABLE:
        raise RuntimeError(
            "Módulo 'requests' não está instalado. "
            "Instale com: pip install requests"
        )

    currency = (currency or _default_currency()).upper()
    cache_key = f"{currency}::{filter_expr}::{max_results}"
    now = time.time()

    cached = _PRICE_CACHE.get(cache_key)
    if cached and now - cached[0] < _CACHE_TTL_S:
        return cached[1]

    params = {
        "api-version": _API_VERSION,
        "currencyCode": currency,
        "$filter": filter_expr,
    }

    all_items: list[dict] = []
    url: str | None = f"{_RETAIL_PRICES_API}?{urllib.parse.urlencode(params)}"
    pages = 0

    while url and len(all_items) < max_results and pages < _MAX_PAGE_FOLLOW:
        resp = requests.get(url, timeout=_DEFAULT_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        all_items.extend(payload.get("Items", []))
        url = payload.get("NextPageLink")
        pages += 1

    all_items = all_items[:max_results]
    _PRICE_CACHE[cache_key] = (now, all_items)
    return all_items


def _error_response(e: Exception) -> str:
    return json.dumps(
        {
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()[:2000],
            "timestamp": _now_iso(),
        },
        ensure_ascii=False,
        indent=2,
    )


# ═════════════════════════════════════════════════════════════════════════════
# TOOLS
# ═════════════════════════════════════════════════════════════════════════════


@mcp.tool()
def azure_pricing_diagnostics() -> str:
    """
    Smoke test do MCP server. Valida que: (1) requests está instalado,
    (2) a Retail Prices API responde, (3) defaults estão configurados.

    Returns:
        JSON com status, defaults e amostra (1 SKU de Storage Account em BR South).
    """
    try:
        if not REQUESTS_AVAILABLE:
            return _error_response(
                RuntimeError("Módulo 'requests' não está disponível")
            )

        # Sample query usa eastus + serviceFamily=Storage (filtro amplo que sempre
        # retorna items em qualquer região; brazilsouth pode ter cobertura parcial
        # de SKUs antigos como Standard_LRS).
        sample = _query_retail_api(
            filter_expr=(
                "serviceFamily eq 'Storage' and armRegionName eq 'eastus' "
                "and priceType eq 'Consumption'"
            ),
            max_results=1,
        )

        return json.dumps(
            {
                "status": "ok",
                "api_endpoint": _RETAIL_PRICES_API,
                "api_version": _API_VERSION,
                "defaults": {
                    "region": _default_region(),
                    "currency": _default_currency(),
                    "hours_per_month": _hours_per_month(),
                },
                "sample_query": {
                    "filter": "serviceFamily=Storage, region=eastus, priceType=Consumption",
                    "items_returned": len(sample),
                    "sample_item": sample[0] if sample else None,
                },
                "cache_size_entries": len(_PRICE_CACHE),
                "timestamp": _now_iso(),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return _error_response(e)


@mcp.tool()
def azure_pricing_get_retail_price(
    service_name: str,
    region: str | None = None,
    sku_name: str | None = None,
    product_name: str | None = None,
    meter_name: str | None = None,
    price_type: str = "Consumption",
    currency: str | None = None,
    max_results: int = 20,
) -> str:
    """
    Busca preço unitário retail de SKUs Azure.

    Args:
        service_name: nome do serviço Azure (ex: "Azure OpenAI", "Storage",
                      "Cognitive Services", "Azure Cosmos DB", "Virtual Machines",
                      "Microsoft Fabric"). Match exato.
        region: arm region name (ex: "brazilsouth", "eastus"). Default = .env.
                Use "global" pra serviços sem região (ex: AAD).
        sku_name: filtro adicional por SKU (ex: "Standard_LRS", "S1", "F2").
        product_name: filtro adicional por produto (ex: "Azure AI Search").
        meter_name: filtro por meter (ex: "S1 Search Unit Hour").
        price_type: "Consumption" (PAYG), "Reservation" (RI), "DevTestConsumption".
        currency: 3-letter code (USD, BRL). Default = .env.
        max_results: máximo de SKUs a retornar (1-100).

    Returns:
        JSON com items contendo: armSkuName, productName, skuName, meterName,
        unitPrice, unitOfMeasure, retailPrice, reservationTerm, savingsPlan, etc.
        Cada item inclui timestamp e link pra fonte.
    """
    try:
        region = (region or _default_region()).lower()
        currency = (currency or _default_currency()).upper()
        max_results = max(1, min(int(max_results), 100))

        filters = [f"serviceName eq '{service_name}'", f"priceType eq '{price_type}'"]
        if region and region.lower() != "global":
            filters.append(f"armRegionName eq '{region}'")
        if sku_name:
            filters.append(f"skuName eq '{sku_name}'")
        if product_name:
            filters.append(f"productName eq '{product_name}'")
        if meter_name:
            filters.append(f"meterName eq '{meter_name}'")

        filter_expr = " and ".join(filters)
        items = _query_retail_api(filter_expr, currency=currency, max_results=max_results)

        return json.dumps(
            {
                "query": {
                    "service_name": service_name,
                    "region": region,
                    "sku_name": sku_name,
                    "product_name": product_name,
                    "meter_name": meter_name,
                    "price_type": price_type,
                    "currency": currency,
                    "filter_expression": filter_expr,
                },
                "items_count": len(items),
                "items": items,
                "source": _RETAIL_PRICES_API,
                "timestamp": _now_iso(),
                "notes": (
                    "Retail prices são públicos. Para preços EA/MCA negociados, "
                    "use price sheet exportado do portal Azure."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return _error_response(e)


@mcp.tool()
def azure_pricing_get_price_with_regional_fallback(
    service_name: str,
    primary_region: str | None = None,
    sku_name: str | None = None,
    product_name: str | None = None,
    meter_name: str | None = None,
    price_type: str = "Consumption",
    currency: str | None = None,
    fallback_regions: str = "eastus2,eastus,westeurope,northeurope",
) -> str:
    """
    Busca preço de um SKU tentando primary_region, e se vazio, cai em
    regiões de fallback automaticamente. Útil para Azure OpenAI / Foundry
    cuja cobertura regional é incompleta (ex: brazilsouth tem poucos SKUs).

    A Microsoft cobra OpenAI por "deployment region" — então usar pricing
    de eastus2 para um cliente brazilsouth é PRICING CORRETO quando o SKU
    não tem registro em brazilsouth.

    Args:
        service_name: nome do serviço Azure (ex: "Azure OpenAI").
        primary_region: região preferida. Default = .env.
        sku_name / product_name / meter_name: filtros opcionais.
        price_type: "Consumption" (PAYG) ou "Reservation".
        currency: 3-letter code. Default = .env.
        fallback_regions: csv de regiões em ordem de tentativa.

    Returns:
        JSON com:
          - items encontrados (mesma estrutura de get_retail_price)
          - region_used (qual região retornou o resultado)
          - cross_region_pricing (true se caiu em fallback)
          - regions_tried (lista de regiões testadas)
    """
    try:
        primary = (primary_region or _default_region()).lower()
        currency = (currency or _default_currency()).upper()
        regions_to_try = [primary] + [
            r.strip().lower() for r in fallback_regions.split(",") if r.strip()
        ]
        # Remove duplicates preservando ordem
        seen = set()
        regions_unique = [r for r in regions_to_try if not (r in seen or seen.add(r))]

        regions_tried: list[str] = []
        found_items: list[dict] = []
        region_used: str | None = None

        for region in regions_unique:
            regions_tried.append(region)
            filters = [
                f"serviceName eq '{service_name}'",
                f"priceType eq '{price_type}'",
            ]
            if region != "global":
                filters.append(f"armRegionName eq '{region}'")
            if sku_name:
                filters.append(f"skuName eq '{sku_name}'")
            if product_name:
                filters.append(f"productName eq '{product_name}'")
            if meter_name:
                filters.append(f"meterName eq '{meter_name}'")
            filter_expr = " and ".join(filters)

            items = _query_retail_api(filter_expr, currency=currency, max_results=10)
            if items:
                found_items = items
                region_used = region
                break

        return json.dumps(
            {
                "query": {
                    "service_name": service_name,
                    "primary_region": primary,
                    "sku_name": sku_name,
                    "product_name": product_name,
                    "meter_name": meter_name,
                    "currency": currency,
                },
                "region_used": region_used,
                "cross_region_pricing": region_used != primary if region_used else False,
                "regions_tried": regions_tried,
                "items_count": len(found_items),
                "items": found_items,
                "warning": (
                    None
                    if region_used == primary
                    else (
                        f"⚠️ {service_name} não tem SKUs em {primary}. "
                        f"Usando preço de {region_used} (cross-region pricing). "
                        f"Microsoft cobra OpenAI/AI services por deployment region, "
                        f"então este preço é o efetivamente cobrado."
                    )
                    if region_used
                    else (
                        f"❌ Nenhum SKU encontrado em {regions_tried}. "
                        f"Verifique service_name e filtros."
                    )
                ),
                "source": _RETAIL_PRICES_API,
                "timestamp": _now_iso(),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return _error_response(e)


@mcp.tool()
def azure_pricing_list_skus(
    service_name: str,
    region: str | None = None,
    currency: str | None = None,
    max_results: int = 50,
) -> str:
    """
    Lista todos os SKUs de um serviço numa região. Útil pra descobrir
    quais tiers existem antes de pricing detalhado.

    Args:
        service_name: nome do serviço (ex: "Azure AI Search").
        region: arm region name. Default = .env.
        currency: 3-letter code. Default = .env.
        max_results: até 100.

    Returns:
        JSON com lista deduplicada de SKUs disponíveis.
    """
    try:
        region = (region or _default_region()).lower()
        currency = (currency or _default_currency()).upper()
        max_results = max(1, min(int(max_results), 100))

        filter_expr = (
            f"serviceName eq '{service_name}' "
            f"and armRegionName eq '{region}' "
            "and priceType eq 'Consumption'"
        )
        items = _query_retail_api(filter_expr, currency=currency, max_results=max_results)

        # Dedup por (productName, skuName, meterName)
        seen = set()
        skus = []
        for it in items:
            key = (
                it.get("productName"),
                it.get("skuName"),
                it.get("meterName"),
            )
            if key in seen:
                continue
            seen.add(key)
            skus.append(
                {
                    "productName": it.get("productName"),
                    "skuName": it.get("skuName"),
                    "meterName": it.get("meterName"),
                    "armSkuName": it.get("armSkuName"),
                    "unitOfMeasure": it.get("unitOfMeasure"),
                    "retailPrice": it.get("retailPrice"),
                    "currencyCode": it.get("currencyCode"),
                }
            )

        return json.dumps(
            {
                "service_name": service_name,
                "region": region,
                "currency": currency,
                "skus_count": len(skus),
                "skus": skus,
                "source": _RETAIL_PRICES_API,
                "timestamp": _now_iso(),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return _error_response(e)


@mcp.tool()
def azure_pricing_estimate_monthly_cost(
    resources_json: str,
    currency: str | None = None,
    hours_per_month: float | None = None,
) -> str:
    """
    Calcula custo mensal de uma lista de recursos. Substitui o uso manual
    da Azure Pricing Calculator UI.

    Args:
        resources_json: lista JSON de recursos. Cada item deve conter:
          - service_name (str, obrigatório)
          - region (str, opcional — default .env)
          - sku_name (str, opcional mas recomendado pra precisão)
          - product_name (str, opcional)
          - meter_name (str, opcional)
          - quantity (float, opcional — quantas unidades; default 1.0)
          - hours_per_month (float, opcional — override; pra recursos pausados)
          - label (str, opcional — nome amigável no breakdown)

          Exemplo:
          [
            {"service_name": "Azure AI Search", "sku_name": "Standard S1",
             "region": "brazilsouth", "quantity": 1, "label": "AI Search prod"},
            {"service_name": "Storage", "sku_name": "Standard_LRS",
             "region": "brazilsouth", "quantity": 100, "label": "Storage 100GB"}
          ]

        currency: 3-letter code. Default = .env.
        hours_per_month: override global (730 default).

    Returns:
        JSON com:
          - breakdown por resource
          - subtotals por service_name
          - total mensal + total anual
          - link pra calculadora oficial recriar o cenário
          - flags pra resources sem match (precisam SKU correto)
    """
    try:
        currency = (currency or _default_currency()).upper()
        global_hpm = hours_per_month if hours_per_month is not None else _hours_per_month()

        try:
            resources = json.loads(resources_json)
        except json.JSONDecodeError as e:
            return _error_response(ValueError(f"resources_json inválido: {e}"))

        if not isinstance(resources, list):
            return _error_response(ValueError("resources_json deve ser lista JSON"))

        # ── Validador determinístico de fixed costs ─────────────────────────
        # Bloqueia listas inválidas (ex: Azure Firewall só com data processed).
        # Retorna erro estruturado com a(s) linha(s) faltantes e o preço de
        # referência da tabela embutida. Agente DEVE corrigir e re-chamar.
        violations = _detect_fixed_cost_violations(resources)
        if violations:
            return json.dumps(
                {
                    "error": "fixed_cost_validation_failed",
                    "message": (
                        "Lista de resources inválida: detectados serviços que requerem "
                        "fixed cost de deployment mas só têm consumption/data meter. "
                        "Sem o fixed cost, o total mensal subestima a realidade em "
                        "centenas a milhares de USD/mês. Veja `violations` abaixo e "
                        "adicione as linhas sugeridas ANTES de re-chamar esta tool."
                    ),
                    "violations": violations,
                    "violation_count": len(violations),
                    "remediation_protocol": (
                        "1. Para cada violation: adicione `missing_line_to_add` ao seu "
                        "resources_json. 2. Se a Retail API não retornar match pra esse "
                        "fixed meter, o MCP usará automaticamente "
                        "`_fixed_price_reference_usd_per_hour` da tabela. 3. Re-chame "
                        "`azure_pricing_estimate_monthly_cost` com a lista completa."
                    ),
                    "timestamp": _now_iso(),
                },
                ensure_ascii=False,
                indent=2,
            )

        breakdown = []
        warnings = []
        total = 0.0

        for idx, res in enumerate(resources):
            label = res.get("label") or f"resource_{idx}"
            service = res.get("service_name")
            if not service:
                warnings.append(f"[{label}] sem service_name — pulado")
                continue

            region = (res.get("region") or _default_region()).lower()
            sku = res.get("sku_name")
            product = res.get("product_name")
            meter = res.get("meter_name")
            qty = float(res.get("quantity", 1.0))
            hpm = float(res.get("hours_per_month", global_hpm))

            def _build_filter(reg: str) -> str:
                filters = [f"serviceName eq '{service}'", "priceType eq 'Consumption'"]
                if reg and reg != "global":
                    filters.append(f"armRegionName eq '{reg}'")
                if sku:
                    filters.append(f"skuName eq '{sku}'")
                if product:
                    filters.append(f"productName eq '{product}'")
                if meter:
                    filters.append(f"meterName eq '{meter}'")
                return " and ".join(filters)

            filter_expr = _build_filter(region)
            items = _query_retail_api(filter_expr, currency=currency, max_results=5)
            region_used = region
            cross_region = False

            # Fallback regional automático para serviços com cobertura limitada
            # (Azure OpenAI, alguns Cognitive Services). Tenta regiões alternativas
            # comuns. Microsoft cobra OpenAI por deployment region, então preço
            # de eastus2 é o efetivamente cobrado mesmo cliente em brazilsouth.
            FALLBACK_REGIONS = ["eastus2", "eastus", "westeurope", "northeurope"]
            if not items and service in (
                "Azure OpenAI",
                "Cognitive Services",
                "Azure Cognitive Search",
            ):
                for fb_region in FALLBACK_REGIONS:
                    if fb_region == region:
                        continue
                    fb_items = _query_retail_api(
                        _build_filter(fb_region), currency=currency, max_results=5
                    )
                    if fb_items:
                        items = fb_items
                        region_used = fb_region
                        cross_region = True
                        warnings.append(
                            f"[{label}] sem SKU em {region}, usando preço de {fb_region} "
                            f"(cross-region pricing — Microsoft cobra OpenAI por deployment region)"
                        )
                        break

            if not items:
                # ── Fallback determinístico de fixed costs ──────────────
                # Se a API não retornou match mas o resource é um fixed
                # cost conhecido (Firewall, VPN, App GW, Bastion), usa o
                # valor da tabela embutida em vez de retornar $0.
                fallback_price = _lookup_fixed_cost_fallback(service, sku, meter)
                if fallback_price:
                    monthly_fb = fallback_price["price_usd_per_hour"] * hpm * qty
                    warnings.append(
                        f"[{label}] sem match na API; usando preço determinístico "
                        f"da tabela MCP (${fallback_price['price_usd_per_hour']}/hr "
                        f"para {service} {sku or '<auto>'}). Fonte: KB §13.3."
                    )
                    breakdown.append(
                        {
                            "label": label,
                            "service_name": service,
                            "sku_name": sku,
                            "meter_name": meter or fallback_price["meter_name"],
                            "region_requested": region,
                            "region_used": region,
                            "match_found": True,
                            "source": "deterministic_table_fallback",
                            "unit_price": fallback_price["price_usd_per_hour"],
                            "unit_of_measure": "1 Hour",
                            "quantity": qty,
                            "hours_per_month_applied": hpm,
                            "monthly_cost": round(monthly_fb, 4),
                            "currency": currency,
                        }
                    )
                    total += monthly_fb
                    continue

                warnings.append(
                    f"[{label}] sem match na API com filtros: {filter_expr}. "
                    f"Verifique service_name/sku_name/region — use list_skus."
                )
                breakdown.append(
                    {
                        "label": label,
                        "service_name": service,
                        "sku_name": sku,
                        "region": region,
                        "match_found": False,
                        "monthly_cost": 0.0,
                    }
                )
                continue

            # Usa o primeiro match (filtros bem específicos devem retornar 1)
            item = items[0]
            unit_price = float(item.get("retailPrice", 0.0))
            unit_measure = item.get("unitOfMeasure", "")

            # Calcula custo mensal baseado em unit_of_measure
            #   "1 Hour"      → unit_price * hpm * qty
            #   "1 Month"     → unit_price * qty
            #   "1/Month"     → unit_price * qty
            #   "1 GB-Month"  → unit_price * qty
            #   "1 GB"        → unit_price * qty (consumo único)
            #   "1 Operations" → unit_price * qty
            unit_lower = unit_measure.lower()
            if "hour" in unit_lower:
                monthly = unit_price * hpm * qty
            else:
                # Default: unit é mensal ou single-purchase
                monthly = unit_price * qty

            breakdown.append(
                {
                    "label": label,
                    "service_name": service,
                    "product_name": item.get("productName"),
                    "sku_name": item.get("skuName"),
                    "meter_name": item.get("meterName"),
                    "region_requested": region,
                    "region_used": region_used,
                    "cross_region_pricing": cross_region,
                    "match_found": True,
                    "unit_price": unit_price,
                    "unit_of_measure": unit_measure,
                    "quantity": qty,
                    "hours_per_month_applied": hpm if "hour" in unit_lower else None,
                    "monthly_cost": round(monthly, 4),
                    "currency": currency,
                }
            )
            total += monthly

        # Subtotais por service_name
        subtotals: dict[str, float] = {}
        for b in breakdown:
            if b.get("match_found"):
                svc = b["service_name"]
                subtotals[svc] = subtotals.get(svc, 0.0) + b["monthly_cost"]

        return json.dumps(
            {
                "summary": {
                    "total_monthly": round(total, 2),
                    "total_annual": round(total * 12, 2),
                    "currency": currency,
                    "hours_per_month_default": global_hpm,
                    "resources_count": len(resources),
                    "matched_count": sum(1 for b in breakdown if b.get("match_found")),
                    "unmatched_count": sum(
                        1 for b in breakdown if not b.get("match_found")
                    ),
                },
                "subtotals_by_service": {
                    svc: round(amt, 2) for svc, amt in subtotals.items()
                },
                "breakdown": breakdown,
                "warnings": warnings,
                "source": _RETAIL_PRICES_API,
                "timestamp": _now_iso(),
                "notes": (
                    "Valores casam com Pricing Calculator pra retail. "
                    "Reservations e EA discounts NÃO inclusos — use "
                    "compare_reservation_terms / EA price sheet pra esses."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return _error_response(e)


@mcp.tool()
def azure_pricing_compare_reservation_terms(
    service_name: str,
    sku_name: str | None = None,
    product_name: str | None = None,
    region: str | None = None,
    currency: str | None = None,
) -> str:
    """
    Compara preços Pay-as-you-go vs 1-year RI vs 3-year RI pra um SKU.

    Args:
        service_name: nome do serviço (ex: "Virtual Machines", "Azure Cosmos DB").
        sku_name: SKU específico (ex: "Standard_D4s_v3").
        product_name: produto específico.
        region: default = .env.
        currency: default = .env.

    Returns:
        JSON com comparativo: payg_monthly, ri_1y_monthly, ri_3y_monthly,
        savings_1y_pct, savings_3y_pct, breakeven_months.
    """
    try:
        region = (region or _default_region()).lower()
        currency = (currency or _default_currency()).upper()

        base_filters = [f"serviceName eq '{service_name}'"]
        if region and region != "global":
            base_filters.append(f"armRegionName eq '{region}'")
        if sku_name:
            base_filters.append(f"skuName eq '{sku_name}'")
        if product_name:
            base_filters.append(f"productName eq '{product_name}'")

        results = {}
        for term_label, price_type, term_filter in [
            ("payg", "Consumption", None),
            ("ri_1year", "Reservation", "reservationTerm eq '1 Year'"),
            ("ri_3year", "Reservation", "reservationTerm eq '3 Years'"),
        ]:
            filters = base_filters + [f"priceType eq '{price_type}'"]
            if term_filter:
                filters.append(term_filter)
            filter_expr = " and ".join(filters)
            items = _query_retail_api(filter_expr, currency=currency, max_results=3)
            results[term_label] = items[0] if items else None

        # Normalizar pra custo mensal
        hpm = _hours_per_month()
        monthly = {}
        for k, item in results.items():
            if not item:
                monthly[k] = None
                continue
            price = float(item.get("retailPrice", 0.0))
            unit = item.get("unitOfMeasure", "").lower()
            term = item.get("reservationTerm", "")

            if "hour" in unit:
                monthly[k] = price * hpm
            elif term == "1 Year":
                monthly[k] = price / 12.0  # preço anual → mensal
            elif term == "3 Years":
                monthly[k] = price / 36.0  # preço 3-anos → mensal
            else:
                monthly[k] = price

        # Savings vs PAYG
        payg = monthly.get("payg")
        ri_1y = monthly.get("ri_1year")
        ri_3y = monthly.get("ri_3year")

        savings_1y_pct = (
            round((1 - ri_1y / payg) * 100, 1) if payg and ri_1y else None
        )
        savings_3y_pct = (
            round((1 - ri_3y / payg) * 100, 1) if payg and ri_3y else None
        )

        return json.dumps(
            {
                "query": {
                    "service_name": service_name,
                    "sku_name": sku_name,
                    "product_name": product_name,
                    "region": region,
                    "currency": currency,
                    "hours_per_month": hpm,
                },
                "monthly_cost": {
                    "payg": round(payg, 2) if payg is not None else None,
                    "ri_1year": round(ri_1y, 2) if ri_1y is not None else None,
                    "ri_3year": round(ri_3y, 2) if ri_3y is not None else None,
                },
                "savings_vs_payg": {
                    "ri_1year_pct": savings_1y_pct,
                    "ri_3year_pct": savings_3y_pct,
                },
                "raw_items": results,
                "source": _RETAIL_PRICES_API,
                "timestamp": _now_iso(),
                "notes": (
                    "Reservations exigem commitment (1 ou 3 anos). "
                    "Quebra de contrato pode ter penalidade. "
                    "Savings plans (alternativa) são mais flexíveis — use savings_plan_calc."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return _error_response(e)


@mcp.tool()
def azure_pricing_savings_plan_calc(
    hourly_commitment_usd: float,
    actual_usage_hours: float,
    term_years: int = 1,
) -> str:
    """
    Calcula o ROI de um Azure Savings Plan dado o commitment e uso real.

    Savings plans dão até 65% de desconto sobre compute (vs PAYG) em troca
    de commitment hourly fixo por 1 ou 3 anos. Modelo:
      - Commit $X/hora durante N anos
      - Microsoft aplica $X de crédito por hora consumida
      - Excesso de uso é cobrado em PAYG normal
      - Underuse: $X/hora cobrado mesmo se não usar (waste)

    Args:
        hourly_commitment_usd: quanto está comprometendo $/hora (ex: 5.00).
        actual_usage_hours: horas que você de fato usa por mês.
        term_years: 1 ou 3.

    Returns:
        JSON com: monthly_commitment, monthly_actual_use, savings_estimated,
        breakeven_hours, recommendation (good_fit / overcommitted / undercommitted).
    """
    try:
        hpm = _hours_per_month()
        monthly_commit = hourly_commitment_usd * hpm
        monthly_actual = hourly_commitment_usd * min(actual_usage_hours, hpm)
        waste = monthly_commit - monthly_actual if monthly_actual < monthly_commit else 0
        # Discount típico do savings plan
        discount_pct = 0.20 if term_years == 1 else 0.40
        savings_estimated = monthly_actual * discount_pct
        # Recomendação
        utilization = monthly_actual / monthly_commit if monthly_commit > 0 else 0
        if utilization < 0.7:
            recommendation = "overcommitted"
            recommendation_detail = (
                f"Utilização {utilization*100:.0f}% — está pagando por horas que não usa. "
                "Reduza o commit ou considere PAYG."
            )
        elif utilization > 0.95:
            recommendation = "good_fit"
            recommendation_detail = (
                f"Utilização {utilization*100:.0f}% — savings plan compensa."
            )
        else:
            recommendation = "monitor"
            recommendation_detail = (
                f"Utilização {utilization*100:.0f}% — savings plan compensa "
                "mas há folga; monitore tendência."
            )

        return json.dumps(
            {
                "inputs": {
                    "hourly_commitment_usd": hourly_commitment_usd,
                    "actual_usage_hours_per_month": actual_usage_hours,
                    "term_years": term_years,
                    "hours_per_month": hpm,
                },
                "calculation": {
                    "monthly_commitment_paid": round(monthly_commit, 2),
                    "monthly_actual_use_value": round(monthly_actual, 2),
                    "monthly_waste": round(waste, 2),
                    "utilization_pct": round(utilization * 100, 1),
                    "discount_pct_assumed": discount_pct * 100,
                    "estimated_monthly_savings_vs_payg": round(savings_estimated, 2),
                    "annual_savings": round(savings_estimated * 12, 2),
                },
                "recommendation": recommendation,
                "recommendation_detail": recommendation_detail,
                "timestamp": _now_iso(),
                "notes": (
                    "Cálculo aproximado — discount real varia por SKU. "
                    "Para análise precisa, consulte o Savings Plan Recommender no portal."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return _error_response(e)


@mcp.tool()
def azure_pricing_currency_convert(
    amount: float,
    from_currency: str = "USD",
    to_currency: str = "BRL",
) -> str:
    """
    Converte valor entre currencies usando a taxa atual da Azure Retail Prices API
    (mesma rate que a calculadora usa, então valores batem).

    Args:
        amount: valor a converter.
        from_currency: 3-letter code de origem.
        to_currency: 3-letter code de destino.

    Returns:
        JSON com amount_original, amount_converted, exchange_rate, timestamp.
    """
    try:
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        if from_currency == to_currency:
            return json.dumps(
                {
                    "amount_original": amount,
                    "amount_converted": amount,
                    "from_currency": from_currency,
                    "to_currency": to_currency,
                    "exchange_rate": 1.0,
                    "timestamp": _now_iso(),
                },
                ensure_ascii=False,
                indent=2,
            )

        # Estratégia: tenta múltiplos SKUs de referência até achar um que esteja
        # disponível em AMBAS as currencies. Bandwidth é universal (sempre tem
        # em todas as currencies suportadas pela Azure); Storage e VMs também.
        REFERENCE_SKUS = [
            # Bandwidth (egress) — universal
            (
                "serviceName eq 'Bandwidth' and meterName eq 'Data Transfer Out' "
                "and priceType eq 'Consumption'"
            ),
            # Storage Standard_LRS em eastus (cobertura ampla)
            (
                "serviceName eq 'Storage' and armRegionName eq 'eastus' "
                "and skuName eq 'Standard_LRS' and priceType eq 'Consumption'"
            ),
            # VM B1s (smallest VM, sempre disponível)
            (
                "serviceName eq 'Virtual Machines' and armRegionName eq 'eastus' "
                "and skuName eq 'B1s' and priceType eq 'Consumption'"
            ),
        ]

        rate = None
        rate_source_info = None
        for ref_filter in REFERENCE_SKUS:
            items_from = _query_retail_api(
                ref_filter, currency=from_currency, max_results=1
            )
            items_to = _query_retail_api(
                ref_filter, currency=to_currency, max_results=1
            )

            if items_from and items_to:
                price_from = float(items_from[0].get("retailPrice", 0.0))
                price_to = float(items_to[0].get("retailPrice", 0.0))
                if price_from > 0 and price_to > 0:
                    rate = price_to / price_from
                    rate_source_info = (
                        f"Derived from {items_from[0].get('serviceName')} / "
                        f"{items_from[0].get('skuName') or items_from[0].get('meterName')} "
                        f"({from_currency} {price_from:.6f} vs {to_currency} {price_to:.6f})"
                    )
                    break

        if rate is None:
            return _error_response(
                RuntimeError(
                    f"Não foi possível obter rate {from_currency}→{to_currency} "
                    f"de nenhum SKU de referência. Currencies suportadas Azure: "
                    f"USD, EUR, GBP, BRL, JPY, CAD, AUD, INR, etc. "
                    f"Verifique se '{to_currency}' está correto."
                )
            )

        converted = amount * rate

        return json.dumps(
            {
                "amount_original": amount,
                "amount_converted": round(converted, 2),
                "from_currency": from_currency,
                "to_currency": to_currency,
                "exchange_rate": round(rate, 6),
                "rate_source": rate_source_info,
                "timestamp": _now_iso(),
                "notes": (
                    "Rate é a MESMA que a Azure Pricing Calculator usa. "
                    "Microsoft atualiza periodicamente (diariamente), não em "
                    "tempo real. Pequenas variações vs Banco Central esperadas."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return _error_response(e)


@mcp.tool()
def azure_pricing_list_regions() -> str:
    """
    Lista todas as arm region names suportadas pela Retail Prices API.
    Útil quando o usuário não sabe o slug exato da região.

    Returns:
        JSON com lista de regiões agrupadas por geografia.
    """
    try:
        # Lista hard-coded das regiões principais (a API não tem endpoint de listing)
        regions = {
            "Brazil": ["brazilsouth", "brazilsoutheast"],
            "US": [
                "centralus",
                "eastus",
                "eastus2",
                "northcentralus",
                "southcentralus",
                "westcentralus",
                "westus",
                "westus2",
                "westus3",
            ],
            "Canada": ["canadacentral", "canadaeast"],
            "Mexico": ["mexicocentral"],
            "Europe": [
                "northeurope",
                "westeurope",
                "francecentral",
                "francesouth",
                "germanywestcentral",
                "germanynorth",
                "italynorth",
                "norwayeast",
                "norwaywest",
                "polandcentral",
                "spaincentral",
                "swedencentral",
                "swedensouth",
                "switzerlandnorth",
                "switzerlandwest",
                "uksouth",
                "ukwest",
            ],
            "Asia Pacific": [
                "australiacentral",
                "australiaeast",
                "australiasoutheast",
                "centralindia",
                "southindia",
                "westindia",
                "eastasia",
                "southeastasia",
                "japaneast",
                "japanwest",
                "koreacentral",
                "koreasouth",
            ],
            "Middle East / Africa": [
                "uaecentral",
                "uaenorth",
                "qatarcentral",
                "southafricanorth",
                "southafricawest",
                "israelcentral",
            ],
            "Global / Non-regional": ["global"],
        }
        return json.dumps(
            {
                "regions_by_geography": regions,
                "total_regions": sum(len(v) for v in regions.values()),
                "default_region": _default_region(),
                "timestamp": _now_iso(),
                "notes": (
                    "Use 'global' pra serviços sem região (Entra ID, etc). "
                    "Nem todos SKUs estão em todas regiões — confirme com list_skus."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return _error_response(e)


@mcp.tool()
def azure_pricing_generate_calculator_url(
    resources_json: str,
) -> str:
    """
    Gera URL da Azure Pricing Calculator oficial pra recriar o cenário manualmente.
    Útil pra auditabilidade — usuário pode validar os números no portal.

    Args:
        resources_json: mesma estrutura de estimate_monthly_cost (lista JSON).

    Returns:
        JSON com a URL base da calculadora + lista de items a adicionar manualmente
        (a calculadora não suporta deep link pra cenários completos, mas pode-se
         pré-selecionar produtos via query param).
    """
    try:
        try:
            resources = json.loads(resources_json)
        except json.JSONDecodeError as e:
            return _error_response(ValueError(f"resources_json inválido: {e}"))

        service_to_calc_product = {
            "Azure OpenAI": "cognitive-services",
            "Cognitive Services": "cognitive-services",
            "Azure AI Search": "search",
            "Storage": "storage",
            "Azure Cosmos DB": "cosmos-db",
            "Virtual Machines": "virtual-machines",
            "Microsoft Fabric": "microsoft-fabric",
            "Functions": "functions",
            "App Service": "app-service",
            "Key Vault": "key-vault",
        }

        suggested_urls = []
        for res in resources:
            svc = res.get("service_name", "")
            calc_slug = service_to_calc_product.get(svc, "")
            url = f"{_PRICING_CALCULATOR_BASE}"
            if calc_slug:
                url = f"{_PRICING_CALCULATOR_BASE}#products={calc_slug}"
            suggested_urls.append(
                {
                    "label": res.get("label", svc),
                    "service_name": svc,
                    "sku_name": res.get("sku_name"),
                    "region": res.get("region", _default_region()),
                    "calculator_url": url,
                }
            )

        return json.dumps(
            {
                "calculator_base_url": _PRICING_CALCULATOR_BASE,
                "resources_to_add_manually": suggested_urls,
                "instructions": [
                    "1. Abra o calculator_url de cada resource",
                    "2. Selecione região + SKU exatos retornados pelo MCP",
                    "3. Valor mensal deve casar com monthly_cost do MCP "
                    "(delta máx 0.5% por timing de currency)",
                ],
                "timestamp": _now_iso(),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return _error_response(e)


# ─── Entry Point ─────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()
