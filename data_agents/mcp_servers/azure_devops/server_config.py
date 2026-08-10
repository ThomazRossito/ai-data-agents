"""
Configuração do MCP Server: azure_devops.

Integração com o MCP **oficial** da Microsoft para Azure DevOps
(`microsoft/azure-devops-mcp`, pacote npm `@azure-devops/mcp`). Cobre Repos
(branches, PRs, policies), Pipelines (builds/runs/YAML), Boards (work items,
iterations, backlogs), Wiki, Test Plans, Search e Advanced Security.

Casos de uso no data-agents:
  - azure-devops-engineer: gestão de pipelines YAML (CI/CD, deploy de Databricks
    DABs e Fabric via service principal), hierarquia de work items no Boards,
    branch/PR policies em Repos, Test Plans, Artifacts.

Servidor: @azure-devops/mcp (via npx) — repositório oficial microsoft/azure-devops-mcp
Protocolo: stdio
Documentação verificada em (WebFetch, 2026-08-09):
  https://raw.githubusercontent.com/microsoft/azure-devops-mcp/main/docs/GETTINGSTARTED.md
  https://raw.githubusercontent.com/microsoft/azure-devops-mcp/main/docs/TOOLSET.md

Comando confirmado (GETTINGSTARTED.md):
  npx -y @azure-devops/mcp <org>

Métodos de autenticação confirmados (GETTINGSTARTED.md — tabela "Authentication Methods"):
  - interactive (default, sem flag) — login interativo via browser, não serve p/ automação
  - azcli   (--authentication azcli)  — usa sessão `az login` ativa na máquina
  - envvar  (--authentication envvar) — bearer token cru via env ADO_MCP_AUTH_TOKEN
  - pat     (--authentication pat)    — Personal Access Token via env PERSONAL_ACCESS_TOKEN,
            **codificado em base64** como "<qualquer-string-não-vazia>:<pat-cru>"
            (a API do Azure DevOps só usa a parte do PAT; o e-mail pode ser qualquer valor)

Este projeto usa **pat** por padrão: é o único método não-interativo adequado para um
agente automatizado (envvar/bearer também serviria, mas exige que ALGO externo já tenha
emitido um bearer token — pat é o caminho direto a partir de um token gerado no ADO).
O dono do projeto usa ADO real (CI/CD + Boards) e roda o agente sem intervenção humana,
então "interactive" e "azcli" (que dependem de sessão de browser/CLI local) não servem
para o caso de uso principal.

# ⚠️ verificar: os nomes de tools abaixo foram extraídos de docs/TOOLSET.md, que documenta
# a nomenclatura como exibida no VS Code/GitHub Copilot (formato "mcp_ado_<dominio>_<ação>",
# onde "ado" é o nome do server escolhido nos exemplos oficiais de mcp.json). Não há, nos
# docs públicos, confirmação de como o Claude Agent SDK expõe esses MESMOS tools quando o
# server é registrado com a chave "azure_devops" (convenção deste projeto) — pela convenção
# `mcp__<server_key>__<tool_name>` já usada em todo o repo, a lista abaixo assume que o nome
# "cru" da tool (sem o prefixo "mcp_ado_") é o que o SDK usa após "mcp__azure_devops__". Se ao
# rodar `claude mcp list` / inspecionar tools reais os nomes vierem diferentes (ex.: com um
# prefixo "ado_" preservado, ou nomes truncados), ATUALIZE esta lista — não assuma.

Como obter:
  1. Azure DevOps → ícone de usuário → Personal Access Tokens → New Token
     Escopos mínimos recomendados: Code (Read & Write), Build (Read & Execute),
     Work Items (Read & Write), Project and Team (Read), Test Management (Read & Write)
  2. Copie o token cru para AZURE_DEVOPS_TOKEN no .env (SEM base64 — a codificação é
     feita automaticamente por este módulo antes de repassar ao servidor MCP)

Custo: gratuito (MCP open source da Microsoft; Azure DevOps em si tem plano free até 5
usuários com pipelines/repos ilimitados para projetos privados pequenos).

Referência: https://github.com/microsoft/azure-devops-mcp
"""

