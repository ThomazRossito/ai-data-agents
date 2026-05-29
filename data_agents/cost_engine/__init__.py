"""
Cost calculation engines — funções puras pra estimar custo de workloads cloud.

Cada engine é determinístico: mesma entrada → mesma saída, sem side effects.
Consumido por:
  - Streamlit Cost App (data_agents/cost_app/)
  - MCP servers (mcp_servers/databricks_pricing/, mcp_servers/azure_pricing/)
  - Agentes (databricks-cost-calculator, azure-cost-calculator)
  - Scripts de validação (scripts/validate_*_pricing.py)

Engines disponíveis:
  - databricks: Databricks (AWS + Azure + GCP) — DBU rates, instance mapping,
    DBCU commit, spot, Photon modeling. Cobre compute clusters.
  - databricks_ai_ml (PR 5, 2026-05-28): scenarios AI/ML específicos —
    LLM (Foundation Model + Proprietary), Vector Search, Lakebase, Agent Bricks.
    Modela custos não-compute (tokens, GB, CU·h, answers) com promo auto-aplicação.
"""

from data_agents.cost_engine.databricks import (
    DatabricksScenario,
    calculate_databricks_cost,
    load_databricks_catalog,
)
from data_agents.cost_engine.databricks_ai_ml import (
    AgentBricksScenario,
    LakebaseScenario,
    LLMScenario,
    VectorSearchScenario,
    calculate_agent_bricks_cost,
    calculate_lakebase_cost,
    calculate_llm_cost,
    calculate_vector_search_cost,
)

__all__ = [
    "DatabricksScenario",
    "calculate_databricks_cost",
    "load_databricks_catalog",
    # PR 5: AI/ML scenarios
    "LLMScenario",
    "VectorSearchScenario",
    "LakebaseScenario",
    "AgentBricksScenario",
    "calculate_llm_cost",
    "calculate_vector_search_cost",
    "calculate_lakebase_cost",
    "calculate_agent_bricks_cost",
]
