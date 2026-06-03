# Módulo B — Controles Detalhados (V2.8.1)

> Texto normativo derivado do checklist oficial. Cada controle lista: **Requisito**,
> **Evidência exigida**, **Documentação aceita**, **Clientes** e **Janela**. O agente
> audita os documentos do usuário contra ESTES itens, subitem a subitem.

---

## 1.0 Assess

### 1.1 Analytics Portfolio Assessment

**Requisito:** demonstrar como o parceiro avalia o estado atual e os requisitos do cliente
para garantir planejamento e sizing adequados de pré-migração/pré-deployment. A avaliação
deve cobrir áreas específicas de soluções analytics:

- **Business need:** dores atuais e necessidades dos usuários; product fit e gaps; necessidades de armazenamento de dados (volume, tipo, localização, estado atual vs futuro); data governance e compliance; budget.
- **Application Landscape:** infraestrutura atual ou greenfield; arquitetura lógica e requisitos de migração (se aplicável); informações de todas as aplicações, serviços e plataformas BI SaaS (ex: PowerBI.com, Tableau online).
- **Performance Benchmarks:** requisitos de performance da aplicação e de transferência de dados.
- **User Personas:** papéis dos usuários, como cada um usa/acessa os dados; engajamento de stakeholders (business, BI, analytics, data science).
- **Skilling Plan:** plano de skilling para analytics em escala (template de guidance).
- **Data needs:** tipo/volume/frequência/velocidade; centralização; classificação e risco; fontes (on-prem, AWS, Google) e destino (Azure); quem/o que consome os dados.
- **Networking:** componentes existentes que conectam ao Azure (inclui modelos serverless e Classic do Azure Databricks).
- **Security and Compliance needs:** IAM, RBAC, encryption, compliance por indústria/geografia.
- **Availability, resiliency, DR needs:** expectativas pós-Azure, demanda/escalabilidade, uptime e SLAs.

**Evidência exigida:** documentos de design demonstrando os itens acima revisados, de pelo menos
**3 clientes únicos** com deployments analytics concluídos nos **últimos 24 meses** (todos os
detalhes do assessment considerados por cliente). Pode ser manual ou via ferramenta de assessment.

**Documentação aceita:** Assessment Report cobrindo os componentes acima, por cliente. Pode incluir
Assessment Checklist, Templates, Questionnaires, Project Plans, Skilling Plans, Data Migration
Assistant (DMA) Reports, ou outros relatórios de tooling de terceiros.

---

## 2.0 Design and Proof of Concept (PoC) or Pilot

### 2.1 Solution Design

**Requisito:** apresentar designs de solução com abordagem consistente que atenda aos requisitos do
assessment. O design deve cobrir áreas específicas de analytics:

- **User Roles:** papéis para deploy da solução (ETL users, analysts, developer, report designer, data scientists) com RBAC.
- **Data Source:** todas as fontes e tipos de arquivo a ingerir.
- **Data Migration approach:** abordagem de migração dos dados (se aplicável).
- **Ingestion and Transformation Engine:** ex. Azure Data Factory, Fabric Data Factory, Fabric Spark, Fabric Data Warehouse, Fabric Event streams, Informatica, Data Stage, Azure Databricks.
- **Data Storage and Format:** ex. Azure Blob, Azure Data Lake, Fabric Data Warehouse, Synapse Dedicated SQL Pools, Fabric Eventhouse, Fabric Lakehouse. Formatos: CSV, JSON, Parquet, Delta.
- **Encryption Method:** TDE, masking, customer managed keys, encryption cluster↔worker, query encryption, Azure Key Vault.
- **Security:** row/column/object/resource-item level security, VNets, private endpoints.
- **Analytics Service:** Azure Synapse Analytics OU Azure Databricks OU Microsoft Fabric OU Dedicated SQL Pool.
- **Data Reporting and Visualization:** Power BI, Tableau, MicroStrategy, etc.
- **DevOps:** source depot (Visual Studio, Git), linguagem de código, redesign/backward compatibility, processo de deploy.
- **Azure Landing Zone (constraints analytics-specific):** regional planning; network/infra providers; networking + NSGs + identity/access; evidência de IAM e RBAC, data sovereignty & encryption, app security, auditing; arquitetura Hub-Spoke; produtos de segurança (Azure Security Services, M365 Security); governance tooling para custo (budgets/alertas); backup/recovery; compliance regulatório (GDPR, HIPAA); solução de monitoramento; visualização/alerting; baseline de operações; risco de migração.

