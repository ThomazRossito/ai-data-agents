"""
Configuração do MCP Server Customizado: databricks_pricing.

Expõe o calculation engine determinístico (data_agents.cost_engine.databricks)
e os pricing catalogs YAML como tools MCP. Permite que agents (em particular
o databricks-cost-calculator) cotem cenários Databricks conversacionalmente
sem precisar serializar/deserializar manualmente.

Características:
  - Sem credenciais obrigatórias (catalog estático + APIs públicas opcionais)
  - Retorna valores que casam 1:1 com data_agents/cost_engine/databricks.py
    (mesmo engine usado pelo Streamlit App em data_agents/cost_app/)
  - Todas as tools incluem timestamp + catalog_version pra auditabilidade

Servidor: databricks-pricing-mcp (entry point em pyproject.toml)
Protocolo: stdio
Autenticação: nenhuma
Dependências: pyyaml, requests (já incluso no projeto)
"""


def get_databricks_pricing_mcp_config() -> dict:
    """Retorna a configuração MCP para o servidor databricks_pricing customizado."""
    from data_agents.config.settings import settings  # importação local — evita circular import

    return {
        "databricks_pricing": {
            "type": "stdio",
            "command": settings.databricks_pricing_command,
            "args": [],
            "env": {
                # Defaults configuráveis via .env (não obrigatórios — todos têm fallback)
                "DATABRICKS_PRICING_DEFAULT_CLOUD": settings.databricks_pricing_default_cloud,
                "DATABRICKS_PRICING_DEFAULT_REGION": settings.databricks_pricing_default_region,
                "DATABRICKS_PRICING_DEFAULT_CURRENCY": settings.databricks_pricing_default_currency,
                "DATABRICKS_PRICING_FX_USD_BRL": str(settings.databricks_pricing_fx_usd_brl),
            },
        }
    }


# ─── Lista de Tools ──────────────────────────────────────────────────────────
#
# Formato: mcp__<server_name>__<tool_name>
# server_name = "databricks_pricing" (chave em ALL_MCP_CONFIGS)

DATABRICKS_PRICING_MCP_TOOLS = [
    # Diagnóstico
    "mcp__databricks_pricing__databricks_pricing_diagnostics",
    # Lookup determinístico do catalog
    "mcp__databricks_pricing__databricks_pricing_get_dbu_rate",
    "mcp__databricks_pricing__databricks_pricing_get_instance_price",
    "mcp__databricks_pricing__databricks_pricing_list_instances",
    "mcp__databricks_pricing__databricks_pricing_list_regions",
    # Cálculo de cost
    "mcp__databricks_pricing__databricks_pricing_calc_cluster_cost",
    "mcp__databricks_pricing__databricks_pricing_compare_payg_vs_dbcu",
    # Utilidades
    "mcp__databricks_pricing__databricks_pricing_currency_convert",
    "mcp__databricks_pricing__databricks_pricing_save_scenario",
    # Bridge App → Agent (Chunk 2.3): ler scenarios salvos no App
    "mcp__databricks_pricing__databricks_pricing_list_scenarios",
    "mcp__databricks_pricing__databricks_pricing_load_scenario",
    "mcp__databricks_pricing__databricks_pricing_delete_scenario",
    "mcp__databricks_pricing__databricks_pricing_search_scenarios",
]

# Subset readonly (lookup sem cálculos, sem writes/deletes)
# Inclui list/load/search (são reads do bridge) mas NÃO inclui delete_scenario
# (destrutivo) nem save_scenario (write).
DATABRICKS_PRICING_MCP_READONLY_TOOLS = [
    "mcp__databricks_pricing__databricks_pricing_diagnostics",
    "mcp__databricks_pricing__databricks_pricing_get_dbu_rate",
    "mcp__databricks_pricing__databricks_pricing_get_instance_price",
    "mcp__databricks_pricing__databricks_pricing_list_instances",
    "mcp__databricks_pricing__databricks_pricing_list_regions",
    "mcp__databricks_pricing__databricks_pricing_currency_convert",
    "mcp__databricks_pricing__databricks_pricing_list_scenarios",
    "mcp__databricks_pricing__databricks_pricing_load_scenario",
    "mcp__databricks_pricing__databricks_pricing_search_scenarios",
]
