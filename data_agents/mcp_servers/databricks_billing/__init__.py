"""
Databricks Billing MCP — análise FinOps via system.billing.usage do Unity Catalog.

Fase 3 do Databricks Cost Calculator: enquanto Fase 0/1/2 cotam workloads
DETERMINISTICAMENTE (catalog YAML estático), este MCP analisa workloads em
PRODUÇÃO consultando dados reais de consumo.

Tools (5):
  - databricks_billing_diagnostics: smoke test de conectividade + mock mode
  - databricks_billing_get_dbu_usage_daily: DBU por dia × SKU na janela
  - databricks_billing_get_top_cost_clusters: top N clusters por custo
  - databricks_billing_get_cost_by_compute_type: breakdown jobs/all_purpose/sql/serverless
  - databricks_billing_compare_estimate_vs_actual: bridge Fase 2 ↔ Fase 3

Modos de operação (via DATABRICKS_BILLING_MOCK_MODE no .env):
  - true (default): usa billing_mock.py — DataFrames sintéticos
  - false: executa SQL real via databricks-sdk + warehouse_id configurado
"""

from data_agents.mcp_servers.databricks_billing.server_config import (
    DATABRICKS_BILLING_MCP_READONLY_TOOLS,
    DATABRICKS_BILLING_MCP_TOOLS,
    get_databricks_billing_mcp_config,
)

__all__ = [
    "DATABRICKS_BILLING_MCP_READONLY_TOOLS",
    "DATABRICKS_BILLING_MCP_TOOLS",
    "get_databricks_billing_mcp_config",
]
