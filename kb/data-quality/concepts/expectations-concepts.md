# Expectations — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** Validação de dados, SDP expectations, camadas Medallion

---

## Três Níveis de Expectativas

| Nível | Comportamento | Uso | Exemplo |
|-------|---------------|-----|---------|
| **@dp.expect** | Alerta apenas, continua pipeline | Bronze, alertas | `@expect(condition = "col IS NOT NULL")` |
| **@dp.expect_or_drop** | Remove registros inválidos | Silver, limpeza | `@expect_or_drop(condition = "valor > 0")` |
| **@dp.expect_or_fail** | Bloqueia pipeline se falhar | Gold, crítico | `@expect_or_fail(condition = "COUNT(*) > 1000")` |

---

## Estratégia por Camada

| Camada | Nível | Comportamento |
|--------|-------|---------------|
| **Bronze** | `@dp.expect` | Alerta apenas — não rejeita dados brutos |
| **Silver** | `@dp.expect_or_drop` | Remove registros inválidos — pipeline continua |
| **Gold** | `@dp.expect_or_fail` | Bloqueia se condição crítica falha |

---

## SQL Alert Tasks: Conceito

SQL Alert Tasks são tasks nativas em Databricks Jobs que executam condições SQL **dentro do DAG**. Se a condição falha, o job para antes de executar tasks downstream.

**Diferença das Expectations:**
- Expectations validam **dentro do pipeline** (Bronze/Silver/Gold)
- SQL Alert Tasks validam **no orquestrador** (entre tasks do Job)

---

## Padrão Recomendado: Dupla Camada

Combine SQL Alert Tasks (Jobs DAG) + `@dp.expect_or_fail` (Pipeline) para máxima proteção:

```
Camada 1: SQL Alert Task (valida Silver antes de iniciar Gold)
    ↓ Se passa
Camada 2: Pipeline Gold com @dp.expect_or_fail
    ↓ Se passa
Downstream tasks (notify, export, etc)
```

**Benefício:** Falha rápida em dados ruins antes de gastar créditos com pipeline.

---

## Naming Convention para Expectations

```
Padrão: [TABLE]_[DIMENSION]_[RULE]

Exemplos:
  silver_cliente_id_not_null
  gold_fact_valor_positive
  silver_cliente_email_format
```

---

## Checklist de Implementação

- [ ] Bronze tem @dp.expect (alerta apenas)
- [ ] Silver tem @dp.expect_or_drop em TODAS as validações
- [ ] Gold tem @dp.expect_or_fail em métricas críticas
- [ ] SQL Alerts criados no Databricks SQL Editor
- [ ] SQL Alert Tasks configuradas no DABs
- [ ] Dupla camada de validação implementada (Job + Pipeline)
- [ ] Nomes de expectations seguem padrão [TABLE]_[DIMENSION]_[RULE]
- [ ] Alertas de email configurados (pause_subscriptions em dev)
- [ ] Resultados de expectations logados em metadados
- [ ] Runbooks de remediação documentados
