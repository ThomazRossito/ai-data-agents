---
name: azure-devops-engineer
description: "Playbook operacional do Azure DevOps (Repos, Pipelines, Boards, Artifacts, Test Plans) via MCP oficial microsoft/azure-devops-mcp. Use ao montar azure-pipelines.yml de deploy de Databricks Asset Bundles/Fabric, políticas de PR, ou modelar hierarquia de Boards."
updated_at: "2026-08-09"
source: kb/azure-devops/index.md + kb/azure-devops/concepts/*.md + docs/GETTINGSTARTED.md e docs/TOOLSET.md (microsoft/azure-devops-mcp, verificado via WebFetch 2026-08-09)
---

# SKILL: Azure DevOps Engineer

> **Fonte:** `microsoft/azure-devops-mcp` (docs oficiais) + KB interna `kb/azure-devops/`
> **Atualizado:** Agosto 2026
> **Uso:** Leia este arquivo ANTES de montar pipelines YAML, hierarquia de Boards, ou qualquer
> tarefa Azure DevOps.

---

## 0. Quando usar o MCP vs quando marcar "⚠️ verificar"

- **Sempre** prefira uma tool MCP (`mcp__azure_devops__*`) a inventar comportamento. Se o MCP
  `azure_devops` não estiver ativo (sem `AZURE_DEVOPS_ORG`/`AZURE_DEVOPS_TOKEN`), PARE e oriente a
  configuração — nunca simule uma resposta de tool.
- Se uma tool esperada não existir na lista confirmada
  (`data_agents/mcp_servers/azure_devops/server_config.py` → `AZURE_DEVOPS_MCP_TOOLS`), ou se um
  nome de task de pipeline YAML/flag de CLI não estiver confirmado por doc oficial, marque
  explicitamente **⚠️ verificar** na resposta — nunca invente.

---

## 1. Montar `azure-pipelines.yml` de deploy Databricks (checklist)

1. Confirmar target(s) do `databricks.yml` do bundle (`dev`/`staging`/`prod`).
2. Trigger: PR para `main` → só `validate`; merge em `main` → cadeia de `deploy` por ambiente.
3. Credenciais de service principal via **variable group linkado a Azure Key Vault** — nunca
   hardcoded, nunca PAT de usuário em pipeline de produção.
4. Cada stage de deploy usa `environment: "<nome>"` — o **approval** (gate humano) é configurado
   na UI do ADO (Environments → Approvals and checks), não no YAML.
5. `staging` e `prod` SEMPRE com approval; `dev` pode ser auto-deploy.
6. Comandos: `databricks bundle validate -t <target>` e `databricks bundle deploy -t <target>`.
7. Ver template completo em `kb/azure-devops/concepts/deploy-databricks-fabric.md`.

## 2. Branch/PR Policies (checklist)

1. `main` protegido: mínimo de reviewers + build validation obrigatória + linked work item.
2. PR sempre referencia um work item (`workItems` no `repo_create_pull_request`).
3. Merge só depois do build de `Validate` verde (branch policy de build validation aponta para a
   pipeline de CI).
4. Ver `kb/azure-devops/concepts/repos-branching.md` para o fluxo completo.

## 3. Hierarquia de Boards (checklist)

1. Confirmar processo do projeto (Agile vs Scrum) antes de criar work items —
   `wit_get_work_item_type`.
2. Agile: Epic → Feature → User Story → Task. Scrum: Epic → Feature → PBI → Task.
3. Criar de cima para baixo; usar `wit_add_child_work_items` para já nascer com o link
   parent/child (evita um passo extra de `wit_work_items_link`).
4. Se o pedido for de ANÁLISE/otimização da árvore (não criação) — escalar `task-architect`.
5. Ver `kb/azure-devops/concepts/boards-work-items.md`.

## 4. Quando usar o MCP do Azure DevOps

| Situação | Ferramenta |
|---|---|
| Listar projetos/times | `core_list_projects`, `core_list_project_teams` |
| Criar/ler/ligar work items | `wit_create_work_item`, `wit_get_work_item`, `wit_add_child_work_items`, `wit_work_items_link` |
| Consultar work items por filtro | `wit_query_by_wiql` (WIQL) |
| Criar/revisar PR | `repo_create_pull_request`, `repo_get_pull_request_changes`, `repo_vote_pull_request` |
| Criar/disparar pipeline | `pipelines_create_pipeline`, `pipelines_run_pipeline` |
| Diagnosticar build | `pipelines_get_build_status`, `pipelines_get_build_log` |
| Test Plans | `testplan_create_test_plan`, `testplan_create_test_case`, `testplan_show_test_results_from_build_id` |
| Wiki | `wiki_get_page_content`, `wiki_create_or_update_page` |

Lista completa: `data_agents/mcp_servers/azure_devops/server_config.py`.

## 5. Autenticação do MCP (referência rápida)

| Método | Flag | Env var | Uso |
|---|---|---|---|
| interactive | (default) | — | dev local, não serve p/ automação |
| azcli | `--authentication azcli` | — | máquina já logada via `az login` |
| envvar | `--authentication envvar` | `ADO_MCP_AUTH_TOKEN` | bearer já emitido por outra ferramenta |
| **pat** (usado por este projeto) | `--authentication pat` | `PERSONAL_ACCESS_TOKEN` (base64 de `"<qualquer>:<pat>"`) | CI/CD, automação sem sessão interativa |

A codificação base64 é feita automaticamente por `get_azure_devops_mcp_config()` — configure
apenas o PAT cru em `AZURE_DEVOPS_TOKEN` no `.env`.
