# Compute — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** Tipos de compute, matriz de decisão, custos

---

## Tipos de Compute

| Tipo | Startup | Estado | Linguagens |
|------|---------|--------|------------|
| **Databricks Connect** | Instant (local) | Dentro do Python | Python/PySpark |
| **Serverless SQL Warehouse** | ~5-10s | Nenhum | SQL |
| **Job Clusters** | ~2-5min | Nenhum | Python/SQL/Scala |
| **Interactive Clusters** | ~5-8min | Mantém entre chamadas | Python/Scala/SQL/R |
| **Serverless Compute** | ~25-50s | Nenhum | Python/SQL |

---

## Matriz de Decisão

| Critério | Databricks Connect | Serverless SQL | Job Clusters | Interactive | Serverless Compute |
|----------|-------------------|----------------|--------------|-------------|-------------------|
| **Tipo de código** | PySpark ETL | SQL queries | Multi-task DAG | Exploração ad-hoc | Python/SQL batch |
| **Custo** | Gratuito (local) | Por query | DBU compartilhado | DBU + overhead | DBU serverless |
| **Quando usar** | ETL rápido, testes | Dashboard, queries | Pipelines 24/7 | Notebooks exploração | Heavy ML/batch |

---

## Fluxo de Decisão

```
PySpark + dados < 1GB?           → Databricks Connect
SQL puro (dashboard/report)?     → Serverless SQL Warehouse
Multi-task com dependências?     → Job Clusters
ML pesado (> 1h execução)?       → Serverless Compute
Exploração/iteração com state?   → Interactive Cluster
```

---

## Regras Críticas

| Regra | Motivo |
|-------|--------|
| **Databricks Connect requer Python 3.12** | `databricks-connect >= 16.4` não funciona com versões anteriores |
| **Nunca inicie cluster sem perguntar** | Startup é ~5-8 minutos, custo imediato |
| **Serverless não mantém state** | Dados devem passar por Volume ou Delta table entre tasks |
| **Interactive: sempre `autotermination_minutes`** | Sem isso, cluster roda 24/7 |
| **Serverless SQL não é compute** | É gateway SQL — não execute PySpark direto |

---

## Custo Estimado

| Tipo | Custo/Hora | Melhor Para |
|------|-----------|------------|
| Databricks Connect | Gratuito (local) | Testes, dev |
| Serverless SQL | ~$2-5/query | Queries BI |
| Job Cluster 2 workers | ~$1-2 (DBU) | Pipelines |
| Interactive 2 workers | ~$1-2 (DBU) + overhead | Exploração |
| Serverless Compute | ~$2-4 (DBU serverless) | ML heavy |

---

## Checklist de Implementação

- [ ] Databricks Connect instalado com Python 3.12
- [ ] Serverless SQL Warehouse criado para queries BI
- [ ] Job Clusters definidos em DAB para pipelines
- [ ] Auto-termination = 15-20 min em Interactive Clusters
- [ ] Nenhum cluster inicia sem confirmação do usuário
- [ ] Spark Config validado (speculation, dynamicAllocation, etc.)
