# DDL — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** CREATE TABLE, CREATE SCHEMA, ALTER TABLE, VOLUME, TBLPROPERTIES

---

## CREATE TABLE: Managed (Padrão)

```sql
CREATE TABLE gold_catalog.sales.fact_vendas (
  id_venda BIGINT NOT NULL COMMENT 'Chave primária',
  id_cliente BIGINT NOT NULL COMMENT 'FK para dim_cliente',
  data_venda DATE NOT NULL COMMENT 'Data da transação',
  valor DECIMAL(10, 2) NOT NULL COMMENT 'Valor em reais (R$)',
  quantidade INT COMMENT 'Quantidade de itens',
  desconto DECIMAL(4, 2) COMMENT 'Desconto em %',
  status VARCHAR(20) COMMENT 'Enum: ativa|cancelada|pendente',
  criado_em TIMESTAMP NOT NULL COMMENT 'Data de criação',
  atualizado_em TIMESTAMP COMMENT 'Data de atualização'
)
USING DELTA
COMMENT 'Fatos de vendas - Camada Gold'
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'delta.enableDeletionVectors' = 'true'
);
```

---

## CREATE TABLE: External (Storage Externo)

```sql
CREATE TABLE gold_catalog.sales.fact_vendas_external (
  id_venda BIGINT,
  id_cliente BIGINT,
  data_venda DATE
)
USING DELTA
LOCATION 's3://my-bucket/gold/sales/fact_vendas';
-- DROP TABLE não remove dados em s3://
```

---

## CREATE SCHEMA

```sql
CREATE SCHEMA IF NOT EXISTS gold_catalog.sales
COMMENT 'Schemas com agregações finais para análise de vendas'
LOCATION '/user/hive/warehouse/gold_catalog.db/sales';
```

---

## ALTER TABLE

```sql
-- Adicionar coluna
ALTER TABLE gold_catalog.sales.fact_vendas
ADD COLUMN margem_liquida DECIMAL(10, 2)
COMMENT 'Margem líquida da transação';

-- Com default
ALTER TABLE gold_catalog.sales.fact_vendas
ADD COLUMN versao_modelo INT DEFAULT 1;

-- Renomear coluna
ALTER TABLE gold_catalog.sales.fact_vendas
RENAME COLUMN valor TO valor_bruto;

-- Deletar coluna (Delta 2.0+)
ALTER TABLE gold_catalog.sales.fact_vendas
DROP COLUMN desconto;
```

---

## TBLPROPERTIES: Configuração Completa

```sql
CREATE TABLE gold_catalog.sales.fact_vendas (...)
USING DELTA
TBLPROPERTIES (
  -- Delta Lake features
  'delta.enableChangeDataFeed' = 'true',
  'delta.enableDeletionVectors' = 'true',

  -- Retenção e limpeza
  'delta.deletedFileRetentionDuration' = '30 days',

  -- Clustering
  'delta.liquid.clustering.enabled' = 'true',

  -- Compatibilidade (suporta rename/drop)
  'delta.columnMapping.mode' = 'name',

  -- Classificação e governança
  'classification' = 'PII/Restrito',
  'data_owner' = 'analytics-team@empresa.com.br',
  'retention_days' = '1825'  -- 5 anos
);
```

---

## Exemplo Completo: Star Schema DDL

### dim_cliente

```sql
CREATE TABLE gold_catalog.sales.dim_cliente (
  id_cliente BIGINT NOT NULL COMMENT 'PK',
  pii_nome VARCHAR(255) NOT NULL COMMENT 'Nome completo (PII)',
  pii_cpf VARCHAR(14) COMMENT 'CPF (PII)',
  pii_email VARCHAR(100) COMMENT 'Email (PII)',
  data_cadastro DATE COMMENT 'Data de cadastro',
  status VARCHAR(20) COMMENT 'ativo|inativo',
  regiao VARCHAR(2) COMMENT 'UF (SP, RJ, MG, ...)',
  segmento VARCHAR(50) COMMENT 'Premium|Gold|Silver|Bronze',
  created_at TIMESTAMP COMMENT 'Data de criação',
  updated_at TIMESTAMP COMMENT 'Última atualização'
)
USING DELTA
CLUSTER BY (id_cliente)
COMMENT 'Dimensão de Clientes - Camada Gold'
TBLPROPERTIES (
  'classification' = 'PII/Restrito',
  'delta.enableChangeDataFeed' = 'true'
);
```

### fact_vendas

```sql
CREATE TABLE gold_catalog.sales.fact_vendas (
  id_transacao BIGINT NOT NULL COMMENT 'PK',
  id_cliente BIGINT NOT NULL COMMENT 'FK',
  id_produto BIGINT NOT NULL COMMENT 'FK',
  id_data BIGINT NOT NULL COMMENT 'FK (dim_data)',
  data_venda DATE NOT NULL,
  quantidade INT NOT NULL,
  valor_unitario DECIMAL(10, 2) NOT NULL,
  valor_total DECIMAL(12, 2) NOT NULL,
  desconto_pct DECIMAL(4, 2),
  valor_liquido DECIMAL(12, 2),
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP
)
USING DELTA
CLUSTER BY (data_venda, id_cliente)
COMMENT 'Fatos de Vendas - Camada Gold'
TBLPROPERTIES (
  'classification' = 'Confidencial',
  'delta.enableChangeDataFeed' = 'true',
  'delta.enableDeletionVectors' = 'true',
  'retention_days' = '2555'  -- 7 anos (fiscal)
);
```

---

## CREATE VOLUME

```sql
CREATE VOLUME IF NOT EXISTS gold_catalog.assets
COMMENT 'Armazena modelos ML, arquivos estáticos';

-- Usar em Python
-- dbutils.fs.ls("/Volumes/gold_catalog/assets/")
```
