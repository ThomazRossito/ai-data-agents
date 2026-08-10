"""
Configuração do MCP Server para Databricks.

⚠️ ESTADO ATUAL — descasamento conhecido (auditoria 2026-07-26):
O pin `databricks-mcp-server>=0.4.4` (pyproject.toml) resolve, no PyPI, para o
pacote da COMUNIDADE de Olivier Debeuf De Rijcker / markov-kernel (MIT) —
https://github.com/markov-kernel/databricks-mcp — e NÃO para o servidor oficial
do ai-dev-kit da Databricks. `run_server.py` importa o módulo `databricks_mcp`
desse pacote (tools granulares: list_/create_/run_ de clusters, jobs, workspace,
Unity Catalog, execute_sql).

O servidor do ai-dev-kit (https://github.com/databricks-solutions/ai-dev-kit,
Field Engineering) é um pacote DIFERENTE (`databricks_mcp_server`, tools `manage_*`),
NÃO publicado no PyPI — daí a colisão de nome. A lista `DATABRICKS_MCP_TOOLS`
abaixo foi escrita para ESSE servidor do ai-dev-kit e pode não corresponder ao
servidor markov instalado.

Resolução pendente (decisão do time): (a) assumir o pacote markov e reduzir a
tool-list às tools reais dele; ou (b) adotar o servidor do ai-dev-kit
(vendorizar / instalar editável). Verificar o servidor real com:
  databricks-mcp-server --list-tools

Pré-requisitos:
  pip install databricks-mcp-server   # markov-kernel (comunidade), NÃO Databricks
  Configurar: DATABRICKS_HOST e DATABRICKS_TOKEN no .env
"""


def get_databricks_mcp_config() -> dict:
    """Retorna a configuração MCP para o Databricks."""
    import sys
    from pathlib import Path
    from data_agents.config.settings import settings  # importação local para evitar circular import

    _wrapper = str(Path(__file__).parent / "run_server.py")

    return {
        "databricks": {
            "type": "stdio",
            "command": sys.executable,
            "args": [_wrapper],
            "env": {
                "DATABRICKS_HOST": settings.databricks_host,
                "DATABRICKS_TOKEN": settings.databricks_token,
                "DATABRICKS_SQL_WAREHOUSE_ID": settings.databricks_sql_warehouse_id,
            },
        }
    }


# ⚠️ Lista escrita para o servidor do ai-dev-kit (tools manage_*/create_or_update_*).
# NÃO reflete necessariamente o servidor markov instalado (ver docstring acima).
# Reconciliar com `databricks-mcp-server --list-tools` antes de confiar nesta lista.
# Auditoria 2026-07-26: itens como list_pipelines/get_pipeline/describe_table/
# wait_for_run/get_best_warehouse/manage_ka/manage_mas NÃO existem no pacote markov.
DATABRICKS_MCP_TOOLS = [
    # Unity Catalog — Descoberta de metadados
    "mcp__databricks__list_catalogs",
    "mcp__databricks__list_schemas",
    "mcp__databricks__list_tables",
    "mcp__databricks__describe_table",
    "mcp__databricks__get_table_schema",
    "mcp__databricks__get_table_stats_and_schema",  # stats + schema combinados (novo)
    "mcp__databricks__sample_table_data",
    # SQL
    "mcp__databricks__execute_sql",
    "mcp__databricks__execute_sql_multi",  # executa múltiplas queries em paralelo (novo)
    "mcp__databricks__list_sql_warehouses",
    "mcp__databricks__get_best_warehouse",  # seleciona warehouse ideal para a query (novo)
    "mcp__databricks__get_query_history",
    # Jobs & Workflows
    "mcp__databricks__list_jobs",
    "mcp__databricks__get_job",
    "mcp__databricks__run_job_now",
    "mcp__databricks__list_job_runs",
    "mcp__databricks__get_run",
    "mcp__databricks__cancel_run",
    "mcp__databricks__wait_for_run",  # aguarda conclusão com polling (novo)
    # Spark Declarative Pipelines (LakeFlow)
    "mcp__databricks__list_pipelines",
    "mcp__databricks__get_pipeline",
    "mcp__databricks__create_or_update_pipeline",
    "mcp__databricks__start_pipeline",
    "mcp__databricks__stop_pipeline",
    "mcp__databricks__get_pipeline_update",
    # Compute
    "mcp__databricks__list_clusters",
    "mcp__databricks__get_cluster",
    "mcp__databricks__start_cluster",
    "mcp__databricks__manage_cluster",  # create/modify/terminate clusters (novo)
    "mcp__databricks__manage_sql_warehouse",  # CRUD completo de warehouses (novo)
    "mcp__databricks__list_compute",  # node types, spark versions disponíveis (novo)
    "mcp__databricks__execute_code",  # executa código em serverless/cluster (novo)
    # Workspace & Notebooks
    "mcp__databricks__list_workspace",
    "mcp__databricks__export_notebook",
    "mcp__databricks__import_notebook",
    "mcp__databricks__upload_to_workspace",  # upload de arquivos/pastas (novo)
    # Files & Volumes
    "mcp__databricks__list_files",
    "mcp__databricks__read_file",
    "mcp__databricks__upload_to_volume",
    "mcp__databricks__list_volume_files",
    # AI/BI — Genie e Dashboards
    "mcp__databricks__create_or_update_genie",  # cria/atualiza Genie Space (novo)
    "mcp__databricks__create_or_update_dashboard",  # cria/publica AI/BI Dashboard (novo)
    # AI Agents — Knowledge Assistants e Mosaic AI Supervisor
    "mcp__databricks__manage_ka",  # Knowledge Assistants (novo)
    "mcp__databricks__manage_mas",  # Mosaic AI Supervisor Agents (novo)
    # Model Serving
    "mcp__databricks__list_serving_endpoints",  # lista endpoints disponíveis (novo)
    "mcp__databricks__get_serving_endpoint_status",  # verifica saúde do endpoint (novo)
    "mcp__databricks__query_serving_endpoint",  # invoca chat/ML model (novo)
]

# Subconjunto apenas de leitura/descoberta (para agentes sem permissão de escrita)
DATABRICKS_MCP_READONLY_TOOLS = [
    t
    for t in DATABRICKS_MCP_TOOLS
    if any(
        kw in t
        for kw in [
            "list_",
            "get_",
            "describe_",
            "sample_",
            "export_",
            "read_",
            "query_serving_endpoint",  # leitura de modelo — permitido em readonly
        ]
    )
]

# Subconjunto AI/BI — Genie, Dashboards, Knowledge Assistants, Mosaic AI Supervisor
DATABRICKS_AIBI_TOOLS = [
    "mcp__databricks__create_or_update_genie",
    "mcp__databricks__create_or_update_dashboard",
    "mcp__databricks__manage_ka",
    "mcp__databricks__manage_mas",
]

# Subconjunto Model Serving — endpoints de modelos ML/GenAI
DATABRICKS_SERVING_TOOLS = [
    "mcp__databricks__list_serving_endpoints",
    "mcp__databricks__get_serving_endpoint_status",
    "mcp__databricks__query_serving_endpoint",
]

# Subconjunto Compute avançado — criação/gestão de clusters e execução de código
DATABRICKS_COMPUTE_TOOLS = [
    "mcp__databricks__manage_cluster",
    "mcp__databricks__manage_sql_warehouse",
    "mcp__databricks__list_compute",
    "mcp__databricks__execute_code",
    "mcp__databricks__wait_for_run",
]
