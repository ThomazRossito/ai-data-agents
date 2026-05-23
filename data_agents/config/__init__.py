"""
Pacote `config` — settings centrais e MCP registry.

Não re-exporta nomes do nível raiz por design: importar `from config import settings`
causaria atribute shadowing entre o sub-módulo `config.settings` (Python module) e o
objeto `settings` (Settings instance), quebrando `unittest.mock.patch("data_agents.config.settings.settings")`.

Sempre importe explicitamente:

    from data_agents.config.settings import settings
    from data_agents.config.mcp_servers import build_mcp_registry
"""
