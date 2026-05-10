# Compliance e LGPD — Padrões de Implementação

> Padrões de implementação. Para conceitos, veja concepts/.

**Domínio:** DDL consent, right-to-erasure SQL, TTL, masking views, breach log

---

## DDL: Consent Management

```sql
CREATE TABLE IF NOT EXISTS catalog.governance.consent_log (
  consent_id STRING NOT NULL,
  user_id STRING NOT NULL,
  data_category STRING NOT NULL,  -- marketing, analytics, personalization
  consent_type STRING NOT NULL,   -- opt_in | opt_out
  legal_basis STRING,             -- consentimento | contrato | obrigacao_legal
  consent_timestamp TIMESTAMP NOT NULL,
  ip_address STRING,
  user_agent STRING,
  revoked_at TIMESTAMP,
  CONSTRAINT pk_consent PRIMARY KEY (consent_id)
);
```

---

## Right-to-Erasure (Direito ao Esquecimento)

```sql
-- 1. Identificar todos os dados do usuário
SELECT 'dim_cliente' AS tabela, COUNT(*) AS registros
FROM catalog.gold.dim_cliente WHERE pii_cpf = '123.456.789-00'

UNION ALL

SELECT 'silver_compras', COUNT(*)
FROM catalog.silver.compras WHERE id_cliente = (
  SELECT id_cliente FROM catalog.gold.dim_cliente
  WHERE pii_cpf = '123.456.789-00'
);

-- 2. Pseudoanonimizar (não deletar para fins fiscais)
UPDATE catalog.gold.dim_cliente
SET
  pii_nome = CONCAT('ERASURE_', SHA2(pii_cpf, 256)),
  pii_cpf = NULL,
  pii_email = NULL,
  pii_telefone = NULL,
  data_erasure = CURRENT_TIMESTAMP()
WHERE pii_cpf = '123.456.789-00';

-- 3. Registrar erasure
INSERT INTO catalog.governance.erasure_log
VALUES (
  UUID(),
  '123.456.789-00',
  CURRENT_TIMESTAMP(),
  'LGPD Art. 18 - Direito ao Esquecimento',
  CURRENT_USER()
);
```

---

## DDL: Data Retention (TTL)

```sql
-- Política de retenção por categoria
CREATE TABLE IF NOT EXISTS catalog.governance.retention_policies (
  data_category STRING PRIMARY KEY,
  retention_days INT NOT NULL,
  legal_basis STRING NOT NULL,
  deletion_action STRING NOT NULL  -- DELETE | ANONYMIZE | ARCHIVE
);

INSERT INTO catalog.governance.retention_policies VALUES
('dados_comerciais', 1825, 'Código Civil Art. 206', 'ANONYMIZE'),
('dados_fiscais', 1825, 'Lei 5.172/1966', 'ARCHIVE'),
('dados_trabalhistas', 7300, 'CLT Art. 11', 'ARCHIVE'),
('dados_marketing', 365, 'Consentimento LGPD', 'DELETE');

-- Aplicar TTL: deletar dados expirados
DELETE FROM catalog.silver.cliente_marketing
WHERE created_at < CURRENT_DATE() - 365
  AND EXISTS (
    SELECT 1 FROM catalog.governance.retention_policies
    WHERE data_category = 'dados_marketing'
      AND deletion_action = 'DELETE'
  );
```

---

## Masking Views SQL

```sql
-- View mascarada para analistas (sem PII direto)
CREATE VIEW catalog.gold.dim_cliente_masked AS
SELECT
  id_cliente,
  LEFT(pii_nome, 1) || '***' AS nome_inicial,
  REGEXP_REPLACE(pii_cpf, r'\d{3}\.\d{3}\.\d{3}-(\d{2})', r'***.***.***-\1') AS cpf_masked,
  REGEXP_REPLACE(pii_email, r'^(.{2}).*@', r'\1***@') AS email_masked,
  regiao,
  segmento
FROM catalog.gold.dim_cliente;

-- Apenas equipe de privacidade acessa a tabela original
GRANT SELECT ON VIEW catalog.gold.dim_cliente_masked TO GROUP 'analysts@empresa.com.br';
REVOKE SELECT ON TABLE catalog.gold.dim_cliente FROM GROUP 'analysts@empresa.com.br';
```

---

## Breach Log e Notificação

```sql
-- DDL: Log de violações
CREATE TABLE IF NOT EXISTS catalog.governance.breach_log (
  breach_id STRING NOT NULL PRIMARY KEY,
  detected_at TIMESTAMP NOT NULL,
  description STRING NOT NULL,
  affected_records_count INT,
  data_categories STRING,  -- CPF, email, etc
  breach_type STRING,       -- UNAUTHORIZED_ACCESS | DATA_LEAK | SYSTEM_BREACH
  severity STRING,          -- HIGH | MEDIUM | LOW
  notification_anpd BOOLEAN DEFAULT FALSE,
  notification_date TIMESTAMP,
  resolution_date TIMESTAMP,
  root_cause STRING,
  responsible_person STRING
);

-- Query para violações não notificadas (> 72h)
SELECT
  breach_id,
  detected_at,
  description,
  severity,
  TIMESTAMPDIFF(HOUR, detected_at, CURRENT_TIMESTAMP()) AS horas_desde_deteccao
FROM catalog.governance.breach_log
WHERE notification_anpd = FALSE
  AND TIMESTAMPDIFF(HOUR, detected_at, CURRENT_TIMESTAMP()) > 72
  AND severity = 'HIGH';
```
