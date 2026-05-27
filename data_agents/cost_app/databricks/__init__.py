"""
Databricks Cost Calculator — Streamlit App.

Entry point: app.py (rodar via `streamlit run data_agents/cost_app/databricks/app.py`)
Porta default: 8514 (configurável via env DATABRICKS_COST_APP_PORT)

Módulos:
  - app: entry point Streamlit (multipage)
  - instance_prices: catalog estático de instance prices (mock pro MVP)
  - scenarios: persistência de cenários em JSON (bridge Agent→App futura)
  - exporters: XLSX export via openpyxl

Consume:
  - data_agents.cost_engine.databricks: engine determinístico
  - data/databricks_pricing/{azure,aws}.yaml: catalog de DBU rates
"""

from data_agents.cost_app.databricks.instance_prices import (
    get_instance_price_usd_per_hour,
    list_instances_for_region,
)
from data_agents.cost_app.databricks.scenarios import (
    list_saved_scenarios,
    load_scenario,
    save_scenario,
)

__all__ = [
    "get_instance_price_usd_per_hour",
    "list_instances_for_region",
    "list_saved_scenarios",
    "load_scenario",
    "save_scenario",
]
