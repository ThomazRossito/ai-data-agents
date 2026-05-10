# SDP LakeFlow — Regras e Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** 7 regras SDP obrigatórias, decisão STREAMING TABLE vs MATERIALIZED VIEW, camadas medallion

---

## 7 Regras SDP Obrigatórias

| Regra | Descrição |
|-------|-----------|
| **R1: API Moderna** | Usar `pyspark.pipelines` (SDP), nunca `import dlt` (legado) |
| **R2: CREATE OR REFRESH** | Nunca CREATE OR REPLACE (perde Time Travel) |
| **R3: Camadas Medallion** | Bronze/Silver = STREAMING TABLE; Gold = MATERIALIZED VIEW |
| **R4: AUTO CDC** | Para SCD2, sempre AUTO CDC — nunca LAG/LEAD/ROW_NUMBER manual |
| **R5: Expectations** | Usar expect_or_drop na Silver; expect_or_fail na Gold |
| **R6: Multi-Schema** | Um pipeline, múltiplos schemas (bronze_*, silver_*, gold_*) |
| **R7: Sem Notebooks** | Código SDP em repositório Git, não em Notebooks |

---

## STREAMING TABLE vs MATERIALIZED VIEW: Por Camada

| Camada | Tipo | Motivo |
|--------|------|--------|
| **Bronze** | STREAMING TABLE obrigatória | Ingestão incremental, append-only |
| **Silver** | STREAMING TABLE obrigatória | stream() para CDC incremental |
| **Gold** | MATERIALIZED VIEW obrigatória | Agregações finais, schema definido para BI |

---

## DDL: CREATE OR REFRESH vs CREATE OR REPLACE

| Operação | Comportamento | Efeito |
|----------|--------------|--------|
| CREATE (novo) | Cria se não existe | Cria nova tabela |
| CREATE EXISTS | Erro se já existe | Não idempotente |
| CREATE OR REFRESH | Cria ou atualiza (idempotente) | Usa SDP semantics — CORRETO |
| CREATE OR REPLACE | Deleta e recria | Perde histórico Delta Time Travel — ERRADO |

---

## AUTO CDC: Por Que Nunca Manual?

| Abordagem | Problema |
|-----------|---------|
| LAG/LEAD manual | Propenso a off-by-one, null handling incorreto |
| ROW_NUMBER manual | Não detecta deletions corretamente |
| AUTO CDC | Databricks garante ordem com `__START_AT` e `__END_AT` |

AUTO CDC usa double underscore: `__START_AT`, `__END_AT`.

---

## Expectations: Comportamento por Tipo

| Tipo | Comportamento | Camada |
|------|--------------|--------|
| `@expect` | Apenas alerta — linha não é removida | Silver |
| `@expect_or_drop` | Remove linha inválida — pipeline continua | Silver obrigatório |
| `@expect_or_fail` | Falha o pipeline inteiro | Gold obrigatório |

---

## Multi-Schema vs Múltiplos Pipelines

| Abordagem | Vantagem |
|-----------|---------|
| **Um pipeline, múltiplos schemas** | Lineage clara, DAG único, observabilidade unificada |
| **Múltiplos pipelines** | Só se regimes de execução forem muito diferentes |

---

## SDP vs DLT (Legado)

| Aspecto | SDP (pyspark.pipelines) | DLT (import dlt) |
|---------|------------------------|-------------------|
| Status | Atual (2024+) | Descontinuado |
| Performance | Melhor | Menor |
| UI | Melhor | Legacy |
| Observabilidade | Melhor | Limited |
