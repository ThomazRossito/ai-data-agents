# Cutover e Rollback — Runbook de Migração

> Runbook operacional para a fase de ativação (cutover) em migrações SQL Server → Databricks.
> Complementa `kb/migration/index.md` (fases ASSESS → RECONCILE, mapeamento de tipos, anti-padrões)
> com o passo final: freeze da fonte, catch-up de deltas, reconciliação, corte de consumidores,
> critérios de rollback e hypercare. Para padrões de implementação SQL, veja `kb/sql-patterns/`.

**Domínio:** migration — Cutover Execution
**Fonte:** Curso "SQL Server Migration", `04 - Activate/4.3 Lecture - Cutover Execution.md`
**Agentes:** migration-expert

---

## 1. Estratégias de Cutover (6)

A escolha da estratégia depende de tolerância a risco, restrição de downtime e complexidade
operacional que a organização consegue sustentar. Nenhuma é universalmente superior — são
trade-offs entre segurança, velocidade e custo de infraestrutura.

| Estratégia | Descrição | Risco | Downtime | Complexidade | Melhor Para |
|---|---|---|---|---|---|
| **Big Bang** | Troca completa em um único momento planejado | Alto | Janela planejada | Baixa | Datasets pequenos, prazos apertados |
| **Phased/Incremental** | Workloads migram em ondas por domínio/dependência | Baixo | Mínimo | Média | Grandes empresas, dependências complexas |
| **Blue-Green** | Ambientes paralelos com dados de produção; switchover instantâneo (DNS/connection string) | Baixo | Quase zero | Alta | Sistemas mission-critical, SLA rígido |
| **Canary** | Roteia um percentual pequeno de tráfego para o novo sistema, aumentando gradualmente | Muito Baixo | Nenhum | Alta | Workloads de alto risco, validação gradual |
| **A/B Testing** | Divide tráfego entre os dois sistemas para comparação de resultados | Baixo | Nenhum | Alta | Validação de performance, aceite de usuário |
| **Pilot Group** | Migra times/departamentos específicos primeiro, depois expande | Baixo | Por grupo | Média | Rollouts organization-wide |

**Notas de decisão:**
- **Big Bang** exige testes exaustivos pré-cutover (maior risco se algo falhar) — só usar com alta confiança na validação.
- **Blue-Green** exige infraestrutura duplicada durante a transição (custo mais alto), mas permite rollback instantâneo.
- **Canary/A/B** exigem infraestrutura de roteamento de tráfego e resultados comparáveis entre sistemas — período de operação paralela mais longo.
- **Phased/Pilot** reduzem o raio de impacto por onda, mas alongam o cronograma total e exigem gerenciar estado dual-sistema.

---

## 2. Freeze Window — Fases, Duração e Exit Criteria

O freeze window é o período crítico em que as escritas na fonte são interrompidas para permitir
sincronização final e validação antes do corte.

| Fase | Duração | Atividades | Exit Criteria |
|---|---|---|---|
| **Pre-Freeze** | 1-2 dias | Notificar stakeholders, desabilitar jobs agendados, pausar CDC | Todas as escritas na fonte paradas |
| **Delta Catch-up** | 2-4 horas | Sync incremental final, processar eventos CDC pendentes | Contagens de linhas batem, sem mudanças pendentes |
| **Reconciliation** | 2-4 horas | Rodar Lakebridge reconcile, validar agregações | Zero discrepâncias de dados |
| **Go/No-Go Gate** | 30 min | Revisar resultados de validação, confirmar prontidão de rollback | Aprovação dos stakeholders |
| **Cutover** | 1-2 horas | Trocar connection strings, atualizar DNS, redirecionar consumidores | Todos os consumidores em Databricks |
| **Smoke Test** | 1-2 horas | Rodar queries críticas, verificar dashboards, checar alerting | Todos os testes passam |

> **Coordenação do Freeze Window:** coordenar com todos os produtores upstream e consumidores
> downstream. Comunicar o cronograma de freeze com antecedência (tipicamente 1-2 semanas).
> Definir caminhos de escalação claros para mudanças críticas que precisem ocorrer durante o freeze.

### 2.1 Delta Catch-up via Change Data Feed (CDF)

