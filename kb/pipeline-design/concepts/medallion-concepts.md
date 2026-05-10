# Medallion Architecture — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** Bronze/Silver/Gold regras, tabela comparativa, checklist

---

## Bronze: Ingestão Raw

**Objetivo:** Capturar dados exatamente como chegam da fonte.

| Regra | Descrição |
|-------|-----------|
| **NUNCA transforme** | Sem conversão de tipo, limpeza ou deduplicação |
| **Auto Loader obrigatório** | Use `read_files()` com `cloud_files` / `cloudFiles` |
| **Schema inference com rescue** | `cloudFiles.schemaInferenceMode: 'addNewColumns'` |
| **Apenas STREAMING TABLE** | Nunca MATERIALIZED VIEW na Bronze |
| **Minimal metadata** | Sempre adicione `_ingested_at`, `_file_path` |

---

## Silver: Limpeza e Tipagem

**Objetivo:** Dados consistentes, validados e de qualidade.

| Regra | Descrição |
|-------|-----------|
| **OBRIGATÓRIO STREAMING TABLE** | Nunca MATERIALIZED VIEW na Silver |
| **Sempre use AUTO CDC** | Para histórico de mudanças, nunca LAG/LEAD/ROW_NUMBER |
| **expect_or_drop obrigatório** | Remove registros inválidos, não falha pipeline |
| **Tipagem forte** | DECIMAL(p,s) para valores, DATE validado |
| **Deduplicação** | Via chave natural em AUTO CDC |

---

## Gold: Agregações e Star Schema

**Objetivo:** Dados prontos para análise e BI.

| Regra | Descrição |
|-------|-----------|
| **MATERIALIZED VIEW obrigatória** | Nunca STREAMING TABLE no Gold |
| **CLUSTER BY (nunca PARTITION BY)** | Liquid Clustering automático |
| **expect_or_fail crítico** | Bloqueia pipeline se dados inválidos |
| **Star Schema rigoroso** | dim_* independentes, fact_* com INNER JOINs |
| **Surrogate keys BIGINT** | ROW_NUMBER() para chaves primárias |

---

## Tabela Comparativa: O que é Permitido por Camada

| Operação | Bronze | Silver | Gold |
|----------|--------|--------|------|
| **Ingestão raw** | ✓ OBRIGATÓRIO | ✗ | ✗ |
| **Auto Loader** | ✓ OBRIGATÓRIO | ✗ | ✗ |
| **STREAMING TABLE** | ✓ OBRIGATÓRIO | ✓ OBRIGATÓRIO | ✗ |
| **MATERIALIZED VIEW** | ✗ | ✗ | ✓ OBRIGATÓRIO |
| **AUTO CDC** | ✗ | ✓ RECOMENDADO | ✗ |
| **expect_or_drop** | ✗ | ✓ OBRIGATÓRIO | ✓ SIM |
| **expect_or_fail** | ✗ | ✗ | ✓ OBRIGATÓRIO |
| **Tipagem forte** | ✗ (aceita strings) | ✓ OBRIGATÓRIO | ✓ OBRIGATÓRIO |
| **Agregações** | ✗ | ✗ | ✓ OBRIGATÓRIO |
| **CLUSTER BY** | ✓ SIM | ✓ SIM | ✓ OBRIGATÓRIO |
| **PARTITION BY** | ✗ | ✗ | ✗ (use CLUSTER BY) |

---

## Checklist de Implementação

- [ ] Bronze usa `read_files()` com `cloudFiles` options
- [ ] Bronze schema inference com `_rescued_data` ativado
- [ ] Bronze nunca transforma dados
- [ ] Silver usa STREAMING TABLE (não MATERIALIZED VIEW)
- [ ] Silver implementa AUTO CDC para histórico
- [ ] Silver usa `@expect_or_drop` para validação
- [ ] Gold usa MATERIALIZED VIEW (não STREAMING TABLE)
- [ ] Gold tem `dim_data` gerada via SEQUENCE + EXPLODE
- [ ] Gold fact_* faz INNER JOIN com todas as dimensões
- [ ] Gold usa CLUSTER BY em todas as tabelas
- [ ] Surrogate keys em dim_* são BIGINT com ROW_NUMBER()
