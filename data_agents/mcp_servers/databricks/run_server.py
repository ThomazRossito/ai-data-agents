"""
Wrapper stdio para o servidor MCP do ai-dev-kit (Databricks, oficial).

Por que um wrapper em vez de chamar o `run_server.py` do pacote
---------------------------------------------------------------
O ai-dev-kit distribui o entrypoint como script solto na raiz do
`databricks-mcp-server/`, fora do módulo Python — instalando via pip/git ele não
vem junto. O que vem é o objeto `databricks_mcp_server.server.mcp` (FastMCP), e
é isso que este arquivo sobe.

Até 2026-09-14 este wrapper importava `databricks_mcp` (pacote markov-kernel,
comunidade) e existia para redirecionar o log dele para `logs/`. O servidor do
ai-dev-kit loga em stderr e só quando `DATABRICKS_MCP_DEBUG` está setado, então
o redirecionamento deixou de ser necessário.

Falha rápida e legível
----------------------
Se o pacote não estiver instalado, o erro padrão seria um ModuleNotFoundError
enterrado no log do SDK. Aqui ele vira uma mensagem que diz o que instalar.
"""

from __future__ import annotations

import sys


def _main() -> int:
    try:
        from databricks_mcp_server.server import mcp
    except ModuleNotFoundError as exc:
        sys.stderr.write(
            "databricks MCP: pacote `databricks_mcp_server` (ai-dev-kit) não encontrado.\n"
            "Instale as dependências do projeto — o pyproject.toml aponta para o git:\n"
            "    pip install -e .\n"
            f"Detalhe: {exc}\n"
        )
        return 1

    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
