# Monitoramento e Alertas — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** Arquitetura de alertas, thresholds, escalação

---

## Arquitetura de Alertas

```
Data Sources (Bronze/Silver/Gold)
       ↓
System Tables + KQL Queries (Fabric) / SQL Queries (Databricks)
       ↓
SQL Alert Tasks (Databricks Jobs) + Activator (Fabric)
       ↓
Email + Webhook (Teams/Slack)
       ↓
Data Engineer → Investigate → Fix
```

---

## Thresholds Recomendados por Tipo

### Freshness (Horas desde última atualização)

| Tabela | Threshold | SLA |
|--------|-----------|-----|
| **silver_vendas** | > 2h | Critical |
| **silver_cliente** | > 24h | Warning |
| **gold_fact_receita** | > 4h | Critical |
| **bronze_*** | > 3h | Warning |

### Completeness (% de nulls)

| Coluna | Threshold | Ação |
|--------|-----------|------|
| **id_cliente (FK)** | > 1% | Alert + expect_or_drop |
| **valor_total (métrica)** | > 2% | Alert + review |
| **data_evento (dimensão)** | > 0.5% | Alert + investigate |
| **email (opcional)** | > 10% | Warning only |

### Volume (% change vs baseline)

| Cenário | Threshold | Ação |
|---------|-----------|------|
| **Volume drop** | < -30% | Critical alert |
| **Volume spike** | > +50% | Warning alert |
| **Zero records** | = 0 | Critical alert |
| **Baseline drift** | ±20% over 7d | Investigate trend |

### Latência (Minutos de delay)

| Etapa | Threshold | SLA |
|-------|-----------|-----|
| **Auto Loader → Bronze** | > 10m | Warning |
| **Bronze → Silver** | > 15m | Warning |
| **Silver → Gold** | > 20m | Critical |
| **Total end-to-end** | > 60m | Critical |

---

## Estrutura de Escalação

```
Alerta Dispara (SQL Alert Task)
         ↓
Email para data-team@company.com
         ↓
Teams/Slack notification (bridge)
         ↓
Data Engineer recebe (< 5 min)
         ↓
Investigação (check logs, run profiling)
         ↓
Root cause (bad data, wrong config, etc)
         ↓
Fix implemented + documented
         ↓
Validation + close alert
```

---

## Databricks vs Fabric: Ferramentas de Alerta

| Plataforma | Ferramenta | Trigger |
|------------|------------|---------|
| **Databricks** | SQL Alert Tasks | Scheduled Job |
| **Fabric** | Activator | Real-time KQL stream |
| **Ambos** | Webhooks Teams/Slack | Via Python |

---

## Checklist de Monitoramento

- [ ] 5+ SQL Alert Tasks configuradas (freshness, completeness, volume, duplicatas, quality)
- [ ] Alertas agendados a cada 1h (ou mais frequente se crítico)
- [ ] Webhooks Teams/Slack testados
- [ ] Thresholds por tipo de anomalia definidos
- [ ] System Tables queries configuradas para audit
- [ ] Dashboard de alerts criado (Databricks SQL)
- [ ] Runbook de investigação documentado
- [ ] Escalação para data owner definida
- [ ] Testes de alerta (simular condição, verificar notificação)
- [ ] Monitoramento de latência end-to-end ativado
