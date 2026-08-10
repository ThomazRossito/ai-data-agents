# Azure Pipelines — CI/CD em YAML

## Estrutura básica

Um `azure-pipelines.yml` é composto por **trigger** (o que dispara o pipeline), **pool** (agent
pool), e um ou mais **stages**, cada um com **jobs**, cada um com **steps/tasks**.

```yaml
trigger:
  branches:
    include:
      - main

pr:
  branches:
    include:
      - main

pool:
  vmImage: "ubuntu-latest"

stages:
  - stage: Validate
    condition: eq(variables['Build.Reason'], 'PullRequest')
    jobs:
      - job: ValidateJob
        steps:
          - script: echo "validate step"

  - stage: DeployDev
    dependsOn: Validate
    condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
    jobs:
      - deployment: DeployDevJob
        environment: "dev"
        strategy:
          runOnce:
            deploy:
              steps:
                - script: echo "deploy to dev"
```

## Feature-branch → main

- **Pull Request** para `main` dispara o bloco `pr:` (trigger de PR) — tipicamente só a stage de
  `validate` (build, lint, testes, `bundle validate`).
- **Merge em `main`** dispara o bloco `trigger:` — a stage de `deploy` roda a partir daí.
- Combine com **branch policies** em Repos (build validation obrigatória antes do merge) para
  garantir que nenhum PR seja mergeado sem o `validate` verde.

## Environments + Approvals (multi-ambiente dev/staging/prod)

`environment: "prod"` referencia um **Environment** do Azure Pipelines (Pipelines → Environments).
Um Environment pode ter **Approvals and checks** configurados na UI do ADO (não no YAML) — isso é
o que implementa o **gate humano** antes de promover para staging/prod. O `deployment job` só
prossegue depois que o approval é concedido manualmente por um usuário autorizado.

Padrão recomendado:
1. `Validate` (sempre, em qualquer branch/PR)
2. `DeployDev` (auto, sem approval — ambiente de baixo risco)
3. `DeployStaging` (approval opcional — 1 aprovador)
4. `DeployProd` (approval obrigatório — 1+ aprovadores, branch protegido)

## Variáveis e segredos

- **Variable groups** (Pipelines → Library) para variáveis compartilhadas entre pipelines.
- **Azure Key Vault linked variable group** para segredos (service principal secret, tokens) —
  nunca hardcode segredos no YAML nem em variable group sem link a Key Vault.
- Referencie no YAML: `variables: - group: "meu-variable-group"`.

## Diagnóstico de builds

Via MCP: `pipelines_get_build_status` (status atual), `pipelines_get_build_log` (log completo),
`pipelines_get_build_changes` (commits associados ao build), `pipelines_get_build_definitions`
(listar definitions do projeto).
