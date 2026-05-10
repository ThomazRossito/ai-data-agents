# Cross-Platform Fabric ↔ Databricks — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** Estratégias de integração, decisão de abordagem

---

## 3 Estratégias de Integração

| Estratégia | Custo | Latência | Complexidade | Quando usar |
|-----------|-------|----------|--------------|------------|
| **1. ABFSS Compartilhado** | Mínimo | Baixa | Baixa | Mesma conta storage (recomendado) |
| **2. OneLake Shortcuts** | Mínimo | Muito baixa | Média | Leitura zero-copy Fabric → Databricks |
| **3. Export/Upload API** | Médio | Alta | Alta | Storage accounts separados |

---

## Mapeamento de Tipos

| Databricks (Delta Lake) | Fabric (OneLake) | Comportamento |
|-------------------------|-----------------|---------------|
| INT / BIGINT | int32 / int64 | 1:1 |
| DECIMAL(p,s) | decimal(p,s) | 1:1 com precisão |
| STRING | string | UTF-8 válido |
| DATE | date | 1:1 |
| TIMESTAMP | timestamp | Timezone: UTC recomendado |
| ARRAY<T> | array<T> | Suportado em Parquet |
| STRUCT<...> | object | Flattening necessário |
| MAP | ❌ | Converter para ARRAY de KV pairs |

---

## Limitações por Estratégia

| Estratégia | Limitação |
|-----------|-----------|
| **ABFSS Compartilhado** | Requer mesma conta Azure Storage |
| **OneLake Shortcuts** | Leitura apenas (não escrita) |
| **Export/Upload** | Latência alta, overhead de movimentação |
