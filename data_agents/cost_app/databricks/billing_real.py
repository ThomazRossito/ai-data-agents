"""
Real mode loader — system.billing.usage + list_prices via databricks-sdk.

Substitui o `RuntimeError` placeholder do Chunk 3.1 por integração real com
Unity Catalog. Mantém a mesma assinatura `(usage_df, prices_df)` que o mock
para que o engine `cost_engine.billing` continue agnóstico da fonte.

Estratégia:
  - `databricks.sdk.WorkspaceClient` autentica via DATABRICKS_HOST + TOKEN
  - `client.statement_execution.execute_statement(...)` roda SQL via warehouse
  - Polling do statement até COMPLETED ou erro
  - Resultado convertido pra pandas DataFrame
  - Cache em memória por (cloud, days_back) — TTL 5 min — evita queries repetidas

Schema retornado é IDÊNTICO ao do `billing_mock.py`:
  - usage_df: usage_date, workspace_id, sku_name, usage_quantity, usage_unit,
    cloud, cluster_id, cluster_name (extraído de usage_metadata.cluster_id)
  - prices_df: sku_name, cloud, currency_code, price_per_dbu (extraído de
    pricing.default), price_start_time, price_end_time

Requer (validado no `_validate_config`):
  - DATABRICKS_HOST + DATABRICKS_TOKEN (.env do projeto)
  - DATABRICKS_BILLING_WAREHOUSE_ID (warehouse pra rodar SQL)
  - Unity Catalog habilitado + USE CATALOG system + SELECT em system.billing

Sem credenciais válidas → RuntimeError descritivo (mais informativo que o
placeholder original — mostra qual variável está faltando).
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger("databricks_billing.real")


# ─── Configuração ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RealModeConfig:
    """Configuração necessária pra rodar SQL real contra system.billing.

    Carregada de env vars (priorizado) ou settings (fallback). Não armazena
    tokens — só nomes de variáveis e flags.
    """

    host: str
    token: str
    warehouse_id: str
    statement_timeout_seconds: int = 60
    poll_interval_seconds: float = 0.5

    @classmethod
    def from_env(cls) -> RealModeConfig:
        """Carrega de env vars. Usado pelo MCP server stdio."""
        host = os.environ.get("DATABRICKS_HOST", "").strip()
        token = os.environ.get("DATABRICKS_TOKEN", "").strip()
        warehouse_id = os.environ.get("DATABRICKS_BILLING_WAREHOUSE_ID", "").strip()

        if not host:
            raise RuntimeError(
                "DATABRICKS_HOST não configurado. Setar no .env do projeto "
                "(ex: https://adb-xxx.azuredatabricks.net)."
            )
        if not token:
            raise RuntimeError(
                "DATABRICKS_TOKEN não configurado. Gerar PAT em "
                "User Settings → Developer → Access Tokens, e setar no .env."
            )
        if not warehouse_id:
            raise RuntimeError(
                "DATABRICKS_BILLING_WAREHOUSE_ID não configurado. "
                "Setar no .env com o ID de um SQL Warehouse (Pro ou Serverless) "
                "com SELECT em system.billing. Veja Settings → Compute → SQL Warehouses."
            )

        return cls(host=host, token=token, warehouse_id=warehouse_id)


# ─── Cache simples (TTL 5min) ────────────────────────────────────────────────


_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL_SECONDS = 300  # 5 min


def _cache_get(key: str) -> Any | None:
    """Retorna valor cacheado se ainda válido, None caso contrário."""
    entry = _CACHE.get(key)
    if entry is None:
        return None
    timestamp, value = entry
    if time.time() - timestamp > _CACHE_TTL_SECONDS:
        del _CACHE[key]
        return None
    return value


def _cache_set(key: str, value: Any) -> None:
    _CACHE[key] = (time.time(), value)


def clear_cache() -> None:
    """Limpa cache. Útil para testes e quando user pede 'forçar refresh'."""
    _CACHE.clear()


# ─── SQL queries ─────────────────────────────────────────────────────────────


def _build_usage_sql(days_back: int, cloud_filter: str | None = None) -> str:
    """SQL pra system.billing.usage com extração de cluster_id/cluster_name.

    Args:
        days_back: quantos dias retroativos buscar (ex: 60).
        cloud_filter: 'AZURE' | 'AWS' | None (todos).

    Returns:
        SQL string parametrizado por days_back (sem injection — int validado).
    """
    days_back = int(days_back)  # defensivo, não aceita string
    cloud_clause = ""
    if cloud_filter is not None:
        cloud_filter_upper = cloud_filter.upper()
        if cloud_filter_upper not in ("AZURE", "AWS", "GCP"):
            raise ValueError(f"cloud inválido: {cloud_filter}")
        cloud_clause = f"AND cloud = '{cloud_filter_upper}'"

    return f"""
