# Azure DevOps → Databricks / Fabric — Padrão de Deploy Verificado

> Fatos abaixo já verificados (não são "⚠️ verificar") — usar como padrão de referência.

## Databricks: Asset Bundles (DABs) via Azure Pipelines

O caminho padrão de CI/CD de ADO para Databricks é via **Databricks Asset Bundles (DABs)**, com os
comandos `databricks bundle validate` e `databricks bundle deploy` invocados de dentro de um
`azure-pipelines.yml`, autenticando com **service principal** (nunca PAT de usuário em pipeline de
produção).

### Autenticação por service principal

Variáveis de ambiente lidas pela Databricks CLI (via variable group linkado a Azure Key Vault):

```yaml
variables:
  - group: "databricks-sp-credentials"   # linkado a Azure Key Vault

steps:
  - script: |
      databricks bundle validate -t $(ENV_TARGET)
    displayName: "Validate DAB"
    env:
      DATABRICKS_HOST: $(DATABRICKS_HOST)
      DATABRICKS_CLIENT_ID: $(DATABRICKS_CLIENT_ID)
      DATABRICKS_CLIENT_SECRET: $(DATABRICKS_CLIENT_SECRET)
```

### Multi-ambiente dev/staging/prod

O `databricks.yml` do bundle define **targets** (`dev`, `staging`, `prod`), cada um com seu
próprio workspace/host. O pipeline ADO usa **stages** + **Environments** (com approvals) para
disparar `deploy -t <target>` no ambiente correto:

```yaml
stages:
  - stage: ValidateBundle
    condition: eq(variables['Build.Reason'], 'PullRequest')
    jobs:
      - job: Validate
        steps:
          - script: databricks bundle validate -t dev

  - stage: DeployDev
    dependsOn: ValidateBundle
    condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
    jobs:
      - deployment: Deploy
        environment: "databricks-dev"
        strategy:
          runOnce:
            deploy:
              steps:
                - script: databricks bundle deploy -t dev

  - stage: DeployStaging
    dependsOn: DeployDev
    jobs:
      - deployment: Deploy
        environment: "databricks-staging"   # approval configurado na UI do Environment
        strategy:
          runOnce:
            deploy:
              steps:
                - script: databricks bundle deploy -t staging

  - stage: DeployProd
    dependsOn: DeployStaging
    jobs:
      - deployment: Deploy
        environment: "databricks-prod"   # approval obrigatório (1+ aprovadores)
        strategy:
          runOnce:
            deploy:
              steps:
                - script: databricks bundle deploy -t prod
```

### Feature-branch → main

- PR para `main` → dispara `ValidateBundle` (build_reason = PullRequest) — apenas
  `bundle validate`, sem deploy.
- Merge em `main` → dispara a cadeia `DeployDev → DeployStaging → DeployProd`, cada stage
  seguinte com gate de approval no respectivo Environment.

## Microsoft Fabric via service principal

O mesmo padrão de credenciais de ambiente se aplica a deploys no Fabric: uma **Azure AD app
registration** (service principal) com acesso ao workspace Fabric alvo, cujas credenciais
(`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`) vêm de variable group linkado a Key
Vault — nunca em texto claro no YAML. O deploy em si (via Fabric REST API/CLI ou Fabric
Deployment Pipelines nativos) roda dentro do mesmo esqueleto de stages/Environments/approvals
acima. Para o conteúdo específico do deploy Fabric (itens, Deployment Pipelines nativos do
Fabric), consulte `fabric-engineer` — este documento cobre apenas o esqueleto de CI/CD no ADO.

## Regra de ouro

Este agente (`azure-devops-engineer`) é dono do **YAML de CI/CD** (stages, triggers, Environments,
approvals, variable groups) — nunca do **conteúdo do pipeline de dados** (transformações,
Medallion, DLT/SDP). Se o pedido for sobre o que a pipeline de dados FAZ, escale para
`databricks-engineer`/`fabric-engineer`; se for sobre COMO ela é acionada/promovida entre
ambientes via ADO, é escopo deste agente.
