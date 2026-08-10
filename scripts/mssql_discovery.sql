/* =============================================================================
   mssql_discovery.sql
   Biblioteca de queries DMV / system catalog views — Discovery & Assessment
   SQL Server -> Databricks Migration
   =============================================================================

   FONTE (curso oficial Databricks "SQL Server Migration"):
     - 01 - Discover/1.2 Lecture - Discovery and Landscape Analysis.md
     - 01 - Discover/1.3 Lecture - Planning and Road-mapping.md
     - 01 - Discover/1.4 Demo - Discovery & Planning Phase.md
     - 05 - Enable/5.2 Lecture - Security and Fine-Grained Access.md

   KB normativa companion: kb/migration/concepts/discovery-assessment.md
   (cada seção abaixo referencia a seção correspondente da KB como "KB Sx").

   USO:
     - Rodar cada bloco (SSMS, Azure Data Studio ou sqlcmd) contra cada
       instancia/database em escopo. Substituir 'AdventureWorksDW' pelo nome
       real do banco alvo onde indicado no comentario acima do USE.
     - Todas as queries sao SOMENTE LEITURA (inventario/discovery). Nenhuma
       altera dados, schema ou configuracao do servidor.
     - Usar os resultados para popular a Complexity Scoring Matrix e o
       T-Shirt Sizing descritos na KB companion (secoes 2 e 4).
     - Nomes de DMVs/catalog views usados aqui aparecem literalmente no
       curso-fonte acima -- nao inventar nomes de views.
   ============================================================================= */


-- =============================================================================
-- SECAO 1 -- INSTANCIAS E DATABASES
-- Categoria de discovery: Data Assets (KB S1)
-- =============================================================================

-- 1.1 Inventario de databases por instancia: nome, estado, compatibility
--     level, recovery model e tamanho em GB. Rodar em CADA instancia SQL
--     Server do escopo (troque de instancia e re-execute).
--     compatibility_level 130/140/150/160 = SQL Server 2016/2017/2019/2022 --
--     um nivel baixo em uma versao nova pode indicar constraints de
--     compatibilidade de aplicacao que afetam o planejamento da migracao.
-- Fonte: 1.2, 1.4
SELECT
    @@SERVERNAME AS server_name,
    d.name AS database_name,
    d.state_desc,
    d.compatibility_level,
    d.recovery_model_desc,
    CAST(SUM(mf.size) * 8.0 / 1024 / 1024 AS DECIMAL(10,2)) AS size_gb
FROM sys.databases d
JOIN sys.master_files mf ON mf.database_id = d.database_id
WHERE d.database_id > 4  -- exclude system DBs (master, model, msdb, tempdb)
GROUP BY d.name, d.state_desc, d.compatibility_level,
         d.recovery_model_desc, d.database_id
ORDER BY size_gb DESC;
GO


-- =============================================================================
-- SECAO 2 -- ROW COUNTS E T-SHIRT SIZING
-- Categoria de discovery: Data Assets (KB S1) -- alimenta T-Shirt Sizing (KB S4)
-- =============================================================================

-- 2.1 Row count por tabela via sys.dm_db_partition_stats -- le metadata do
--     storage engine e retorna em segundos mesmo em databases com milhares
--     de tabelas (NAO faz table scan). index_id IN (0,1) = heap ou clustered
--     index (evita contar cada nonclustered index como linha separada).
--     Classificar o resultado em: S<1.000 | M 1.000-50.000 | L 50.000-1.000.000
--     | XL>1.000.000 (KB S4).
-- Fonte: 1.2, 1.4
USE AdventureWorksDW;  -- Substituir pelo nome do banco alvo
GO
SELECT
    s.name AS schema_name,
    t.name AS table_name,
    SUM(p.row_count) AS row_count
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.dm_db_partition_stats p
    ON p.object_id = t.object_id
    AND p.index_id IN (0, 1)  -- heap or clustered index
GROUP BY s.name, t.name
ORDER BY row_count DESC;
GO


-- =============================================================================
-- SECAO 3 -- OBJETOS E COMPLEXIDADE
-- Categoria de discovery: Pipelines & ETL (KB S1) -- alimenta heuristica T-SQL (KB S3)
-- =============================================================================

-- 3.1 Contagem de objetos por tipo (tabelas, views, procedures, functions,
--     triggers) -- visao rapida do volume de codigo a converter.
-- Fonte: 1.2
USE AdventureWorksDW;  -- Substituir pelo nome do banco alvo
GO
SELECT
    type_desc,
    COUNT(*) AS object_count
