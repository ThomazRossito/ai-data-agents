# Mapa de Inferência: Recurso/Artefato → Subitem de Controle

> Em audits reais, screenshots do Azure Portal e prints de ferramentas **são** a evidência. Use este
> mapa para conectar o que aparece nas imagens (após OCR) aos subitens dos controles do Módulo B.
> Regra: a EXISTÊNCIA de um recurso provado por screenshot **conta como evidência** do subitem
> correspondente (marque proveniência `(OCR)`), mesmo que não haja um documento textual formal.

## Recursos Azure / ferramentas → controle.subitem

| Evidência visual / artefato | Sinais no OCR | Controle.subitem que satisfaz (no mínimo parcial) |
|---|---|---|
| **Azure Key Vault** | "Key Vault", "managed identity", "kv" | 2.1 Encryption (cofre de chaves/segredos), 2.1 Security |
| **Service Principals / Grupos de Acesso** | "Service principal", "GRP-AZU-", "Members", "Owners" | 2.1 User Roles, 2.1 Security (RBAC/IAM), 1.1 User Personas |
| **Azure Data Lake Storage Gen2** | "Data Lake Storage Gen2", "stgdl", "Containers", "StorageV2" | 2.1 Data Storage (storage type) |
| **Storage accounts** | "Storage account", "StorageV2", "Blob" | 2.1 Data Storage |
| **Azure Data Factory** | "Data factory (V2)", "ADF", "pipeline", "linked service" | 2.1 Ingestion/Transformation Engine, 2.1 Data Source |
| **Azure Databricks** | "Azure Databricks Service", "workflow", "job cluster", "DBU" | 2.1 Analytics Service, 2.1 Ingestion (Spark), 3.1 Deployment |
| **Power BI** | "Power BI service", "Power BI Gateway", "Dataflow" | 2.1 Data Reporting/Visualization |
| **Kafka / CDC** | "Kafka", "CDC", "Change Data Capture" | 2.1 Ingestion Engine, 2.1 Data Migration approach |
| **Azure DevOps (repos/branches/pipelines)** | "Repos", "Branches", "develop/release/master", "Pipelines", "Esteira" | 2.1 DevOps (source depot, deploy process), 3.1 Deployment (deployment sequence) |
| **SonarQube / Fortify (SAST)** | "SonarQube", "Quality Gate", "Coverage %", "Fortify", "SAST" | 4.1 Service Validation/Testing (qualidade de código), 2.1 DevOps |
| **Gráfico de custo / FinOps** | "Custo", "FinOps", "DBU", "redução de custos", "% Variação" | (contexto FinOps — apoia 1.1 Budget; NÃO é controle próprio do Módulo B) |
| **Arquitetura Medallion (Transient/Bronze/Silver/Gold)** | "Bronze", "Silver", "Gold", "Lakehouse", "Medallion" | 2.1 Solution Design (arquitetura), 3.1 Deployment |
| **Wiki/onboarding/Guia de fluxo/RITM** | "Wiki", "onboarding", "Guia Prático", "RITM", "SOP", "runbook" | 4.2 Post-deployment Documentation (procedimentos/how-to), 3.1 as-built |
| **Data Quality Framework / validações** | "Data Quality", "Completeness", "Uniqueness", "Range", "Format", "Timeliness" | 4.1 Service Validation/Testing |
| **Naming/Tagging/ambientes (TU/TH/PR/EDA)** | "azu-bs...-tu/th/pr", "tags", "naming" | 2.1 ALZ Resource organization (parcial), 3.1 Deployment (ambientes) |

## Limites (não force além do que o print prova)

- Um screenshot que prova **existência** de Key Vault cobre "há cofre de chaves" — **não** prova
  automaticamente metodologia de encryption (TDE, CMK). Se o controle pede a metodologia e só há o
  print do recurso → **🟡 Parcial**, não ✅ Completa.
- Service Principals + grupos provam IAM/RBAC em nível de plataforma — **não** provam row/column-level
  security. Diferencie no relatório.
- Recurso sem cliente nominal vinculável → ainda conta para cobertura do cliente em escopo se o lote
  inteiro é daquele cliente; mas registre `data: n/d` quando o print não tem data.
- OCR de diagrama captura rótulos; cite o que está legível e marque `⚠️ Needs Review` se ilegível.
