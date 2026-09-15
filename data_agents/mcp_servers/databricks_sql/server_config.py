"""
Configuração do MCP Server: databricks_sql (GERENCIADO pela Databricks).

Este é um **managed MCP server** — a Databricks hospeda, autentica e governa.
Não há processo local, pacote a instalar nem servidor a manter.

Diferença para o MCP `databricks/` deste projeto:
  - `databricks/`     → gestão de workspace (jobs, pipelines, clusters, UC admin),
                        processo local via stdio
  - `databricks_sql/` → execução de SQL sobre Unity Catalog, remoto via HTTP,
                        com permissão aplicada pelo **próprio Unity Catalog**

Casos de uso no data-agents:
  - databricks-engineer: executar SELECT/SHOW/DESCRIBE sobre o Lakehouse
  - data-quality-steward: profiling e validação lendo tabelas reais
  - governance-auditor: auditoria de dados com o UC barrando o que não pode ver

Servidor: managed MCP da Databricks (Public Preview desde jan/2026)
Protocolo: **HTTP** (Streamable HTTP) — não é stdio
URL: https://<workspace-hostname>/api/2.0/mcp/sql
Autenticação: PAT via header `Authorization: Bearer <token>`

Por que HTTP e não stdio
------------------------
O ``claude_agent_sdk`` suporta quatro formatos de MCP (``McpServerConfig``):
``McpStdioServerConfig``, ``McpSSEServerConfig``, ``McpHttpServerConfig`` e
``McpSdkServerConfig``. Este usa o terceiro — ``{type, url, headers}``, sem
``command``/``args``/``env``. Foi o primeiro MCP não-stdio do projeto.

Por que PAT e não OAuth
-----------------------
A doc oficial lista **ambos** como suportados para managed MCP servers. OAuth é
o recomendado para produção/time (escopos granulares, refresh automático); PAT
é classificado como segurança média, adequado a uso individual. Como este é um
projeto pessoal e o ``DATABRICKS_TOKEN`` já existe no ``.env``, usamos PAT.
Migrar para OAuth exige criar um app no account console e gerenciar client_id
(+ secret, se confidencial).

⚠️ Custo: diferente dos MCPs stdio locais, este consome **Databricks SQL
compute** a cada query. Não é gratuito.

Tools expostas (enumeradas ao vivo via `tools/list` em 2026-09-13)
-----------------------------------------------------------------
O servidor declara **anotações MCP** que classificam o risco de cada tool —
informação que vem do próprio servidor, não da nossa heurística:

  execute_sql            annotations.destructiveHint = true
      SQL completo: SELECT, INSERT, UPDATE, CREATE TABLE, ALTER TABLE.
  execute_sql_read_only  annotations.readOnlyHint = true
      Apenas SELECT / SHOW / DESCRIBE. Garantido pelo servidor.
  poll_sql_result
      Recupera resultado de query longa pelo `statement_id` devolvido por
      `execute_sql`/`execute_sql_read_only`.

Isto é uma melhoria real de postura: até aqui, "somente leitura" no Databricks
dependia do nosso ``check_sql_cost`` inspecionar a string SQL por regex. Agora
existe um tool cujo contrato de leitura é imposto do lado do servidor.

Referências:
  https://docs.databricks.com/aws/en/agents/mcp-tools/managed-mcp
  https://docs.databricks.com/aws/en/agents/mcp-tools/connect-clients
"""


def get_databricks_sql_mcp_config() -> dict:
    """Retorna a configuração MCP (HTTP) do servidor SQL gerenciado."""
    from data_agents.config.settings import settings  # local — evita circular import

    # DATABRICKS_HOST normalmente já vem com esquema (https://adb-....net),
    # mas aceitamos sem, e removemos barra final para não gerar '//api'.
    host = (settings.databricks_host or "").strip().rstrip("/")
    if host and not host.startswith(("http://", "https://")):
        host = f"https://{host}"

    return {
        "databricks_sql": {
            "type": "http",
            "url": f"{host}/api/2.0/mcp/sql",
            "headers": {"Authorization": f"Bearer {settings.databricks_token}"},
        }
    }


# ─── Lista de Tools ───────────────────────────────────────────────────────────
# Nomes conferidos ao vivo contra o workspace (JSON-RPC `tools/list`), não
# copiados de documentação.

DATABRICKS_SQL_MCP_TOOLS = [
    # destructiveHint: true — permite DDL/DML
    "mcp__databricks_sql__execute_sql",
    # readOnlyHint: true — SELECT/SHOW/DESCRIBE
    "mcp__databricks_sql__execute_sql_read_only",
    # recupera resultado de query longa
    "mcp__databricks_sql__poll_sql_result",
]

#: Subconjunto seguro — exclui `execute_sql`.
#:
#: Preferir este alias na maioria dos agentes. `execute_sql_read_only` tem o
#: contrato de leitura imposto pelo SERVIDOR; conceder `execute_sql` devolve ao
#: agente a capacidade de DDL/DML, que passaria a depender só dos nossos hooks.
DATABRICKS_SQL_MCP_READONLY_TOOLS = [
    "mcp__databricks_sql__execute_sql_read_only",
    "mcp__databricks_sql__poll_sql_result",
]