import base64


def get_azure_devops_mcp_config() -> dict:
    """Retorna a configuração MCP para o Azure DevOps (oficial, stdio, auth PAT)."""
    from data_agents.config.settings import settings  # importação local para evitar circular import

    # Formato exigido pelo servidor (docs/GETTINGSTARTED.md §Personal Access Token):
    # base64("<qualquer-string-não-vazia>:<pat-cru>"). O prefixo "pat" antes do ":"
    # é apenas o placeholder de e-mail exigido pelo formato — a API ignora essa parte.
    raw_token = settings.azure_devops_token
    encoded_pat = (
        base64.b64encode(f"pat:{raw_token}".encode("utf-8")).decode("ascii") if raw_token else ""
    )

    return {
        "azure_devops": {
            "type": "stdio",
            "command": "npx",
            "args": [
                "-y",
                "@azure-devops/mcp",
                settings.azure_devops_org,
                "--authentication",
                "pat",
            ],
            "env": {
                "PERSONAL_ACCESS_TOKEN": encoded_pat,
            },
        }
    }


# ─── Lista de Tools ────────────────────────────────────────────────────────────
# Extraída de docs/TOOLSET.md (microsoft/azure-devops-mcp, verificado 2026-08-09).
# ⚠️ verificar nome exato exposto pelo SDK em runtime — ver nota no docstring acima.

