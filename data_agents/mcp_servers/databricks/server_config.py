"""
Configuração do MCP Server: databricks — servidor do ai-dev-kit (Databricks, oficial).

HISTÓRICO, PARA NÃO REPETIR
---------------------------
Até 2026-09-14 este arquivo declarava 47 tools para um servidor que não estava
instalado. O pin ``databricks-mcp-server>=0.4.4`` resolvia no PyPI para o pacote
da comunidade (markov-kernel, módulo ``databricks_mcp``), enquanto a lista de
tools tinha sido escrita para o servidor do ai-dev-kit (módulo
``databricks_mcp_server``) — dois projetos diferentes com o mesmo nome de
distribuição. Medido em 2026-09-14, contra o código dos dois servidores:

    declaradas ........................... 47
    existiam no servidor instalado ....... 13
    existiam no ai-dev-kit ...............  9
    não existiam em NENHUM ............... 26   ← fantasmas

Todo agente com ``databricks_all`` recebia 34 tools inexistentes. Chamar
``list_pipelines`` devolvia "tool not found". O ``databricks-engineer`` promete
LakeFlow/DLT, Genie, AI/BI e KA/MAS na descrição — nenhuma dessas superfícies
existia no servidor instalado.

POR QUE O AI-DEV-KIT, E NÃO O GERENCIADO
----------------------------------------
A Databricks oferece MCP servers gerenciados (Public Preview; doc de 11/set/2026):
Genie One, Genie Agent, AI Search, Databricks SQL e UC Functions — mais os *MCP
Services* em Beta (``system.ai.dbsql``, ``web_search``, ``sandbox``). **Nenhum
cobre jobs, pipelines, clusters, UC admin, dashboards ou serving.** Para o caminho
de administração/escrita, o servidor do ai-dev-kit
(https://github.com/databricks-solutions/ai-dev-kit, Field Engineering) é a única
opção oficial.

Divisão de trabalho resultante:

    SQL sobre o Lakehouse ............ MCP gerenciado ``databricks_sql`` (HTTP)
    Jobs, pipelines, clusters,
    UC admin, dashboards, serving,
    Genie spaces, Vector Search,
    Lakebase, Apps .................. ESTE servidor (ai-dev-kit, stdio)

O pacote markov-kernel saiu do ``pyproject.toml``.

INSTALAÇÃO — É UM EXTRA, NÃO DEPENDÊNCIA CORE
----------------------------------------------
O ai-dev-kit não publica no PyPI. Está no ``pyproject.toml`` como extra
``databricks-admin``, pinado no SHA que foi lido para escrever este arquivo — o
vocabulário abaixo é válido para ESSE commit (``AI_DEV_KIT_COMMIT``).

    pip install -e ".[databricks-admin]"     # completo — compila plutoprint (minutos)
    make install-databricks-admin            # atalho — pula o build C++

Por que extra e não core: ``databricks-tools-core`` exige ``plutoprint==0.19.0``,
que só existe como sdist e compila C++ (meson + ICU baixado do GitHub) durante o
``pip install``. Isso não pode entrar no caminho crítico da CI nem de quem só
quer rodar o projeto com Fabric. A única tool que usa plutoprint
(``generate_and_upload_pdf``) não é oferecida aos agentes — ver ``_PDF``.

Sem o extra instalado, ``run_server.py`` falha rápido com mensagem que diz o que
instalar, e ``build_mcp_registry`` segue ativando os demais MCPs.

Autenticação: ``DATABRICKS_HOST`` + ``DATABRICKS_TOKEN`` (PAT) via SDK unificado
(``databricks_tools_core/client.py``, opção 3 da cadeia de auth).

Testes: ``tests/unit/test_mcp_configs.py`` compara a lista abaixo com um SNAPSHOT
dos nomes de tool no SHA pinado (``tests/fixtures/ai_dev_kit_tools.txt``), gerado
por ``scripts/snapshot_ai_dev_kit_tools.py`` a partir do fonte do servidor. A CI
não instala o extra; o snapshot é o que a mantém honesta.

ACTION-DISPATCH MUDA O QUE "READONLY" SIGNIFICA
-----------------------------------------------
As tools ``manage_*`` recebem ``action="create" | "delete" | "list" | ...``. O
``allowed_tools`` do SDK filtra por NOME de tool, então ``manage_pipeline`` ou
entra inteira ou não entra — ``action="delete"`` passa por qualquer agente que
tenha a tool. Duas consequências, ambas implementadas:

  1. ``DATABRICKS_MCP_READONLY_TOOLS`` é uma **lista explícita** de tools que não
     mutam estado do workspace SEJA QUAL FOR o argumento. Uma ``manage_*`` só
     entra se TODAS as suas actions forem de leitura (verificado no fonte do
     servidor, no SHA pinado). O heurístico antigo ``list_/get_/describe_`` não
     funciona mais e foi removido.

  2. ``hooks/security_hook.py::check_destructive_action`` inspeciona
     ``tool_input["action"]`` e barra verbos destrutivos ANTES da chamada. É a
     compensação obrigatória: sem ela, migrar para action-dispatch removeria em
     silêncio o controle por tool que S5/S6 pressupõem.

Custo: ``execute_sql``, ``execute_code``, ``ask_genie``, ``query_vs_index`` gastam
compute. Isso é domínio do ``cost_guard_hook``, não deste alias — "readonly" aqui
significa "não muta", não "não custa".
"""

