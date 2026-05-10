# Star Schema — Cross-Reference (Pipeline Design)

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** DAG de dependências do pipeline, validações de integridade referencial

> **Canonical Source:** As regras completas de Star Schema (dimensões, fatos, SCD2, surrogate keys, CLUSTER BY)
> estão em `kb/sql-patterns/concepts/star-schema-source-of-truth.md`.
> Este arquivo contém apenas conteúdo específico de pipeline design (DAG de dependências e validações).

---

## DAG de Dependências Gold

```
silver_cliente
     ↓
gold_dim_cliente ──┐
                   ├→ gold_fact_vendas ← gold_dim_data
silver_produto     ├→ gold_fact_vendas_diarias
     ↓             │
gold_dim_produto ──┘

silver_vendas ─────→ gold_fact_vendas
                    gold_fact_vendas_diarias
```

**Princípio:** Nunca `dim_*` depende diretamente de `silver_*_transacional`. Sempre uma entidade de referência autônoma.

---

## Validações de Integridade Referencial

### Pré-Gold (checar antes de construir fatos)

```sql
-- Verificar integridade referencial Silver → Silver antes do join
SELECT COUNT(*)
FROM silver_vendas v
LEFT JOIN silver_cliente c ON v.id_cliente = c.id_cliente
WHERE c.id_cliente IS NULL;  -- Deve ser 0

SELECT COUNT(DISTINCT id_cliente)
FROM silver_cliente
WHERE id_cliente IS NULL;  -- Deve ser 0
```

### Pós-Gold (validar saída)

```sql
-- Validar que INNER JOINs não perderam dados
SELECT COUNT(*) FROM gold_fact_vendas;  -- Comparar com silver_vendas COUNT

-- Verificar nenhuma FK é NULL
SELECT COUNT(*) FROM gold_fact_vendas WHERE dim_cliente_key IS NULL;  -- Deve ser 0
SELECT COUNT(*) FROM gold_fact_vendas WHERE dim_data_key IS NULL;     -- Deve ser 0

-- Dim_data cobertura
SELECT MIN(data), MAX(data) FROM gold_dim_data;  -- 2020-01-01 ... 2030-12-31
```

---

## Orquestração do Gold (DABs)

```yaml
# resources/jobs.yml — ordem de execução Gold
resources:
  jobs:
    gold_build:
      tasks:
        # 1. Dimensões independentes (paralelo)
        - task_key: build_dim_cliente
          pipeline_task:
            pipeline_id: ${resources.pipelines.dim_cliente.id}

        - task_key: build_dim_produto
          pipeline_task:
            pipeline_id: ${resources.pipelines.dim_produto.id}

        - task_key: build_dim_data
          pipeline_task:
            pipeline_id: ${resources.pipelines.dim_data.id}

        # 2. Fatos (dependem de todas as dimensões)
        - task_key: build_fact_vendas
          depends_on:
            - task_key: build_dim_cliente
            - task_key: build_dim_produto
            - task_key: build_dim_data
          run_if: "ALL_SUCCESS"
          notebook_task:
            notebook_path: ../src/gold_fact_vendas

        # 3. Validação final
        - task_key: validate_gold
          depends_on:
            - task_key: build_fact_vendas
          run_if: "ALL_SUCCESS"
          sql_task:
            warehouse_id: "abc123"
            sql_file: "../queries/validate_gold_integrity.sql"
```
