# Azure Repos — Branching e Pull Requests

## Branch policies

Configuradas por branch (tipicamente `main`) em Project Settings → Repositories → Branches →
Branch policies. Políticas comuns:
- **Require a minimum number of reviewers** (ex.: 1-2 aprovadores)
- **Check for linked work items** (todo PR deve referenciar um work item)
- **Build validation** (o pipeline de `Validate` deve passar antes do merge)
- **Comment requirements** (todos os comentários resolvidos antes do merge)

O MCP não expõe hoje uma tool dedicada de "configurar branch policy" no `docs/TOOLSET.md`
verificado — políticas são geralmente configuradas via UI/REST API direta do ADO fora do MCP.
Se o usuário pedir para automatizar isso, marque **⚠️ verificar** se existe tool equivalente antes
de assumir que não é possível.

## Fluxo feature-branch → main

1. Criar branch de feature: `repo_create_branch` (a partir de `main`).
2. Desenvolver, commitar.
3. Abrir PR: `repo_create_pull_request` (sourceRefName, targetRefName, title, workItems).
4. Revisão: `repo_get_pull_request_changes` (diff), `repo_create_pull_request_thread`
   (comentários inline com `filePath` + linhas), `repo_reply_to_comment`.
5. Aprovação: `repo_vote_pull_request` (10 = approved, 5 = approved with suggestions,
   0 = no vote, -5 = waiting for author, -10 = rejected — valores do enum do ADO REST API;
   ⚠️ verificar contra a doc oficial antes de usar em produção).
6. Merge: `repo_update_pull_request` (status: completed, mergeStrategy, deleteSourceBranch).

## Pesquisa de código e commits

- `search_code` — busca full-text em repositórios (requer Azure DevOps Search instalado/habilitado
  na organização).
- `repo_search_commits` — filtros por autor, data, texto de commit.
- `repo_list_pull_requests_by_commits` — encontrar em quais PRs um commit específico entrou.

## Navegação de arquivos

`repo_list_directory` / `repo_get_file_content` — leitura de arquivos em uma branch/tag/commit
específico (parâmetro `version` + `versionType`), útil para inspecionar `azure-pipelines.yml`
existente antes de propor mudanças.
