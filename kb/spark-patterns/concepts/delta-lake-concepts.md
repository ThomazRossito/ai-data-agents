# Delta Lake Operations — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** MERGE, OPTIMIZE, VACUUM, Time Travel, CLUSTER BY vs ZORDER, CDF, Deletion Vectors

---

## Operações Principais

| Operação | Propósito | Quando usar |
|----------|-----------|-------------|
| **MERGE INTO** | Upsert (inserir ou atualizar) | Sincronizar dados, SCD2 |
| **OPTIMIZE** | Compactar arquivos pequenos | Diariamente em tabelas frequentemente escritas |
| **VACUUM** | Limpar arquivos antigos | Após OPTIMIZE, manter storage limpo |
| **Time Travel** | Acessar versões anteriores | Debugging, rollback, auditoria |
| **CDF (Change Data Feed)** | Consumir mudanças incrementais | Replicação, CDC downstream |
| **Deletion Vectors** | Soft delete eficiente | Deletions frequentes |

---

## VACUUM: Regras de Retenção

| Retenção | Time Travel | Uso |
|----------|-------------|-----|
| 0 hours | Não | NUNCA em produção — irreversível |
| 24 hours | 1 dia | Cuidado: pouco histórico |
| 168 hours | 7 dias | Recomendado (default) |
| 720 hours | 30 dias | Para dados críticos |

**Regra:** VACUUM com RETAIN < 168 hours requer delta.retentionDurationCheck.enabled=false.

---

## CLUSTER BY vs ZORDER

| Aspecto | CLUSTER BY | ZORDER BY |
|---------|------------|-----------|
| Performance | Melhor (nativo) | Bom (legado) |
| Cardinality | Sem limite | Até 3 colunas |
| Auto-clustering | Sim (background) | Manual (OPTIMIZE) |
| Recomendação | Novo padrão | Legado |

**Regra:** Usar CLUSTER BY em novas tabelas. ZORDER apenas em tabelas legadas.

---

## Schema Evolution

| Opção | Comportamento | Quando usar |
|-------|--------------|-------------|
| `mergeSchema=true` | Aceita novas colunas | Leitura com schema mismatch |
| `overwriteSchema=true` | Substitui schema inteiro | Deletar coluna legada |

---

## Change Data Feed (CDF): Tipos de Change

| Tipo | Significado |
|------|-------------|
| `insert` | Nova linha inserida |
| `update_preimage` | Valores antes do UPDATE |
| `update_postimage` | Valores depois do UPDATE |
| `delete` | Linha deletada |

---

## Deletion Vectors (Delta 2.0+)

Soft delete: marcações de deleção sem reescrever arquivos. Habilitar via TBLPROPERTIES.

**Vantagem:** Deletions não reescrevem arquivos (menor overhead de I/O).
