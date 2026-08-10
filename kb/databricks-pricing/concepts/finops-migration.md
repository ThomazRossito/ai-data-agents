---
concept: finops-migration
domain: databricks-pricing
updated_at: 2026-08-02
source: course_corpus "SQL Server Migration" (05 - Enable/5.1, 06 - Closeout/6.1, 04 - Activate/4.2) + verificação web ago/2026
---

# FinOps na Migração SQL Server → Databricks

## 1. Escopo deste conceito

Os demais arquivos de `kb/databricks-pricing/concepts/` (`dbu-model.md`, `system-billing.md` etc.) cobrem a **mecânica de precificação** (DBU rate, schema `system.billing`). Este arquivo cobre o **modelo operacional de FinOps especificamente na migração SQL Server → Databricks** — o que muda pro time que vinha de licenciamento SQL Server, quais anti-padrões evitar, e quais quick-wins aplicar no primeiro trimestre pós-go-live.

Fontes: corpus do curso "SQL Server Migration" — fases **05 Enable** (`5.1 Lecture - Platform Operations and Cost Management.md`) e **06 Closeout** (`6.1 Lecture - Observability and Cost Monitoring.md`), complementado por **04 Activate** (`4.2 Lecture - Observability, Monitoring & Performance Optimization.md`) e verificação web (ago/2026, citada explicitamente onde usada).

## 2. Modelo de custo: de licença para consumo

| SQL Server | Databricks | Nota |
|---|---|---|
| Licenciamento per-core / vCore ou DTU (Azure SQL) | **DBUs** (Databricks Units) | Unidade de consumo base — ver `dbu-model.md` |
| Instance size / service tier | Warehouse size + SKU | SKUs diferentes têm DBU rate diferente |
| Licença anual (on-prem) / cobrança horária ou por segundo (Azure SQL) | **Cobrança por segundo** | On-prem SQL Server não tem billing por segundo — é o câmbio mental mais importante pro time de FinOps |
| Auto-pause (só Azure SQL Serverless) | **Auto-stop** | Disponível em qualquer warehouse/cluster Databricks, não restrito a um tier serverless específico |
| Read scale-out / Elastic Pools (Azure SQL) | Auto-scaling clusters | Scaling horizontal |
| **Resource Governor** | **Budgets + Alerts** | **Ver anti-padrão crítico abaixo — NÃO são equivalentes em comportamento** |
| Disco local (on-prem) / Azure Storage (Azure SQL) | Storage do cloud provider | Via Unity Catalog / DBFS |

*Fonte: 05.1 §2 "Understanding the Cost Model" + Summary.*

## 3. Anti-padrão crítico: budgets são informativos, NÃO suspendem compute

Este é o erro de FinOps mais comum na migração — assumir que "Budget" no Databricks se comporta como o **Resource Governor** do SQL Server.

| | SQL Server Resource Governor | Databricks Budgets |
|---|---|---|
| Comportamento ao exceder limite | Pode limitar/classificar e conter recursos por workload group | **Apenas notifica por e-mail** (thresholds configuráveis, ex: 50/75/90%) |
| Suspende compute automaticamente? | Sim (via classificação de workload) | **NÃO** |
| Onde configurar | `sys.resource_governor_*` | Account Console → Budgets (nível conta), escopado por workspace ou tag |

> **Implicação prática:** se o time assume "configurei o budget, está protegido", o cluster/warehouse **continua rodando e cobrando** normalmente mesmo depois do alerta disparar. O controle "hard" equivalente ao Resource Governor no Databricks é **cluster policy** (`dbus_per_hour` com range máximo + `autotermination_minutes`) — não o budget. Budget é observability; cluster policy é enforcement.

*Fonte: 05.1 §5 (aviso "Configure Budget Alerts Before Production") + 06.1 §"Creating Account Level Budget Tracking and Alerts" ("estas alertas são apenas informativas — notificam você, mas não suspendem compute automaticamente").*

## 4. Estratégia de tagging

### 4.1 Schema recomendado

| Tag key | Propósito | Valores de exemplo |
|---|---|---|
| `team` | Ownership | `data-engineering`, `analytics`, `ml-ops` |
| `project` | Rastreamento de projeto | `adventureworks-migration`, `customer-360` |
| `environment` | Ambiente | `dev`, `staging`, `prod` |
| `cost-center` | Código financeiro | `CC-1001`, `CC-2045` |
| `workload` | Tipo de workload | `etl`, `bi`, `ml-training`, `ad-hoc` |

### 4.2 Atenção: o atributo de tag muda por tipo de recurso

