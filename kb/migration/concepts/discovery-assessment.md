# Discovery e Assessment — SQL Server → Databricks

> KB normativa para a fase **ASSESS** (e parte de **ANALYZE**) do fluxo de 5 fases definido em
> `kb/migration/index.md` (`ASSESS → ANALYZE → DESIGN → TRANSPILE → RECONCILE`), aplicada a migrações
> **SQL Server → Databricks**. Consolida as 5 categorias de discovery, a Complexity Scoring Matrix,
> heurísticas de complexidade T-SQL, t-shirt sizing, a decisão Analytics-First vs ETL-First, vetores de
> deployment, os 8 anti-padrões de migração e o papel do Lakebridge/Lakehouse Federation no discovery.
> Precede `kb/migration/concepts/cutover-rollback.md` (fase de ativação/cutover) no ciclo de vida da migração.

**Domínio:** migration — Discovery & Assessment
**Fonte:** Curso "SQL Server Migration" — `01 - Discover/1.2 Lecture - Discovery and Landscape Analysis.md`
e `01 - Discover/1.3 Lecture - Planning and Road-mapping.md` (+ apoio de `00 - Foundations/0.2`,
`00 - Foundations/0.4`, `01 - Discover/1.4`, `05 - Enable/5.2` — ver Referências)
**Agentes:** migration-expert

---

## 1. As 5 Categorias de Discovery

Discovery completo cobre 5 categorias. Faltar qualquer uma leva a surpresas durante a migração.

| Categoria | O que Descobrir | Por que Importa |
|---|---|---|
| **Data Assets** | Databases, tabelas, views, schemas, tamanhos, tipos de dados | Dimensionar o esforço de migração de dados |
| **Pipelines & ETL** | Stored procedures, pacotes SSIS, jobs SQL Agent, UDFs, triggers | Planejar conversão de código e esforço de teste |
| **Consumers & Users** | Ferramentas BI (SSRS, Power BI), aplicações via JDBC/ODBC, logins ativos | Coordenar cutover de consumidores downstream |
| **Security & Access** | Logins SQL, roles de database, Windows Auth/grupos AD, políticas RLS | Replicar controles de acesso no Unity Catalog |
| **Operations & SLAs** | Schedules de SQL Agent jobs, SLAs, monitoramento (alerts, SCOM) | Manter níveis de serviço pós-migração |

Cite: `01 - Discover/1.2 Lecture - Discovery and Landscape Analysis.md`, seção "Discovery Categories".

---

## 2. Complexity Scoring Matrix — 7 Dimensões

Pontuar cada workload (database/domínio) nas 7 dimensões abaixo, 1-4 pontos cada. A soma determina a
wave de migração recomendada.

