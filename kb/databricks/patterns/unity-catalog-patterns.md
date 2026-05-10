# Unity Catalog — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** Grant SQL, Volumes, System Tables queries, Lineage

---

## Grants: Sequência Correta

```sql
-- Dar acesso completo a data_engineers
GRANT USE CATALOG ON CATALOG main TO `data_engineers`;
GRANT USE SCHEMA ON SCHEMA main.analytics TO `data_engineers`;
GRANT SELECT, MODIFY ON TABLE main.analytics.users TO `data_engineers`;
```

## Revogar Acesso

```sql
REVOKE SELECT ON TABLE main.analytics.users FROM `contractors`;
```

## Validar Permissões

```sql
SELECT principal, action_type
FROM system.information_schema.applicable_privileges
WHERE table_name = 'users';
```

---

## Volumes

```sql
-- Criar volume
CREATE VOLUME main.raw.landing COMMENT "Arquivos entrada não processados";
```

```python
# Upload de arquivo
upload_to_volume(
    local_path="/tmp/data.csv",
    volume_path="/Volumes/main/raw/landing/data.csv"  # Path completo
)

# Listar conteúdo
list_volume_files(volume_path="/Volumes/main/raw/landing/")
```

---

## System Tables: Habilitar Acesso

```sql
GRANT USE CATALOG ON CATALOG system TO `data_engineers`;
GRANT USE SCHEMA ON SCHEMA system.access TO `data_engineers`;
GRANT SELECT ON SCHEMA system.access TO `data_engineers`;
```

---

## System Tables: Queries Comuns

```sql
-- Auditoria: mudanças de permissão (SEMPRE filtrar por data)
SELECT event_time, user_identity.email, action_name, request_params
FROM system.access.audit
WHERE (action_name LIKE '%GRANT%' OR action_name LIKE '%REVOKE%')
  AND event_date >= current_date() - 30
ORDER BY event_time DESC
LIMIT 100;

-- Lineage: tabelas que alimentam uma tabela
SELECT DISTINCT source_table_full_name, source_column_name
FROM system.access.table_lineage
WHERE target_table_full_name = 'main.analytics.users'
  AND event_date >= current_date() - 7;

-- Billing: DBU por semana
SELECT workspace_id, sku_name, usage_date, SUM(usage_quantity) AS dbus
FROM system.billing.usage
WHERE usage_date >= current_date() - 30
GROUP BY workspace_id, sku_name, usage_date;
```

---

## Lineage Recursiva (Multi-Nível)

```sql
-- Mostrar cadeia completa: A -> B -> C
WITH RECURSIVE lineage AS (
  SELECT source_table_full_name, target_table_full_name, 1 AS level
  FROM system.access.table_lineage
  WHERE target_table_full_name = 'main.analytics.dashboard_source'
    AND event_date >= current_date() - 7

  UNION ALL

  SELECT tl.source_table_full_name, tl.target_table_full_name, l.level + 1
  FROM system.access.table_lineage tl
  JOIN lineage l ON tl.target_table_full_name = l.source_table_full_name
  WHERE tl.event_date >= current_date() - 7 AND l.level < 5
)
SELECT * FROM lineage ORDER BY level;
```

---

## Verificar Catalog de Tabela

```sql
SELECT catalog_name FROM system.information_schema.tables
WHERE table_name = 'users';
```
