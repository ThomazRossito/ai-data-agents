# PII Classification — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** PII brasileiro, classificação, estratégias de mascaramento

---

## PII Brasileiro: Padrões

| Dado | Padrão Regex | Categoria |
|------|-------------|---------|
| **CPF** | `\d{3}\.\d{3}\.\d{3}-\d{2}` | PII Sensível |
| **CNPJ** | `\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}` | PII Empresarial |
| **RG** | `\d{1,2}\.\d{3}\.\d{3}-[0-9X]` | PII Sensível |
| **Email** | `.+@.+\..+` | PII Básico |
| **Telefone** | `(\+55)?\s?\(?\d{2}\)?\s?\d{4,5}-?\d{4}` | PII Básico |
| **Data Nasc.** | `\d{2}/\d{2}/\d{4}` | PII Básico |

---

## Níveis de Classificação

| Nível | Exemplos | Acesso |
|-------|----------|--------|
| **PII Restrito** | CPF, RG, Saúde | Apenas equipe de privacidade + DPO |
| **PII Sensível** | Email, telefone | Data engineers com justificativa |
| **PII Público** | Nome, endereço | Analistas com mascaramento |
| **Confidencial** | Dados financeiros | Equipes autorizadas |
| **Interno** | Dados de negócio | Todos colaboradores |
| **Público** | Dados publicados | Sem restrição |

---

## Convenção de Nomenclatura

```
Prefixo pii_ em colunas com dados pessoais:
  pii_cpf
  pii_email
  pii_telefone
  pii_nome

Facilita: data discovery, mascaramento automático, auditoria
```

---

## 4 Estratégias de Mascaramento

| Estratégia | Quando | Reversível |
|-----------|--------|-----------|
| **Hashing** | Auditoria, matches sem expor | Não |
| **Truncação** | Mostrar parcial (email: u***@) | Não |
| **Tokenização** | Integração com sistemas terceiros | Sim (com key) |
| **Nullificação** | Analytics que não precisam do dado | Não |

---

## Tags Unity Catalog para PII

```sql
-- Tag em tabela inteira
ALTER TABLE catalog.gold.dim_cliente
SET TAGS ('classification' = 'PII/Restrito', 'data_owner' = 'privacy@empresa.com.br');

-- Tag em coluna específica
ALTER TABLE catalog.gold.dim_cliente
ALTER COLUMN pii_cpf SET TAGS ('pii_type' = 'CPF', 'masking_required' = 'true');
```
