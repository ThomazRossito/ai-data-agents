---
domain: azure-devops
updated_at: 2026-08-09
agents: [azure-devops-engineer]
mcp_validated: "2026-08-09"
---

# KB: Azure DevOps — Índice

**Domínio:** Azure DevOps (ADO) — Repos, Pipelines, Boards, Artifacts, Test Plans.
**Agente:** `azure-devops-engineer`
**MCP:** oficial `microsoft/azure-devops-mcp` (`@azure-devops/mcp`, verificado via WebFetch em 2026-08-09
contra `docs/GETTINGSTARTED.md` e `docs/TOOLSET.md` do repositório).

---

## Conteúdo Disponível

### Conceitos (`concepts/`)

| Arquivo | Conteúdo |
|---|---|
| `concepts/pipelines-cicd.md` | Azure Pipelines YAML: stages, jobs, triggers, Environments + approvals, variable groups/Key Vault |
| `concepts/boards-work-items.md` | Hierarquia de work items Agile (epic→feature→user story→task) e Scrum (epic→feature→PBI→task), links parent/child, iterations |
| `concepts/repos-branching.md` | Branch policies, pull requests, threads de review, estratégia feature-branch→main |
| `concepts/deploy-databricks-fabric.md` | Padrão verificado: ADO → Databricks via Databricks Asset Bundles (DABs), autenticação por service principal, multi-ambiente dev/staging/prod |

---

## Componentes do Azure DevOps (visão geral)

| Componente | O que cobre |
|---|---|
| **Repos** | Git repositories, branch policies, pull requests |
| **Pipelines** | CI/CD via YAML (`azure-pipelines.yml`), builds, releases, environments |
| **Boards** | Work item tracking — Epics, Features, User Stories/PBIs, Tasks, Bugs |
| **Artifacts** | Feeds de pacotes (NuGet/npm/Maven/PyPI) privados |
| **Test Plans** | Test plans, suites, casos de teste, resultados por build |

---

## Regras de Negócio Críticas

### MCP oficial — auditoria de nomenclatura
O MCP oficial (`microsoft/azure-devops-mcp`) passou por uma **consolidação de tools com
renomeação** (ver aviso em `README.md` do repositório upstream). A referência normativa de nomes
de tool é `docs/TOOLSET.md` do repositório (não invente nomes fora dessa lista). A lista completa
usada por este projeto está espelhada em
`data_agents/mcp_servers/azure_devops/server_config.py` (`AZURE_DEVOPS_MCP_TOOLS`).

### Autenticação
4 métodos suportados pelo servidor local (`--authentication <método>`):
`interactive` (default, browser login), `azcli` (sessão `az login`), `envvar` (bearer cru via
`ADO_MCP_AUTH_TOKEN`), `pat` (Personal Access Token via `PERSONAL_ACCESS_TOKEN`, **base64** de
`"<qualquer-string>:<pat-cru>"`). Este projeto usa **pat** por padrão — único método não-interativo
adequado para automação sem depender de sessão de browser/CLI local.

> A Microsoft também oferece um **Remote MCP Server** (`https://mcp.dev.azure.com/{org}`, HTTP)
> recomendado para novos setups, mas este projeto usa o servidor **local stdio** (`npx
> @azure-devops/mcp`) para manter consistência com o padrão `stdio` de todos os outros MCPs do
> projeto.

### Domínios (filtro opcional de tools)
O servidor aceita `-d <domínio>` para restringir tools carregadas: `core`, `work`, `work-items`,
`repositories`, `wiki`, `pipelines`, `search`, `test-plans`, `advanced-security`. Por padrão (sem
`-d`), todos os domínios são carregados — é o comportamento usado por este projeto
(`get_azure_devops_mcp_config()` não passa `-d`).

### Governança
- PII em work items/wiki (dados de cliente) → escalar `governance-auditor` (S6).
- Credenciais de service principal em pipelines → sempre via variable group / Azure Key Vault
  linked variable group, nunca em texto claro no YAML (S5).

---

## Escalação

| Situação | Agente |
|---|---|
| Conteúdo do pipeline de dados Databricks (transformações, DLT/SDP) | `databricks-engineer` |
| Conteúdo do pipeline de dados Fabric (Medallion, Data Factory) | `fabric-engineer` |
| Análise/otimização estrutural da árvore de work items (DAG, split/merge) | `task-architect` |
| Custo de Azure (agent pools, storage) | `azure-cost-calculator` |
| PII em work items/wiki | `governance-auditor` |
