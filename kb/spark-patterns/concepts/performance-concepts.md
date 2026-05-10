# Performance Spark — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** DataFrame vs RDD, UDF vs Native, broadcast, partições, AQE, anti-patterns

---

## DataFrame API vs RDD API

| API | Performance | Otimização | Recomendação |
|-----|-------------|------------|--------------|
| **DataFrame** | 5-100x mais rápido | Catalyst optimizer automático | Sempre usar |
| **RDD** | Lento | Sem otimização de Catalyst | Apenas casos extremos |

---

## UDF vs Native Functions

| Tipo | Performance | Motivo |
|------|-------------|--------|
| **Native** (pyspark.sql.functions) | 50-100x mais rápido | Execução em Spark/JVM |
| **Python UDF** | Lento | Serialização Python ↔ JVM |

**Regra:** Usar funções nativas sempre. UDF apenas quando a operação não existe nativamente.

---

## Partições: repartition vs coalesce

| Operação | Shuffle | Quando usar |
|----------|---------|-------------|
| `repartition(N)` | Sim (I/O alto) | Aumentar paralelismo antes de transformações complexas |
| `coalesce(N)` | Não | Reduzir partições antes de escrever (mais eficiente) |

---

## broadcast(): Otimizar Joins

| Situação | Ação |
|----------|------|
| Tabela < 100MB (tabela de referência) | broadcast() a tabela pequena |
| Tabela > 100MB | Não forçar broadcast (risco OOM) |

**Benefício:** Evita shuffle de tabela grande — envia tabela pequena para cada worker.

---

## cache() vs persist()

| Operação | Storage | Quando usar |
|----------|---------|-------------|
| `cache()` | MEMORY_AND_DISK | DataFrame usado 2+ vezes |
| `persist(DISK_ONLY)` | Disco | Dados > 30GB (evitar memory pressure) |
| `persist(MEMORY_ONLY)` | Memória | Apenas se garantido que cabe |
| `unpersist()` | — | Liberar cache após uso |

---

## Adaptive Query Execution (AQE)

Ativo por default no Databricks 7.3+. Benefícios automáticos:
- Ajusta shuffle partitions baseado em dados reais
- Converte join strategy se tabela menor que threshold
- Coalesce partições vazias

**Não requer código.**

---

## Shuffle Partitions: Guideline

| Tamanho de Dados | Partições Recomendadas |
|-----------------|------------------------|
| < 1GB | 4-8 |
| 1-10GB | 16-32 |
| 10-100GB | 64-128 |
| 100-1000GB | 256-512 |
| > 1000GB | 512-2048 |

Default Databricks: 200.

---

## Anti-Patterns

| Anti-Pattern | Problema | Solução |
|-------------|---------|---------|
| `SELECT *` | Lê colunas desnecessárias | Selecionar apenas colunas necessárias |
| Múltiplos passes sem cache | Relê arquivo N vezes | cache() + uma pass com múltiplas agregações |
| Nested loops em DataFrames | O(n²) | repartitionBy + write.partitionBy |
| `collect()` em DataFrame grande | OOM no driver | mapInPandas, foreachBatch |
| UDF em coluna calculada | Lento (Python overhead) | Native function |
