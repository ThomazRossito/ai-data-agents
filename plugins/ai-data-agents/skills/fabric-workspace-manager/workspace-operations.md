# Workspace Operations - Referencia Tecnica

## REST API Endpoints

### Workspaces

**GET /workspaces**
- Lista todos os workspaces
- Suporta paginacao: `?$top=100&$skip=0`
- Retorno: `{ "value": [...], "continuationToken": "..." }`

**GET /workspaces/{workspaceId}**
- Obter detalhes de um workspace especifico
- Retorno: `{ "id": "...", "displayName": "...", "description": "...", "capacityId": "...", "type": "..." }`

**POST /workspaces**
- Criar workspace novo
- Payload obrigatorio: `{ "displayName": "MyWorkspace" }`
- Payload opcional: `{ "capacityId": "...", "description": "..." }`

**PATCH /workspaces/{workspaceId}**
- Atualizar propriedades
- Payload: `{ "displayName": "NewName", "description": "NewDesc" }`

**DELETE /workspaces/{workspaceId}**
- Deletar workspace

### Role Assignments (RBAC)

**GET /workspaces/{workspaceId}/roleAssignments**
- Listar todas as atribuicoes de funcao
- Retorno: array de `{ "id": "...", "principal": {...}, "role": "Admin" }`

**GET /workspaces/{workspaceId}/roleAssignments/{userUuid}**
- Obter atribuicao especifica de um usuario

**POST /workspaces/{workspaceId}/roleAssignments**
- Atribuir papel novo
- Payload:
  ```json
  {
    "principal": {
      "id": "user-uuid",
      "type": "User"
    },
    "role": "Admin"
  }
  ```

**PATCH /workspaces/{workspaceId}/roleAssignments/{userUuid}**
- Atualizar papel existente
- Payload: `{ "role": "Contributor" }`

**DELETE /workspaces/{workspaceId}/roleAssignments/{userUuid}**
- Remover atribuicao

### Capacity Assignment

**POST /workspaces/{workspaceId}/assignToCapacity**
- Vincular workspace a capacidade
- Payload: `{ "capacityId": "capacity-uuid" }`
- Retorno: 202 Accepted (Long Running Operation)

**POST /workspaces/{workspaceId}/unassignFromCapacity**
- Desvincullar workspace de capacidade
- Retorno: 202 Accepted

---

## Exemplos Python

### Criar workspace com capacidade

```python
from pyfabricops import create_workspace

ws = create_workspace(
    display_name="DataLake-Prod",
    capacity="premium-cap-001",
    description="Production data lake workspace"
)
```

### Atribuir Admin a usuario

```python
from pyfabricops import add_workspace_role_assignment

add_workspace_role_assignment(
    workspace="DataLake-Prod",
    user_uuid="00000000-0000-0000-0000-000000000001",
    user_type="User",
    role="Admin"
)
```

### Atribuir Contributor a grupo

```python
from pyfabricops import add_workspace_role_assignment

add_workspace_role_assignment(
    workspace="DataLake-Prod",
    user_uuid="00000000-0000-0000-0000-000000000002",
    user_type="Group",
    role="Contributor"
)
```

### Vincular capacidade com polling

```python
from pyfabricops import assign_to_capacity
import time

assign_to_capacity(
    workspace="DataLake-Prod",
    capacity="capacity-premium"
)
# Aguarda 202; workspace sera vinculado em ~10-30 segundos
```

---

## Tipos de Usuario

| Tipo | Descricao |
|------|-----------|
| `User` | Usuario Azure AD individual |
| `Group` | Grupo Azure AD (seguranca ou Microsoft 365) |
| `ServicePrincipal` | Application/SPN para automacao |
| `ServicePrincipalProfile` | Perfil de SPN |

---

## Papeis (Roles)

| Papel | Permissoes | Caso de Uso |
|-------|-----------|-----------|
| `Admin` | CRUD em workspace e items | Proprietario/Gerente |
| `Contributor` | Criar/editar items | Data engineer |
| `Member` | Consumir items | Analista/BI developer |
| `Viewer` | Somente leitura | Stakeholder/Leitor |

---

## HTTP Status Codes

| Status | Significado |
|--------|------------|
| 200 | Sucesso (GET/PATCH/DELETE completo) |
| 201 | Criado (POST completado) |
| 202 | Aceito (LRO iniciada) |
| 400 | Request invalida (validacao) |
| 401 | Nao autenticado (token invalido/expirado) |
| 403 | Nao autorizado (permissao insuficiente) |
| 404 | Recurso nao encontrado |
| 409 | Conflito (nome duplicado, estado invalido) |
| 422 | Entidade nao processavel (validacao de negocio) |
| 429 | Throttle (rate limit) |
| 500+ | Erro de servidor |
