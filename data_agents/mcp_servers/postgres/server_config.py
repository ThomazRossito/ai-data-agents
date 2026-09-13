"""
Configuração do MCP Server: postgres (Postgres MCP Pro).

Conexão a banco PostgreSQL com inteligência de schema, planos de execução,
tuning de índices, health checks e execução de SQL com controle de acesso.

Casos de uso no data-agents:
  - SQL Expert: consultas a bancos PostgreSQL externos (metastore, catálogos,
    sistemas operacionais), comparação de dados entre Postgres e Databricks/Fabric
  - Data Quality Steward: inspeção de schemas e dados em fontes PostgreSQL
    antes de ingestão nos Data Lakes
  - Governance Auditor: auditoria de dados em sistemas transacionais Postgres

Servidor: postgres-mcp (crystaldba/postgres-mcp, "Postgres MCP Pro") via `uvx`
Licença: MIT
Protocolo: stdio
Autenticação: POSTGRES_URL → exportado como `DATABASE_URI` para o servidor

Por que este servidor (auditoria 2026-09-13)
--------------------------------------------
O anterior era `@modelcontextprotocol/server-postgres`, **arquivado pela
Anthropic em maio/2025** após o Datadog Security Labs divulgar uma **SQL
injection**: a sequência `COMMIT; DROP SCHEMA public CASCADE` **contornava o
modo read-only**, ou seja, a promessa de "somente leitura" não se sustentava.

O Postgres MCP Pro trata exatamente esse vetor: ele faz o **parse do SQL antes
de executar** (biblioteca `pglast`) e **rejeita qualquer statement `commit` ou
`rollback`**, impedindo que o agente encerre a transação read-only e abra uma
nova com permissão de escrita.

Modo de acesso
--------------
Configurado em `--access-mode=restricted`:
  - transações **read-only**;
  - **limite de tempo** de execução (evita query longa degradando o sistema).

O modo `unrestricted` (leitura + escrita) existe para desenvolvimento e **não**
é usado aqui — seria incompatível com a postura read-only do projeto (S5/S6).

Formato da connection string:
  postgresql://usuario:senha@host:5432/banco
  postgresql://usuario:senha@host:5432/banco?sslmode=require  (ambientes cloud)

Ativação: condicional — o MCP só sobe quando `POSTGRES_URL` está preenchido
(`settings.py`). Com a variável vazia, o servidor não é registrado.

Extensões opcionais no banco (habilitam tuning e análise completa):
  CREATE EXTENSION IF NOT EXISTS pg_stat_statements;  -- estatísticas de query
  CREATE EXTENSION IF NOT EXISTS hypopg;              -- índices hipotéticos
Sem elas, as tools de schema e execução funcionam; as de tuning ficam limitadas.

Custo: gratuito (open source, MIT)

Referência: https://github.com/crystaldba/postgres-mcp
"""


def get_postgres_mcp_config() -> dict:
    """Retorna a configuração MCP para o PostgreSQL (Postgres MCP Pro)."""
    from data_agents.config.settings import settings  # importação local para evitar circular import

    return {
        "postgres": {
            "type": "stdio",
            "command": "uvx",
            "args": [
                "postgres-mcp",
                # Modo restrito: transações read-only + limite de tempo de execução.
                # Coerente com a postura read-only do projeto (S5/S6).
                "--access-mode=restricted",
            ],
            # A connection string vai por env (DATABASE_URI), não no argv —
            # evita que a senha apareça na linha de comando do processo.
            "env": {"DATABASE_URI": settings.postgres_url},
        }
    }


# ─── Lista de Tools ───────────────────────────────────────────────────────────
# O Postgres MCP Pro expõe funcionalidade SOMENTE por tools (não usa Resources),
# ao contrário do servidor arquivado que expunha schema como Resource.
# Nomes conferidos no README oficial do projeto (tabela "Postgres MCP Pro Tools").

POSTGRES_MCP_TOOLS = [
    # ── Schema intelligence ──
    "mcp__postgres__list_schemas",
    "mcp__postgres__list_objects",
    "mcp__postgres__get_object_details",
    # ── Execução de SQL (read-only em modo restricted) ──
    "mcp__postgres__execute_sql",
    # ── Planos de query ──
    "mcp__postgres__explain_query",
    "mcp__postgres__get_top_queries",
    # ── Tuning de índices ──
    "mcp__postgres__analyze_workload_indexes",
    "mcp__postgres__analyze_query_indexes",
    # ── Saúde do banco ──
    "mcp__postgres__analyze_db_health",
]

#: Subconjunto de inspeção — exclui `execute_sql`.
#:
#: Em modo restricted o `execute_sql` já é read-only, mas ele é a única tool que
#: roda SQL arbitrário. Mantê-lo fora do alias readonly é defesa em profundidade:
#: um agente que só precisa inspecionar schema não deve poder executar query.
POSTGRES_MCP_READONLY_TOOLS = [
    "mcp__postgres__list_schemas",
    "mcp__postgres__list_objects",
    "mcp__postgres__get_object_details",
    "mcp__postgres__explain_query",
    "mcp__postgres__get_top_queries",
    "mcp__postgres__analyze_workload_indexes",
    "mcp__postgres__analyze_query_indexes",
    "mcp__postgres__analyze_db_health",
]
