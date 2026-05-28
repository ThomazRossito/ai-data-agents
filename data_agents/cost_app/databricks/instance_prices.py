"""
Instance prices mock — estimativas estáticas USD/hora pra instances Azure/AWS.

⚠️ MOCK PARA MVP: valores estimados de prazo 2026-05. Não usar em cotação
real sem confirmar contra Azure Retail Prices API ou AWS Pricing API.

Na Fase 2, o MCP `databricks_pricing` substitui esse módulo por chamadas
em runtime às APIs oficiais:
  - Azure: https://prices.azure.com/api/retail/prices
  - AWS: https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/

Estrutura:
  PRICES[cloud][region][instance_sku] = price_usd_per_hour

Os valores aqui são approximate retail on-demand pricing. Para spot/reserved
o desconto vem do catalog YAML (data/databricks_pricing/{azure,aws}.yaml),
aplicado no cost_engine.
"""

from __future__ import annotations

from typing import Literal

CloudName = Literal["azure", "aws"]


# ─── Azure Retail Prices estimados ──────────────────────────────────────────
# Fontes: Azure Calculator + Retail Prices API spot-checks em 2026-05
# Region multiplier: Brazil South ~25% mais caro que US East
# =============================================================================

_AZURE_PRICES_USD_HOUR: dict[str, dict[str, float]] = {
    "eastus": {
        # General Purpose DSv2
        "Standard_DS3_v2": 0.229,
        "Standard_DS4_v2": 0.458,
        "Standard_DS5_v2": 0.916,
        # Memory Optimized DSv2
        "Standard_DS12_v2": 0.371,
        "Standard_DS13_v2": 0.741,
        "Standard_DS14_v2": 1.482,
        "Standard_DS15_v2": 1.853,
        # Memory Optimized Eds_v4
        "Standard_E4ds_v4": 0.252,
        "Standard_E8ds_v4": 0.504,
        "Standard_E16ds_v4": 1.008,
        "Standard_E32ds_v4": 2.016,
        "Standard_E64ds_v4": 4.032,
        # Compute Optimized Fs_v2
        "Standard_F4s_v2": 0.169,
        "Standard_F8s_v2": 0.338,
        "Standard_F16s_v2": 0.677,
        "Standard_F32s_v2": 1.354,
        "Standard_F64s_v2": 2.707,
        "Standard_F72s_v2": 3.045,
        # Storage Optimized Ls_v2
        "Standard_L8s_v2": 0.696,
        "Standard_L16s_v2": 1.392,
        "Standard_L32s_v2": 2.784,
        "Standard_L64s_v2": 5.568,
        "Standard_L80s_v2": 6.960,
        # GPU NC-series v3
        "Standard_NC6s_v3": 3.060,
        "Standard_NC12s_v3": 6.120,
        "Standard_NC24s_v3": 12.240,
    },
    "brazilsouth": {
        # Brazil South ~25-30% premium vs US East (electricity + tax)
        "Standard_DS3_v2": 0.286,
        "Standard_DS4_v2": 0.526,
        "Standard_DS5_v2": 1.144,
        "Standard_DS12_v2": 0.464,
        "Standard_DS13_v2": 0.928,
        "Standard_DS14_v2": 1.856,
        "Standard_DS15_v2": 2.320,
        "Standard_E4ds_v4": 0.315,
        "Standard_E8ds_v4": 0.630,
        "Standard_E16ds_v4": 1.260,
        "Standard_E32ds_v4": 2.520,
        "Standard_E64ds_v4": 5.040,
        "Standard_F4s_v2": 0.212,
        "Standard_F8s_v2": 0.424,
        "Standard_F16s_v2": 0.848,
        "Standard_F32s_v2": 1.696,
        "Standard_F64s_v2": 3.392,
        "Standard_F72s_v2": 3.816,
        "Standard_L8s_v2": 0.872,
        "Standard_L16s_v2": 1.744,
        "Standard_L32s_v2": 3.488,
        "Standard_L64s_v2": 6.976,
        "Standard_L80s_v2": 8.720,
        "Standard_NC6s_v3": 3.825,
        "Standard_NC12s_v3": 7.650,
        "Standard_NC24s_v3": 15.300,
    },
    "westeurope": {
        "Standard_DS3_v2": 0.245,
        "Standard_DS4_v2": 0.490,
        "Standard_DS5_v2": 0.980,
        "Standard_DS12_v2": 0.397,
        "Standard_DS13_v2": 0.793,
        "Standard_DS14_v2": 1.586,
        "Standard_DS15_v2": 1.983,
        "Standard_E4ds_v4": 0.270,
        "Standard_E8ds_v4": 0.539,
        "Standard_E16ds_v4": 1.078,
        "Standard_E32ds_v4": 2.157,
        "Standard_E64ds_v4": 4.314,
        "Standard_F4s_v2": 0.181,
        "Standard_F8s_v2": 0.362,
        "Standard_F16s_v2": 0.724,
        "Standard_F32s_v2": 1.448,
        "Standard_F64s_v2": 2.897,
        "Standard_L8s_v2": 0.745,
        "Standard_L16s_v2": 1.490,
        "Standard_L32s_v2": 2.979,
        "Standard_L64s_v2": 5.958,
        "Standard_NC6s_v3": 3.273,
        "Standard_NC12s_v3": 6.546,
        "Standard_NC24s_v3": 13.092,
    },
}

