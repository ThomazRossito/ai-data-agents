# Auditoria — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** Queries de auditoria SQL, Fabric audit, pipeline diário, relatório trimestral

---

## Consultas de Auditoria Databricks

```sql
-- 1. Quem acessou qual tabela (últimos 7 dias)
SELECT
  actor_email,
  action_type,
  object_type,
  object_id,
  event_time,
  COUNT(*) AS num_acessos
FROM system.access.audit
WHERE event_date >= CURRENT_DATE() - 7
  AND (object_id LIKE '%dim_cliente%'
       OR object_id LIKE '%fact_vendas%'
       OR object_id LIKE '%PII%')
GROUP BY actor_email, action_type, object_type, object_id, event_time
ORDER BY event_time DESC;

-- 2. Tentativas de acesso negado
SELECT
  actor_email,
  object_id,
  action_type,
  request_params,
  event_time
FROM system.access.audit
WHERE event_date >= CURRENT_DATE() - 7
  AND (action_type = 'DENIED_PERMISSION'
       OR action_type = 'FAILED_AUTHENTICATION');

-- 3. Modificações de dados DML (últimos 30 dias)
SELECT
  actor_email,
  object_id,
  action_type,
  new_value,
  event_time
FROM system.access.audit
WHERE event_date >= CURRENT_DATE() - 30
  AND action_type IN ('MODIFY', 'INSERT', 'DELETE')
  AND object_type = 'TABLE'
ORDER BY event_time DESC;

-- 4. Mudanças de permissões GRANT/REVOKE (últimos 90 dias)
SELECT
  actor_email,
  action_type,
  object_id,
  request_params,
  event_time
FROM system.access.audit
WHERE event_date >= CURRENT_DATE() - 90
  AND action_type IN ('GRANT', 'REVOKE')
ORDER BY event_time DESC;

-- 5. Behavior Analytics: usuários com atividade incomum
SELECT
  actor_email,
  COUNT(*) AS num_acessos,
  COUNT(DISTINCT object_id) AS tabelas_acessadas,
  COUNT(DISTINCT action_type) AS tipos_acao,
  MIN(event_time) AS primeiro_acesso,
  MAX(event_time) AS ultimo_acesso
FROM system.access.audit
WHERE event_date >= CURRENT_DATE() - 7
GROUP BY actor_email
HAVING COUNT(*) > 1000  -- Threshold de atividade
ORDER BY num_acessos DESC;
```

---

## Auditoria Fabric (Python)

```python
import requests

def get_fabric_audit_events(workspace_id, token):
    url = f"https://api.fabric.microsoft.com/v1/admin/workspaces/{workspace_id}/audit"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "startDate": "2026-04-01",
        "endDate": "2026-04-09"
    }
    response = requests.get(url, headers=headers, params=params)
    return response.json()

# Processar eventos
audit_events = get_fabric_audit_events(workspace_id, token)
for event in audit_events.get("value", []):
    print(f"{event['CreationTime']}: {event['Operation']} by {event['UserId']}")
```

---

## Auditoria Fabric (SQL via OneLake Catalog)

```sql
-- Fabric audit via SQL endpoint
SELECT
  operation,
  user_id,
  item_name,
  item_type,
  activity_id,
  creation_time
FROM fabric_admin.audit_log
WHERE creation_time >= DATEADD(DAY, -7, GETDATE())
  AND item_type IN ('Lakehouse', 'Report', 'Dataset')
ORDER BY creation_time DESC;
```

---

## Pipeline Diário de Auditoria (DABs)

```sql
-- SQL Query executada diariamente (Alert Task)
-- Alert: "Dados PII acessados por usuário fora da lista autorizada"
SELECT
  actor_email,
  object_id,
  COUNT(*) AS acessos
FROM system.access.audit
WHERE event_date = CURRENT_DATE() - 1
  AND object_id LIKE '%PII%'
  AND actor_email NOT IN (
    SELECT email FROM catalog.governance.authorized_pii_users
  )
GROUP BY actor_email, object_id
HAVING COUNT(*) > 0;
```
