# Auditoria — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** system.access.audit, estrutura da tabela, frequência de auditoria

---

## Estrutura de system.access.audit

| Campo | Tipo | Descrição |
|-------|------|-----------|
| **event_id** | STRING | ID único do evento |
| **actor_email** | STRING | Email do usuário que executou a ação |
| **action_type** | STRING | CREATE, READ, MODIFY, DELETE, GRANT, REVOKE |
| **object_type** | STRING | TABLE, SCHEMA, CATALOG, VOLUME, CLUSTER |
| **object_id** | STRING | ID qualificado (ex: catalog.schema.table) |
| **new_value** | VARIANT | Valor anterior/novo para mudanças |
| **event_time** | TIMESTAMP | Timestamp exato do evento |
| **event_date** | DATE | Data do evento (coluna **particionada**) |

---

## Regra Crítica: Sempre Filtrar por event_date

```
✅ WHERE event_date >= CURRENT_DATE() - 30   → filtra partição, rápido
❌ WHERE event_time >= CURRENT_TIMESTAMP() - INTERVAL 30 DAY  → full scan, timeout
```

---

## Categorias de Eventos Auditáveis

| Categoria | action_type | Frequência Recomendada |
|-----------|-------------|----------------------|
| **Acessos a tabelas sensíveis** | SELECT, READ | Diária |
| **Tentativas negadas** | DENIED_PERMISSION, FAILED_AUTHENTICATION | Diária |
| **Modificações de dados** | MODIFY, INSERT, DELETE | Semanal |
| **Mudanças de permissões** | GRANT, REVOKE | Mensal |
| **Atividade incomum** | Qualquer (threshold alto) | Diária |

---

## Frequência de Auditoria

| Tipo | Frequência | Ação |
|------|-----------|------|
| **Acesso a dados PII** | Diária | Alerta automático em acesso anômalo |
| **GRANT/REVOKE** | Semanal | Revisar permissões concedidas |
| **DML em Gold** | Semanal | Revisar modificações em dados produção |
| **Auditoria completa** | Mensal | Relatório de compliance |
| **Quarterly review** | Trimestral | Revogar acessos desnecessários |

---

## Template de Relatório Trimestral

```
QUARTERLY DATA ACCESS REPORT — [QUARTER] [YEAR]

SCOPE:
  Catalog: gold_catalog
  Tables: fact_vendas, dim_cliente, fact_financeiro
  Period: [start_date] to [end_date]

KEY METRICS:
  - Total access events: [N]
  - Unique users accessing PII: [N]
  - GRANT operations: [N]
  - DENIED_PERMISSION events: [N]
  - DML modifications in Gold: [N]

ANOMALIES DETECTED:
  - [List any users with unusual access patterns]

ACTIONS TAKEN:
  - [List any permissions revoked or investigations]

NEXT REVIEW: [DATE]
```
