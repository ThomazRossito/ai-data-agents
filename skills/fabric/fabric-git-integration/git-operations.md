# Git Operations - Referencia Tecnica

## REST API Endpoints

### Git Connection

**POST /workspaces/{workspaceId}/git/connect**
- Conectar workspace ao repositorio (GitHub ou ADO)
- Payload GitHub:
  ```json
  {
    "gitProviderDetails": {
      "gitProviderType": "GitHub",
      "ownerName": "myorg",
      "repositoryName": "fabric-repo",
      "branchName": "main",
      "directoryName": "/"
    },
    "myGitCredentials": {
      "source": "ConfiguredConnection",
      "connectionId": "connection-uuid"
    }
  }
  ```
- Payload ADO:
  ```json
  {
    "gitProviderDetails": {
      "gitProviderType": "AzureDevOps",
      "organizationName": "MyOrg",
      "projectName": "AnalyticsProject",
      "repositoryName": "fabric-repo",
      "branchName": "develop",
      "directoryName": "/src"
    },
    "myGitCredentials": {
      "source": "ConfiguredConnection",
      "connectionId": "connection-uuid"
    }
  }
  ```

**GET /workspaces/{workspaceId}/git/connection**
- Obter detalhes da conexao Git atual

**GET /workspaces/{workspaceId}/git/status**
- Obter status da sincronizacao
- Retorno: `{ "remoteCommitHash": "...", "workspaceHead": "...", "branch": "main", ... }`

**POST /workspaces/{workspaceId}/git/disconnect**
- Desconectar do Git

### Commits and Sync

**POST /workspaces/{workspaceId}/git/commitToGit**
- Fazer commit de workspace para Git (LRO)
- Payload All:
  ```json
  {
    "mode": "All",
    "comment": "Automatizado - v2.0"
  }
  ```
- Payload Selective:
  ```json
  {
    "mode": "Selective",
    "comment": "Selective commit",
    "items": [
      {"itemId": "item-uuid", "itemType": "Notebook"}
    ]
  }
  ```

**POST /workspaces/{workspaceId}/git/updateFromGit**
- Sincronizar com remote (Pull + Merge) (LRO)
- Payload:
  ```json
  {
    "remoteCommitHash": "abc123...",
    "workspaceHead": "def456...",
    "conflictResolution": {
      "conflictResolutionPolicy": "PreferRemote"
    },
    "options": {
      "allowOverrideItems": true
    }
  }
  ```

### Credentials

**GET /workspaces/{workspaceId}/git/myGitCredentials**
- Obter tipo de credencial atual

**PATCH /workspaces/{workspaceId}/git/myGitCredentials**
- Atualizar credencial
- Payload Automatic:
  ```json
  {
    "source": "Automatic"
  }
  ```
- Payload ConfiguredConnection:
  ```json
  {
    "source": "ConfiguredConnection",
    "connectionId": "connection-uuid"
  }
  ```
- Payload None:
  ```json
  {
    "source": "None"
  }
  ```

---

## Branch Strategies

### Feature Branch (Development)
- Branch: `develop` ou `feature/feature-name`
- Strategy: Commit seletivos, merge para main via PR

### Release Branch (Staging)
- Branch: `release/v1.0` ou `staging`
- Strategy: Commit seletivo de modelos prontos para release

### Production Branch (Main)
- Branch: `main` ou `production`
- Strategy: Commits validados, preferencialmente via deploy pipeline

---

## Credentials

### Service Principal (SPN)
Para automacao em produção. Requer:
- Application ID
- Tenant ID
- Client Secret

Payload connection:
```json
{
  "source": "ConfiguredConnection",
  "connectionId": "spn-connection-uuid"
}
```

### User Credentials
Para desenvolvimento. Usuario faz login manualmente.

```json
{
  "source": "Automatic"
}
```

### No Credentials
Apenas leitura (read-only).

```json
{
  "source": "None"
}
```

---

## Conflict Resolution Policies

### PreferWorkspace
Manter conteudo local (workspace). Remote vira backup.
Use quando workspace eh fonte de verdade.

### PreferRemote
Sobrescrever com remote (Git). Local vira backup.
Use quando Git eh fonte de verdade.

---

## Item Types Suportados

Tipos validos para selective commit:
- Notebook
- SemanticModel
- Report
- Dashboard
- MLModel
- Environment
- DataPipeline
- etc

---

## Exemplos Python

### Conectar GitHub e fazer commit

```python
from git_integration import github_connect, commit_to_git

# 1. Conectar
github_connect(
    workspace="analytics",
    connection="github-token",
    owner_name="DataTeam",
    repository_name="fabric-analytics",
    branch_name="develop"
)

# 2. Commit tudo
commit_to_git(
    workspace="analytics",
    mode="All",
    comment="Producao semanal"
)
```

### Sincronizar com conflito resolver

```python
from git_integration import update_from_git

success = update_from_git(
    workspace="analytics",
    conflict_resolution_policy="PreferRemote",
    allow_override_items=True
)
```

---

## Exemplos cURL

### Conectar GitHub

```bash
curl -X POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/git/connect \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "gitProviderDetails": {
      "gitProviderType": "GitHub",
      "ownerName": "myorg",
      "repositoryName": "fabric-repo",
      "branchName": "main"
    },
    "myGitCredentials": {
      "source": "ConfiguredConnection",
      "connectionId": "conn-uuid"
    }
  }'
```

### Fazer commit

```bash
curl -X POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/git/commitToGit \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "All",
    "comment": "Producao automatizada"
  }'
```

### Verificar status

```bash
curl -X GET https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/git/status \
  -H "Authorization: Bearer TOKEN"
```