AZURE_DEVOPS_MCP_TOOLS = [
    # Advanced Security
    "mcp__azure_devops__advsec_get_alerts",
    "mcp__azure_devops__advsec_get_alert_details",
    # Core
    "mcp__azure_devops__core_list_projects",
    "mcp__azure_devops__core_list_project_teams",
    "mcp__azure_devops__core_get_identity_ids",
    # Pipelines
    "mcp__azure_devops__pipelines_create_pipeline",
    "mcp__azure_devops__pipelines_get_builds",
    "mcp__azure_devops__pipelines_get_build_status",
    "mcp__azure_devops__pipelines_get_build_log",
    "mcp__azure_devops__pipelines_get_build_log_by_id",
    "mcp__azure_devops__pipelines_get_build_changes",
    "mcp__azure_devops__pipelines_get_build_definitions",
    "mcp__azure_devops__pipelines_get_build_definition_revisions",
    "mcp__azure_devops__pipelines_run_pipeline",
    "mcp__azure_devops__pipelines_get_run",
    "mcp__azure_devops__pipelines_list_runs",
    "mcp__azure_devops__pipelines_update_build_stage",
    "mcp__azure_devops__pipelines_list_artifacts",
    "mcp__azure_devops__pipelines_download_artifact",
    # Repositories
    "mcp__azure_devops__repo_list_repos_by_project",
    "mcp__azure_devops__repo_get_repo_by_name_or_id",
    "mcp__azure_devops__repo_list_branches_by_repo",
    "mcp__azure_devops__repo_list_my_branches_by_repo",
    "mcp__azure_devops__repo_get_branch_by_name",
    "mcp__azure_devops__repo_create_branch",
    "mcp__azure_devops__repo_search_commits",
    "mcp__azure_devops__repo_list_pull_requests_by_repo_or_project",
    "mcp__azure_devops__repo_list_pull_requests_by_commits",
    "mcp__azure_devops__repo_get_pull_request_by_id",
    "mcp__azure_devops__repo_get_pull_request_changes",
    "mcp__azure_devops__repo_create_pull_request",
    "mcp__azure_devops__repo_update_pull_request",
    "mcp__azure_devops__repo_update_pull_request_reviewers",
    "mcp__azure_devops__repo_vote_pull_request",
    "mcp__azure_devops__repo_list_pull_request_threads",
    "mcp__azure_devops__repo_list_pull_request_thread_comments",
    "mcp__azure_devops__repo_create_pull_request_thread",
    "mcp__azure_devops__repo_update_pull_request_thread",
    "mcp__azure_devops__repo_reply_to_comment",
    "mcp__azure_devops__repo_list_directory",
    "mcp__azure_devops__repo_get_file_content",
    # Search
    "mcp__azure_devops__search_code",
    "mcp__azure_devops__search_wiki",
    "mcp__azure_devops__search_workitem",
    # Test Plans
    "mcp__azure_devops__testplan_list_test_plans",
    "mcp__azure_devops__testplan_create_test_plan",
    "mcp__azure_devops__testplan_list_test_suites",
    "mcp__azure_devops__testplan_create_test_suite",
    "mcp__azure_devops__testplan_add_test_cases_to_suite",
    "mcp__azure_devops__testplan_list_test_cases",
    "mcp__azure_devops__testplan_create_test_case",
    "mcp__azure_devops__testplan_update_test_case_steps",
    "mcp__azure_devops__testplan_show_test_results_from_build_id",
    # Wiki
    "mcp__azure_devops__wiki_list_wikis",
    "mcp__azure_devops__wiki_get_wiki",
    "mcp__azure_devops__wiki_list_pages",
    "mcp__azure_devops__wiki_get_page",
    "mcp__azure_devops__wiki_get_page_content",
    "mcp__azure_devops__wiki_create_or_update_page",
    # Work Items
    "mcp__azure_devops__wit_get_work_item",
    "mcp__azure_devops__wit_get_work_items_batch_by_ids",
    "mcp__azure_devops__wit_create_work_item",
    "mcp__azure_devops__wit_update_work_item",
    "mcp__azure_devops__wit_update_work_items_batch",
    "mcp__azure_devops__wit_add_child_work_items",
    "mcp__azure_devops__wit_work_items_link",
    "mcp__azure_devops__wit_work_item_unlink",
    "mcp__azure_devops__wit_add_artifact_link",
    "mcp__azure_devops__wit_link_work_item_to_pull_request",
    "mcp__azure_devops__wit_list_work_item_comments",
    "mcp__azure_devops__wit_add_work_item_comment",
    "mcp__azure_devops__wit_update_work_item_comment",
    "mcp__azure_devops__wit_list_work_item_revisions",
    "mcp__azure_devops__wit_get_work_item_type",
    "mcp__azure_devops__wit_my_work_items",
    "mcp__azure_devops__wit_get_work_items_for_iteration",
    "mcp__azure_devops__wit_list_backlogs",
    "mcp__azure_devops__wit_list_backlog_work_items",
    "mcp__azure_devops__wit_get_query",
    "mcp__azure_devops__wit_get_query_results_by_id",
    "mcp__azure_devops__wit_query_by_wiql",
    "mcp__azure_devops__wit_get_work_item_attachment",
    # Work (iterations/capacity)
    "mcp__azure_devops__work_list_iterations",
    "mcp__azure_devops__work_create_iterations",
    "mcp__azure_devops__work_list_team_iterations",
    "mcp__azure_devops__work_assign_iterations",
    "mcp__azure_devops__work_get_iteration_capacities",
    "mcp__azure_devops__work_get_team_capacity",
    "mcp__azure_devops__work_update_team_capacity",
    "mcp__azure_devops__work_get_team_settings",
]