| Dimensão | Small (1 pt) | Medium (2 pts) | Large (3 pts) | X-Large (4 pts) |
|---|---|---|---|---|
| **Table Count** | < 10 | 10-50 | 50-200 | > 200 |
| **Data Volume** | < 10 GB | 10-100 GB | 100 GB - 1 TB | > 1 TB |
| **T-SQL Complexity** | DML simples, joins | Stored procs, UDFs, CTEs | Cursors, WHILE loops, dynamic SQL | CLR objects, linked servers, OPENROWSET |
| **SSIS Complexity** | Sem SSIS, ou data flows simples | Transforms moderados, Lookup/Merge Join | Script Tasks (C#), data flows complexos | Script Tasks + CLR + chamadas de serviço externo |
| **Dependencies** | Nenhuma | 1-3 upstream | 4-10 upstream | > 10 ou circular |
| **SLA Sensitivity** | Nenhuma / batch diário | SLA diário | SLA horário | Real-time / sub-minuto |
| **Consumers** | 1 time interno | 2-5 times | Enterprise-wide | Externo / customer-facing |

Cite: `01 - Discover/1.3 Lecture - Planning and Road-mapping.md`, seção "Complexity Scoring Matrix".

### 2.1 Mapeamento Score → Wave

| Pontuação Total | Tamanho | Wave Recomendada |
|---|---|---|
| 6-10 | Small | **Wave 1** (candidato) |
| 11-16 | Medium | **Wave 2** (candidato) |
| 17-20 | Large | **Wave 3** (candidato) |
| 21+ | X-Large | **Wave 3** com suporte de especialista e timeline estendida |

Cite: `01 - Discover/1.3 Lecture - Planning and Road-mapping.md`, seção "Workload Complexity Score to Wave Mapping".

> **Nota:** não confundir com a "Classificação de Complexidade de Objetos" (Simples/Médio/Complexo/
> Bloqueado) em `kb/migration/index.md` — aquela pontua **objetos individuais** (esforço de
> transpilação de uma procedure/view específica); esta pontua o **workload/database completo** para
> alocação de wave no roadmap. São complementares: um workload "Wave 3" pode ter objetos individuais
> "Simples" e "Bloqueado" misturados.

---

## 3. Heurística de Complexidade T-SQL

### 3.1 Nível de Script/Procedure (heurística automatizável)

Aplicada via `LIKE` sobre `sys.sql_modules.definition` — ver implementação em
`scripts/mssql_discovery.sql` §3.2:

| Condição | Complexidade |
|---|---|
| Contém `CURSOR` | **High** |
| Contém `EXEC(` ou `EXECUTE(` (dynamic SQL) | **High** |
| Contém `OPENROWSET` ou `OPENQUERY` | **High** |
| Contém `WHILE` | **Medium** |
| `LEN(definition) > 5000` caracteres | **Medium** |
| Nenhuma das condições acima | **Low** |

Cite: `01 - Discover/1.2 Lecture - Discovery and Landscape Analysis.md`, seção "Stored Procedure Complexity Assessment".

### 3.2 Nível de Categoria (esforço de conversão)

| Categoria | Características | Esforço de Conversão Databricks |
|---|---|---|
| **Simple** | DML (SELECT/INSERT/UPDATE/DELETE), JOINs padrão, agregações | Baixo — maioria converte com mudanças mínimas |
| **Medium** | Stored procedures, scalar UDFs, CTEs, MERGE, window functions, WHILE loops | Médio — requer teste; WHILE loops podem precisar refatoração |
| **Complex** | CURSOR row-by-row, dynamic SQL (EXEC/sp_executesql), assemblies CLR | Alto — CURSOR precisa reescrita set-based; CLR precisa reescrita em Python UDF |

Cite: `01 - Discover/1.3 Lecture - Planning and Road-mapping.md`, seção "T-SQL Complexity Categories".

---

## 4. T-Shirt Sizing por Volume de Linhas

Classificação alimentada por `sys.dm_db_partition_stats` (row count sem table scan completo —
ver `scripts/mssql_discovery.sql` §2).

| Tamanho | Row Count |
|---|---|
| **S (Small)** | < 1.000 |
| **M (Medium)** | 1.000 - 50.000 |
| **L (Large)** | 50.000 - 1.000.000 |
| **XL (Extra Large)** | > 1.000.000 |

Tabelas pequenas migram primeiro (early wins / Wave 1); tabelas grandes ou complexas migram em waves
posteriores, com mais teste.

Cite: `01 - Discover/1.2 Lecture - Discovery and Landscape Analysis.md`, seção "Workload Classification and T-Shirt Sizing".

---

## 5. Analytics-First vs ETL-First — Árvore de Decisão

### 5.1 Árvore de Decisão

1. **Driver principal é redução de custo (licenciamento) ou compliance/timeline regulatório?**
   → **SIM: ETL-First**. → NÃO: ir para a pergunta 2.
2. **Driver principal é quick win ou capacidades de IA/BI?**
   → **SIM: Analytics-First**. → NÃO (nenhum dos drivers acima se aplica): default **ETL-First**.

### 5.2 Comparação de Estratégias

| Estratégia | Abordagem | Melhor Para |
|---|---|---|
| **ETL-First** | Construir camadas Bronze → Silver → Gold no Databricks, depois mover consumidores BI | Migrações cost-driven (redução de licença SQL Server), timelines de compliance, design greenfield de Lakehouse |
| **Analytics-First** | Usar Lakehouse Federation para ler dados do SQL Server a partir do Databricks imediatamente; migrar ETL em paralelo | Migrações time-sensitive, prioridade em AI/ML, organizações que querem demonstrar valor rápido antes do compromisso total |

### 5.3 Fases por Estratégia

| Fase | ETL-First | Analytics-First |
|---|---|---|
| **1** | Ingestão via CDC para Bronze/Silver; databases de reporting do SQL Server seguem live | Federation (foreign catalog) → acesso AI/BI imediato; SQL Server segue autoritativo |
| **2** | Camada Gold migra para o Databricks; pipelines SSIS substituídos por Lakeflow Jobs | CDC + Lakeflow Connect ingerindo Bronze→Silver→Gold em paralelo |
| **3** | Consumidores (Power BI, SSRS, apps) reconectam ao Databricks SQL Warehouse; SQL Server decomissionado | Cutover de consumidores para dados Databricks-nativos; decomissionar reporting DBs e SSIS |

> CDC nativo do SQL Server + Lakeflow Connect habilita migração **zero-downtime**: lê do transaction
> log e entrega mudanças row-level (`INSERT`/`UPDATE`/`DELETE`) para tabelas Delta, mantendo o SQL
> Server como sistema de registro operacional enquanto o Databricks é populado em paralelo.

Cite: `01 - Discover/1.3 Lecture - Planning and Road-mapping.md`, seções "Selecting a Migration Strategy" e "Zero-Downtime Migration with SQL Server CDC".

---

## 6. Vetor de Deployment — Conectividade e CDC

### 6.1 Conectividade e CDC por Vetor

| Deployment | Requisito de Rede | Autenticação | Suporte a CDC |
|---|---|---|---|
| **On-premises** | ExpressRoute, Direct Connect ou VPN; firewall liberando a porta JDBC 1433 a partir dos egress IPs do cluster Databricks | SQL auth ou Windows/Kerberos | Sim (SQL Server 2008+) |
| **Azure SQL Database** | Private endpoint preferencial; endpoint público com regras de firewall por IP | SQL auth ou Entra ID | Sim, a partir de compatibilidade SQL Server 2022 — **com restrições** |
| **Azure SQL Managed Instance** | Private endpoint dentro da VNet; VNet injection ou peering do workspace Databricks | SQL auth ou Entra ID | Sim |
| **AWS RDS SQL Server** | Security group liberando porta 1433 para o Databricks; VPC peering se em VPC separada | SQL auth | Sim |

> Confirmar disponibilidade de CDC e eventuais restrições do agente de replicação para o vetor
> específico antes de definir a estratégia de ingestão. **Lakehouse Federation** (§8.2) cobre apenas
> SQL Server on-premises, Azure SQL Database e Azure SQL Managed Instance — não há suporte de
> Federation documentado para AWS RDS SQL Server no material do curso.

Cite: `01 - Discover/1.3 Lecture - Planning and Road-mapping.md`, seção "Connectivity Requirements by Deployment Vector"; `01 - Discover/1.2 Lecture - Discovery and Landscape Analysis.md`, callout "CDC Support by Deployment Vector".

### 6.2 Padrão de Ingestão por Cenário

| Padrão | Quando Usar | Ferramenta Databricks |
|---|---|---|
| **CDC (Change Data Capture)** | Tabelas OLTP ativas, requisitos real-time ou near-real-time; CDC habilitado na fonte | Lakeflow Connect com `AUTO CDC` |
| **Batch (Full Load)** | Tabelas de referência/lookup, pequenas, atualização infrequente | Lakeflow Connect, JDBC batch load |
| **Batch (Incremental)** | Tabelas grandes com coluna de timestamp ou identity para watermarking | Lakeflow Connect, Auto Loader |
| **SSIS Pipeline Replacement** | Pacotes SSIS fazendo ETL de outras fontes para dentro do SQL Server | Lakeflow Job (via conversão Lakebridge) |
| **Federation** | Estratégia Analytics-First; acesso de leitura temporário durante a migração | Lakehouse Federation |

Cite: `01 - Discover/1.3 Lecture - Planning and Road-mapping.md`, seção "Defining Ingestion Strategy".

---

## 7. Os 8 Anti-Padrões de Migração

| Anti-Padrão | Risco | O que Acontece | Como Evitar |
|---|---|---|---|
| **Skipping Assessment** | Crítico | Dependências perdidas (linked servers, fontes SSIS não documentadas, scripts custom de SQL Agent) causam complexidade surpresa e cronogramas estourados | Fazer profile de todos os workloads com Lakebridge Profiler e Analyzer (`--source-dialect mssql`) antes de escrever qualquer código de migração |
| **Big-Bang Migration** | Crítico | Cutover único para todos os databases — sem caminho de rollback, outages extensos | Migrar por workload ou domínio; manter operação paralela com procedimentos de rollback testados |
| **Premature Decommission** | Crítico | Aposentar o SQL Server antes de todos os consumidores migrarem ou obrigações de retenção serem cumpridas | Manter o SQL Server live até todos os consumidores migrarem; exigir sign-off explícito dos stakeholders |
| **Lift-and-Shift Mentality** | Alto | Tradução 1:1 de SSIS/stored procedures herda dívida técnica legada e perde os benefícios do Lakehouse | Adotar arquitetura medallion, Unity Catalog e Lakeflow Pipelines; usar o Lakebridge como ponto de partida e depois otimizar |
| **No Parallel Validation** | Alto | Fazer cutover sem rodar em paralelo expõe problemas de qualidade de dados em produção | Rodar pipelines em paralelo com Lakebridge Reconcile por 1-2 semanas; exigir sign-off antes de depreciar o SQL Server |
| **Ignoring T-SQL Dialect Gaps** | Alto | `NOLOCK`, `FOR XML PATH`, `STUFF`, temp tables e `GOTO` exigem tratamento específico facilmente esquecido | Usar o Lakebridge Analyzer para identificar problemas de compatibilidade antes da migração começar |
| **Ignoring Change Management** | Médio | Foco puramente técnico, sem retreinamento de DBAs, leva a falha de adoção | Treinar os DBAs do SQL Server em Databricks; envolvê-los cedo — sua expertise é valiosa para validação |
| **Underestimating Governance** | Médio | Migrar sem replicar o modelo de segurança do SQL Server (logins, roles, RLS, DDM) no Unity Catalog | Mapear o modelo de segurança existente antes do cutover; validar paridade de sync do Entra ID e de row filter/column mask |

Cite: `00 - Foundations/0.2 Lecture - Migration Maturity Model.md`, seção "Migration Anti-Patterns".

---

## 8. Papel do Lakebridge Analyzer e da Lakehouse Federation no Discovery Client-Side

### 8.1 Lakebridge

Lakebridge (Databricks Labs) cobre 3 fases: **Assessment** (Profiler + Analyzer) → **Conversion**
(transpile) → **Reconciliation**. Instalado via `databricks labs install lakebridge` (Databricks CLI).

| Componente | Função | Fase |
|---|---|---|
| **Lakebridge Profiler** | Conecta ao SQL Server ao vivo, analisa padrões de workload, estima economia de TCO, identifica heavy users e queries caras. Produz relatório executivo | Assessment |
| **Lakebridge Analyzer** | Escaneia arquivos de DDL/código exportados e pacotes SSIS (offline — não requer conexão ao vivo); gera relatório `.xlsx` com complexity score LOW/MEDIUM/HIGH por objeto | Assessment |
| **Transpile (BladeBridge / next-gen transpiler)** | Conversão de código-fonte SQL/SSIS para Databricks | Conversion |
| **Lakebridge Reconcile (Reconciler)** | Validação automatizada de schema, row count e dados entre SQL Server e Databricks | Reconciliation |

> Fato de produto (verificado na web, ago/2026, sem arquivo de curso associado): o motor de transpile do
> Lakebridge também oferece Morpheus e Switch além do BladeBridge. A versão do curso expõe na CLI
> apenas `[1] Bladebridge` / `[2] Morpheus` como opções de transpiler.

**Pré-requisito do Analyzer:** exportar DDL via **SMO (PowerShell)** ou SSMS *Generate Scripts → Schema
only* — produz `CREATE TABLE`/procedure/view/function/trigger `.sql` que o Analyzer consome.

```bash
databricks labs lakebridge analyze \
  --source-directory lakebridge/inputs/ddl \
  --report-file lakebridge/output/assessment.xlsx
# Select the source technology → [15] MS SQL Server (DDL) | [30] SSIS | [31] SSRS
```

**Saída do Analyzer** (seções do relatório):

| Seção | Conteúdo |
|---|---|
| Summary | Total de scripts analisados, versão do analyzer, dialeto de origem |
| SQL Programs | Cada arquivo com complexity score, contagem de linhas e statements |
| SQL Script Categories | Breakdown por tipo: CREATE_PROCEDURE, CREATE_VIEW, TABLE_DDL, etc. |
| SQL Special Patterns | Construtos que exigem atenção: CURSOR, EXEC dinâmico, CLR, linked server calls |
| Functions | Funções T-SQL usadas com contagem de chamadas; flag em funções sem equivalente direto |
| Referenced Objects | Tabelas/views com operações CREATE/READ/WRITE/DROP por script |
| SQL Data Types | Tipos usados; destaca os que exigem mapeamento (`UNIQUEIDENTIFIER`, `HIERARCHYID`, `XML`, `MONEY`/`SMALLMONEY`, `GEOGRAPHY`, `GEOMETRY`, `SQL_VARIANT`) |

Cite: `01 - Discover/1.2 Lecture - Discovery and Landscape Analysis.md`, seções "Automated Discovery with Lakebridge" e "Analyzer Output"; `01 - Discover/1.4 Demo - Discovery & Planning Phase.md`, "Demo 1: Discovery and Analysis using Lakebridge".

### 8.2 Lakehouse Federation

Permite discovery **client-side a partir do próprio Databricks**, sem tocar a instância SQL Server
diretamente — útil quando o acesso direto à fonte é restrito, ou para validar o discovery a partir de
um segundo ângulo.

| Aspecto | Detalhe |
|---|---|
| **Direção** | Databricks → SQL Server (unidirecional; sem padrão de acesso externo tipo Iceberg REST para SQL Server) |
| **Objetos Unity Catalog** | **Connection** (host/porta/credenciais) + **Foreign Catalog** (espelha o database SQL Server como catálogo UC) |
| **Modo de acesso** | **Read-only**; query pushdown onde suportado |
| **Pushdown suportado** | Predicados (`WHERE`), projeções de coluna, `LIMIT`; parcial: funções string/math/date-time, `CAST`, `ALIAS`, `SORT ORDER` — roteado via **JDBC** |
| **Fontes suportadas** | SQL Server on-premises, Azure SQL Database, Azure SQL Managed Instance |
| **Autenticação** | Usuário/senha ou Microsoft Entra ID (OAuth / OAuth M2M) |

Uso em discovery: `SHOW SCHEMAS`/`SHOW TABLES`/`DESCRIBE TABLE` contra o foreign catalog; consultas ao
`information_schema.tables`/`columns` federado para inventário de tabelas/colunas e distribuição de
tipos; agregações de profiling (row counts, distribuição de nulls, min/max) direto contra as tabelas
federadas — tudo sem mover dados.

Cite: `00 - Foundations/0.4 Lecture - Interoperability Patterns.md`, seções "Lakehouse Federation" e "Query Pushdown"; `01 - Discover/1.2 Lecture - Discovery and Landscape Analysis.md`, seção "Databricks-Side Discovery via Federation"; `01 - Discover/1.4 Demo - Discovery & Planning Phase.md`, "Demo 3: Database Inventory and Profiling via Federation".

---

## 9. Estrutura de Waves (Wave 0-4)

| Wave | Foco | Duração Típica |
|---|---|---|
| **Wave 0 — Foundation** | Provisionamento do workspace Databricks, setup do Unity Catalog, conectividade de rede (VPN/ExpressRoute/VPC), teste de conectividade JDBC, configuração do conector Lakeflow Connect | 2-4 semanas |
| **Wave 1 — Quick Wins** | Tabelas de referência/lookup (batch load), tabelas de reporting de baixa complexidade, MVP use case, estabelecer padrões Bronze/Silver/Gold | 4-6 semanas |
| **Wave 2 — Core Data** | Tabelas fato principais via CDC, stored procedures core (Simple/Medium), SSIS data flows simples → Lakeflow Jobs, cutover de relatórios Power BI/SSRS primários | 6-12 semanas |
| **Wave 3 — Complex Workloads** | Stored procedures CURSOR-based (reescrita), procedures com dynamic SQL, SSIS Script Tasks (reescrita de C#), assemblies CLR → Python UDFs | 4-8 semanas |
| **Wave 4 — Cutover & Closeout** | Edge cases remanescentes, SQL Agent jobs → Lakeflow Jobs, decomissionamento do SQL Server | 2-4 semanas |

> Durações reais dependem do escopo levantado no discovery. Planejar buffer de 20-30% para
> incertezas. A fase de cutover propriamente dita (Wave 4, execução) é detalhada em
> `kb/migration/concepts/cutover-rollback.md`.

Cite: `01 - Discover/1.3 Lecture - Planning and Road-mapping.md`, seção "Wave Structure".

---

## Checklist de Saída do Discovery (referência rápida)

- [ ] Todas as instâncias SQL Server documentadas com versão, edição e vetor de deployment
- [ ] Inventário completo de databases com tamanhos e compatibility level
- [ ] Contagem de objetos por database (tabelas, views, procedures, functions, triggers)
- [ ] Stored procedures com complexity assessment (LOW/MEDIUM/HIGH)
- [ ] Inventário de pacotes SSIS (SSISDB catalog + verificação de pacotes file-system)
- [ ] Inventário de SQL Agent jobs com schedules e último status de execução
- [ ] Tabelas CDC-enabled identificadas e disponibilidade de CDC confirmada por vetor de deployment
- [ ] Aplicações cliente e ferramentas BI conectadas mapeadas
- [ ] Tipos de login (SQL auth vs Windows auth) e role memberships documentados
- [ ] RLS, Dynamic Data Masking e requisitos de compliance documentados
- [ ] Relatórios Lakebridge Analyzer gerados para código T-SQL e pacotes SSIS
- [ ] Estratégia de migração selecionada (ETL-First ou Analytics-First)
- [ ] Workloads pontuados na Complexity Scoring Matrix e alocados em waves
- [ ] Estrutura de waves definida e aprovada pelos stakeholders

---

## Referências

- Curso "SQL Server Migration":
  - `00 - Foundations/0.2 Lecture - Migration Maturity Model.md` (anti-padrões, seção 7)
  - `00 - Foundations/0.4 Lecture - Interoperability Patterns.md` (Lakehouse Federation, seção 8.2)
  - `01 - Discover/1.2 Lecture - Discovery and Landscape Analysis.md` (discovery categories, DMVs, Lakebridge)
  - `01 - Discover/1.3 Lecture - Planning and Road-mapping.md` (scoring, sizing, estratégia, waves)
  - `01 - Discover/1.4 Demo - Discovery & Planning Phase.md` (demo prático de discovery + Lakebridge + Federation)
  - `05 - Enable/5.2 Lecture - Security and Fine-Grained Access.md` (RLS/DDM/permissions — DMVs em `scripts/mssql_discovery.sql` §8)
- Ver também: `kb/migration/index.md` (fluxo 5 fases, mapeamento de tipos, anti-padrões M01-M10)
- Ver também: `kb/migration/concepts/cutover-rollback.md` (fase de ativação/cutover subsequente ao discovery)
- Ver também: `scripts/mssql_discovery.sql` (biblioteca de queries DMV companion, seção a seção)
- [Lakebridge Documentation](https://databrickslabs.github.io/lakebridge/docs/overview/)
- [Lakehouse Federation Documentation](https://docs.databricks.com/en/query-federation/index.html)
- [Lakeflow Connect Documentation](https://docs.databricks.com/en/ingestion/lakeflow-connect/index.html)
- [SQL Server CDC Documentation](https://learn.microsoft.com/en-us/sql/relational-databases/track-changes/about-change-data-capture-sql-server)
