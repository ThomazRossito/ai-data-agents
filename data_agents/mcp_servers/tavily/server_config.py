"""
Configuração do MCP Server: tavily.

Provê busca web otimizada para LLMs com resultados prontos para consumo pelo modelo.
Diferente de uma busca genérica, o Tavily retorna conteúdo já processado e relevante,
sem ruído de HTML/CSS/ads.

Casos de uso no data-agents:
  - Business Analyst: pesquisa de mercado, benchmarks de indústria, documentação de APIs
  - Governance Auditor: busca de normas LGPD/GDPR, frameworks de governança, regulatórios
  - Qualquer agente: troubleshooting de erros sem documentação local

Servidor: tavily-mcp — pacote OFICIAL npm (github.com/tavily-ai/tavily-mcp), via npx
Protocolo: stdio
Autenticação: TAVILY_API_KEY (obrigatório)

Plano gratuito: 1.000 créditos/mês — sem cartão de crédito
  - Busca básica: 1 crédito/request
  - Busca avançada (com extração de conteúdo): mais créditos
Plano pago: $0.008/crédito ou pacotes a partir de $30/mês

Adquirida pela Nebius em fevereiro/2026.
Referência: https://docs.tavily.com/

POR QUE npx E NÃO uvx (hotfix 2026-09-15)
-----------------------------------------
Este servidor NUNCA subiu. A config era `uvx tavily-mcp`, mas o pacote PyPI
`tavily-mcp` (0.2.3, autor "Your Name <your.email@example.com>", não é o da
Tavily) expõe os executáveis `check`, `mcp` e `tavily` — não existe
`tavily-mcp`. O uvx falha na hora:

    $ uvx tavily-mcp
    ... provides executables: check, mcp, tavily
    Use `uvx --from tavily-mcp <EXECUTABLE-NAME>` instead.

Efeito: em TODO o histórico de logs/audit.jsonl não há uma única linha
`mcp__tavily__*` — enquanto firecrawl, context7, WebSearch etc. aparecem. O
`databricks-engineer` declarava `tavily_all` em `tools:` e a tool não existia
na sessão. Cinco rodadas de correção de prompt/hook ("use tavily ANTES de
responder") miraram uma tool que não estava lá. O Supervisor Sonnet 5 disse
isso com todas as letras no eval: "o binding do tavily não estava ativo para
ele".

O servidor oficial da Tavily é o pacote npm `tavily-mcp` (README: `npx -y
tavily-mcp@latest`), tools `tavily-search`, `tavily-extract`, `tavily-map`,
`tavily-crawl`. Pinado na versão (política do projeto), como context7 e
memory_mcp, que já usam npx. Alternativa remota sem processo local:
`https://mcp.tavily.com/mcp` (transporte http) — não adotada aqui para não
colocar a chave em URL.
"""

#: Versão pinada do pacote npm oficial. Verificado em 2026-09-15: `npm view
#: tavily-mcp version` → 0.2.22. Atualize deliberadamente, com o vocabulário
#: de tools revisado.
TAVILY_MCP_NPM_VERSION = "0.2.22"


def get_tavily_mcp_config() -> dict:
    """Retorna a configuração MCP para o Tavily (pacote oficial npm, via npx)."""
    from data_agents.config.settings import settings  # importação local para evitar circular import

    return {
        "tavily": {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", f"tavily-mcp@{TAVILY_MCP_NPM_VERSION}"],
            "env": {
                "TAVILY_API_KEY": settings.tavily_api_key,
            },
        }
    }


# ─── Lista de Tools ───────────────────────────────────────────────────────────

TAVILY_MCP_TOOLS = [
    # Busca web otimizada para LLMs — retorna resultados limpos sem ruído HTML
    # Parâmetros: query, search_depth ("basic"|"advanced"), max_results, include_answer
    "mcp__tavily__tavily-search",
    # Extrai conteúdo completo de uma URL específica — útil para ler docs e artigos
    # Parâmetros: urls (lista)
    "mcp__tavily__tavily-extract",
]
