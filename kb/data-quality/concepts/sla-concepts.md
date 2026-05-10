# SLA Contracts — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** SLA vs Expectation, dimensões de qualidade, escalação

---

## Conceito: SLA vs Expectation

| Aspecto | SLA | Expectation |
|--------|-----|-----------|
| **Escopo** | Contrato formal por tabela | Validação em código |
| **Público** | Data owner, analytics team | Data engineers |
| **Frequência** | Monitorado continuamente | Executado a cada pipeline run |
| **Violação** | Incident, post-mortem | Pipeline falha, refaz |
| **Documento** | Tabela SQL, contrato | Decorator @dp.expect_or_fail |

---

## Dimensões de SLA

| Dimensão | Definição | Exemplo de threshold |
|----------|-----------|---------------------|
| **Freshness** | Horas desde última atualização | MAX(data_carga) >= NOW - 4h |
| **Completeness** | % não-nulo em colunas críticas | ≥ 95% |
| **Availability** | Uptime do pipeline | ≥ 99.5% |
| **Uniqueness** | Sem duplicatas em chave primária | COUNT(*) = COUNT(DISTINCT id) |
| **Validity** | Valores dentro dos domínios | status IN ('ATIVO', 'CANCELADO') |

---

## Esquema de SLA Contracts

```
catalog.quality.sla_contracts
  ├── contract_id           STRING  -- ex: SLA-SLV-VENDAS-001
  ├── table_name            STRING
  ├── data_owner            STRING
  ├── data_owner_email      STRING
  ├── sla_freshness_hours   INT
  ├── sla_completeness_pct  DOUBLE
  ├── sla_availability_pct  DOUBLE
  ├── sla_uniqueness_required BOOLEAN
  ├── sla_unique_keys       STRING
  ├── monitoring_frequency  STRING
  ├── escalation_level_1_minutes INT
  ├── escalation_level_2_minutes INT
  ├── escalation_level_3_minutes INT
  └── active                BOOLEAN
```

---

## Escalação: 3 Níveis

| Nível | Trigger | Response Time | Owner |
|-------|---------|---------------|-------|
| **Level 1** | SLA violado por < 50% | 15 min | On-call data engineer |
| **Level 2** | SLA violado por 50-100% | 5 min | data-eng-lead |
| **Level 3** | SLA violado > 2 horas | Imediato | data-eng-director |

---

## Post-Mortem: Quando e Como

**Quando:** SLA violado > 1 hora OU impacto > 1000 registros

**Timeline:** Dentro de 24 horas após resolução

**Participantes:** data_owner, data engineer, times afetados

**Documentação:** Root cause, prevenção, action items

---

## Checklist de SLA Contracts

- [ ] Template YAML criado e documentado
- [ ] Tabela `catalog.quality.sla_contracts` criada e populada
- [ ] SLAs definidos para todas as Gold tables
- [ ] SLAs definidos para críticas Silver tables
- [ ] Monitoramento horário configurado (SQL Alert Task)
- [ ] Tabela `catalog.quality.sla_violations` criada
- [ ] Dashboard de SLA status criado
- [ ] Escalação automática implementada (3 níveis)
- [ ] Notificações (Teams/PagerDuty/Email) testadas
- [ ] Runbook de remediação documentado
- [ ] Post-mortem process defined e documentado
