# PII Classification — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** Masking SQL, hashing, tokenização, erasure, tags UC

---

## 1. Hashing (SHA-256)

```sql
-- Mascarar CPF via hash
SELECT
  SHA2(pii_cpf, 256) AS cpf_hash,  -- Não reversível
  SHA2(pii_email, 256) AS email_hash,
  valor_total,
  data_venda
FROM catalog.gold.fact_vendas;
```

---

## 2. Truncação

```sql
-- Mostrar apenas primeiros caracteres
SELECT
  LEFT(pii_nome, 1) || '***' AS nome_inicial,
  REGEXP_REPLACE(pii_cpf, r'\d{3}\.\d{3}\.\d{3}-(\d{2})', r'***.***.***-\1') AS cpf_masked,
  REGEXP_REPLACE(pii_email, r'^(.{2}).*@', r'\1***@') AS email_masked
FROM catalog.gold.dim_cliente;
```

---

## 3. Tokenização

```sql
-- Criar tabela de tokens
CREATE TABLE IF NOT EXISTS catalog.governance.pii_tokens (
  token_id STRING PRIMARY KEY,
  pii_type STRING,     -- CPF | EMAIL | TELEFONE
  pii_value STRING,    -- Valor original (encriptado)
  created_at TIMESTAMP,
  expires_at TIMESTAMP
);

-- Substituir CPF por token
INSERT INTO catalog.governance.pii_tokens
SELECT
  UUID() AS token_id,
  'CPF' AS pii_type,
  ENCRYPT(pii_cpf, 'aes-256', secret_key) AS pii_value,
  CURRENT_TIMESTAMP(),
  CURRENT_TIMESTAMP() + INTERVAL 1 YEAR
FROM catalog.gold.dim_cliente;
```

---

## 4. Nullificação

```sql
-- Remover dado para analytics
SELECT
  id_cliente,
  NULL AS pii_cpf,
  NULL AS pii_email,
  segmento,
  regiao,
  data_cadastro
FROM catalog.gold.dim_cliente;
```

---

## Tags Unity Catalog

```sql
-- Tag em tabela
ALTER TABLE catalog.gold.dim_cliente
SET TAGS (
  'classification' = 'PII/Restrito',
  'data_owner' = 'privacy@empresa.com.br',
  'retention_days' = '1825'
);

-- Tag em coluna
ALTER TABLE catalog.gold.dim_cliente
ALTER COLUMN pii_cpf SET TAGS (
  'pii_type' = 'CPF',
  'masking_required' = 'true',
  'lgpd_basis' = 'contrato'
);
```

---

## Erasure (LGPD - Direito ao Esquecimento)

```sql
-- Pseudoanonimizar cliente específico
UPDATE catalog.gold.dim_cliente
SET
  pii_nome = CONCAT('ERASURE_', SHA2(pii_cpf, 256)),
  pii_cpf = NULL,
  pii_email = NULL,
  pii_telefone = NULL,
  data_erasure = CURRENT_TIMESTAMP(),
  motivo_erasure = 'LGPD Art. 18 - Solicitação do Titular'
WHERE pii_cpf = '123.456.789-00';
```

---

## DDL: erasure_log

```sql
CREATE TABLE IF NOT EXISTS catalog.governance.erasure_log (
  erasure_id STRING NOT NULL PRIMARY KEY,
  pii_identifier STRING,  -- Valor original mascarado para referência
  erasure_timestamp TIMESTAMP NOT NULL,
  legal_basis STRING,
  requested_by STRING,
  executed_by STRING,
  affected_tables STRING  -- JSON array de tabelas modificadas
);
```

---

## Detectar PII em Tabelas (Auditoria)

```sql
-- Encontrar colunas com prefixo pii_
SELECT
  table_catalog,
  table_schema,
  table_name,
  column_name,
  data_type
FROM information_schema.columns
WHERE column_name LIKE 'pii_%'
ORDER BY table_catalog, table_schema, table_name;
```
