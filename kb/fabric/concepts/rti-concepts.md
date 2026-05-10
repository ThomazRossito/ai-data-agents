# RTI Eventhouse — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** RTI, Eventhouse, KQL, Eventstream, Activator, tiering

---

## Real-Time Intelligence: Componentes

| Componente | Função | Exemplo |
|------------|--------|---------|
| **Eventhouse** | KQL Database para armazenar eventos | logs, sensores, clickstream |
| **Eventstream** | Ingestion hub (Kafka, Event Hub) | conecta Event Hub → Eventhouse |
| **Activator** | Alertas automáticos baseados em thresholds | anomalia → email |

**Latência:** <1 segundo (vs. Lakehouse: minutos).

---

## KQL vs SQL

| Aspecto | SQL | KQL |
|---------|-----|-----|
| **Sintaxe** | SELECT ... FROM | table \| operation |
| **JOINs** | INNER/LEFT/FULL | kind=left/inner/semi |
| **Agregações** | GROUP BY | summarize by |
| **Função Tempo** | DATE_TRUNC() | bin(timestamp, 1h) |
| **Performance** | Index-based | Column-based scans |

**Gotcha:** KQL não suporta UPDATE/DELETE — use novo schema + materialized view.

---

## Eventstream: Fontes Suportadas

| Fonte | Padrão | Nota |
|-------|--------|------|
| **Kafka** | Topic + Consumer Group | Default em clouds |
| **Event Hub** | Connection string | Azure nativo |
| **Event Grid** | Topic subscription | Serverless |
| **Cosmos DB** | Change Feed | NoSQL events |
| **Custom Source** | HTTP POST | API genérica |

---

## Activator: Tipos de Trigger

| Condição | Exemplo | Resposta |
|----------|---------|----------|
| **Threshold excedido** | `count > 1000` | Email SLA |
| **Anomalia detectada** | `stdev(value) > 3*mean` | Slack notification |
| **Sem dados (dead source)** | `count == 0 for 10m` | PagerDuty alert |
| **Degradação** | `latency > 5s` | Dashboard highlight |

---

## Retenção e Tiering

| Tier | Duração | SLA | Custo |
|------|---------|-----|-------|
| **Hot** | 30-90 dias | <1s | $normal |
| **Warm** | 90-365 dias | ~10s | $reduced |
| **Cold** | 365+ dias | ~1m | $minimal |

---

## Decision Matrix: Lakehouse vs Eventhouse

| Use Lakehouse quando | Use Eventhouse quando |
|---------------------|----------------------|
| Dados batch (diários, horários) | Streaming contínuo (eventos/logs) |
| Schema estável, transformações complexas | Real-time dashboards (<1s latência) |
| BI/Reports com Direct Lake | Alertas automáticos (Activator) |
| Volume: 100GB-10TB | Volume: 1M-10M eventos/dia |
| | TTL curto (<90 dias) |

---

## Checklist RTI Implementation

- [ ] Eventhouse criado com schema pré-definido
- [ ] Eventstream conectado (Kafka/Event Hub/Custom)
- [ ] Ingestão validada (0 failures por 24h)
- [ ] Materialized views para agregações críticas
- [ ] Retention policies configuradas (hot=30d, cold=365d)
- [ ] Activator triggers testados (email/webhook)
- [ ] Queries KQL otimizadas
- [ ] Monitoramento: `.show ingestion failures` em alert
- [ ] Documentação: KQL query library versionada no Git
