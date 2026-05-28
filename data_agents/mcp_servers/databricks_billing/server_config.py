"""
Configuração do MCP Server Customizado: databricks_billing.

Expõe `data_agents.cost_engine.billing` (Fase 3) como tools MCP. Permite que
agents (em particular o `databricks-cost-calculator` estendido) analisem
workloads Databricks em PRODUÇÃO conversacionalmente.

Características:
  - Modo mock por default (DATABRICKS_BILLING_MOCK_MODE=true) — não requer
    credenciais Databricks. Útil pra dev/test.
  - Modo real (DATABRICKS_BILLING_MOCK_MODE=false) — requer Unity Catalog +
    workspace admin + warehouse_id configurado (DATABRICKS_BILLING_WAREHOUSE_ID).
  - Todas as tools são READS — não há writes em system.billing.

Servidor: databricks-billing-mcp (entry point em pyproject.toml)
Protocolo: stdio
Autenticação:
  - Mock mode: nenhuma
  - Real mode: DATABRICKS_HOST + DATABRICKS_TOKEN (via .env do projeto)
"""


def get_databricks_billing_mcp_config() -> dict:
    """Retorna a configuração MCP para o servidor databricks_billing customizado."""
    from data_agents.config.settings import settings  # importação local — evita circular

    return {
        "databricks_billing": {
            "type": "stdio",
            "command": settings.databricks_billing_command,
            "args": [],
            "env": {
                # Modo de operação: "true" usa mock, "false" tenta SQL real
                "DATABRICKS_BILLING_MOCK_MODE": str(settings.databricks_billing_mock_mode).lower(),
                # Warehouse pra rodar SQL real (ignorado em mock mode)
                "DATABRICKS_BILLING_WAREHOUSE_ID": settings.databricks_billing_warehouse_id,
                # Credenciais Databricks (necessárias só se mock_mode=false)
                "DATABRICKS_HOST": settings.databricks_host,
                "DATABRICKS_TOKEN": settings.databricks_token,
            },
        }
    }


# ─── Lista de Tools ──────────────────────────────────────────────────────────
#
# Formato: mcp__<server_name>__<tool_name>
# server_name = "databricks_billing" (chave em ALL_MCP_CONFIGS)

DATABRICKS_BILLING_MCP_TOOLS = [
    "mcp__databricks_billing__databricks_billing_diagnostics",
    "mcp__databricks_billing__databricks_billing_get_dbu_usage_daily",
    "mcp__databricks_billing__databricks_billing_get_top_cost_clusters",
    "mcp__databricks_billing__databricks_billing_get_cost_by_compute_type",
    "mcp__databricks_billing__databricks_billing_compare_estimate_vs_actual",
]

# Todas as 5 tools são READS de system.billing (não há writes).
# Readonly = idêntico ao set completo.
DATABRICKS_BILLING_MCP_READONLY_TOOLS = list(DATABRICKS_BILLING_MCP_TOOLS)