# ─── AWS EC2 On-Demand estimados ────────────────────────────────────────────
# Fontes: AWS Pricing Calculator spot-checks em 2026-05
# São Paulo (sa-east-1) ~50% mais caro que us-east-1
# =============================================================================

_AWS_PRICES_USD_HOUR: dict[str, dict[str, float]] = {
    "us-east-1": {
        # General Purpose M5
        "m5.large": 0.096,
        "m5.xlarge": 0.192,
        "m5.2xlarge": 0.384,
        "m5.4xlarge": 0.768,
        "m5.8xlarge": 1.536,
        "m5.12xlarge": 2.304,
        "m5.16xlarge": 3.072,
        "m5.24xlarge": 4.608,
        # Graviton M6g
        "m6g.xlarge": 0.154,
        "m6g.2xlarge": 0.308,
        "m6g.4xlarge": 0.616,
        # Memory Optimized R5
        "r5.xlarge": 0.252,
        "r5.2xlarge": 0.504,
        "r5.4xlarge": 1.008,
        "r5.8xlarge": 2.016,
        "r5.12xlarge": 3.024,
        "r5.16xlarge": 4.032,
        # Memory Optimized R6i / R6id
        "r6i.xlarge": 0.252,
        "r6i.2xlarge": 0.504,
        "r6i.4xlarge": 1.008,
        "r6id.xlarge": 0.302,
        "r6id.2xlarge": 0.605,
        "r6id.4xlarge": 1.210,
        # Compute Optimized C5
        "c5.xlarge": 0.170,
        "c5.2xlarge": 0.340,
        "c5.4xlarge": 0.680,
        "c5.9xlarge": 1.530,
        "c5.12xlarge": 2.040,
        "c5.18xlarge": 3.060,
        "c5.24xlarge": 4.080,
        # Storage Optimized I3
        "i3.xlarge": 0.312,
        "i3.2xlarge": 0.624,
        "i3.4xlarge": 1.248,
        "i3.8xlarge": 2.496,
        "i3.16xlarge": 4.992,
        # GPU
        "p3.2xlarge": 3.060,
        "p3.8xlarge": 12.240,
        "p3.16xlarge": 24.480,
        "g4dn.xlarge": 0.526,
        "g4dn.4xlarge": 1.204,
        "g4dn.12xlarge": 3.912,
        "g5.xlarge": 1.006,
        "g5.4xlarge": 1.624,
        "g5.12xlarge": 5.672,
    },
    "us-west-2": {
        # us-west-2 = us-east-1 prices (paridade)
        "m5.large": 0.096,
        "m5.xlarge": 0.192,
        "m5.2xlarge": 0.384,
        "m5.4xlarge": 0.768,
        "m5.8xlarge": 1.536,
        "m5.12xlarge": 2.304,
        "m5.16xlarge": 3.072,
        "m5.24xlarge": 4.608,
        "r5.xlarge": 0.252,
        "r5.2xlarge": 0.504,
        "r5.4xlarge": 1.008,
        "r5.8xlarge": 2.016,
        "r5.12xlarge": 3.024,
        "r5.16xlarge": 4.032,
        "c5.xlarge": 0.170,
        "c5.2xlarge": 0.340,
        "c5.4xlarge": 0.680,
        "c5.9xlarge": 1.530,
        "i3.xlarge": 0.312,
        "i3.2xlarge": 0.624,
        "i3.4xlarge": 1.248,
        "g4dn.xlarge": 0.526,
        "g5.xlarge": 1.006,
    },
    "sa-east-1": {
        # São Paulo ~50% premium vs us-east-1
        "m5.large": 0.143,
        "m5.xlarge": 0.286,
        "m5.2xlarge": 0.571,
        "m5.4xlarge": 1.142,
        "m5.8xlarge": 2.285,
        "m5.12xlarge": 3.427,
        "m5.16xlarge": 4.570,
        "m5.24xlarge": 6.854,
        "r5.xlarge": 0.376,
        "r5.2xlarge": 0.752,
        "r5.4xlarge": 1.503,
        "r5.8xlarge": 3.006,
        "r5.12xlarge": 4.509,
        "r5.16xlarge": 6.012,
        "c5.xlarge": 0.253,
        "c5.2xlarge": 0.507,
        "c5.4xlarge": 1.013,
        "c5.9xlarge": 2.280,
        "i3.xlarge": 0.466,
        "i3.2xlarge": 0.932,
        "i3.4xlarge": 1.864,
        "i3.8xlarge": 3.728,
        "g4dn.xlarge": 0.784,
        "g4dn.4xlarge": 1.793,
        "g5.xlarge": 1.499,
    },
    "eu-west-1": {
        "m5.large": 0.107,
        "m5.xlarge": 0.214,
        "m5.2xlarge": 0.428,
        "m5.4xlarge": 0.856,
        "m5.8xlarge": 1.712,
        "m5.12xlarge": 2.568,
        "m5.16xlarge": 3.424,
        "r5.xlarge": 0.281,
        "r5.2xlarge": 0.561,
        "r5.4xlarge": 1.122,
        "c5.xlarge": 0.190,
        "c5.2xlarge": 0.380,
        "i3.xlarge": 0.347,
        "i3.2xlarge": 0.694,
        "g4dn.xlarge": 0.585,
    },
    "eu-central-1": {
        "m5.large": 0.115,
        "m5.xlarge": 0.230,
        "m5.2xlarge": 0.460,
        "m5.4xlarge": 0.920,
        "m5.8xlarge": 1.840,
        "r5.xlarge": 0.302,
        "r5.2xlarge": 0.605,
        "r5.4xlarge": 1.210,
        "c5.xlarge": 0.204,
        "c5.2xlarge": 0.408,
        "i3.xlarge": 0.373,
        "g4dn.xlarge": 0.628,
    },
}