Se CDF estiver habilitado, use as colunas de sistema `_commit_timestamp` e `_commit_version` via
`table_changes()` para rastreamento preciso de sincronização em nível de transação:

```sql
-- Habilitar CDF em uma tabela (idealmente já habilitado desde a fase DESIGN)
ALTER TABLE my_table SET TBLPROPERTIES (delta.enableChangeDataFeed = true);

-- Consultar mudanças desde uma versão ou timestamp
SELECT * FROM table_changes('my_table', '2025-01-15T00:00:00');
```

### 2.2 Delta Catch-up via MERGE federado (Lakehouse Federation)

Quando não há um mecanismo de sync automatizado (Lakeflow Connect ou pipeline customizado),
use `MERGE` manual contra o catálogo federado (foreign catalog) criado na fase de Foundations:

```sql
-- MERGE manual para deltas finais usando catálogo federado
MERGE INTO adventureworks_bronze.factinternetsales AS target
USING adventureworks.dbo.factinternetsales AS source
ON target.SalesOrderID = source.SalesOrderID
    AND target.SalesOrderDetailID = source.SalesOrderDetailID
WHEN MATCHED AND source.ModifiedDate > target.ModifiedDate THEN
    UPDATE SET *
WHEN NOT MATCHED THEN
    INSERT *;
```

### 2.3 Validar Contagens Pós Catch-up

```sql
SELECT 'FactInternetSales' AS table_name, COUNT(*) AS databricks_count, SUM(SalesAmount) AS databricks_sum
FROM adventureworks_bronze.factinternetsales
UNION ALL
SELECT 'DimProduct' AS table_name, COUNT(*) AS databricks_count, NULL AS databricks_sum
FROM adventureworks_bronze.dimproduct;
```

Cite: `04 - Activate/4.3 Lecture - Cutover Execution.md`, seções "Delta Catch-up Synchronization".

---

## 3. Congelamento da Fonte — Comandos SQL Server

Rodar diretamente no SQL Server ao iniciar o Pre-Freeze:

```sql
-- Desabilitar jobs do SQL Agent
EXEC msdb.dbo.sp_update_job @job_name = 'AdventureWorks_ETL_Daily', @enabled = 0;
EXEC msdb.dbo.sp_update_job @job_name = 'AdventureWorks_CDC_Capture', @enabled = 0;

-- Verificar que os jobs estão desabilitados
SELECT name, enabled FROM msdb.dbo.sysjobs
WHERE name LIKE 'AdventureWorks%';

-- Documentar o LSN do CDC antes do freeze (referência para rollback)
SELECT sys.fn_cdc_get_max_lsn() AS max_lsn;

-- Verificar que não há mudanças de CDC pendentes
SELECT COUNT(*) AS pending_changes
FROM cdc.dbo_FactInternetSales_CT
WHERE __$start_lsn > sys.fn_cdc_get_max_lsn();
```

**Por que documentar o LSN:** `sys.fn_cdc_get_max_lsn()` marca o ponto exato do congelamento.
Se for necessário rollback, esse LSN comprova que nenhuma escrita ocorreu na fonte durante a
janela e serve de referência de auditoria pós-incidente — documentar o valor retornado antes
de prosseguir para o Delta Catch-up.

---

## 4. Reconciliação Final (Lakebridge)

```bash
# Reconciliação final antes do cutover
databricks labs lakebridge reconcile

# Verificar o AI/BI Dashboard usando o recon_id gerado

# Se houver discrepâncias, investigar antes de prosseguir — não avançar para o gate com pendências
databricks labs lakebridge aggregates-reconcile
```

Exit criteria desta fase: **zero discrepâncias de dados**. Qualquer divergência aberta bloqueia
o avanço para o Go/No-Go Gate (seção 5).

---

## 5. Go/No-Go Gate

Janela de 30 minutos, imediatamente antes do cutover. Revisar:
- Resultados de validação da Reconciliation (seção 4) — zero discrepâncias
- Prontidão do procedimento de rollback (seção 7) — equipe e comandos disponíveis
- Aprovação explícita dos stakeholders (não apenas do time técnico)

Só avançar para Cutover com aprovação formal registrada.

---

## 6. Matriz de Decisão de Rollback (Numérica)

