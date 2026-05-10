# Delta Lake Operations — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** MERGE INTO, OPTIMIZE, VACUUM, Time Travel, CDF, Deletion Vectors

---

## MERGE INTO: Upsert

```sql
-- Padrão: Inserir ou atualizar
MERGE INTO gold_catalog.sales.fact_vendas AS target
USING staging.vendas_new AS source
  ON target.id_venda = source.id_venda
    AND target.data_venda = source.data_venda
WHEN MATCHED AND target.valor < source.valor THEN
  UPDATE SET
    valor = source.valor,
    desconto = source.desconto,
    updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN
  INSERT (id_venda, data_venda, valor, desconto, created_at)
  VALUES (source.id_venda, source.data_venda, source.valor, source.desconto, CURRENT_TIMESTAMP());
```

### Performance: Filtrar Target Antes de MERGE

```sql
-- Rápido: filtrar por range de datas antes do MERGE
MERGE INTO gold_catalog.sales.fact_vendas AS target
USING staging.vendas_new AS source
  ON target.id_venda = source.id_venda
    AND target.data_venda >= CURRENT_DATE() - 7  -- Filtro de partição
WHEN MATCHED THEN UPDATE SET valor = source.valor
WHEN NOT MATCHED THEN INSERT *;
```

---

## OPTIMIZE + CLUSTER BY

```sql
-- Compactar arquivos e reordenar (moderno)
OPTIMIZE gold_catalog.sales.fact_vendas
CLUSTER BY (data_venda, regiao);

-- Legado: ZORDER (ainda funciona)
OPTIMIZE gold_catalog.sales.fact_vendas
ZORDER BY (data_venda, regiao);
```

---

## VACUUM: Limpeza Segura

```sql
-- Recomendado: 7 dias de retenção
VACUUM gold_catalog.sales.fact_vendas RETAIN 168 HOURS;

-- Criar backup antes de VACUUM agressivo
CREATE TABLE gold_catalog.sales.fact_vendas_backup_2026_04_01 AS
SELECT * FROM gold_catalog.sales.fact_vendas;

VACUUM gold_catalog.sales.fact_vendas RETAIN 168 HOURS;
```

---

## Time Travel

```sql
-- Por versão específica
SELECT * FROM gold_catalog.sales.fact_vendas VERSION AS OF 42;

-- Ver histórico de versões
SELECT * FROM DESCRIBE HISTORY gold_catalog.sales.fact_vendas LIMIT 10;

-- Por timestamp
SELECT * FROM gold_catalog.sales.fact_vendas
TIMESTAMP AS OF '2026-04-09 13:00:00';

-- Dados de 3 dias atrás
SELECT * FROM gold_catalog.sales.fact_vendas
TIMESTAMP AS OF CURRENT_TIMESTAMP() - INTERVAL 3 DAY;

-- Restaurar tabela inteira para versão anterior
RESTORE TABLE gold_catalog.sales.fact_vendas
TO TIMESTAMP AS OF CURRENT_TIMESTAMP() - INTERVAL 7 DAY;
```

---

## CLUSTER BY: Criar Tabela

```sql
CREATE TABLE gold_catalog.sales.fact_vendas (
  id_venda BIGINT,
  data_venda DATE,
  regiao STRING,
  valor DECIMAL(10, 2)
)
USING DELTA
CLUSTER BY (data_venda, regiao);
```

---

## Change Data Feed (CDF)

```sql
-- Habilitar CDF ao criar tabela
CREATE TABLE gold_catalog.sales.fact_vendas (...)
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

-- Habilitar em tabela existente
ALTER TABLE gold_catalog.sales.fact_vendas
SET TBLPROPERTIES (delta.enableChangeDataFeed = 'true');

-- Ler mudanças entre versões
SELECT * FROM table_changes("gold_catalog.sales.fact_vendas", 10, 15);
-- Resultado: _change_type (insert, update_preimage, update_postimage, delete)
```

---

## Deletion Vectors

```sql
-- Ativar Deletion Vectors (Delta 2.0+)
ALTER TABLE gold_catalog.sales.fact_vendas
SET TBLPROPERTIES (delta.enableDeletionVectors = 'true');

-- Delete sem reescrever arquivo inteiro
DELETE FROM gold_catalog.sales.fact_vendas
WHERE data_venda < '2020-01-01';
```

---

## Schema Evolution

```python
# Aceitar novas colunas na leitura
df = spark.read \
    .option("mergeSchema", "true") \
    .parquet("s3://bucket/sales/2026-04-09/")

# Substituir schema inteiro (cuidado — perde colunas antigas)
df.write \
    .option("overwriteSchema", "true") \
    .mode("overwrite") \
    .format("delta") \
    .save("/dbfs/user/hive/warehouse/fact_vendas")
```
