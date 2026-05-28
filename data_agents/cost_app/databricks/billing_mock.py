"""
Mock generator de DataFrames system.billing.* — para dev/test sem Databricks.

Gera dados sintéticos com características realistas:
  - 30 dias por padrão (configurável)
  - 4 SKUs típicos (JOBS Premium, ALL_PURPOSE Premium, SQL, SERVERLESS)
  - 5 clusters fictícios com nomes plausíveis
  - Variância controlada: jobs > all_purpose > sql > serverless em DBU médio
  - Weekend dip (sex/sáb/dom têm ~40% do consumo de dias úteis)
  - Determinístico via seed (reprodutível em testes)

Compatibilidade com o engine `billing.py`:
  - Schema usage_df: usage_date, workspace_id, sku_name, usage_quantity,
    usage_unit, cloud, cluster_id, cluster_name
    (cluster_id/cluster_name já extraídos do usage_metadata, como o SQL real
    faria via dot notation usage_metadata.cluster_id)
  - Schema prices_df: sku_name, cloud, currency_code, price_per_dbu,
    price_start_time, price_end_time
    (price_per_dbu já extraído de pricing.default)

NÃO usar este módulo em produção — só dev/test. O `DATABRICKS_BILLING_MOCK_MODE`
em settings.py controla quando o MCP server usa mock vs SQL real.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


# ─── Catalog determinístico (consistente com data/databricks_pricing/azure.yaml) ──

# SKUs realistas que casam com o schema system.billing.usage.
# Valores price_per_dbu confirmados no kb/databricks-pricing/concepts/dbu-model.md.
# PR 1 fix 2026-05-28: PREMIUM_SERVERLESS_COMPUTE_* era $0.95 (fictício),
# corrigido para $0.35 (Jobs Serverless real, /product/pricing/lakeflow-jobs).
# PR 2 vai adicionar SKUs distintas pra DLT/SQL/All-Purpose Serverless.
_MOCK_SKUS_AZURE: tuple[tuple[str, float, float], ...] = (
    # (sku_name, price_per_dbu, baseline_daily_dbus_per_cluster)
    ("PREMIUM_JOBS_COMPUTE_AZURE", 0.20, 12.0),
    ("PREMIUM_ALL_PURPOSE_COMPUTE_AZURE", 0.55, 6.0),
    ("PREMIUM_SQL_PRO_COMPUTE_AZURE", 0.22, 4.0),
    ("PREMIUM_SERVERLESS_COMPUTE_AZURE", 0.35, 3.0),
)

_MOCK_SKUS_AWS: tuple[tuple[str, float, float], ...] = (
    ("PREMIUM_JOBS_COMPUTE_AWS", 0.10, 12.0),
    ("PREMIUM_ALL_PURPOSE_COMPUTE_AWS", 0.55, 6.0),
    ("PREMIUM_SQL_PRO_COMPUTE_AWS", 0.22, 4.0),
    ("PREMIUM_SERVERLESS_COMPUTE_AWS", 0.35, 3.0),
)

# Clusters fictícios com nomes plausíveis (ETL Bronze é o canonical do projeto).
# job_id/cluster_id são hashes determinísticos do nome para serem estáveis entre runs.
_MOCK_CLUSTER_NAMES: tuple[str, ...] = (
    "etl-bronze-prod",
    "etl-silver-prod",
    "ml-training-prod",
    "ad-hoc-analytics",
    "dlt-streaming",
)


def _cluster_id_for(name: str) -> str:
    """Gera um cluster_id estável a partir do nome (mimicks Databricks IDs)."""
    h = hashlib.sha256(name.encode("utf-8")).hexdigest()
    # Formato Databricks: "0123-456789-abcdef01"
    return f"{h[:4]}-{h[4:10]}-{h[10:18]}"


def _is_weekend(d: date) -> bool:
    """Sexta, sábado, domingo = weekend (dip de consumo). weekday() retorna
    0=segunda, 6=domingo. Sex=4, Sab=5, Dom=6."""
    return d.weekday() >= 4


# ─── Generators ─────────────────────────────────────────────────────────────


def generate_mock_usage_df(
    days: int = 30,
    workspace_id: int = 1234567890123456,
    cloud: str = "AZURE",
    seed: int = 42,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Gera DataFrame fake de system.billing.usage com `days` dias de histórico.

    Args:
        days: número de dias de histórico (padrão 30). end_date - days + 1 = start.
        workspace_id: ID do workspace pra preencher (igual em todos os rows).
        cloud: "AZURE" ou "AWS". Determina o pool de SKUs.
        seed: seed pro random pra reprodutibilidade.
        end_date: data final inclusiva (default = today UTC).

    Returns:
        DataFrame com colunas: usage_date, workspace_id, sku_name, usage_quantity,
        usage_unit, cloud, cluster_id, cluster_name.

    Premissas:
        - jobs_compute domina (40% do total estimado)
        - weekend dip de 60% nos dias sex/sáb/dom
        - 5 clusters, cada um ativo em ~60% dos dias (não 100%)
        - usage_quantity tem ruído ±20% multiplicativo
    """
    import pandas as pd

    if end_date is None:
        end_date = datetime.now(timezone.utc).date()

    skus = _MOCK_SKUS_AZURE if cloud.upper() == "AZURE" else _MOCK_SKUS_AWS
    rng = random.Random(seed)

    rows: list[dict] = []
    for day_offset in range(days):
        usage_date = end_date - timedelta(days=days - 1 - day_offset)
        weekend_factor = 0.4 if _is_weekend(usage_date) else 1.0

        for cluster_name in _MOCK_CLUSTER_NAMES:
            cluster_id = _cluster_id_for(cluster_name)

            # Cluster pode estar inativo ~40% dos dias (mimicks intermitência real)
            if rng.random() < 0.4:
                continue

            # Cada cluster usa 1-2 SKUs (não todos)
            num_skus_for_cluster = rng.randint(1, 2)
            chosen_skus = rng.sample(skus, num_skus_for_cluster)

            for sku_name, _price, baseline_dbus in chosen_skus:
                # Variância ±20% multiplicativa
                noise = rng.uniform(0.8, 1.2)
                quantity = round(baseline_dbus * weekend_factor * noise, 2)
                if quantity <= 0:
                    continue
                rows.append(
                    {
                        "usage_date": usage_date,
                        "workspace_id": workspace_id,
                        "sku_name": sku_name,
                        "usage_quantity": quantity,
                        "usage_unit": "DBU",
                        "cloud": cloud.upper(),
                        "cluster_id": cluster_id,
                        "cluster_name": cluster_name,
                    }
                )

    df = pd.DataFrame(rows)
    if df.empty:
        # Fallback raro: garante schema mesmo se random sortear inatividade total
        df = pd.DataFrame(
            columns=[
                "usage_date",
                "workspace_id",
                "sku_name",
                "usage_quantity",
                "usage_unit",
                "cloud",
                "cluster_id",
                "cluster_name",
            ]
        )
    return df


