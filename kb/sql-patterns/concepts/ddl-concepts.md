# DDL — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** Managed vs External, naming conventions, tipos de dados, TBLPROPERTIES

---

## Managed vs External Tables

| Tipo | Armazenamento | DELETE Tabela | Uso |
|------|--------------|---------------|-----|
| **Managed** | /user/hive/warehouse/ | Deleta dados | Padrão (warehouse) |
| **External** | S3/ADLS location | Mantém dados | Dados compartilhados |

**Regra:** Usar External apenas quando os dados precisam persistir após DROP TABLE ou são compartilhados entre catálogos.

---

## Convenções de Nomenclatura

**Padrão obrigatório: snake_case**

| Prefixo | Tipo | Exemplo |
|---------|------|---------|
| `bronze_` | Raw (Bronze) | `bronze_erp_clientes_raw` |
| `silver_` | Transformado (Silver) | `silver_crm_clientes_clean` |
| `gold_` | Agregado/Star Schema | `gold_vendas.fact_vendas` |
| `dim_` | Dimensão | `dim_cliente`, `dim_data` |
| `fact_` | Fato | `fact_vendas`, `fact_eventos` |
| `pii_` | Coluna com dados pessoais | `pii_cpf`, `pii_email` |

---

## Data Types: Escolha Correta

| Tipo | Uso | Exemplo |
|------|-----|---------|
| BIGINT | IDs, counts grandes | `id_cliente BIGINT` |
| INT | Inteiro pequeno (flags, dias) | `num_dias INT` |
| DECIMAL(p,s) | Valores monetários (precisão fixa) | `valor DECIMAL(10,2)` |
| DOUBLE | Floats científicos (menos preciso) | `taxa_conversao DOUBLE` |
| DATE | Data apenas (YYYY-MM-DD) | `data_venda DATE` |
| TIMESTAMP | Data + hora | `criado_em TIMESTAMP` |
| VARCHAR(n) | String com tamanho máximo | `status VARCHAR(20)` |
| STRING | String ilimitado (recomendado) | `descricao STRING` |
| BOOLEAN | Verdadeiro/Falso | `is_ativo BOOLEAN` |
| ARRAY\<T\> | Lista de valores | `tags ARRAY<STRING>` |

**Regra para Direct Lake:** DATE não TIMESTAMP em colunas de data. BIGINT não INT em IDs (risco overflow).

---

## TBLPROPERTIES: Propriedades Comuns

| Propriedade | Valor | Efeito |
|-------------|-------|--------|
| `delta.enableChangeDataFeed` | `'true'` | Habilita CDF para CDC |
| `delta.enableDeletionVectors` | `'true'` | Soft delete eficiente |
| `delta.columnMapping.mode` | `'name'` | Suporta rename/drop colunas |
| `delta.liquid.clustering.enabled` | `'true'` | Liquid clustering |
| `delta.deletedFileRetentionDuration` | `'30 days'` | Retenção de arquivos deletados |
| `classification` | `'PII/Restrito'` | Classificação de dados |
| `data_owner` | email | Proprietário dos dados |
| `retention_days` | número | Retenção em dias |

---

## Organização de Schemas (Padrão)

```
gold_catalog
  ├─ sales/       (fact_vendas, dim_cliente, dim_produto)
  ├─ finance/     (fact_faturamento, dim_contas)
  ├─ marketing/   (fact_eventos, dim_campanha)
  └─ governance/  (audit_log, compliance_checklist)
```

---

## CREATE VOLUME: Para Arquivos (Não SQL)

Volumes são armazenamento de arquivos (não tabelas SQL):
- Modelos de ML
- Configurações JSON/YAML
- Arquivos estáticos

Path padrão: `/Volumes/catalog/schema/volume_name/`
