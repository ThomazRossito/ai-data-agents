# Drift Detection — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** Drift, schema change, distribuição de dados
**Plataformas:** Databricks, Azure Fabric

---

## Tipos de Drift

### Schema Drift
**Definição:** Mudanças estruturais no schema (colunas adicionadas, removidas, tipos alterados).

| Tipo | Exemplo | Detecção |
|------|---------|----------|
| **Column Addition** | Nova coluna `promo_code` aparece | Schema comparison diff |
| **Column Removal** | Coluna `legacy_id` desaparece | Schema comparison diff |
| **Type Change** | `valor` STRING → DECIMAL | Type mismatch error |
| **Nullable Change** | `id_cliente` NOT NULL → nullable | Type mismatch error |

### Data Drift
**Definição:** Mudanças estatísticas em dados válidos (distribuição muda, valores anômalos aumentam).

| Tipo | Exemplo | Detecção |
|------|---------|----------|
| **Distribution Shift** | Média de `valor_total` sobe 40% | Percentile comparison |
| **New Values** | Categoria `BLOQUEADO` nunca vista antes | Cardinality check |
| **Null Increase** | Nulls em `email` sobem de 1% para 8% | Null % threshold |
| **Outlier Spike** | Min/max de `valor_total` expandem | Min/max comparison |

---

## Thresholds de Data Drift

| Métrica | Threshold | Ação |
|---------|-----------|------|
| **Média (Avg)** | > 20% de mudança | Alert + investigate |
| **Desvio padrão** | > 30% de mudança | Check outliers |
| **Nulls** | > 5% de mudança | Check validação Silver |
| **Min/Max** | Novos extremos | Check novo range |
| **Cardinality** | > 50% de mudança | Check novo valor |
| **Volume diário** | > 30% de mudança | Check fonte |

---

## Protocolo de Resposta

### Etapas

| Etapa | Ação |
|-------|------|
| **1. Alerta Dispara** | SQL Alert Task detecta mudança → notificação Teams/Email |
| **2. Investigação** | Confirmar drift, identificar lineage, perfil hora-a-hora |
| **3. Fix** | Depende do tipo (ver tabela abaixo) |
| **4. Validação + Fechamento** | Confirmar drift normalizado, atualizar log |

### Ações por Tipo de Drift

| Tipo de Drift | Ação |
|---------------|------|
| **Schema Addition** | Aceitar (mergeSchema=true) ou bloquear (review owner) |
| **Schema Deletion** | Rejeitar pipeline, notificar source owner |
| **Type Change** | Manual fix em Bronze ou Silver expectations |
| **Distribution Shift** | Atualizar expectations/thresholds ou investigar fonte |
| **Null Increase** | Revis validação em Bronze, adjust expect_or_drop |
| **Outlier** | Investigar evento raro ou erro de entrada |

---

## SDP Auto-Evolution para Schema Drift

**Comportamento com `mergeSchema=true`:** Novas colunas são adicionadas automaticamente em tabelas Bronze, sem falha de pipeline.

**Quando bloquear:** Se a mudança de schema não é esperada, desabilitar auto-evolution e notificar source owner.

---

## Checklist de Drift Detection

- [ ] SDP com `mergeSchema=true` configurado na Bronze
- [ ] Tabela `catalog.quality.schema_history` criada
- [ ] Comparação de schema automática agendada (diária)
- [ ] Tabela `catalog.quality.drift_log` criada e monitorada
- [ ] Thresholds de data drift definidos (20% avg, 30% volume, etc)
- [ ] SQL Alert Tasks para schema e data drift configuradas
- [ ] Runbook de investigação documentado
- [ ] Escalação para source owner definida
- [ ] Validação de resolução de drift implementada
- [ ] Dashboard de drift aberto/resolvido criado
