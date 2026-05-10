# SLA Contracts — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** YAML template, DDL tables, monitoramento SQL, escalação Python

---

## Template YAML de SLA Contract

```yaml
# SLA Contrato
contract_id: "SLA-SLV-VENDAS-001"
table_name: "catalog.silver.vendas"

data_owner: "Data Product Manager - Sales"
data_owner_email: "sales-dpm@company.com"
backup_owner_email: "data-eng-lead@company.com"

sla:
  freshness:
    max_hours_since_update: 4
    definition: "MAX(data_carga) >= NOW() - INTERVAL 4 HOUR"
    severity: "CRITICAL"

  completeness:
    min_nonnull_percent: 95
    critical_columns: ["id_cliente", "valor_total", "data_evento"]
    severity: "CRITICAL"

  availability:
    min_uptime_percent: 99.5
    maintenance_window: "2-4 AM UTC, Sundays"

  uniqueness:
    no_duplicates: true
    unique_keys: ["id_venda"]
    severity: "CRITICAL"

  validity:
    valid_statuses: ["ATIVO", "CANCELADO", "RETORNADO"]
    valid_valor_range: [0, 1000000]

monitoring:
  frequency: "Hourly"
  check_schedule: "0 * * * ?"

alerts:
  - dimension: "freshness"
    threshold: "max_hours >= 4"
    channels: ["teams", "pagerduty"]
    escalation_after_minutes: 30

  - dimension: "completeness"
    threshold: "nonnull_pct < 95"
    channels: ["email", "slack"]
    escalation_after_minutes: 60

escalation:
  level_1:
    response_time: "15 minutes"
    owner: "on-call data engineer"
  level_2:
    response_time: "5 minutes"
    owner: "data-eng-lead"
  level_3:
    response_time: "Immediate"
    owner: "data-eng-director"

postmortem:
  required_if: "SLA violated > 1 hour OR data quality impact > 1000 rows"
  timeline: "Within 24 hours of resolution"
```

---

## DDL: sla_contracts e sla_violations

```sql
CREATE TABLE IF NOT EXISTS catalog.quality.sla_contracts (
  contract_id STRING,
  table_name STRING,
  catalog STRING,
  schema STRING,
  data_owner STRING,
  data_owner_email STRING,
  backup_owner STRING,
  sla_freshness_hours INT,
  sla_completeness_pct DOUBLE,
  sla_availability_pct DOUBLE,
  sla_uniqueness_required BOOLEAN,
  sla_unique_keys STRING,
  sla_valid_values STRING,  -- JSON
  monitoring_frequency STRING,
  dashboard_url STRING,
  alert_channels STRING,  -- JSON array
  escalation_level_1_minutes INT,
  escalation_level_2_minutes INT,
  escalation_level_3_minutes INT,
  refresh_frequency STRING,
  refresh_expected_duration_minutes INT,
  created_date DATE,
  created_by STRING,
  last_updated_date DATE,
  last_updated_by STRING,
  active BOOLEAN
);

CREATE TABLE IF NOT EXISTS catalog.quality.sla_violations (
  violation_id STRING,
  contract_id STRING,
  table_name STRING,
  dimension STRING,
  sla_threshold STRING,
  actual_value STRING,
  violation_severity STRING,
  violation_start TIMESTAMP,
  violation_resolved TIMESTAMP,
  resolution_action STRING,
  created_by STRING
);
```

---

## Verificação Horária (SQL Alert Task)

```sql
WITH sla_check AS (
  SELECT
    'silver_vendas' AS table_name,
    MAX(data_carga) AS last_update,
    CASE
      WHEN DATEDIFF(CURRENT_TIMESTAMP(), MAX(data_carga)) > 4 THEN 'VIOLATED'
      ELSE 'OK'
    END AS freshness_status,
    ROUND(100.0 * SUM(CASE WHEN id_cliente IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS completeness_pct,
    CASE
      WHEN 100.0 * SUM(CASE WHEN id_cliente IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*) < 95 THEN 'VIOLATED'
      ELSE 'OK'
    END AS completeness_status,
    CASE
      WHEN COUNT(*) = COUNT(DISTINCT id_venda) THEN 'OK'
      ELSE 'VIOLATED'
    END AS uniqueness_status,
    CURRENT_TIMESTAMP() AS check_timestamp
  FROM silver_vendas
)
SELECT * FROM sla_check
WHERE freshness_status = 'VIOLATED'
   OR completeness_status = 'VIOLATED'
   OR uniqueness_status = 'VIOLATED';
```

---

## DABs: Escalação Automática

```yaml
resources:
  jobs:
    sla_escalation:
      name: "SLA Escalation Hourly"
      tasks:
        - task_key: check_sla
          sql_task:
            alert:
              alert_id: "sla-check-alert"
            warehouse_id: "abc123"

        - task_key: escalate_if_violated
          depends_on:
            - task_key: check_sla
          run_if: "AT_LEAST_ONE_FAILED"
          notebook_task:
            notebook_path: ../src/escalate_sla_violation
            base_parameters:
              escalation_level: "1"
```

## Python: Lógica de Escalação

```python
from datetime import datetime
import requests

def escalate_sla_violation(table_name, violation_duration_minutes):
    contract = spark.read.table("catalog.quality.sla_contracts") \
        .filter(f"table_name = '{table_name}'").collect()[0]

    if violation_duration_minutes <= contract['escalation_level_1_minutes']:
        level, owner, urgency = 1, "on-call-data-engineer", "medium"
    elif violation_duration_minutes <= contract['escalation_level_2_minutes']:
        level, owner, urgency = 2, contract['data_owner_email'], "high"
    else:
        level, owner, urgency = 3, "data-eng-director", "critical"

    send_escalation_alert(level=level, owner=owner, urgency=urgency,
                          table=table_name, duration=violation_duration_minutes)

    spark.sql(f"""
        INSERT INTO catalog.quality.sla_violations
        VALUES (
            CONCAT('VIO-', CURRENT_TIMESTAMP_MS()),
            '{contract['contract_id']}',
            '{table_name}',
            'ESCALATION_LEVEL_{level}',
            'Violation duration > {violation_duration_minutes} min',
            '{urgency}',
            CURRENT_TIMESTAMP(), NULL, 'Escalation triggered', 'system'
        )
    """)
```

---

## View de Dashboard SLA Status

```sql
CREATE VIEW IF NOT EXISTS catalog.quality.sla_status AS
SELECT
  c.contract_id,
  c.table_name,
  c.data_owner,
  (SELECT MAX(data_carga) FROM silver_vendas) AS last_update,
  c.sla_freshness_hours,
  CASE
    WHEN DATEDIFF(CURRENT_TIMESTAMP(), (SELECT MAX(data_carga) FROM silver_vendas)) <= c.sla_freshness_hours
    THEN 'PASS' ELSE 'FAIL'
  END AS freshness_status,
  CURRENT_TIMESTAMP() AS check_time
FROM catalog.quality.sla_contracts c;
```