# ─── Public API ──────────────────────────────────────────────────────────────


def _get_mock_price(cloud: str, region: str, instance_sku: str) -> float:
    """Fetch interno do mock (sem real mode). Usado como fallback do real loader."""
    if cloud == "azure":
        prices = _AZURE_PRICES_USD_HOUR
    elif cloud == "aws":
        prices = _AWS_PRICES_USD_HOUR
    else:
        raise ValueError(f"Cloud desconhecida: {cloud!r}")

    region_prices = prices.get(region)
    if region_prices is None:
        raise KeyError(
            f"Region {region!r} não está no mock de {cloud!r}. Disponíveis: {sorted(prices.keys())}"
        )

    price = region_prices.get(instance_sku)
    if price is None:
        raise KeyError(
            f"Instance SKU {instance_sku!r} não está no mock de {cloud!r}/{region!r}. "
            f"Disponíveis: {sorted(region_prices.keys())[:5]}..."
        )

    return price


def get_instance_price_usd_per_hour(
    cloud: CloudName,
    region: str,
    instance_sku: str,
) -> float:
    """
    Retorna preço USD/hora on-demand pra um instance SKU numa cloud+region.

    **Modo de operação** (controlado via `DATABRICKS_INSTANCE_PRICES_MODE` no .env):
      - `mock` (default): valores estáticos hardcoded — útil pra dev/test sem rede
      - `real`: queries via Azure Retail Prices API (público, sem auth) e
        AWS Pricing API (requer AWS credentials). Fallback transparente pro
        mock se API falhar (network, auth, region não suportada).

    Args:
        cloud: "azure" ou "aws"
        region: region id (ex: "brazilsouth", "us-east-1")
        instance_sku: SKU completo (ex: "Standard_DS4_v2", "m5.xlarge")

    Returns:
        Preço USD/hora on-demand (sem desconto).

    Raises:
        KeyError: se cloud/region/sku não encontrado no mock E API falhou.
        ValueError: se cloud inválido.
    """
    # Tenta real mode quando habilitado; fallback transparente pro mock
    from data_agents.cost_app.databricks.instance_prices_real import (
        get_instance_price_real_or_mock,
    )

    price, _source = get_instance_price_real_or_mock(
        cloud=cloud, region=region, sku_name=instance_sku, mock_fallback_fn=_get_mock_price
    )
    return price


def list_instances_for_region(cloud: CloudName, region: str) -> list[str]:
    """Lista todos os instance SKUs disponíveis no mock pra uma region."""
    if cloud == "azure":
        prices = _AZURE_PRICES_USD_HOUR
    elif cloud == "aws":
        prices = _AWS_PRICES_USD_HOUR
    else:
        raise ValueError(f"Cloud desconhecida: {cloud!r}")

    region_prices = prices.get(region, {})
    return sorted(region_prices.keys())


def list_regions_for_cloud(cloud: CloudName) -> list[str]:
    """Lista todas as regions disponíveis no mock pra uma cloud."""
    if cloud == "azure":
        return sorted(_AZURE_PRICES_USD_HOUR.keys())
    if cloud == "aws":
        return sorted(_AWS_PRICES_USD_HOUR.keys())
    raise ValueError(f"Cloud desconhecida: {cloud!r}")


def get_mock_metadata() -> dict[str, object]:
    """Retorna metadata sobre o mock — pra mostrar no UI."""
    return {
        "is_mock": True,
        "last_updated": "2026-05",
        "source_notes": "Estimativas estáticas baseadas em portais de pricing (Azure Calculator + AWS Calculator). Não usar pra cotação real sem validar contra APIs oficiais.",
        "azure_regions_count": len(_AZURE_PRICES_USD_HOUR),
        "aws_regions_count": len(_AWS_PRICES_USD_HOUR),
        "total_skus_azure": sum(len(v) for v in _AZURE_PRICES_USD_HOUR.values()),
        "total_skus_aws": sum(len(v) for v in _AWS_PRICES_USD_HOUR.values()),
    }