> **Nota 1:** se a landing zone foi implementada pelo cliente/outro parceiro, o parceiro Analytics
> deve revisar contra os pontos acima e fornecer recomendações documentadas das mudanças.
> **Nota 2:** para Fabric em ALZ — se não há Identity/Networking deployados, demonstrar as 10
> constraints restantes para 3 clientes únicos.

**Evidência exigida:** documentos de solution design cobrindo os pontos acima, de pelo menos
**3 clientes únicos** com projetos Azure Analytics concluídos nos **últimos 24 meses**.

**Documentação aceita:** Project plans, Functional specifications, Architectural diagrams,
Automated tooling reports, Physical and logical diagrams.

### 2.2 Azure Well-Architected Review of Workloads

**Requisito:** demonstrar uso do Azure Well-Architected Review, executado com o **Core
Well-Architected Review Assessment**.

**Evidência exigida:** resultados exportados de **2 dos 5 pilares** do WAR, usando os assessments
desses pilares. Reviews nos **últimos 12 meses**, para **3 clientes** indicando o nome do cliente
em cada exemplo. (Reviews podem ser antes, durante ou após o deployment.)

### 2.3 Proof of Concept or Pilot

**Requisito:** evidência de **3 PoCs/pilots de analytics concluídos** que validam as decisões de
design antes do rollout em produção. Cada PoC/pilot deve documentar: propósito, dores do cliente,
critérios de sucesso, benefícios pretendidos e resultados — para um dos produtos: Azure Synapse
Analytics OU Azure Databricks OU Microsoft Fabric OU Dedicated SQL Pool.

**Evidência exigida:** documentação para **3 clientes** com PoC/pilot concluído nos **últimos 24 meses**.

**Documentação aceita:** PoC/Pilot Architecture Diagrams; Reference Architectural Design Blueprints;
Test Plans and Results; Implementation Documentation; outros PoC Documents; Monitoring Tool Report.

---

## 3.0 Deployment

### 3.1 Deployment

**Requisito:** evidência da capacidade de implementar soluções Analytics em **produção**, com base
em designs aprovados pelo cliente. Pelo menos **3 clientes** devem ter Azure Synapse Analytics OU
Azure Databricks OU Microsoft Fabric OU Dedicated SQL Pool.

**Evidência exigida:** documentação para **3 clientes únicos** com projetos concluídos nos
**últimos 24 meses**. Cada cliente deve incluir **2 ou mais** dos itens abaixo, cobrindo toda a
sequência (do design ao deploy em produção):

- Signed SOW (statement of work assinado) — para todos os projetos
- Solution design documents — para todos os projetos
- Project plan e migration/deployment sequence
- Architecture diagrams
- High Level Design (HLD) e Low-Level Design (LLD)
- As-built documentation

---

## 4.0 Review and Release for Operations

### 4.1 Service Validation and Testing

**Requisito:** validar o deployment, incluindo: processo/abordagem de teste e avaliação de
performance de todas as aplicações contra expectativas do usuário e best practices Azure; processo
de avaliação e melhoria de best practices arquiteturais para remediar issues de performance/custo.

**Evidência exigida:** documentação de teste e validação de performance cobrindo os pontos acima
para os **3 clientes únicos**. A documentação deve indicar que a solução atende às expectativas do
cliente, **com sign-off do cliente**. Projetos implementados nos **últimos 24 meses** (podem ser os
mesmos do 3.1).

### 4.2 Post-deployment Documentation

**Requisito:** documentação pós-deploy para garantir o sucesso do cliente no uso do novo serviço
Azure: como o parceiro documenta decisões, designs arquiteturais e procedimentos implementados;
e Standard Operating Procedures (SOPs) de business-as-usual descrevendo cenários "how-to".

**Evidência exigida:** documentação dos pontos acima para **3 clientes únicos** com projetos Azure
analytics concluídos nos **últimos 24 meses**.