| Tipo de recurso | Atributo |
|---|---|
| Jobs | `tags` |
| Pipelines | `tags` |
| SQL Warehouses | `tags` |
| **Clusters** | **`custom_tags`** (não `tags`!) |

Esse detalhe quebra silenciosamente Asset Bundles copiados de um template de Job pra um Cluster sem ajustar o nome do atributo.

### 4.3 Enforcement via cluster policies (regex)

Tag é convenção até virar **regra imposta**. Cluster policies garantem atribuição de custo completa:

```json
{
  "dbus_per_hour": { "type": "range", "maxValue": 50 },
  "autotermination_minutes": { "type": "range", "minValue": 10, "maxValue": 60, "defaultValue": 20 },
  "custom_tags.team": { "type": "unlimited" },
  "custom_tags.cost-center": {
    "type": "regex",
    "pattern": "CC-[0-9]{4}(-[A-Z]+)?"
  }
}
```

Cluster policies só se aplicam a **all-purpose clusters** e **job compute** — não a SQL Warehouses (que carregam `tags` diretamente no recurso, sem policy).

*Fonte: 05.1 §3 ("Tagging Strategy for Cost Attribution" + exemplo JSON de cluster policy + "Applying Tags via Asset Bundles").*

### 4.4 Propagação para system.billing.usage

Tags aplicadas em clusters/jobs/pipelines/warehouses propagam para a coluna `custom_tags` de `system.billing.usage`. Sem tags, o consumo aparece como "unattributed compute" — impossível fazer chargeback ou identificar workloads caros por time/projeto.

*Fonte: 4.2 §7 (callout "Tag Resources for Cost Attribution").*

## 5. Query central: custo por tag e SKU

```sql
SELECT
    custom_tags['team'] AS team,
    custom_tags['project'] AS project,
    custom_tags['environment'] AS environment,
    sku_name,
    DATE_TRUNC('month', usage_start_time) AS usage_month,
    SUM(usage_quantity) AS total_dbus,
    COUNT(DISTINCT usage_date) AS active_days
FROM system.billing.usage
WHERE usage_start_time >= CURRENT_DATE - INTERVAL 90 DAYS
  AND custom_tags IS NOT NULL
GROUP BY ALL
ORDER BY usage_month DESC, total_dbus DESC
```

Variante por job (usa `usage_metadata.job_id`/`job_name`, não `custom_tags`):

```sql
SELECT
    usage_date,
    usage_metadata.job_name AS job_name,
    usage_metadata.job_id AS job_id,
    sku_name,
    SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE usage_metadata.job_id IS NOT NULL
  AND usage_date >= current_date() - INTERVAL 90 DAYS
GROUP BY usage_date, usage_metadata.job_name, usage_metadata.job_id, sku_name
ORDER BY total_dbus DESC
```

Para o schema completo de `system.billing.usage`/`list_prices` (colunas, pattern de classificação de SKU, mock mode do agente), ver **`concepts/system-billing.md`** — este arquivo foca na narrativa de migração; aquele foca na mecânica da tabela. Não duplicado aqui.

*Fonte: 05.1 §3 ("DBU usage by tag and SKU") + 4.2 §7 ("Usage attributed to jobs").*

## 6. Rightsizing pós-migração

| Prática | Detalhe |
|---|---|
| **Serverless como default** | Databricks recomenda serverless pra maioria dos workloads — zero config, sempre disponível, escala automática |
| **IWM (Intelligent Workload Management)** | Warehouses serverless usam ML pra prever recursos, gerenciar filas e escalar dinamicamente |
| **Sinal de subdimensionamento** | **Peak Queued Queries > 0** de forma consistente na página de monitoring do warehouse = precisa de mais capacidade |
| **Photon só compensa em wide transforms** | SQL/DataFrame com joins, agregações, scans grandes. ETL simples sem wide transforms, ou queries < 2s, tem impacto mínimo — **não ativar por padrão sem esse sinal** |
| **Auto-stop agressivo em dev/test** | 5-10 min de auto-termination em ambientes não-produtivos |
| **Warehouse único maior > múltiplos pequenos** | Comece com 1 warehouse maior e deixe o serverless gerenciar concorrência — mais fácil reduzir depois do que escalar sob pressão |

Regra de bolso de ROI de Photon (quando vale comparar) está em `concepts/photon-roi.md` — não duplicado aqui.

*Fonte: 05.1 §4 ("Right-Sizing Compute Resources", "SQL Warehouse Sizing (Serverless)", "Photon Assessment").*

## 7. Quick-wins de custo (primeiro trimestre pós-go-live)

