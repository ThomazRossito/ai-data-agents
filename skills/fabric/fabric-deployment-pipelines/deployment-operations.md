# Deployment Operations - Referencia Tecnica

## REST API Endpoints

### Deployment Pipelines

**GET /deploymentPipelines**
- Listar todos os pipelines
- Suporta paginacao: `?$top=100&$skip=0`

**POST /deploymentPipelines**
- Criar pipeline novo
- Payload:
  ```json
  {
    "displayName": "MyPipeline",
    "description": "3-stage CI/CD",
    "stages": [
      {"displayName": "Dev", "description": "Development", "isPublic": false},
      {"displayName": "Test", "description": "Testing", "isPublic": false},
      {"displayName": "Prod", "description": "Production", "isPublic": true}
    ]
  }
  ```

**GET /deploymentPipelines/{pipelineId}**
- Obter detalhes do pipeline

**PATCH /deploymentPipelines/{pipelineId}**
- Atualizar nome/descricao do pipeline
- Payload: `{ "displayName": "NewName" }`

**DELETE /deploymentPipelines/{pipelineId}**
- Deletar pipeline

### Stage Management

**GET /deploymentPipelines/{pipelineId}/stages/{stageId}**
- Obter detalhes de um estagios

**PATCH /deploymentPipelines/{pipelineId}/stages/{stageId}**
- Atualizar propriedades do estagios
- Payload: `{ "displayName": "NewName", "isPublic": true }`

**POST /deploymentPipelines/{pipelineId}/stages/{stageId}/assignWorkspace**
- Vincular workspace ao estagios
- Payload: `{ "workspaceId": "workspace-uuid" }`

**POST /deploymentPipelines/{pipelineId}/stages/{stageId}/unassignWorkspace**
- Desvincullar workspace do estagios

### Deployments

**POST /deploymentPipelines/{pipelineId}/deploy**
- Iniciar deploy (LRO)
- Payload:
  ```json
  {
    "sourceStageId": "stage-uuid-1",
    "targetStageId": "stage-uuid-2",
    "note": "Producao semanal",
    "items": [
      {"sourceItemId": "item-uuid", "itemType": "SemanticModel"}
    ],
    "options": {
      "allowCrossRegionDeployment": true
    }
  }
  ```
- Retorno: 202 Accepted (LRO iniciada)

**GET /deploymentPipelines/{pipelineId}/operations**
- Listar historico de deploys

**GET /deploymentPipelines/{pipelineId}/operations/{operationId}**
- Obter detalhes de uma operacao especifica

### Role Assignments

**POST /deploymentPipelines/{pipelineId}/roleAssignments**
- Atribuir papel novo
- Payload:
  ```json
  {
    "principal": {"id": "user-uuid", "type": "User"},
    "role": "Admin"
  }
  ```

**DELETE /deploymentPipelines/{pipelineId}/roleAssignments/{roleAssignmentId}**
- Remover atribuicao

---

## Deploy Modes

### Full Deploy (All Items)

Deploy todos os items do estagios origem para o destino. Sem items no payload.

```json
{
  "sourceStageId": "...",
  "targetStageId": "...",
  "note": "Deploy total de Dev para Test"
}
```

### Selective Deploy (Specific Items)

Deploy apenas items especificos. Inclua array items.

```json
{
  "sourceStageId": "...",
  "targetStageId": "...",
  "items": [
    {"sourceItemId": "uuid-1", "itemType": "SemanticModel"},
    {"sourceItemId": "uuid-2", "itemType": "Report"}
  ],
  "note": "Deploy seletivo de modelos"
}
```

Tipos de items suportados: SemanticModel, Report, Dashboard, Notebook, MLModel, etc.

---

## Conflict Resolution

### PreferWorkspace
Mantém items locais no workspace destino se conflito ocorrer.

### PreferRemote
Sobrescreve items locais com versao do estagios origem.

```json
{
  "sourceStageId": "...",
  "targetStageId": "...",
  "options": {
    "conflictResolution": {
      "conflictResolutionPolicy": "PreferRemote"
    }
  }
}
```

---

## LRO Polling

Deploy retorna 202 Accepted com location header.

```
POST /deploymentPipelines/{pipelineId}/deploy
< HTTP/1.1 202 Accepted
< location: https://api.fabric.microsoft.com/v1/deploymentPipelines/{pipelineId}/operations/{operationId}

{
  "id": "operation-uuid",
  "status": "NotStarted"
}
```

Poll GET /deploymentPipelines/{pipelineId}/operations/{operationId} ate:
- status == "Succeeded" -- Deploy completo
- status == "Failed" -- Deploy falhou
- status == "Running" -- Aguarde e retry

---

## Exemplos cURL

### Criar pipeline

```bash
curl -X POST https://api.fabric.microsoft.com/v1/deploymentPipelines \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "displayName": "DataLake-Pipeline",
    "stages": [
      {"displayName": "Dev", "description": "Development", "isPublic": false},
      {"displayName": "Test", "description": "Testing", "isPublic": false}
    ]
  }'
```

### Iniciar deploy

```bash
curl -X POST https://api.fabric.microsoft.com/v1/deploymentPipelines/{pipelineId}/deploy \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "sourceStageId": "dev-stage-uuid",
    "targetStageId": "test-stage-uuid",
    "note": "Producao automatizada"
  }'
```

### Monitorar deploy (polling)

```bash
curl -X GET https://api.fabric.microsoft.com/v1/deploymentPipelines/{pipelineId}/operations/{operationId} \
  -H "Authorization: Bearer TOKEN"
```
