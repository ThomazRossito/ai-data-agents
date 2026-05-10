# Star Schema — Canonical Reference (SQL Patterns)

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** 4 regras com padrões correto/errado, SCD2, surrogate keys, CLUSTER BY
**Canonical source:** Este arquivo. Para pipeline design DAG e orquestração, veja kb/pipeline-design/patterns/star-schema-cross-reference.md.

---

## Regra 1: Dimensões (dim_*) Nunca Derivam de Transacionais

| Aspecto | Anti-Pattern | Correto |
|---------|-------------|---------|
| Fonte | `SELECT DISTINCT FROM silver_vendas` | Entidade de referência autônoma |
| Chave | ID natural exposto | Surrogate key BIGINT (ROW_NUMBER) |
| Histórico | Sem rastreamento | SCD2 com data_inicio / data_fim |
| Qualidade | Cópia literal | Com limpeza e transformação |

---

## Regra 2: dim_data via SEQUENCE + EXPLODE (Nunca SELECT DISTINCT)

| Abordagem | Problema | |
|-----------|---------|--|
| `SELECT DISTINCT data_venda FROM silver_vendas` | Lacunas em datas sem vendas (fins de semana) | ERRADO |
| `EXPLODE(SEQUENCE(DATE '2020-01-01', DATE '2030-12-31', INTERVAL 1 DAY))` | Calendário completo | CORRETO |

**Cobertura mínima:** 10 anos para análises históricas.

---

## Regra 3: fact_* Sempre INNER JOIN com Todas as Dimensões

| Tipo de Join | Resultado | |
|-------------|---------|--|
| LEFT JOIN | FK pode ser NULL | ERRADO |
| INNER JOIN | FK nunca NULL, integridade garantida | CORRETO |

**Consequência de LEFT JOIN:** Relatórios com valores NULL em dimensões, queries de BI quebradas.

---

## Regra 4: CLUSTER BY em Tabelas Gold (Nunca PARTITION BY)

| Operação | Em MATERIALIZED VIEW | Em TABLE |
|----------|---------------------|---------|
| PARTITION BY | Não suportado | Funciona, mas fallback em Direct Lake |
| CLUSTER BY | Suportado (Databricks 13.1+) | Recomendado |

---

## Surrogate Keys: Tipos e Uso

| Tipo | Como gerar | Determinístico | Uso |
|------|-----------|---------------|-----|
| ROW_NUMBER() | `ROW_NUMBER() OVER (ORDER BY id_natural)` | Sim | Dimensões estáticas |
| MONOTONICALLY_INCREASING_ID() | PySpark função | Não (muda em re-run) | Streaming incremental |
| Hash + versão | `CONCAT(id, '-', versao)` | Sim | SCD2 multi-versão |

**Regra:** Surrogate keys (sk_*) são sempre BIGINT. Nunca STRING, nunca UUID.

---

## SCD2: Padrão de Histórico

```
Quando dimensão muda (ex: cliente muda de endereço):
1. Fechar registro atual: data_fim = CURRENT_TIMESTAMP(), is_ativo = FALSE
2. Inserir nova versão: data_inicio = CURRENT_TIMESTAMP(), data_fim = NULL, is_ativo = TRUE

Regra: Sempre um único registro com is_ativo = TRUE por chave natural.
```

---

## Estrutura Star Schema Completa

```
silver_cliente (entidade de referência)
     ↓
gold_dim_cliente (sk_cliente PK, nk_cliente, atributos, SCD2)
     ↓
gold_fact_vendas (sk_cliente FK, sk_produto FK, sk_data FK, métricas)
     ↑
gold_dim_produto (sk_produto PK)
     ↑
gold_dim_data (sk_data PK, calendário sintético 2020-2030)
```

---

## Cheat Sheet: O Que Cada Tabela Contém

| Tabela | Contém | NÃO contém |
|--------|--------|-----------|
| fact_* | Foreign keys (ocultas), métricas numéricas | Atributos descritivos, JOINs à esquerda |
| dim_* | Surrogate key (PK), natural key, atributos descritivos | Métricas, somas, contagens |
| dim_data | Calendário completo sintético | Apenas datas com transações |
