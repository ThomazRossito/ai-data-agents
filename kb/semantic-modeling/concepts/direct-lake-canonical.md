# Direct Lake — Canonical Reference

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** Direct Lake modo de conexão, V-Order, regras de schema, fallback, limites de cardinalidade
**Canonical source:** Este arquivo. Para Fabric-specific content, veja kb/fabric/concepts/direct-lake-cross-reference.md.

---

## O Que é Direct Lake?

```
Power BI (Report Layer) → Direct Lake → Fabric Lakehouse (Gold Tables)
```

Direct Lake é modo de conexão sem importação de dados. Versus Import Mode:

| Propriedade | Direct Lake | Import Mode |
|-------------|-------------|-------------|
| **Latência** | Real-time (< 1s) | Alta (precisa refresh) |
| **Armazenamento** | Zero no Power BI | Cópia em memória |
| **Transformação** | Spark SQL transparente | No modelo BI |
| **Custo** | Pay-as-you-go (queries) | Sem custo de query |

**Fallback:** Direct Lake → Import Mode automaticamente se falhar validação.

---

## Regra 1: V-Order Obrigatório em Gold

V-Order é formato de armazenamento otimizado para Parquet. Impacto:

| Sem V-Order | Com V-Order |
|-------------|-------------|
| Direct Lake: LENTO | Direct Lake: RÁPIDO (10-100x) |
| Data skipping: limitado | Data skipping: automático |

---

## Regra 2: CLUSTER BY, Nunca PARTITION BY

**PARTITION BY causa fallback automático para Import Mode.**

| Operação | Resultado | Razão |
|----------|-----------|-------|
| `PARTITION BY` | Fallback → Import | Incompatível com Direct Lake |
| `CLUSTER BY` | Direct Lake OK | Otimiza I/O sem transações |
| Sem clustering | Direct Lake OK | Menos performance |

---

## Regra 3: Tipos de Coluna (Schema Rules)

| Tipo | Direct Lake | Nota |
|------|------------|------|
| DATE | Obrigatório para datas | Não TIMESTAMP |
| BIGINT | Surrogate keys | Não INT (risco overflow) |
| DECIMAL(p,s) | OK para moeda | |
| STRING | OK, cuidado com alta cardinalidade | |
| ARRAY\<T\> | Limitado | Usar com cuidado |
| BINARY | Rejeitado | Converter |
| MAP\<K,V\> | Rejeitado | ARRAY de KV pairs |
| TIMESTAMP_NTZ | Rejeitado | Usar DATE + TIME |

---

## Regra 4: Limites de Cardinalidade

| Métrica | Limite | Ação se Excedido |
|---------|--------|-----------------|
| Colunas por tabela | 500 | Erro na conexão |
| Linhas (fact table) | 2B+ | Fallback se > 2B lento |
| Dimensões únicas | 100M | Fallback se cardinality alta |
| Valores distintos/coluna | 1M+ | OK, mas filtro BI pode ser lento |

---

## Regra 5: Star Schema Obrigatório

Direct Lake exige star schema bem definido:
- Many-to-One relationships apenas (Fact → Dimensions)
- Surrogate keys BIGINT como PKs nas dimensões
- FKs explícitas na tabela fato

---

## Fallback Triggers

| Trigger | Fix |
|---------|-----|
| V-Order ausente | Reescrever com V-Order |
| PARTITION BY presente | Remover partições, usar CLUSTER BY |
| Cardinalidade > 2B | Arquivar dados antigos |
| TIMESTAMP em coluna de data | Converter para DATE |
| Coluna BINARY | Remover ou converter |
| Coluna calculada no Power BI | Mover para Gold Layer (Lakehouse) |
| Join Many-to-Many | Criar tabela bridge no Lakehouse |

---

## Decision Tree: Direct Lake vs Import

```
Devo usar Direct Lake?
├─ Dados > 2GB? → Sim
│  └─ Schema é star schema? → Sim
│     └─ V-Order aplicado? → Sim
│        └─ CLUSTER BY (sem PARTITION BY)? → Sim
│           └─ Direct Lake OK ✓
│           └─ Não → Corrigir CLUSTER BY
│        └─ Não → Reescrever com V-Order
│     └─ Não → Redesenhar schema
└─ Real-time não é crítico → Considere Import Mode
```

---

## Colunas Calculadas: Lakehouse, Não Power BI

**Regra:** Colunas calculadas devem ser materializadas na Gold Layer, nunca no Power BI.

- Coluna calculada no Power BI = recalcula a cada query, sem V-Order
- Coluna materializada no Lakehouse = Direct Lake usa V-Order, rápido

---

## TMDL: Criação de Semantic Model

Direct Lake requer definição TMDL (Tabular Model Definition Language) para conexão com Fabric Lakehouse.
O modelo é criado e atualizado via Fabric REST API com padrão LRO (Long-Running Operation).

Para detalhes de implementação de TMDL e API patterns, veja:
- `kb/semantic-modeling/patterns/semantic-model-patterns.md`
- `kb/fabric/concepts/direct-lake-cross-reference.md` (Fabric-specific: V-Order Spark config, LRO polling)

---

## Checklist Direct Lake Ready

- [ ] Tabelas Gold com V-Order habilitado
- [ ] Sem PARTITION BY (use CLUSTER BY)
- [ ] Colunas de data como DATE (não TIMESTAMP)
- [ ] Schema star schema com FK explícitas
- [ ] Cardinalidade testada (SELECT DISTINCT COUNT(*))
- [ ] Sem colunas BINARY ou MAP
- [ ] Colunas calculadas na Gold Layer, não no Power BI
- [ ] Relacionamentos Many-to-One apenas