from __future__ import annotations

#: Commit do ai-dev-kit para o qual o vocabulário abaixo foi verificado.
#: Ao subir o pin no pyproject.toml, atualize aqui e rode os testes.
AI_DEV_KIT_COMMIT = "b059fd0"


def get_databricks_mcp_config() -> dict:
    """Retorna a configuração MCP (stdio) do servidor do ai-dev-kit."""
    import sys
    from pathlib import Path

    from data_agents.config.settings import settings  # local — evita circular import

    _wrapper = str(Path(__file__).parent / "run_server.py")

    env = {
        "DATABRICKS_HOST": settings.databricks_host,
        "DATABRICKS_TOKEN": settings.databricks_token,
    }
    # O servidor usa o warehouse default do SDK se não informado; passar o nosso
    # evita `manage_warehouse(action="get_best")` a cada execute_sql.
    if settings.databricks_sql_warehouse_id:
        env["DATABRICKS_SQL_WAREHOUSE_ID"] = settings.databricks_sql_warehouse_id

    return {
        "databricks": {
            "type": "stdio",
            "command": sys.executable,
            "args": [_wrapper],
            "env": env,
        }
    }


# ─── Vocabulário do servidor (ai-dev-kit @ AI_DEV_KIT_COMMIT) ─────────────────
# Enumerado a partir dos decoradores @mcp.tool em databricks_mcp_server/tools/*.py.
# Agrupado pelo módulo de origem. As actions listadas nos comentários vêm do
# código de cada tool, não da documentação.

_P = "mcp__databricks__"

# agent_bricks.py — Knowledge Assistants e Multi-Agent Supervisors
_AGENT_BRICKS = [
    _P + "manage_ka",  # create_or_update | get | find_by_name | delete
    _P + "manage_mas",  # create_or_update | get | find_by_name | delete
]

# aibi_dashboards.py
_AIBI = [
    _P + "manage_dashboard",  # create_or_update | get | list | publish | unpublish | delete
]

# apps.py
_APPS = [
    _P + "manage_app",  # create_or_update | get | list | delete
]

# compute.py
_COMPUTE = [
    _P + "list_compute",  # node types, spark versions, clusters — leitura
    _P + "manage_cluster",  # create | get | modify | start | terminate | delete
    _P + "manage_sql_warehouse",  # create | modify | delete
    _P + "execute_code",  # roda Python/SQL em cluster ou serverless
]

# file.py + volume_files.py + workspace.py
_FILES = [
    _P + "manage_workspace_files",  # upload | delete
    _P + "manage_volume_files",  # list | get_info | upload | download | mkdir | delete
    _P + "manage_workspace",  # objetos do workspace
]

# genie.py
_GENIE = [
    _P + "manage_genie",  # create_or_update | get | list | export | import | delete
    _P + "ask_genie",  # pergunta em linguagem natural — leitura
]

# jobs.py
_JOBS = [
    _P + "manage_jobs",  # CRUD de jobs
    _P + "manage_job_runs",  # run_now | get | list | cancel
]

# lakebase.py
_LAKEBASE = [
    _P + "manage_lakebase_database",  # create_or_update | get | list | delete
    _P + "manage_lakebase_branch",  # create_or_update | delete
    _P + "manage_lakebase_sync",  # create_or_update | delete
    _P + "generate_lakebase_credential",
]