FROM sys.objects
WHERE type IN (
    'U',   -- User table
    'V',   -- View
    'P',   -- Stored procedure
    'FN',  -- Scalar function
    'TF',  -- Table-valued function
    'IF',  -- Inline table-valued function
    'TR'   -- Trigger
)
GROUP BY type_desc
ORDER BY object_count DESC;
GO

-- 3.2 Complexity assessment de stored procedures via heuristica sobre
--     sys.sql_modules.definition (heuristica normativa em
--     kb/migration/concepts/discovery-assessment.md KB S3.1):
--       CURSOR | EXEC(/EXECUTE( | OPENROWSET/OPENQUERY  -> High
--       WHILE  | definition > 5000 caracteres            -> Medium
--       nenhuma das anteriores                           -> Low
--     has_cursor / has_dynamic_sql / has_while_loop sao flags booleanas
--     auxiliares para filtrar/priorizar sem depender so da coluna complexity.
-- Fonte: 1.2, 1.4
USE AdventureWorksDW;  -- Substituir pelo nome do banco alvo
GO
SELECT
    SCHEMA_NAME(o.schema_id) AS schema_name,
    o.name AS procedure_name,
    LEN(m.definition) AS code_length,
    CASE
        WHEN m.definition LIKE '%CURSOR%' THEN 'High'
        WHEN m.definition LIKE '%EXEC(%' OR m.definition LIKE '%EXECUTE(%' THEN 'High'
        WHEN m.definition LIKE '%OPENROWSET%' OR m.definition LIKE '%OPENQUERY%' THEN 'High'
        WHEN m.definition LIKE '%WHILE%' THEN 'Medium'
        WHEN LEN(m.definition) > 5000 THEN 'Medium'
        ELSE 'Low'
    END AS complexity,
    CASE WHEN m.definition LIKE '%CURSOR%' THEN 1 ELSE 0 END AS has_cursor,
    CASE WHEN m.definition LIKE '%EXEC(%' OR m.definition LIKE '%EXECUTE(%' THEN 1 ELSE 0 END AS has_dynamic_sql,
    CASE WHEN m.definition LIKE '%WHILE%' THEN 1 ELSE 0 END AS has_while_loop
FROM sys.objects o
JOIN sys.sql_modules m ON o.object_id = m.object_id
WHERE o.type = 'P'
ORDER BY code_length DESC;
GO


-- =============================================================================
-- SECAO 4 -- SSIS (SSISDB)
-- Categoria de discovery: Pipelines & ETL (KB S1)
-- =============================================================================

-- 4.1 Inventario de pacotes SSIS deployados na SSISDB catalog
--     (folder/project/package + versao + data do ultimo deployment).
--     ATENCAO: nem todo pacote SSIS esta na SSISDB -- ambientes legados podem
--     ter .dtsx no file system ou referenciados via msdb. Confirmar com o
--     time de DBA antes de fechar o inventario de SSIS.
-- Fonte: 1.2
USE SSISDB;
GO
SELECT
    f.name AS folder_name,
    p.name AS project_name,
    pk.name AS package_name,
    pk.version_major,
    pk.last_deployment_time
FROM catalog.packages pk
JOIN catalog.projects p ON pk.project_id = p.project_id
JOIN catalog.folders f ON p.folder_id = f.folder_id
ORDER BY f.name, p.name, pk.name;
GO


-- =============================================================================
-- SECAO 5 -- SQL AGENT JOBS
-- Categoria de discovery: Pipelines & ETL / Operations & SLAs (KB S1)
-- =============================================================================

-- 5.1 Inventario completo de SQL Agent jobs: contagem de steps, contagem de
--     schedules e resultado da ultima execucao (step_id = 0 = job outcome
--     agregado, nao de um step individual). Cada job mapeia para um
--     Lakeflow Job no destino.
-- Fonte: 1.2
SELECT
    j.name AS job_name,
    j.enabled,
    js.step_count,
    jsc.schedule_count,
    j.date_created,
    j.date_modified,
    ISNULL(jh.last_run_outcome_desc, 'Never Run') AS last_run_outcome
FROM msdb.dbo.sysjobs j
CROSS APPLY (
    SELECT COUNT(*) AS step_count
    FROM msdb.dbo.sysjobsteps
    WHERE job_id = j.job_id
) js
CROSS APPLY (
    SELECT COUNT(*) AS schedule_count
    FROM msdb.dbo.sysjobschedules
    WHERE job_id = j.job_id
) jsc
OUTER APPLY (
    SELECT TOP 1
        CASE run_status
            WHEN 1 THEN 'Succeeded'
            WHEN 0 THEN 'Failed'
            ELSE 'Other'
        END AS last_run_outcome_desc
    FROM msdb.dbo.sysjobhistory
    WHERE job_id = j.job_id AND step_id = 0
    ORDER BY run_date DESC, run_time DESC
) jh
ORDER BY j.name;
GO


-- =============================================================================
-- SECAO 6 -- CDC (CHANGE DATA CAPTURE)
-- Categoria de discovery: Pipelines & ETL (KB S1) -- decide estrategia de
-- ingestao por vetor de deployment (KB S6.1) e por cenario (KB S6.2)
-- =============================================================================

-- 6.1 Verificar se CDC esta habilitado no nivel do database corrente.
--     Disponibilidade por vetor de deployment (KB S6.1): on-premises (SQL
--     Server 2008+), Azure SQL Managed Instance e AWS RDS SQL Server ->
--     suportado; Azure SQL Database -> suportado a partir de compatibilidade
--     SQL Server 2022, com restricoes.
-- Fonte: 1.2
SELECT name, is_cdc_enabled
FROM sys.databases
WHERE name = DB_NAME();
GO

-- 6.2 Tabelas com CDC ja habilitado: capture instance, suporte a net
--     changes, LSN inicial e data de criacao da captura. Base para decidir
--     CDC vs Batch por tabela (KB S6.2).
-- Fonte: 1.2
USE AdventureWorksDW;  -- Substituir pelo nome do banco alvo
GO
SELECT
    t.name AS table_name,
    SCHEMA_NAME(t.schema_id) AS schema_name,
    ct.capture_instance,
    ct.supports_net_changes,
    ct.start_lsn,
    ct.create_date
FROM sys.tables t
JOIN cdc.change_tables ct ON t.object_id = ct.source_object_id;
GO


-- =============================================================================
-- SECAO 7 -- CONEXOES ATIVAS E APLICACOES CLIENTE
-- Categoria de discovery: Consumers & Users (KB S1)
-- =============================================================================

-- 7.1 Sessoes ativas com aplicacao cliente, interface de conexao e ultimo
--     request -- identifica quem/o que esta conectado agora, para planejar
--     o cutover de consumidores (BI tools, apps via JDBC/ODBC).
-- Fonte: 1.2
SELECT
    s.session_id,
    s.login_name,
    s.program_name,
    s.client_interface_name,
    s.host_name,
    s.status,
    DB_NAME(s.database_id) AS database_name,
    s.login_time,
    s.last_request_start_time
FROM sys.dm_exec_sessions s
WHERE s.is_user_process = 1
ORDER BY s.last_request_start_time DESC;
GO


-- =============================================================================
-- SECAO 8 -- SEGURANCA E ACESSO
-- Categoria de discovery: Security & Access (KB S1)
-- =============================================================================

-- 8.1 Logins no nivel de servidor (SQL login, Windows user, Windows group).
--     Windows logins/grupos AD precisam mapear para Entra ID + grupo no
--     Unity Catalog no destino.
-- Fonte: 1.2
SELECT
    name AS login_name,
    type_desc AS login_type,
    is_disabled,
    create_date,
    modify_date
FROM sys.server_principals
WHERE type IN ('S', 'U', 'G')  -- SQL login, Windows user, Windows group
ORDER BY type_desc, name;
GO

-- 8.2 Role memberships no nivel de database (rodar por database em escopo).
--     db_datareader -> grant SELECT; db_datawriter -> grant MODIFY no destino.
-- Fonte: 1.2
USE AdventureWorksDW;  -- Substituir pelo nome do banco alvo
GO
SELECT
    r.name AS role_name,
    m.name AS member_name,
    m.type_desc AS member_type
FROM sys.database_role_members drm
JOIN sys.database_principals r ON drm.role_principal_id = r.principal_id
JOIN sys.database_principals m ON drm.member_principal_id = m.principal_id
ORDER BY r.name, m.name;
GO

-- 8.3 Row-Level Security: politicas de seguranca e seus predicados
--     (predicate_type_desc = FILTER ou BLOCK). Mapear para Unity Catalog Row
--     Filters no destino.
-- Fonte: 5.2
SELECT
    sp.name AS policy_name,
    sp.is_enabled,
    SCHEMA_NAME(sp.schema_id) AS policy_schema,
    pred.predicate_type_desc,
    OBJECT_SCHEMA_NAME(pred.target_object_id) AS target_schema_name,
    OBJECT_NAME(pred.target_object_id)         AS target_object_name,
    pred.predicate_definition                  AS predicate_function,
    sp.create_date,
    sp.modify_date
FROM sys.security_policies sp
JOIN sys.security_predicates pred
    ON sp.object_id = pred.object_id
ORDER BY policy_schema, policy_name;
GO

-- 8.4 Dynamic Data Masking: colunas mascaradas e a funcao de masking
--     aplicada (default/email/partial/random). Mapear para Unity Catalog
--     Column Masks no destino.
-- Fonte: 5.2
SELECT
    SCHEMA_NAME(t.schema_id) AS schema_name,
    t.name AS table_name,
    mc.name AS column_name,
    mc.masking_function,
    TYPE_NAME(mc.user_type_id) AS data_type
FROM sys.masked_columns mc
JOIN sys.tables t
    ON mc.object_id = t.object_id
WHERE mc.is_masked = 1
ORDER BY schema_name, table_name, column_name;
GO


-- =============================================================================
-- EXTRA A -- PERMISSOES DE DATABASE (complementa Secao 8 / KB S1 Security & Access)
-- =============================================================================

-- A.1 Permissoes concedidas/negadas no nivel de objeto/schema/database --
--     detalhe granular alem do role membership (8.2), necessario para
--     reconstruir fielmente GRANT/DENY como privilegios do Unity Catalog.
-- Fonte: 5.2
SELECT
    dp.state_desc AS permission_state,
    dp.permission_name,
    dp.class_desc AS object_class,
    OBJECT_SCHEMA_NAME(dp.major_id) AS schema_name,
    OBJECT_NAME(dp.major_id) AS object_name,
    pr.name AS principal_name,
    pr.type_desc AS principal_type,
    gpr.name AS grantor_name
FROM sys.database_permissions dp
JOIN sys.database_principals pr
    ON dp.grantee_principal_id = pr.principal_id
LEFT JOIN sys.database_principals gpr
    ON dp.grantor_principal_id = gpr.principal_id
WHERE dp.class_desc IN ('OBJECT_OR_COLUMN', 'SCHEMA', 'DATABASE')
ORDER BY object_class, schema_name, object_name, principal_name;
GO


-- =============================================================================
-- EXTRA B -- TOP QUERIES POR CPU/IO (Query Store) -- complementa Secao 7 e
-- a dimensao SLA Sensitivity da Complexity Scoring Matrix (KB S2)
-- =============================================================================

-- B.1 Top 20 queries por CPU total nos ultimos 30 dias via Query Store
--     (requer Query Store habilitado no database). Usar para priorizar
--     validacao de performance pos-migracao e para dimensionar SLA
--     Sensitivity na Complexity Scoring Matrix.
-- Fonte: 1.2
USE AdventureWorksDW;  -- Substituir pelo nome do banco alvo
GO
SELECT TOP 20
    qsq.query_id,
    SUBSTRING(qsqt.query_sql_text, 1, 200) AS query_text_preview,
    qsrs.count_executions,
    ROUND(qsrs.avg_cpu_time / 1000.0, 2) AS avg_cpu_ms,
    ROUND(qsrs.avg_duration / 1000.0, 2) AS avg_duration_ms,
    ROUND(qsrs.avg_logical_io_reads, 0) AS avg_logical_reads,
    qsq.object_id,
    OBJECT_NAME(qsq.object_id) AS object_name
FROM sys.query_store_query qsq
JOIN sys.query_store_query_text qsqt ON qsq.query_text_id = qsqt.query_text_id
JOIN sys.query_store_plan qsp ON qsq.query_id = qsp.query_id
JOIN sys.query_store_runtime_stats qsrs ON qsp.plan_id = qsrs.plan_id
JOIN sys.query_store_runtime_stats_interval qsrsi ON qsrs.runtime_stats_interval_id = qsrsi.runtime_stats_interval_id
WHERE qsrsi.start_time >= DATEADD(day, -30, GETUTCDATE())
ORDER BY qsrs.avg_cpu_time DESC;
GO
