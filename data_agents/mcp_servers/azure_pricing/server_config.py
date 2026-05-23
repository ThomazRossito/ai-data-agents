"""
Configuração do MCP Server Customizado: azure_pricing.

Expõe a Azure Retail Prices API (https://prices.azure.com/api/retail/prices)
como conjunto de tools determinísticas para cálculo de custo de recursos Azure.

Características:
  - Sem credenciais obrigatórias (Retail Prices API é pública, sem auth)
  - Retorna valores que casam 1:1 com a Azure Pricing Calculator oficial
    para retail pricing (não cobre descontos EA/MCA negociados)
  - Todas as tools incluem timestamp + URL da fonte para auditabilidade

Servidor: azure-pricing-mcp (entry point em pyproject.toml)
Protocolo: stdio
Autenticação: nenhuma
Dependências: requests (já incluso no projeto via httpx/databricks-sdk)
"""


def get_azure_pricing_mcp_config() -> dict:
    """Retorna a configuração MCP para o servidor azure_pricing customizado."""
    from data_agents.config.settings import settings  # importação local — evita circular import

    return {
        "azure_pricing": {
            "type": "stdio",
            "command": settings.azure_pricing_command,
            "args": [],
            "env": {
                # Defaults configuráveis via .env (não obrigatórios — todos têm fallback)
                "AZURE_PRICING_DEFAULT_REGION": settings.azure_pricing_default_region,
                "AZURE_PRICING_DEFAULT_CURRENCY": settings.azure_pricing_default_currency,
                "AZURE_PRICING_HOURS_PER_MONTH": str(settings.azure_pricing_hours_per_month),
            },
        }
    }


# ─── Lista de Tools ───────────────────────────────────────────────────────────
#
# Formato: mcp__<server_name>__<tool_name>
# server_name = "azure_pricing" (chave em ALL_MCP_CONFIGS)

AZURE_PRICING_MCP_TOOLS = [
    # Diagnóstico
    "mcp__azure_pricing__azure_pricing_diagnostics",
    # Pricing core (lookup determinístico)
    "mcp__azure_pricing__azure_pricing_get_retail_price",
    "mcp__azure_pricing__azure_pricing_get_price_with_regional_fallback",
    "mcp__azure_pricing__azure_pricing_list_skus",
    # Cálculo de custo
    "mcp__azure_pricing__azure_pricing_estimate_monthly_cost",
    "mcp__azure_pricing__azure_pricing_compare_reservation_terms",
    "mcp__azure_pricing__azure_pricing_savings_plan_calc",
    # Utilidades
    "mcp__azure_pricing__azure_pricing_currency_convert",
    "mcp__azure_pricing__azure_pricing_list_regions",
    "mcp__azure_pricing__azure_pricing_generate_calculator_url",
]

# Subset somente leitura (lookup sem cálculos — útil pra agents conservadores)
AZURE_PRICING_MCP_READONLY_TOOLS = [
    "mcp__azure_pricing__azure_pricing_diagnostics",
    "mcp__azure_pricing__azure_pricing_get_retail_price",
    "mcp__azure_pricing__azure_pricing_get_price_with_regional_fallback",
    "mcp__azure_pricing__azure_pricing_list_skus",
    "mcp__azure_pricing__azure_pricing_list_regions",
    "mcp__azure_pricing__azure_pricing_currency_convert",
]
