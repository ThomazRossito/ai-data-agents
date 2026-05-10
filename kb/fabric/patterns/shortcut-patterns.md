# Shortcuts e Mirroring — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** HTTP API shortcuts, mirroring, deployment pipelines, Git integration

---

## Shortcut: OneLake (Cross-Workspace)

```http
POST /workspaces/{workspace-id}/items/{lakehouse-id}/shortcuts
{
  "path": "Tables",
  "name": "shared_dim_customer",
  "target": {
    "oneLake": {
      "itemId": "source-lakehouse-id",
      "path": "/Gold/CRM/dim_customer",
      "workspace_id": "source-workspace-id"
    }
  },
  "shortcutConflictPolicy": "Abort"
}
```

## Shortcut: ADLS Gen2

```http
{
  "path": "Files/External",
  "name": "raw_data_adls",
  "target": {
    "adlsGen2": {
      "connectionId": "{connection-id}",
      "location": "mycontainer",
      "subpath": "/data/raw"
    }
  }
}
```

## Shortcut: Amazon S3

```http
{
  "path": "Files/S3Data",
  "name": "s3_bucket_link",
  "target": {
    "amazonS3": {
      "connectionId": "{s3-connection-id}",
      "location": "my-bucket",
      "subpath": "/datasets/sales"
    }
  }
}
```

## Shortcut: Google Cloud Storage

```http
{
  "path": "Files/GCS",
  "name": "gcs_bucket",
  "target": {
    "googleCloudStorage": {
      "connectionId": "{gcs-connection-id}",
      "location": "my-bucket",
      "subpath": "/data"
    }
  }
}
```

## Conflict Policy como Query Param

```http
POST /workspaces/{workspace-id}/items/{lakehouse-id}/shortcuts?shortcutConflictPolicy=GenerateUniqueName
```

---

## Mirroring: Databricks → Fabric

```http
POST /workspaces/{workspace-id}/items/{lakehouse-id}/mirroring
{
  "name": "databricks_orders_mirror",
  "path": "Tables",
  "sourceType": "databricks",
  "sourceProperties": {
    "workspaceUrl": "https://<workspace-instance>.cloud.databricks.com",
    "tablePath": "catalog.schema.orders",
    "authType": "PersonalAccessToken"
  },
  "syncPolicy": {
    "syncType": "ContinuousSync",
    "interval": 3600
  }
}
```

## Monitorar Mirror

```http
GET /workspaces/{workspace-id}/items/{lakehouse-id}/mirroring/{mirror-id}/status

Response:
{
  "lastSyncTime": "2026-04-09T15:30:00Z",
  "nextSyncTime": "2026-04-09T16:30:00Z",
  "status": "Healthy"
}
```

---

## Deployment Pipelines: Promover Artefatos

```http
# Listar pipelines
GET /deploymentPipelines

# Criar pipeline
POST /deploymentPipelines
{
  "displayName": "Sales Analytics Pipeline",
  "stages": ["Development", "Test", "Production"]
}

# Promover Dev → Test
POST /deploymentPipelines/{pipeline-id}/deploy
{
  "sourceStageOrder": 0,
  "targetStageOrder": 1,
  "items": [
    {"itemId": "{lakehouse-id}", "itemType": "Lakehouse"},
    {"itemId": "{notebook-id}", "itemType": "Notebook"}
  ]
}
```

---

## Git Integration

```http
# Conectar workspace ao GitHub
POST /workspaces/{workspace-id}/git/connect
{
  "gitProviderType": "GitHub",
  "organizationName": "my-org",
  "projectName": "data-platform",
  "repositoryName": "fabric-workspace",
  "branchName": "main",
  "directoryName": "/fabric"
}

# Status de sincronização
GET /workspaces/{workspace-id}/git/status

# Commit mudanças ao Git
POST /workspaces/{workspace-id}/git/commitToGit
{
  "mode": "All",
  "comment": "Update Gold tables with V-Order"
}

# Atualizar workspace do Git
POST /workspaces/{workspace-id}/git/updateFromGit
{
  "remoteCommitHash": "abc123def456",
  "workspaceHead": "HEAD",
  "conflictResolution": {
    "conflictResolutionType": "Workspace"
  }
}
```