Aplicar durante o Smoke Test e o período imediatamente após o cutover. A severidade determina
a ação — não há espaço para julgamento ad-hoc nos casos "Alto".

| Condição | Severidade | Ação | Rollback? |
|---|---|---|---|
| Discrepância de dados **< 0.01%** | Baixa | Investigar, continuar monitorando | Não |
| Discrepância de dados **0.01–1%** | Média | Pausar cutover, investigar causa raiz | Talvez |
| Discrepância de dados **> 1%** | Alta | Rollback imediato | **Sim** |
| Falha em dashboard crítico | Alta | Rollback imediato | **Sim** |
| Degradação de performance **> 50%** | Alta | Rollback se não resolvido em **1 hora** | **Sim** (se não resolvido) |
| Problema em relatório não-crítico | Baixa | Documentar, corrigir in-place | Não |
| Falha de job (não-crítico) | Média | Retry, escalar se persistente | Não |
| Múltiplas falhas de job | Alta | Avaliar escopo, considerar rollback | Talvez |

---

## 7. Procedimento de Rollback

Se a matriz da seção 6 indicar rollback, seguir **nesta ordem** — não pular etapas:

1. Anunciar a decisão de rollback a todos os stakeholders
2. Reverter connection strings dos consumidores para o SQL Server
3. Reabilitar os jobs do SQL Agent e a captura de CDC suspensos
4. Verificar que os dados do SQL Server estão atualizados (sem perda de dados durante a janela de cutover)
5. Confirmar que todos os dashboards e relatórios estão funcionais
6. Documentar o motivo do rollback e as lições aprendidas
7. Agendar post-mortem e plano de remediação

### Comandos de rollback (SQL Server)

```sql
-- Reabilitar jobs do SQL Agent
EXEC msdb.dbo.sp_update_job @job_name = 'AdventureWorks_ETL_Daily', @enabled = 1;
EXEC msdb.dbo.sp_update_job @job_name = 'AdventureWorks_CDC_Capture', @enabled = 1;

-- Verificar que os jobs estão habilitados
SELECT name, enabled FROM msdb.dbo.sysjobs
WHERE name LIKE 'AdventureWorks%';

-- Checar gaps de dados durante a janela de freeze (usar o LSN documentado na seção 3 como referência)
SELECT
    MIN(OrderDate) AS earliest_order,
    MAX(OrderDate) AS latest_order,
    COUNT(*) AS order_count
FROM AdventureWorksDW.dbo.FactInternetSales
WHERE OrderDate >= DATEADD(HOUR, -24, GETDATE());
```

Cite: `04 - Activate/4.3 Lecture - Cutover Execution.md`, seção "Rollback Planning".

---

## 8. Consumer Switchover (checklist)

| Tipo de Consumidor | SQL Server | Databricks | Método de Switchover |
|---|---|---|---|
| BI Dashboards | Conector SQL Server | Conector Databricks SQL | Atualizar data source |
| Relatórios agendados | SQL Server JDBC | Databricks JDBC/ODBC | Atualizar connection string |
| Aplicações | Driver SQL Server | Driver Databricks | Mudança de configuração |
| Data Science | T-SQL / SSIS | PySpark / Databricks Connect | Atualização de código |
| ETL Downstream | Tabelas SQL Server | Tabelas Unity Catalog | Atualizar referências de origem |
| APIs | SQL Server ODBC/OLEDB | Databricks SQL Statement API | Mudança de endpoint |

```bash
# Databricks JDBC (após switchover)
jdbc:databricks://dbc-xxxxx.cloud.databricks.com:443/default;transportMode=http;ssl=1;AuthMech=3;httpPath=/sql/1.0/warehouses/abc123def456

# Com Unity Catalog (catalog/schema explícitos)
jdbc:databricks://dbc-xxxxx.cloud.databricks.com:443/default;transportMode=http;ssl=1;AuthMech=3;httpPath=/sql/1.0/warehouses/abc123def456;ConnCatalog=adventureworks_dev;ConnSchema=adventureworks_bronze
```

---

## 9. Smoke Test Checklist (pós-cutover)

Executar imediatamente após o switchover, antes do Go/No-Go de validação de negócio:

| Teste | Query/Ação | Resultado Esperado |
|---|---|---|
| Acessibilidade de tabela | `SELECT COUNT(*) FROM table` | Retorna contagem |
| Performance de join | Query multi-tabela | Completa em < 30s |
| Precisão de agregação | SUM/AVG vs baseline | Dentro de 0.01% |
| Carregamento de dashboard | Abrir dashboard principal | Renderiza corretamente |
| Job agendado | Disparar job de teste | Completa com sucesso |
| Funcionalidade de alerta | Disparar alerta de teste | Notificação recebida |
| Acesso de usuário | Usuário de teste consulta tabela | Acesso concedido |

---

## 10. Linha do Tempo de Referência

Visão agregada de ponta a ponta (baseada no cronograma típico do curso); a granularidade
hora a hora do Freeze Window está na seção 2.

| Fase | Atividades | Duração Agregada |
|---|---|---|
| Preparação | Validação final + sign-off dos stakeholders + revisão do runbook | ~6 dias |
| Freeze Window | Freeze da fonte + delta catch-up + reconciliação final | ~3 dias (ver seção 2 para detalhe em horas) |
| Cutover | Switchover de consumidores + smoke test + gate de rollback | ~2 dias |
| Validação | Validação de dashboards/relatórios + monitoramento de performance | até 5 dias, em paralelo ao cutover |
| Sign-off + Hypercare | Aprovação de negócio + hypercare | 7-14 dias |

---

## 11. Hypercare (1-2 semanas)

Período de suporte reforçado imediatamente após o cutover:

- Manter thresholds de monitoramento e alerting mais sensíveis que o normal
- Manter o time de migração de plantão (on-call) para resposta rápida
- Daily stand-ups para revisar issues e métricas
- Documentar todos os incidentes e suas resoluções
- Coletar feedback dos usuários para otimizações subsequentes

---

## 12. Sign-off por Owner

Sign-off formal confirma que a migração atende aos critérios de aceite e que a organização está
pronta para operar no Databricks. Cada linha exige owner explícito — sign-off não é um checkbox
único do time técnico.

| Critério | Owner | Status |
|---|---|---|
| Validação de dados completa (contagens, agregações) | Data Engineering | ☐ |
| Todos os dashboards funcionais | BI Team | ☐ |
| Relatórios agendados verificados | Analytics | ☐ |
| Conectividade de aplicações confirmada | Development | ☐ |
| Performance dentro do SLA | Data Engineering | ☐ |
| Segurança e controles de acesso verificados | Security | ☐ |
| Runbooks e documentação atualizados | Operations | ☐ |
| Plano de suporte hypercare em vigor | Support | ☐ |
| **Aprovação final de negócio** | Business Sponsor | ☐ |

---

## Checklist de Execução (referência rápida)

- [ ] Estratégia de cutover selecionada e comunicada (seção 1)
- [ ] Freeze window agendado com stakeholders (seção 2), aviso de 1-2 semanas
- [ ] Procedimento de rollback documentado e testado (seção 7)
- [ ] Jobs do SQL Agent e CDC desabilitados na fonte (seção 3), LSN documentado
- [ ] Delta catch-up de sincronização completo (seção 2.1/2.2)
- [ ] Reconciliação final do Lakebridge aprovada (seção 4)
- [ ] Go/No-Go Gate aprovado formalmente (seção 5)
- [ ] Connection strings dos consumidores atualizadas (seção 8)
- [ ] Smoke tests aprovados (seção 9)
- [ ] Dashboards e relatórios validados
- [ ] Sign-off de negócio obtido (seção 12)
- [ ] Hypercare iniciado (seção 11)

---

## Referências

- Curso "SQL Server Migration" — `04 - Activate/4.3 Lecture - Cutover Execution.md`
- Ver também: `kb/migration/index.md` (fases ASSESS→RECONCILE, mapeamento de tipos, anti-padrões M01-M10)
- Ver também: `kb/sql-patterns/concepts/tsql-conversion-catalog.md` (catálogo de conversão T-SQL usado nas fases anteriores ao cutover)
- [Databricks SQL Connector](https://docs.databricks.com/en/integrations/jdbc-odbc-bi.html)
- [Lakebridge Reconciler](https://databrickslabs.github.io/lakebridge/docs/reconcile/)