SELECT
    usage_date,
    workspace_id,
    sku_name,
    CAST(usage_quantity AS DOUBLE) AS usage_quantity,
    usage_unit,
    cloud,
    usage_metadata.cluster_id AS cluster_id,
    usage_metadata.cluster_name AS cluster_name
FROM system.billing.usage
WHERE usage_date >= current_date() - INTERVAL {days_back} DAYS
  AND usage_unit = 'DBU'
  {cloud_clause}
ORDER BY usage_date DESC
""".strip()


def _build_prices_sql(cloud_filter: str | None = None) -> str:
    """SQL pra system.billing.list_prices com extração de pricing.default.

    Filtra por price_end_time IS NULL (preços vigentes).
    """
    cloud_clause = ""
    if cloud_filter is not None:
        cloud_filter_upper = cloud_filter.upper()
        if cloud_filter_upper not in ("AZURE", "AWS", "GCP"):
            raise ValueError(f"cloud inválido: {cloud_filter}")
        cloud_clause = f"AND cloud = '{cloud_filter_upper}'"

    return f"""
SELECT
    sku_name,
    cloud,
    currency_code,
    CAST(pricing.default AS DOUBLE) AS price_per_dbu,
    price_start_time,
    price_end_time
FROM system.billing.list_prices
WHERE price_end_time IS NULL
  {cloud_clause}
""".strip()


# ─── SQL execution via Databricks SDK ────────────────────────────────────────


def _execute_sql(config: RealModeConfig, sql: str) -> list[dict[str, Any]]:
    """Roda SQL via statement_execution API e retorna list[dict] das rows.

    Polling síncrono até statement COMPLETED ou erro/timeout.

    Args:
        config: RealModeConfig validado.
        sql: SQL statement.

    Returns:
        Lista de dicts (1 dict por row, chaves = nomes de colunas).

    Raises:
        RuntimeError: timeout, statement failed, ou erro de auth/permissão.
    """
    try:
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.service.sql import StatementState
    except ImportError as exc:
        raise RuntimeError(
            "databricks-sdk não instalado. Rode: pip install databricks-sdk>=0.20.0"
        ) from exc

    client = WorkspaceClient(host=config.host, token=config.token)

    logger.info("executing SQL via warehouse %s", config.warehouse_id)
    response = client.statement_execution.execute_statement(
        statement=sql,
        warehouse_id=config.warehouse_id,
        wait_timeout="0s",  # async — fazemos polling explícito
    )

    statement_id = response.statement_id
    if statement_id is None:
        raise RuntimeError("statement_id retornou None — falha do warehouse")

    # Polling
    deadline = time.time() + config.statement_timeout_seconds
    while time.time() < deadline:
        status = client.statement_execution.get_statement(statement_id=statement_id)
        state = status.status.state if status.status else None

        if state == StatementState.SUCCEEDED:
            break
        if state in (StatementState.FAILED, StatementState.CANCELED, StatementState.CLOSED):
            error_msg = ""
            if status.status and status.status.error:
                error_msg = status.status.error.message or ""
            raise RuntimeError(
                f"SQL statement {state}: {error_msg}. "
                "Verifique permissões (SELECT em system.billing) + UC habilitado."
            )
        # PENDING ou RUNNING → continua polling
        time.sleep(config.poll_interval_seconds)
    else:
        raise RuntimeError(
            f"SQL timeout após {config.statement_timeout_seconds}s. "
            "Warehouse pode estar pausado — start manual ou aumentar timeout."
        )

    # Coleta resultado
    if status.manifest is None or status.manifest.schema is None:
        return []

    columns = [col.name for col in status.manifest.schema.columns or []]
    rows: list[dict[str, Any]] = []

    if status.result and status.result.data_array:
        for row_array in status.result.data_array:
            row_dict = dict(zip(columns, row_array, strict=False))
            rows.append(row_dict)

    return rows


# ─── Public API: load_real_dataframes ────────────────────────────────────────


def load_real_dataframes(
    cloud: str = "AZURE",
    days_back: int = 60,
    use_cache: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Carrega (usage_df, prices_df) reais via system.billing.

    Args:
        cloud: "AZURE" | "AWS" | "GCP". Filtra apenas linhas do cloud.
        days_back: quantos dias retroativos buscar (default 60).
        use_cache: se True, retorna do cache se ainda válido (TTL 5min).

    Returns:
        Tupla (usage_df, prices_df) — DataFrames pandas com mesmo schema do
        mock generator (compatibilidade com engine billing.py).

    Raises:
        RuntimeError: config ausente, SDK ausente, SQL failure, ou
            permissão negada (system.billing inacessível).
    """
    cache_key = f"{cloud.upper()}__{days_back}"
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            logger.info("cache hit: %s", cache_key)
            return cached

    config = RealModeConfig.from_env()  # valida credenciais cedo

    # Queries
    usage_sql = _build_usage_sql(days_back=days_back, cloud_filter=cloud)
    prices_sql = _build_prices_sql(cloud_filter=cloud)

    logger.info("loading real data — cloud=%s days=%d", cloud, days_back)
    usage_rows = _execute_sql(config, usage_sql)
    prices_rows = _execute_sql(config, prices_sql)

    usage_df = _to_usage_dataframe(usage_rows)
    prices_df = _to_prices_dataframe(prices_rows)

    if use_cache:
        _cache_set(cache_key, (usage_df, prices_df))

    return usage_df, prices_df


