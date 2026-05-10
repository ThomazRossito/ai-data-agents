"""
Pacote `config` — settings centrais e MCP registry.

Não re-exporta nomes do nível raiz por design: importar `from config import settings`
causaria atribute shadowing entre o sub-módulo `config.settings` (Python module) e o
objeto `settings` (Settings instance), quebrando `unittest.mock.patch("config.settings.settings")`.

Sempre importe explicitamente:

    from config.settings import settings
    from config.mcp_servers import build_mcp_registry
"""