| Estratégia | Implementação | Economia estimada (curso) |
|---|---|---|
| Auto-stop agressivo | 5-10 min em dev/test | 30-50% no tempo ocioso |
| Right-size warehouses | Começar pequeno, escalar por queue time | 20-40% |
| Serverless | Default pra workload variável | Paga só por query ativa |
| Enforce tagging | Cluster policies obrigando tags | Habilita accountability (não é economia direta) |
| Spot instances em jobs | Batch tolerante a falha | 60-80% no compute de job |
| Photon | SQL/Spark SQL com wide transforms | 2-3× mais rápido = menos DBUs consumidos |
| Liquid Clustering | Substitui partitioning | Reduz custo de scan |
| Predictive Optimization | Habilitar em Metastore/Catalog/Schema com herança | Melhor performance, menos manutenção manual |
| Revisar clusters interativos | Auditoria mensal de clusters pessoais | Elimina "zombie clusters" |

> **Caveat:** os percentuais acima são estimativas ilustrativas do material do curso, não números validados pelo engine `databricks_pricing` deste projeto (esse é determinístico via catalog YAML — ver `index.md` §1). Para comprovar economia real num cliente, comparar `system.billing.usage` **antes vs depois** da mudança (tools `databricks_billing_*` / modo ACTUAL do agente `databricks-cost-calculator`, ou `databricks_pricing_compare_estimate_vs_actual`).

*Fonte: 05.1 §6 ("Cost Optimization Quick Wins").*

## 8. Predictive Optimization

Automatiza `OPTIMIZE`, `VACUUM`, `ANALYZE` (e dispara `CLUSTER BY`/Liquid Clustering quando configurado) em **tabelas gerenciadas (managed) do Unity Catalog** — não cobre tabelas externas nem Delta Sharing.

| Característica | Detalhe |
|---|---|
| Escopo | Managed tables apenas (externas e Delta Sharing ficam de fora) |
| Modelo de herança | Habilitar em nível de conta (Metastore), Catalog, ou Schema — tabelas herdam do pai |
| Billing | Serverless compute, cobrado separadamente (SKU de jobs) — ainda aparece em `system.billing.usage` |
| Default | Habilitado por padrão para **contas criadas a partir de 11/nov/2024** |
| Rollout em contas existentes | Curso (4.2) cita conclusão "até fevereiro de 2026"; **verificação web mais recente (ago/2026) indica que o rollout para contas existentes está concluindo agora, ~ago/2026** — trate a data exata como móvel e confirme no workspace (não assuma habilitado sem checar) |

```sql
-- Verificar se predictive optimization está habilitado num schema
DESCRIBE SCHEMA EXTENDED adventureworks_silver;

-- Habilitar em nível de schema (tabelas managed)
ALTER SCHEMA adventureworks_silver ENABLE PREDICTIVE OPTIMIZATION;

-- Verificar histórico de operações executadas automaticamente
SELECT table_name, operation_type, operation_status, start_time, end_time
FROM system.storage.predictive_optimization_operations_history
WHERE start_time >= current_date() - INTERVAL 90 DAYS
ORDER BY start_time DESC;
```

*Fonte: 05.1 §6 ("Predictive Optimization" callout + SQL) + 4.2 §10 (callout + `system.storage.predictive_optimization_operations_history`) + verificação web ago/2026 (data de rollout).*

## 9. Checklist operacional (handoff pós-migração)

- [ ] Tagging schema definido e documentado (`team/project/environment/cost-center/workload`)
- [ ] Cluster policies impõem tags obrigatórias (regex em `custom_tags.cost-center`)
- [ ] SQL Warehouses dimensionados por análise de workload real (não chute)
- [ ] Auto-stop configurado em todo compute (agressivo em dev/test)
- [ ] Budget alerts configurados no Account Console **E** cluster policies como controle "hard" complementar (não confundir os dois — ver §3)
- [ ] Dashboard de atribuição de custo por tag publicado (query §5)
- [ ] Predictive Optimization habilitado nas tabelas de produção (verificado, não assumido — §8)

*Fonte: 05.1 (checklist "Platform Operations Checklist").*

## 10. Ver também

- `concepts/dbu-model.md` — mecânica do DBU rate
- `concepts/system-billing.md` — schema completo `system.billing.usage`/`list_prices`, SKU classification, mock mode
- `concepts/photon-roi.md` — regra de bolso de Photon
- `concepts/estimate-vs-actual.md` — comparar cenário estimado vs consumo real
- `skills/databricks/databricks-observability-migration/SKILL.md` — playbook de monitoramento pós-migração (jobs, pipelines, alertas, tuning)
- `skills/migration/SKILL.md` — playbook das 5 fases de migração