def generate_mock_list_prices_df(cloud: str = "AZURE") -> pd.DataFrame:
    """Gera DataFrame fake de system.billing.list_prices.

    Args:
        cloud: "AZURE" ou "AWS".

    Returns:
        DataFrame com colunas: sku_name, cloud, currency_code, price_per_dbu,
        price_start_time (sempre 2024-01-01), price_end_time (sempre None — vigente).
    """
    import pandas as pd

    skus = _MOCK_SKUS_AZURE if cloud.upper() == "AZURE" else _MOCK_SKUS_AWS
    rows = [
        {
            "sku_name": sku_name,
            "cloud": cloud.upper(),
            "currency_code": "USD",
            "price_per_dbu": price,
            "price_start_time": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "price_end_time": None,  # vigente
        }
        for sku_name, price, _baseline in skus
    ]
    return pd.DataFrame(rows)


def get_mock_metadata() -> dict:
    """Retorna metadata do mock pra diagnostics (mock_mode true/false).

    Espelha a interface de `instance_prices.get_mock_metadata()` da Fase 1
    pra consistência no App.
    """
    return {
        "is_mock": True,
        "days_default": 30,
        "clouds_supported": ["AZURE", "AWS"],
        "num_skus_per_cloud": len(_MOCK_SKUS_AZURE),
        "num_clusters": len(_MOCK_CLUSTER_NAMES),
        "cluster_names": list(_MOCK_CLUSTER_NAMES),
        "seed_default": 42,
        "note": (
            "Mock determinístico via seed. Use DATABRICKS_BILLING_MOCK_MODE=false "
            "no .env pra rodar SQL real contra system.billing (requer Unity Catalog + admin)."
        ),
    }
