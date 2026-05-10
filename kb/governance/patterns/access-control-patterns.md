# Access Control — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** GRANT SQL, RLS views, column masking, auditoria de permissões

---

## Unity Catalog: Sequência Completa de GRANT

```sql
-- 1. Criar role para equipe
CREATE ROLE analyst_br;

-- 2. Conceder USAGE na hierarquia
GRANT USAGE ON CATALOG gold_catalog TO analyst_br;
GRANT USAGE ON SCHEMA gold_catalog.sales TO analyst_br;

-- 3. Conceder SELECT apenas nas tabelas necessárias
GRANT SELECT ON TABLE gold_catalog.sales.fact_vendas TO analyst_br;
GRANT SELECT ON TABLE gold_catalog.sales.dim_cliente TO analyst_br;

-- 4. Atribuir role ao grupo do AAD/Okta
GRANT ROLE analyst_br TO GROUP 'analysts@empresa.com.br';
```

---

## Row-Level Security (RLS) via Dynamic Views

```sql
-- Mascarar dados por região do usuário
CREATE VIEW gold_catalog.sales.fact_vendas_rls AS
SELECT
  *
EXCEPT (valor_unitario)  -- Ocultar coluna sensível
FROM gold_catalog.sales.fact_vendas
WHERE regiao = CURRENT_USER_GROUP('regiao_acesso');

GRANT SELECT ON VIEW gold_catalog.sales.fact_vendas_rls TO analyst_br;
```

---

## Column Masking

```sql
-- Mascarar CPF em visão pública
CREATE VIEW gold_catalog.customers.dim_cliente_public AS
SELECT
  id_cliente,
  CONCAT(SUBSTRING(cpf, 1, 3), '***-**') AS cpf_masked,
  email
FROM gold_catalog.customers.dim_cliente;
```

---

## Offboarding: Revogar Acesso

```sql
-- Script de offboarding automático
REVOKE ALL PRIVILEGES ON CATALOG gold_catalog FROM GROUP 'team-departed@empresa.com.br';
REVOKE ROLE analyst_br FROM GROUP 'team-departed@empresa.com.br';
```

---

## Auditoria: Quem tem Acesso?

```sql
-- Quem tem SELECT na tabela de clientes?
SELECT
  principal,
  privilege,
  grant_time
FROM system.information_schema.effective_privileges
WHERE object_catalog = 'gold_catalog'
  AND object_schema = 'customers'
  AND object_name = 'dim_cliente';

-- Revisar permissões excedentes mensalmente
SELECT
  principal,
  object_name,
  object_type,
  permission
FROM system.access.permissioning
WHERE permission NOT IN ('USAGE', 'SELECT')
ORDER BY principal;
```

---

## Auditoria: Acessos Recentes a Dados Sensíveis

```sql
SELECT
  actor_email,
  object_id,
  action_type,
  event_time
FROM system.access.audit
WHERE event_date >= CURRENT_DATE() - 7
  AND object_id LIKE '%fact_vendas%'
ORDER BY event_time DESC;
```
