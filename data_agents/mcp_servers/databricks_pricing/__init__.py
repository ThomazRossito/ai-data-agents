"""
Databricks Pricing — MCP customizado.

Expõe o calculation engine determinístico (data_agents/cost_engine/databricks.py)
+ pricing catalogs YAML (data/databricks_pricing/{azure,aws}.yaml) como tools
MCP consumíveis por agents (databricks-cost-calculator) e Supervisor.

Server: databricks-pricing-mcp (entry point em pyproject.toml)
Protocolo: stdio
Autenticação: nenhuma (catalog estático local + APIs Azure/AWS pricing públicas)
"""