# manifest.py — rastreio de recursos criados pelo próprio servidor
_MANIFEST = [
    _P + "list_tracked_resources",  # leitura
    _P + "delete_tracked_resource",
]

# pdf.py — `generate_and_upload_pdf` NÃO é oferecida de propósito.
#
# É a única tool que depende de `plutoprint` (renderizador C++ que compila via
# meson e baixa o ICU do GitHub no `pip install`). `make install-databricks-admin`
# instala o servidor com --no-deps justamente para pular esse build; oferecer a
# tool aqui a faria falhar em runtime com ModuleNotFoundError. O projeto tem seu
# próprio caminho de relatório e não precisa dela.
_PDF: list[str] = []

# pipelines.py — Lakeflow Declarative Pipelines
_PIPELINES = [
    _P + "manage_pipeline",  # create | create_or_update | get | find_by_name | update | delete
    _P + "manage_pipeline_run",  # start | stop | get | get_events
]

# serving.py
_SERVING = [
    _P + "manage_serving_endpoint",  # get | list | query | inputs | messages | dataframe_records
]

# sql.py
_SQL = [
    _P + "execute_sql",  # SQL arbitrário — pode escrever
    _P + "execute_sql_multi",  # várias queries em paralelo — pode escrever
    _P + "manage_warehouse",  # list | get_best — leitura
    _P + "get_table_stats_and_schema",  # leitura
    _P + "get_volume_folder_details",  # leitura
]

# unity_catalog.py
_UNITY_CATALOG = [
    _P + "manage_uc_objects",  # catalog|schema|volume|function × create|get|list|update|delete
    _P + "manage_uc_grants",  # grants em catalog|schema|table|volume|function
    _P + "manage_uc_storage",  # create | get | list | update | validate | delete
    _P + "manage_uc_connections",  # create | list | update | create_foreign_catalog
    _P + "manage_uc_tags",  # set_tags | unset_tags | set_comment | query_*_tags
    _P
    + "manage_uc_security_policies",  # set/drop_row_filter | set/drop_column_mask | create_security_function
    _P + "manage_uc_monitors",  # create | get | delete | run_refresh | list_refreshes
    _P
    + "manage_uc_sharing",  # Delta Sharing: create|get|list|delete|add/remove_table|grant/revoke|rotate_token
    _P + "manage_metric_views",  # create | alter | describe | query | grant | drop
]

# user.py
_USER = [
    _P + "get_current_user",  # leitura
]

# vector_search.py
_VECTOR_SEARCH = [
    _P + "manage_vs_endpoint",  # create_or_update | get | list | delete
    _P + "manage_vs_index",  # create_or_update | get | list | delete | ...
    _P + "manage_vs_data",  # upsert | delete | scan | sync
    _P + "query_vs_index",  # busca por similaridade — leitura
]


#: Todas as tools do servidor. A ordem segue os módulos de origem.
DATABRICKS_MCP_TOOLS: list[str] = (
    _AGENT_BRICKS
    + _AIBI
    + _APPS
    + _COMPUTE
    + _FILES
    + _GENIE
    + _JOBS
    + _LAKEBASE
    + _MANIFEST
    + _PDF
    + _PIPELINES
    + _SERVING
    + _SQL
    + _UNITY_CATALOG
    + _USER
    + _VECTOR_SEARCH
)


#: Tools que NÃO mutam estado do workspace, qualquer que seja o argumento.
#:
#: Lista explícita, não heurística. Uma `manage_*` só entra se TODAS as actions
#: dela forem de leitura — `manage_warehouse` (list|get_best) e
#: `manage_serving_endpoint` (get|list|query|inputs|messages|dataframe_records)
#: qualificam; `manage_dashboard` não, porque tem `delete`. Invocar um endpoint
#: de serving gasta compute mas não muta o workspace: isso é do cost_guard.
#:
#: FORA de propósito: `execute_sql`, `execute_sql_multi`, `execute_code` — todos
#: aceitam escrita. Agente que precisa ler SQL deve usar o alias
#: `databricks_sql_readonly`, cujo contrato read-only é imposto pelo servidor
#: gerenciado, não por nós.
DATABRICKS_MCP_READONLY_TOOLS: list[str] = [
    _P + "list_compute",
    _P + "get_current_user",
    _P + "get_table_stats_and_schema",
    _P + "get_volume_folder_details",
    _P + "list_tracked_resources",
    _P + "manage_warehouse",
    _P + "manage_serving_endpoint",
    _P + "ask_genie",
    _P + "query_vs_index",
]

