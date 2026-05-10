# Data Profiling — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** DAMA, dimensões de qualidade, quando executar profiling

---

## 6 Dimensões DAMA de Qualidade

| Dimensão | Definição | Métrica | Threshold |
|----------|-----------|---------|-----------|
| **Completude** | % de valores não-nulos em colunas obrigatórias | (COUNT NOT NULL / COUNT) × 100 | ≥ 95% |
| **Unicidade** | Ausência de duplicatas em PKs/chaves naturais | COUNT DISTINCT / COUNT | 100% |
| **Validade** | Conformidade com domínios esperados | CASE WHEN valor IN (...) | ≥ 98% |
| **Consistência** | Coerência entre tabelas relacionadas (FK) | COUNT sem par em dim | 100% |
| **Pontualidade** | Dados chegam dentro do SLA | MAX(data_carga) >= NOW - SLA_hours | Caso a caso |
| **Acurácia** | Conformidade com sistema de origem | Amostra vs Sistema Source | ≥ 99% |

---

## Quando Executar Profiling

| Cenário | Frequência |
|---------|-----------|
| **Novo datasource** | 1x ao ingerir pela primeira vez |
| **Schema change** | Imediatamente após alteração |
| **Volume increase** | Se volume cresce > 20% |
| **Refresh Regular** | Semanalmente em produção (Gold layer) |
| **Investigação de anomalia** | Ad hoc quando qualidade cai |

---

## Schema de Resultados de Profiling

```
catalog.quality.profiling_results
  ├── profiling_id    STRING
  ├── table_name      STRING
  ├── column_name     STRING
  ├── profiling_date  DATE
  ├── null_count      BIGINT
  ├── null_percent    DOUBLE
  ├── unique_count    BIGINT
  ├── duplicate_count BIGINT
  ├── min_value       STRING
  ├── max_value       STRING
  ├── avg_value       DOUBLE
  ├── stddev_value    DOUBLE
  ├── cardinality     BIGINT
  ├── quality_score   DOUBLE
  ├── status          STRING  -- OK, WARNING, ERROR
  └── notes           STRING
```

---

## Score de Qualidade

| Score | Grade | Significado |
|-------|-------|-------------|
| ≥ 0.95 | EXCELLENT | Dentro de todos os thresholds |
| ≥ 0.85 | GOOD | Pequenas anomalias (warning) |
| ≥ 0.75 | FAIR | Problemas moderados |
| < 0.75 | POOR | Requer ação imediata |

---

## Checklist de Implementação

- [ ] Tabela `catalog.quality.profiling_results` criada
- [ ] Profiling executado para novas sources
- [ ] Queries de 6 dimensões (completude, unicidade, validade, consistência, pontualidade, distribuição) testadas
- [ ] Resultados armazenados em metadados
- [ ] Thresholds de qualidade definidos por tabela
- [ ] Dashboard de qualidade criado
- [ ] Alertas configurados para WARNING/ERROR
- [ ] Profiling regular agendado (semanal para Gold)
- [ ] Documentação de anomalias em sistema de tickets
- [ ] Runbooks de remediação escritos
