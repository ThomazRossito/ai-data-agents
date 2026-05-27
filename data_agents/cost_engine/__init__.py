"""
Cost calculation engines — funções puras pra estimar custo de workloads cloud.

Cada engine é determinístico: mesma entrada → mesma saída, sem side effects.
Consumido por:
  - Streamlit Cost App (data_agents/cost_app/)
  - MCP servers (mcp_servers/databricks_pricing/, mcp_servers/azure_pricing/)
  - Agentes (databricks-cost-calculator, azure-cost-calculator)
  - Scripts de validação (scripts/validate_*_pricing.py)

Engines disponíveis:
  - databricks: Databricks (AWS + Azure) — DBU rates, instance mapping,
    DBCU commit, spot, Photon modeling.
"""

from data_agents.cost_engine.databricks import (
    DatabricksScenario,
    calculate_databricks_cost,
    load_databricks_catalog,
)

__all__ = [
    "DatabricksScenario",
    "calculate_databricks_cost",
    "load_databricks_catalog",
]