#: AI/BI + Agent Bricks — Genie spaces, dashboards, KA, MAS.
DATABRICKS_AIBI_TOOLS: list[str] = _GENIE + _AIBI + _AGENT_BRICKS

#: Model Serving — consulta e inspeção de endpoints.
DATABRICKS_SERVING_TOOLS: list[str] = _SERVING

#: Compute — clusters, warehouses, execução de código.
DATABRICKS_COMPUTE_TOOLS: list[str] = _COMPUTE

#: Pipelines e Jobs — o núcleo de engenharia.
DATABRICKS_PIPELINES_TOOLS: list[str] = _PIPELINES + _JOBS

#: Unity Catalog — administração (objetos, grants, tags, políticas, sharing).
DATABRICKS_UC_ADMIN_TOOLS: list[str] = _UNITY_CATALOG

#: Vector Search — endpoints, índices, dados, busca.
DATABRICKS_VECTOR_SEARCH_TOOLS: list[str] = _VECTOR_SEARCH


# ─── Mapa de migração (nomes antigos → equivalente real) ─────────────────────
#: Os 26 nomes fantasmas e o que usar no lugar. Consumido pelo lint de agentes
#: para apontar a correção certa em vez de só acusar "tool não existe".
LEGACY_TOOL_MAP: dict[str, str] = {
    "list_catalogs": "databricks_sql_readonly → SHOW CATALOGS, ou manage_uc_objects(action='list', object_type='catalog')",
    "list_schemas": "databricks_sql_readonly → SHOW SCHEMAS IN <catalog>",
    "list_tables": "databricks_sql_readonly → SHOW TABLES IN <catalog>.<schema>",
    "describe_table": "get_table_stats_and_schema",
    "get_table_schema": "get_table_stats_and_schema",
    "sample_table_data": "databricks_sql_readonly → SELECT * FROM <t> LIMIT n",
    "list_sql_warehouses": "manage_warehouse(action='list')",
    "get_best_warehouse": "manage_warehouse(action='get_best')",
    "get_query_history": "(sem equivalente no servidor — usar system.query.history via SQL)",
    "list_jobs": "manage_jobs(action='list')",
    "get_job": "manage_jobs(action='get')",
    "run_job_now": "manage_job_runs(action='run_now')",
    "list_job_runs": "manage_job_runs(action='list')",
    "get_run": "manage_job_runs(action='get')",
    "cancel_run": "manage_job_runs(action='cancel')",
    "wait_for_run": "manage_job_runs(action='get') em polling",
    "list_pipelines": "manage_pipeline(action='find_by_name') — não há list global",
    "get_pipeline": "manage_pipeline(action='get')",
    "create_or_update_pipeline": "manage_pipeline(action='create_or_update')",
    "start_pipeline": "manage_pipeline_run(action='start')",
    "stop_pipeline": "manage_pipeline_run(action='stop')",
    "get_pipeline_update": "manage_pipeline_run(action='get')",
    "list_clusters": "list_compute",
    "get_cluster": "manage_cluster(action='get')",
    "start_cluster": "manage_cluster(action='start')",
    "list_workspace": "manage_workspace",
    "export_notebook": "manage_workspace",
    "import_notebook": "manage_workspace_files(action='upload')",
    "upload_to_workspace": "manage_workspace_files(action='upload')",
    "list_files": "manage_volume_files(action='list')",
    "read_file": "manage_volume_files(action='download')",
    "upload_to_volume": "manage_volume_files(action='upload')",
    "list_volume_files": "manage_volume_files(action='list')",
    "create_or_update_genie": "manage_genie(action='create_or_update')",
    "create_or_update_dashboard": "manage_dashboard(action='create_or_update')",
    "list_serving_endpoints": "manage_serving_endpoint(action='list')",
    "get_serving_endpoint_status": "manage_serving_endpoint(action='get')",
    "query_serving_endpoint": "manage_serving_endpoint(action='query')",
    "list_warehouses": "manage_warehouse(action='list')",
}
