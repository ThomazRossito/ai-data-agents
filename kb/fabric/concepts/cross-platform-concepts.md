# Shortcuts, Mirroring e Cross-Platform — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** OneLake shortcuts, mirroring, deployment pipelines, Git integration

---

## O que é Shortcut?

Shortcut é um **link lógico** para dados externos (sem cópia):

| Propriedade | Shortcut | Copy |
|------------|----------|------|
| **Storage** | Referência ao original | Cópia local |
| **Latência** | 1-5ms (rede) | Instantâneo (local) |
| **Custo** | Apenas query | Query + storage |
| **Update** | Real-time (source) | Manual resync |
| **Governance** | Controle fonte | Duplicado |

---

## Tipos de Shortcut Suportados

| Tipo | Caso de Uso |
|------|-------------|
| **OneLake (Cross-Workspace)** | Compartilhar tabelas entre workspaces Fabric |
| **ADLS Gen2** | Dados em Azure Data Lake Storage |
| **Amazon S3** | Dados em buckets AWS |
| **Azure Blob Storage** | Arquivos em Blob |
| **Dataverse** | Dados do Microsoft Dynamics |
| **Google Cloud Storage** | Dados em GCS |
| **S3-Compatible** | Minio, outros |

---

## Conflict Policies

| Policy | Ação | Uso |
|--------|------|-----|
| **Abort** | Falha (padrão) | Evitar overwrites acidentais |
| **GenerateUniqueName** | `dim_customer_1`, `dim_customer_2` | Coexistência de versões |
| **CreateOrOverwrite** | Sobrescreve | Atualizar dados |
| **OverwriteOnly** | Erro se não existe | Append-only (seguro) |

---

## Mirroring: Sincronização Contínua

Mirroring é shortcut com **sincronização automática** (unidirecional):

```
Source (Databricks Unity Catalog, SQL Server, etc.)
  → Fabric Lakehouse Table (synced automatically)
```

**Diferença de Shortcut:** Shortcut lê da fonte em real-time. Mirroring copia periodicamente.

---

## Deployment Pipelines

Deployment Pipelines permitem promover artefatos entre ambientes (Dev → Test → Prod) dentro do Fabric.

---

## Git Integration

Fabric suporta Git nativo (GitHub e Azure DevOps) para versionamento de artefatos.

| Conflito | Resolução |
|----------|-----------|
| Fabric é mais novo | Substituir Git com versão Fabric |
| Git é mais novo | Substituir Fabric com versão Git |
| Conflito manual | Resolver localmente e re-push |
