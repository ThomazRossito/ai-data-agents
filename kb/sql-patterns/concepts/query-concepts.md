# Query Optimization — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** CTE, predicate pushdown, EXPLAIN, partition pruning, semi-joins, aggregate pushdown

---

## Estratégias de Otimização

| Técnica | Benefício | Quando usar |
|---------|-----------|-------------|
| **Predicate Pushdown** | Reduz dados antes de join | Sempre — filtrar antes do JOIN |
| **CTE** | Legibilidade + reutilização | Queries complexas (3+ CTEs) |
| **Semi-join (EXISTS/IN)** | Evita duplicatas sem DISTINCT | Teste de existência |
| **Aggregate Pushdown** | Reduz tamanho do join | Agregar antes de fazer JOIN |
| **CLUSTER BY** | Data skipping automático | Tabelas frequentemente filtradas |
| **TABLESAMPLE** | Exploração rápida | Inspecionar dados sem full scan |

---

## SELECT * : Proibido em Produção

**Problema:** SELECT * em tabela com 50 colunas quando você usa 5 = 10x mais I/O, rede e memória.

**Regra:** Listar explicitamente apenas as colunas necessárias.

---

## EXPLAIN: Leitura do Plano de Execução

| Operação no Plano | Significado |
|-------------------|-------------|
| Scan (partitions=5) | Lê 5 partições (bom paralelismo) |
| BroadcastHashJoin | Broadcast tabela pequena (rápido) |
| SortMergeJoin | Sort-merge join (ambas ordenadas) |
| ShuffleExchange | Shuffle (alto overhead) |

**Use EXPLAIN para:** Confirmar predicate pushdown, identificar SortMergeJoin desnecessário.

---

## Semi-Joins: Quando Usar EXISTS vs JOIN

| Situação | Recomendação | Motivo |
|----------|-------------|--------|
| Teste de existência ("clientes que compraram") | EXISTS / IN | Retorna cada cliente 1x |
| Precisar dados de ambas as tabelas | JOIN | Necessário |
| Múltiplas linhas na tabela B por chave | EXISTS | DISTINCT automático |

---

## CLUSTER BY vs PARTITION BY vs ZORDER

| Aspecto | CLUSTER BY | PARTITION BY | ZORDER BY |
|---------|------------|--------------|-----------|
| Performance Direct Lake | Obrigatório | Fallback | Bom |
| Cardinality | Sem limite | Baixa recomendada | Até 3 colunas |
| Manutenção | Automático | Manual | Manual (OPTIMIZE) |
| Recomendação | Novo padrão | Nunca em Delta | Legado |

---

## TABLESAMPLE: Para Exploração

Retorna percentual amostral da tabela sem full scan.

**Quando usar:**
- Verificar estrutura de tabela desconhecida
- Testar query em dados reais antes de full run
- Estatísticas aproximadas

---

## ANALYZE TABLE: Coletar Estatísticas

Permite ao Catalyst planner tomar melhores decisões de join strategy.

**Output inclui:** Num Files, Num Rows, Total Size.
**Quando executar:** Após cargas grandes ou na primeira vez em tabela nova.