# ─── DataFrame conversion ────────────────────────────────────────────────────


def _to_usage_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Converte rows do statement_execution pro schema do engine.

    Garante schema mínimo mesmo quando rows está vazio.
    """
    import pandas as pd

    schema_cols = [
        "usage_date",
        "workspace_id",
        "sku_name",
        "usage_quantity",
        "usage_unit",
        "cloud",
        "cluster_id",
        "cluster_name",
    ]

    if not rows:
        return pd.DataFrame(columns=schema_cols)

    df = pd.DataFrame(rows)
    # Conversão de tipos
    if "usage_date" in df.columns:
        df["usage_date"] = pd.to_datetime(df["usage_date"]).dt.date
    if "usage_quantity" in df.columns:
        df["usage_quantity"] = pd.to_numeric(df["usage_quantity"], errors="coerce")
    if "workspace_id" in df.columns:
        df["workspace_id"] = pd.to_numeric(df["workspace_id"], errors="coerce").astype("Int64")
    # Garante todas as colunas (preenche faltantes com NaN)
    for col in schema_cols:
        if col not in df.columns:
            df[col] = None

    return df[schema_cols].reset_index(drop=True)


def _to_prices_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Converte rows do list_prices pro schema do engine."""
    import pandas as pd

    schema_cols = [
        "sku_name",
        "cloud",
        "currency_code",
        "price_per_dbu",
        "price_start_time",
        "price_end_time",
    ]

    if not rows:
        return pd.DataFrame(columns=schema_cols)

    df = pd.DataFrame(rows)
    if "price_per_dbu" in df.columns:
        df["price_per_dbu"] = pd.to_numeric(df["price_per_dbu"], errors="coerce")
    if "price_start_time" in df.columns:
        df["price_start_time"] = pd.to_datetime(df["price_start_time"], errors="coerce")
    if "price_end_time" in df.columns:
        df["price_end_time"] = pd.to_datetime(df["price_end_time"], errors="coerce")
    for col in schema_cols:
        if col not in df.columns:
            df[col] = None

    return df[schema_cols].reset_index(drop=True)


def get_real_metadata() -> dict:
    """Metadata pra diagnostics quando real mode está ativo.

    Não chama Databricks — só reporta config presente e estado do cache.
    """
    try:
        config = RealModeConfig.from_env()
        host_masked = config.host[:30] + "..." if len(config.host) > 30 else config.host
        warehouse_masked = (
            config.warehouse_id[:8] + "..." if len(config.warehouse_id) > 8 else config.warehouse_id
        )
        config_ok = True
        config_error = None
    except RuntimeError as exc:
        host_masked = "(missing)"
        warehouse_masked = "(missing)"
        config_ok = False
        config_error = str(exc)

    return {
        "is_mock": False,
        "config_ok": config_ok,
        "config_error": config_error,
        "host": host_masked,
        "warehouse_id": warehouse_masked,
        "cache_entries": len(_CACHE),
        "cache_ttl_seconds": _CACHE_TTL_SECONDS,
        "schema_compatible_with_mock": True,
        "note": (
            "Real mode lê de system.billing.usage + system.billing.list_prices "
            "via SQL warehouse. Requer Unity Catalog + SELECT em system.billing. "
            f"Próximo refresh do cache após {_CACHE_TTL_SECONDS}s."
        ),
    }


# Timestamp da última carga — útil pra UI mostrar 'fresh as of X'
def get_last_load_timestamp() -> datetime | None:
    """Retorna ISO timestamp do entry mais recente do cache, ou None."""
    if not _CACHE:
        return None
    most_recent_ts = max(entry[0] for entry in _CACHE.values())
    return datetime.fromtimestamp(most_recent_ts, tz=timezone.utc)


__all__ = [
    "RealModeConfig",
    "clear_cache",
    "get_last_load_timestamp",
    "get_real_metadata",
    "load_real_dataframes",
]
