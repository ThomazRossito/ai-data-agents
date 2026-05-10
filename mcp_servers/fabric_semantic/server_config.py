"""
Configuração do MCP Server Customizado: fabric_semantic.

Introspecção profunda de Semantic Models no Microsoft Fabric via REST API.
Resolve o gap do fabric_community MCP que não expõe a estrutura interna dos modelos
(tabelas, colunas, medidas DAX, relacionamentos, roles/RLS).

Abordagem A+C:
  A) getDefinition: baixa TMDL base64, parseia tabelas/medidas/relacionamentos.
  C) executeQueries: executa DAX INFO.* em runtime (sem XMLA, sem Premium).

Credenciais: reutiliza AZURE_TENANT_ID + AZURE_CLIENT_ID + AZURE_CLIENT_SECRET + FABRIC_WORKSPACE_ID
Scope OAuth: https://analysis.windows.net/powerbi/api/.default (Power BI REST API)
             https://api.fabric.microsoft.com/.default (Fabric REST API v1)

Permissões necessárias no Azure AD para o Service Principal:
  - Power BI Admin Portal → Tenant Settings → Developer Settings →
    "Allow service principals to use Power BI APIs" = habilitado
  - Service Principal como membro/contribuidor no workspace Fabric
  - Scopes: Dataset.Read.All ou Dataset.ReadWrite.All

Pré-requisitos:
  pip install -e .  (azure-identity + requests já incluídos no pyproject.toml)

Comando: fabric-semantic-mcp (entry point configurado em pyproject.toml)
"""


def get_fabric_semantic_mcp_config() -> dict:
    """Retorna a configuração MCP para o servidor fabric_semantic customizado."""
    from config.settings import settings  # importação local — evita circular import

    return {
        "fabric_semantic": {
            "type": "stdio",
            "command": settings.fabric_semantic_command,
            "args": [],
            "env": {
                "AZURE_TENANT_ID": settings.azure_tenant_id,
                "AZURE_CLIENT_ID": settings.azure_client_id,
                "AZURE_CLIENT_SECRET": settings.azure_client_secret,
                "FABRIC_WORKSPACE_ID": settings.fabric_workspace_id,
            },
        }
    }


# ─── Lista de Tools ───────────────────────────────────────────────────────────

FABRIC_SEMANTIC_MCP_TOOLS = [
    # Diagnóstico — execute primeiro se houver erros de conexão ou autenticação
    "mcp__fabric_semantic__fabric_semantic_diagnostics",
    # Descoberta — lista modelos do workspace com metadados (targetStorageMode, etc.)
    "mcp__fabric_semantic__fabric_semantic_list_models",
    # Definição completa — TMDL: tabelas, colunas, medidas, relacionamentos, roles
    "mcp__fabric_semantic__fabric_semantic_get_definition",
    # Tabelas — lista tabelas do modelo com colunas e modo Direct Lake / Import
    "mcp__fabric_semantic__fabric_semantic_list_tables",
    # Medidas DAX — fórmulas completas agrupadas por tabela
    "mcp__fabric_semantic__fabric_semantic_list_measures",
    # Relacionamentos — cardinalidade, cross-filter, ativos vs inativos
    "mcp__fabric_semantic__fabric_semantic_list_relationships",
    # DAX runtime — INFO.TABLES(), INFO.MEASURES(), SUMMARIZECOLUMNS() via REST API
    "mcp__fabric_semantic__fabric_semantic_execute_dax",
    # Histórico de refresh — status, duração, erros por execução
    "mcp__fabric_semantic__fabric_semantic_get_refresh_history",
    # Escrita — adiciona/atualiza medidas DAX via updateDefinition (Fabric REST API v1)
    "mcp__fabric_semantic__fabric_semantic_update_definition",
]

# Subconjunto somente leitura (sem execute_dax para uso mais restrito)
FABRIC_SEMANTIC_MCP_READONLY_TOOLS = [
    t for t in FABRIC_SEMANTIC_MCP_TOOLS if any(kw in t for kw in ["list_", "get_", "diagnostics"])
]
