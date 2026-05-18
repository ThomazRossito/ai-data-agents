"""
MCP Server — Azure Pricing Calculator (custom).

Wraps the Azure Retail Prices API (https://prices.azure.com/api/retail/prices)
to provide deterministic, audit-grade cost estimates for Azure resources.
Returns values that match the official Azure Pricing Calculator 1:1 for
public retail pricing (does NOT account for negotiated EA/MCA rates).
"""
