# Monitoramento e Alertas — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** SQL Alert Tasks YAML, KQL Activator, webhooks Teams/Slack

---

## Databricks: SQL Alert Tasks (DABs YAML)

```yaml
# resources/jobs.yml
resources:
  jobs:
    quality_monitoring:
      name: "Quality Monitoring Hourly"
      tasks:
        - task_key: check_freshness
          sql_task:
            alert:
              alert_id: "550e8400-e29b-41d4-a716-446655440001"
              pause_subscriptions: false
            warehouse_id: "abc123"

        - task_key: check_completeness
          sql_task:
            alert:
              alert_id: "550e8400-e29b-41d4-a716-446655440002"
            warehouse_id: "abc123"

        - task_key: check_volume
          sql_task:
            alert:
              alert_id: "550e8400-e29b-41d4-a716-446655440003"
            warehouse_id: "abc123"

      schedule:
        quartz_cron_expression: "0 * * * ?"  # Cada hora
        timezone_id: "UTC"
```

---

## Exemplos de Alertas SQL

```sql
-- Alert A: Freshness (Últimas 24h)
SELECT MAX(data_evento) AS last_event_date
FROM silver_vendas
WHERE data_carga >= current_timestamp() - INTERVAL 24 HOUR
HAVING MAX(data_evento) < current_timestamp() - INTERVAL 24 HOUR

-- Alert B: Completeness (Nulls > 5%)
SELECT
  ROUND(100.0 * SUM(CASE WHEN id_cliente IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS null_percent
FROM silver_vendas
WHERE data_carga >= current_timestamp() - INTERVAL 24 HOUR
HAVING ROUND(100.0 * SUM(CASE WHEN id_cliente IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) > 5

-- Alert C: Volume Anomaly (Drop >30%)
WITH daily_counts AS (
  SELECT
    CAST(data_evento AS DATE) AS data,
    COUNT(*) AS vendas_count
  FROM silver_vendas
  WHERE data_evento >= current_date() - 7
  GROUP BY CAST(data_evento AS DATE)
)
SELECT
  (SELECT vendas_count FROM daily_counts WHERE data = current_date()) AS today_count,
  (SELECT AVG(vendas_count) FROM daily_counts WHERE data < current_date()) AS avg_prev,
  ROUND(100.0 * (
    (SELECT vendas_count FROM daily_counts WHERE data = current_date()) -
    (SELECT AVG(vendas_count) FROM daily_counts WHERE data < current_date())
  ) / (SELECT AVG(vendas_count) FROM daily_counts WHERE data < current_date()), 2) AS percent_change
HAVING ROUND(100.0 * (
    (SELECT vendas_count FROM daily_counts WHERE data = current_date()) -
    (SELECT AVG(vendas_count) FROM daily_counts WHERE data < current_date())
  ) / (SELECT AVG(vendas_count) FROM daily_counts WHERE data < current_date()), 2) < -30

-- Alert D: Duplicatas
SELECT COUNT(*) - COUNT(DISTINCT id_venda) AS duplicate_count
FROM silver_vendas
WHERE data_carga >= current_timestamp() - INTERVAL 24 HOUR
HAVING COUNT(*) - COUNT(DISTINCT id_venda) > 0
```

---

## Fabric: Activator KQL

```kusto
// KQL Query para Freshness
silver_vendas
| where data_carga >= now(-24h)
| summarize LastEvent = max(data_evento), EventCount = count()
| where LastEvent < now(-24h)
| project Status = "STALE", LastEvent, EventCount
```

```json
{
  "trigger": {
    "type": "schedule",
    "frequency": "hourly"
  },
  "action": {
    "type": "teams",
    "webhookUrl": "https://outlook.webhook.office.com/webhookb2/...",
    "messageTemplate": {
      "title": "Data Quality Alert",
      "text": "@{LastEvent} - Vendas data not updated in last 24h. Count: @{EventCount}"
    }
  }
}
```

---

## Webhook Teams (Python)

```python
import requests
from datetime import datetime

def send_teams_alert(title, message, severity):
    webhook_url = "https://outlook.webhook.office.com/webhookb2/..."

    color_map = {
        'CRITICAL': 'ff0000',
        'WARNING': 'ffaa00',
        'INFO': '0000ff'
    }

    payload = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": title,
        "themeColor": color_map.get(severity, '0000ff'),
        "sections": [{
            "activityTitle": title,
            "activitySubtitle": f"Severity: {severity} | Time: {datetime.now().isoformat()}",
            "facts": [
                {"name": "Table", "value": "silver_vendas"},
                {"name": "Alert", "value": message}
            ]
        }]
    }

    response = requests.post(webhook_url, json=payload)
    return response.status_code == 200
```

## Webhook Slack (Python)

```python
import requests

def send_slack_alert(title, message, severity):
    webhook_url = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

    color_map = {'CRITICAL': 'danger', 'WARNING': 'warning', 'INFO': 'good'}

    payload = {
        "text": title,
        "attachments": [{
            "fallback": title,
            "color": color_map.get(severity, 'good'),
            "title": title,
            "text": message,
            "fields": [
                {"title": "Severity", "value": severity, "short": True},
                {"title": "Table", "value": "silver_vendas", "short": True}
            ]
        }]
    }

    response = requests.post(webhook_url, json=payload)
    return response.status_code == 200
```

---

## System Tables: Acessos Anômalos

```sql
-- Detectar padrão incomum (ex: bulk export)
SELECT
  user_name,
  COUNT(*) AS access_count,
  COLLECT_SET(DISTINCT resource_id) AS tables_accessed
FROM system.access.audit
WHERE
  action = 'SELECT'
  AND database_name IN ('gold', 'silver')
  AND timestamp >= current_timestamp() - INTERVAL 1 HOUR
GROUP BY user_name
HAVING COUNT(*) > 50
ORDER BY access_count DESC;
```
