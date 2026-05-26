"""
Configuração do MCP customizado: fabric_notebook.

Encapsula operações deterministas de notebook no Microsoft Fabric — montagem do
.ipynb, codificação base64, LRO polling do updateDefinition, retry com backoff —
tudo no servidor, fora do raciocínio do LLM.

Motivação: anti-pattern observado em produção (POC interno, 2026-05) onde o
agente fabric-engineer, ao tentar criar notebooks via `mcp__fabric_official__core_create-item`,
entrou em loop iterativo de Bash+base64, criou 13 notebooks lixo no workspace
e levou 17 minutos pra completar uma tarefa de ~5 segundos.

Auth: ClientSecretCredential (mesmo .env de fabric_semantic, fabric_sql, etc).
Scope: https://api.fabric.microsoft.com/.default
"""

from __future__ import annotations

import sys


def get_fabric_notebook_mcp_config() -> dict:
    """Retorna a configuração MCP para o servidor fabric_notebook customizado."""
    from data_agents.config.settings import settings  # local pra evitar circular import

    return {
        "fabric_notebook": {
            "type": "stdio",
            # Roda diretamente via python -m. Não precisa de entry point em pyproject.toml.
            # Requer que cwd seja a raiz do projeto e que mcp_servers esteja no path
            # (já garantido pelo claude-agent-sdk que herda PYTHONPATH).
            "command": sys.executable,
            "args": ["-m", "mcp_servers.fabric_notebook.server"],
            "env": {
                "AZURE_TENANT_ID": settings.azure_tenant_id,
                "AZURE_CLIENT_ID": settings.azure_client_id,
                "AZURE_CLIENT_SECRET": settings.azure_client_secret,
                "FABRIC_WORKSPACE_ID": settings.fabric_workspace_id,
            },
        }
    }


# ─── Lista de Tools ──────────────────────────────────────────────────────────

FABRIC_NOTEBOOK_MCP_TOOLS = [
    "mcp__fabric_notebook__fabric_notebook_create",
    "mcp__fabric_notebook__fabric_notebook_list",
    "mcp__fabric_notebook__fabric_notebook_get_cells",
    "mcp__fabric_notebook__fabric_notebook_replace",
    "mcp__fabric_notebook__fabric_notebook_add_cell",
    "mcp__fabric_notebook__fabric_notebook_update_cell",
    "mcp__fabric_notebook__fabric_notebook_delete_cell",
    "mcp__fabric_notebook__fabric_notebook_delete",
    # Execução on-demand — cobre o gap relatado na POC Itaúsa (2026-05-14):
    # 'API REST do Fabric não suporta execução direta de pipelines/notebooks'.
    # Ambos os endpoints existem: jobType=RunNotebook e jobType=Pipeline.
    "mcp__fabric_notebook__fabric_notebook_run",
    "mcp__fabric_notebook__fabric_pipeline_run",
    "mcp__fabric_notebook__fabric_notebook_cleanup_test_items",
]

# Subset somente leitura — pra alias `fabric_notebook_readonly` em contextos
# onde não queremos que o agente apague nada (ex: governance audits).
FABRIC_NOTEBOOK_MCP_READONLY_TOOLS = [
    "mcp__fabric_notebook__fabric_notebook_list",
    "mcp__fabric_notebook__fabric_notebook_get_cells",
]
