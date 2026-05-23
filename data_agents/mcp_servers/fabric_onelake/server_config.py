"""
Configuração do MCP customizado: fabric_onelake.

Substitui o `@microsoft/fabric-mcp` (oficial Microsoft) que está com bug
em `onelake_upload_file` (HTTP 400 mesmo com SP Admin + tenant OK + scopes
OK — confirmado por scripts/test_onelake_upload.py).

Usa DFS API direta (onelake.dfs.fabric.microsoft.com), idêntica ao ADLS Gen2,
com fluxo de 3 passos: create → append → flush.

Auth: ClientSecretCredential com scope https://storage.azure.com/.default
"""

from __future__ import annotations

import sys


def get_fabric_onelake_mcp_config() -> dict:
    """Retorna a configuração MCP para o servidor fabric_onelake customizado."""
    from data_agents.config.settings import settings

    return {
        "fabric_onelake": {
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", "mcp_servers.fabric_onelake.server"],
            "env": {
                "AZURE_TENANT_ID": settings.azure_tenant_id,
                "AZURE_CLIENT_ID": settings.azure_client_id,
                "AZURE_CLIENT_SECRET": settings.azure_client_secret,
                # OneLake DFS API requer o NAME do workspace (slug), não GUID.
                # Setting separado pra não confundir com FABRIC_WORKSPACE_ID.
                "FABRIC_WORKSPACE_NAME": settings.fabric_workspace_name,
            },
        }
    }


# ─── Lista de Tools ──────────────────────────────────────────────────────────

FABRIC_ONELAKE_MCP_TOOLS = [
    "mcp__fabric_onelake__fabric_onelake_upload_file",
    "mcp__fabric_onelake__fabric_onelake_upload_local_file",
    "mcp__fabric_onelake__fabric_onelake_download_file",
    "mcp__fabric_onelake__fabric_onelake_list_files",
    "mcp__fabric_onelake__fabric_onelake_file_exists",
    "mcp__fabric_onelake__fabric_onelake_create_directory",
    "mcp__fabric_onelake__fabric_onelake_delete_file",
]

FABRIC_ONELAKE_MCP_READONLY_TOOLS = [
    "mcp__fabric_onelake__fabric_onelake_download_file",
    "mcp__fabric_onelake__fabric_onelake_list_files",
    "mcp__fabric_onelake__fabric_onelake_file_exists",
]