# Subconjunto somente leitura: list_/get_/search_/query_by_wiql/show_test_results
# + downloads que não mutam estado no ADO (download_artifact, get_work_item_attachment).
AZURE_DEVOPS_MCP_READONLY_TOOLS = [
    "mcp__azure_devops__advsec_get_alerts",
    "mcp__azure_devops__advsec_get_alert_details",
    "mcp__azure_devops__core_list_projects",
    "mcp__azure_devops__core_list_project_teams",
    "mcp__azure_devops__core_get_identity_ids",
    "mcp__azure_devops__pipelines_get_builds",
    "mcp__azure_devops__pipelines_get_build_status",
    "mcp__azure_devops__pipelines_get_build_log",
    "mcp__azure_devops__pipelines_get_build_log_by_id",
    "mcp__azure_devops__pipelines_get_build_changes",
    "mcp__azure_devops__pipelines_get_build_definitions",
    "mcp__azure_devops__pipelines_get_build_definition_revisions",
    "mcp__azure_devops__pipelines_get_run",
    "mcp__azure_devops__pipelines_list_runs",
    "mcp__azure_devops__pipelines_list_artifacts",
    "mcp__azure_devops__pipelines_download_artifact",
    "mcp__azure_devops__repo_list_repos_by_project",
    "mcp__azure_devops__repo_get_repo_by_name_or_id",
    "mcp__azure_devops__repo_list_branches_by_repo",
    "mcp__azure_devops__repo_list_my_branches_by_repo",
    "mcp__azure_devops__repo_get_branch_by_name",
    "mcp__azure_devops__repo_search_commits",
    "mcp__azure_devops__repo_list_pull_requests_by_repo_or_project",
    "mcp__azure_devops__repo_list_pull_requests_by_commits",
    "mcp__azure_devops__repo_get_pull_request_by_id",
    "mcp__azure_devops__repo_get_pull_request_changes",
    "mcp__azure_devops__repo_list_pull_request_threads",
    "mcp__azure_devops__repo_list_pull_request_thread_comments",
    "mcp__azure_devops__repo_list_directory",
    "mcp__azure_devops__repo_get_file_content",
    "mcp__azure_devops__search_code",
    "mcp__azure_devops__search_wiki",
    "mcp__azure_devops__search_workitem",
    "mcp__azure_devops__testplan_list_test_plans",
    "mcp__azure_devops__testplan_list_test_suites",
    "mcp__azure_devops__testplan_list_test_cases",
    "mcp__azure_devops__testplan_show_test_results_from_build_id",
    "mcp__azure_devops__wiki_list_wikis",
    "mcp__azure_devops__wiki_get_wiki",
    "mcp__azure_devops__wiki_list_pages",
    "mcp__azure_devops__wiki_get_page",
    "mcp__azure_devops__wiki_get_page_content",
    "mcp__azure_devops__wit_get_work_item",
    "mcp__azure_devops__wit_get_work_items_batch_by_ids",
    "mcp__azure_devops__wit_list_work_item_comments",
    "mcp__azure_devops__wit_list_work_item_revisions",
    "mcp__azure_devops__wit_get_work_item_type",
    "mcp__azure_devops__wit_my_work_items",
    "mcp__azure_devops__wit_get_work_items_for_iteration",
    "mcp__azure_devops__wit_list_backlogs",
    "mcp__azure_devops__wit_list_backlog_work_items",
    "mcp__azure_devops__wit_get_query",
    "mcp__azure_devops__wit_get_query_results_by_id",
    "mcp__azure_devops__wit_query_by_wiql",
    "mcp__azure_devops__wit_get_work_item_attachment",
    "mcp__azure_devops__work_list_iterations",
    "mcp__azure_devops__work_list_team_iterations",
    "mcp__azure_devops__work_get_iteration_capacities",
    "mcp__azure_devops__work_get_team_capacity",
    "mcp__azure_devops__work_get_team_settings",
]

# Aliases genéricos consumidos por config/mcp_servers.py (padrão do projeto: MCP_TOOLS / MCP_READONLY_TOOLS)
MCP_TOOLS = AZURE_DEVOPS_MCP_TOOLS
MCP_READONLY_TOOLS = AZURE_DEVOPS_MCP_READONLY_TOOLS
