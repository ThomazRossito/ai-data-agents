# ABAC no Unity Catalog — Governed Tags e Policies

> ABAC (Attribute-Based Access Control) é a camada de governança **tag-driven** do Unity Catalog:
> tag uma coluna uma vez (`class.us_ssn`, `region_filter`...), crie uma `POLICY` que liga a tag a
> uma UDF de filtro/máscara e a um grupo — a policy se propaga automaticamente para toda tabela
> com a tag, sem tocar em cada `ALTER TABLE` individualmente. **GA em maio/2026** (Governed Tags +
> Data Classification + ABAC), verificado web ago/2026: 3 tipos de policy — `ROW FILTER`,
> `COLUMN MASK` e `GRANT`; policies anexadas em catalog/schema/table. Fonte curso *SQL Server
> Migration*: `02 - Design/2.4 Lecture - Security and Access Design`,
> `02 - Design/2.5 Demo - Architecture & Design Phase`,
> `05 - Enable/5.2 Lecture - Security and Fine-Grained Access`.

**Domínio:** Governed Tags, `CREATE POLICY`, row filter/column mask via ABAC, mapeamento SQL Server RLS/DDM → UC

---

## 1. Três Mecanismos de FGAC no Unity Catalog — Quando Usar Cada Um

Fonte: `05 - Enable/5.2 Lecture`, seção "Fine-Grained Access Control: Three Approaches".

| Mecanismo | Onde vive a lógica | Melhor para |
|---|---|---|
| **ABAC** (Governed Tags + Policy) | Policy anexada a catalog/schema/table via tag — sem view ou função por tabela | **Escala**: governança centralizada em muitas tabelas/times, com herança automática |
| **Row Filter / Column Mask manual** | Função SQL vinculada diretamente à tabela (`ALTER TABLE ... SET ROW FILTER` / `SET MASK`) | Lógica **isolada por tabela**, ou ainda sem disciplina de governed tags |
| **Dynamic View** | Lógica embutida na definição da view (`current_user()`, `is_account_group_member()`, `current_recipient()` no `WHERE`/`CASE`) | Compartilhamento **read-only** (inclusive **Delta Sharing** via `current_recipient()`), joins de múltiplas tabelas seguras, transformações complexas |

**Regra de decisão explícita** (5.2 Lecture): *"Use ABAC when you need centralized governance across many tables with policy inheritance. Use manual filters/masks when you need isolated per-table logic or aren't yet using governed tags."*

⚠️ **Mutuamente exclusivo na mesma tabela:** Row Filter/Column Mask manual e ABAC não coexistem no mesmo objeto — escolha um por tabela. Dynamic Views operam em outra camada e podem ser usadas com qualquer um dos dois (5.2 Lecture, nota do quadro comparativo).

---

## 2. Erro de Conflito: `UC_ABAC_MULTIPLE_ROW_FILTERS`

Fonte literal: `05 - Enable/5.2 Lecture`, quadro "ABAC and Manual Row Filters Cannot Coexist".

> Unity Catalog enforces **one row filter per table per user** at runtime. ABAC policies cannot be applied to tables that already have manual row filters — these must be removed first.

```sql
-- Remover row filter manual ANTES de habilitar ABAC na mesma tabela
ALTER TABLE catalog.schema.table DROP ROW FILTER;
```

Tentar combinar os dois resulta em: **`UC_ABAC_MULTIPLE_ROW_FILTERS`**.

---

## 3. Governed Tags — Criação (UI/API, não DDL)

Fonte: `05 - Enable/5.2 Lecture`, Passo 1, + `02 - Design/2.4 Lecture`, quadro "Programmatic Tag Policy Management".

**Não existe comando SQL DDL para criar uma governed tag.** Criação é via UI (Catalog Explorer → Governed Tags → Create governed tag) ou API/SDK:

| Ação | Mecanismo |
|---|---|
| Criar definição de tag | UI (Catalog Explorer) ou `POST /api/2.1/tag-policies` ou SDK |
| Aplicar tag a coluna | `ALTER TABLE ... ALTER COLUMN ... SET TAGS ('tag_name')` |
| Remover tag | `ALTER TABLE ... ALTER COLUMN ... UNSET TAGS ('tag_name')` |

```python
# SDK — criar governed tag programaticamente (2.4 Lecture / 5.2 Lecture)
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
w.tag_policies.create_tag_policy(
    tag_key="pii",
    description="Identifies PII data for ABAC policies",
    values=[
        {"name": "ssn"},
        {"name": "email"},
        {"name": "phone"}
    ]
)
```

### Tags sistêmicas prontas vs definidas pelo usuário

| Tipo | Exemplos | Valores |
|---|---|---|
| **System governed tags** | `class.us_ssn`, `class.email_address`, `class.phone_number`, `class.name` | Apenas chave (key-only, sem valor) — pré-definidas pela Databricks |
| **User-defined governed tags** | `region_filter`, `pii` (custom) | Podem ter valores permitidos predefinidos (ex.: `apac`, `emea`, `amer`, `all`) |

**Governed vs Regular tags** (5.2 Lecture) — **ABAC só funciona com governed tags**; tags regulares (implícitas, criadas no primeiro uso) não servem para controle de acesso:

| Aspecto | Governed Tag | Regular Tag |
|---|---|---|
| Definição | UI/API apenas | Implícita (criada no primeiro uso) |
| Valores | Apenas valores permitidos predefinidos | Qualquer valor |
| Usa em ABAC | ✅ Sim | ❌ Não |
| Uso típico | Controle de acesso, compliance | Busca, descoberta, organização |

**Privilégios exigidos para aplicar tag a coluna:** `APPLY TAG` no objeto, `USE SCHEMA` no schema pai, `USE CATALOG` no catalog pai, e — para governed tags — `ASSIGN` na tag.

```sql
-- Aplicar tags sistêmicas a colunas PII (2.5 Demo / 5.2 Lecture)
ALTER TABLE adventureworks_silver.customer_detail
ALTER COLUMN EmailAddress SET TAGS ('class.email_address');

ALTER TABLE adventureworks_silver.customer_detail
ALTER COLUMN Phone SET TAGS ('class.phone_number');

-- Tag definida pelo usuário, usada para row filter
ALTER TABLE adventureworks_silver.customer_detail
ALTER COLUMN SalesTerritoryGroup SET TAGS ('region_filter');

-- Consultar tags aplicadas
SELECT catalog_name, schema_name, table_name, column_name, tag_name, tag_value
FROM information_schema.column_tags
WHERE schema_name = 'adventureworks_silver'
ORDER BY table_name, column_name;
```

---

## 4. Regra Central: UDF define O QUÊ, POLICY define QUEM

Citação literal (`05 - Enable/5.2 Lecture`, Passo 3):

> **Important:** In ABAC, the **policy** defines WHO is affected (via the `TO` clause). The **UDF** only defines WHAT data they can see based on the column value — it should not contain `is_account_group_member()` logic.

Ou seja: **nunca** coloque checagem de grupo (`is_account_group_member(...)`) dentro da UDF de row filter/column mask usada por uma ABAC Policy — isso é papel exclusivo do `TO` da `POLICY`. A UDF só recebe o valor da coluna e devolve o resultado do filtro/máscara.

```sql
-- CORRETO — UDF só decide O QUÊ (baseada no valor da coluna, sem checar grupo)
CREATE OR REPLACE FUNCTION adventureworks_gold.filter_apac_only(region STRING)
RETURNS BOOLEAN
RETURN region = 'APAC';

-- ERRADO (anti-padrão) — is_account_group_member() dentro da UDF de uma ABAC policy
-- CREATE OR REPLACE FUNCTION ... RETURN is_account_group_member('apac-users') AND region = 'APAC';
```

> Nota: `is_account_group_member()` dentro da função **é o padrão correto** para Row Filter/Column Mask **manuais** (seção 7) e para Dynamic Views (seção 8) — a restrição "não colocar lógica de grupo na UDF" vale **apenas** quando a UDF é referenciada por uma ABAC `POLICY`, porque a policy já resolve o "quem" via `TO`.

---

## 5. `CREATE POLICY` — Sintaxe e Exemplos Completos

Fonte: `02 - Design/2.5 Demo` (mão-na-massa) + `05 - Enable/5.2 Lecture`, Passo 4.

**Escopo da policy** (herda para baixo — catalog cobre todos os schemas/tabelas filhas):

| Escopo | Sintaxe | Alcance |
|---|---|---|
| Tabela única | `ON TABLE catalog.schema.table` | Só essa tabela |
| Schema (herdado) | `ON SCHEMA catalog.schema` | Todas as tabelas do schema |
| Catalog (herdado) | `ON CATALOG catalog` | Todas as tabelas do catalog |

### Column Mask via ABAC (PII — SSN)

```sql
-- 1. Tag a coluna sensível
ALTER TABLE adventureworks_gold.customers_abac_example
ALTER COLUMN ssn SET TAGS ('class.us_ssn');

-- 2. UDF de máscara (redação total)
CREATE OR REPLACE FUNCTION adventureworks_gold.mask_ssn(ssn STRING)
RETURNS STRING
RETURN '***-**-****';

-- 3. Policy: liga a tag à UDF, aplica ao grupo `no-pii-group`
CREATE OR REPLACE POLICY mask_ssn_policy
ON SCHEMA adventureworks_gold
COMMENT 'Mask SSN columns tagged with class.us_ssn for non-privileged users'
COLUMN MASK adventureworks_gold.mask_ssn
TO `no-pii-group`
FOR TABLES
MATCH COLUMNS
  hasTag('class.us_ssn') AS ssn
ON COLUMN ssn;
```

### Row Filter via ABAC (região APAC)

```sql
-- 1. UDF de filtro — só decide O QUÊ
CREATE OR REPLACE FUNCTION adventureworks_gold.filter_apac_only(region STRING)
RETURNS BOOLEAN
RETURN region = 'APAC';

-- 2. Tag a coluna usada no filtro
ALTER TABLE adventureworks_gold.customers_abac_example
ALTER COLUMN region SET TAGS ('region_filter');

-- 3. Policy: liga a tag à UDF, aplica ao grupo `apac-users` — define QUEM
CREATE OR REPLACE POLICY filter_apac_rows_policy
ON SCHEMA adventureworks_gold
COMMENT 'APAC users can only see APAC region customers'
ROW FILTER adventureworks_gold.filter_apac_only
TO `apac-users`
FOR TABLES
MATCH COLUMNS
  hasTag('region_filter') AS region
USING COLUMNS (region);
```

`MATCH COLUMNS hasTag(...)` resolve, em runtime, **quais colunas** de **quais tabelas** a policy alcança — todas as colunas com a tag, em qualquer tabela dentro do escopo (`ON SCHEMA`/`ON CATALOG`), recebem a mesma regra automaticamente ("tag uma vez, aplica em todo lugar").

**Terceiro tipo de policy — `GRANT`:** fato verificado web (ago/2026) — além de `ROW FILTER` e `COLUMN MASK`, `CREATE POLICY` também suporta um tipo **`GRANT`** (concessão condicional baseada em tag). O curso (2.4/2.5/5.2) só demonstra `ROW FILTER` e `COLUMN MASK`; a sintaxe exata do tipo `GRANT` **não está no corpus do curso** — confirme na documentação oficial antes de gerar esse tipo de policy.

**Criação via UI (alternativa ao SQL):** Catalog Explorer → selecionar catalog → aba **Policies** → **New policy** → configurar Nome, Applied to, Except for, Scope, Purpose, Conditions, Function parameters → **Create policy** (5.2 Lecture).

**Remover row filter manual antes de habilitar ABAC na mesma tabela:**
```sql
ALTER TABLE adventureworks_silver.customer_detail DROP ROW FILTER;
```

---

## 6. Gating de Runtime — ⚠️ Confirmar Versão Mínima

O curso (`05 - Enable/5.2 Lecture`, quadro "Compute Requirement") afirma: **ABAC requer Databricks Runtime 16.4+ ou serverless compute**; usuários em runtimes mais antigos não conseguem acessar tabelas protegidas por ABAC (workaround citado no curso: aplicar a policy apenas a grupos específicos, deixando usuários fora do grupo acessarem via runtime antigo).

⚠️ **Marcar incerteza:** como ABAC + Governed Tags + Data Classification atingiu **GA em maio/2026** (verificado web, ago/2026), o requisito mínimo de runtime pode ter sido relaxado desde a gravação do curso. **Trate como "runtime recente/Serverless" e confirme a versão mínima exata na documentação oficial do Unity Catalog antes de bloquear uma proposta de migração por esse motivo.**

---

## 7. Row Filter / Column Mask Manuais (fora do ABAC)

Quando não convém usar ABAC (tabela isolada, ainda sem governed tags), a função é aplicada **diretamente** à tabela, e a checagem de grupo vai **dentro** da função (ao contrário da regra da seção 4, que só vale para UDFs referenciadas por uma `POLICY`).

```sql
-- Row filter manual: liga a checagem de grupo à própria UDF
CREATE OR REPLACE FUNCTION adventureworks_silver.territory_filter(sales_territory STRING)
RETURNS BOOLEAN
RETURN (
    is_account_group_member('data_admins')
    OR (is_account_group_member('analysts_apac') AND sales_territory = 'Pacific')
    OR (is_account_group_member('analysts_emea') AND sales_territory = 'Europe')
    OR (is_account_group_member('analysts_amer') AND sales_territory = 'North America')
    OR sales_territory = 'North America'   -- default: demais usuários só veem NA
);

ALTER TABLE adventureworks_silver.customer_detail
SET ROW FILTER adventureworks_silver.territory_filter ON (SalesTerritoryGroup);
```

**Boas práticas de performance** (5.2 Lecture): expressões simples (evitar mapping tables/subqueries), preferir `is_account_group_member()` a joins complexos, manter a coluna do filtro na chave de Liquid Clustering, usar funções determinísticas que não lançam erro.

### Column Mask manual — padrões comuns

| Padrão | Uso | Função |
|---|---|---|
| Substituição de caractere | Nomes, endereços | `mask(val)` → `XxxxXxxxx` |
| Revelação parcial | Email, telefone | `mask(val, NULL, NULL, NULL, NULL)` + `RIGHT()` |
| Hash/tokenização | PII para analytics | `sha2(val, 256)` |
| Nulificação | Ocultar de não-autorizados | `NULL` |
| Redação total | SSN, senhas | literal `'***-**-****'` |

```sql
CREATE OR REPLACE FUNCTION adventureworks_silver.mask_email(email STRING)
RETURNS STRING
RETURN (
    CASE
        WHEN is_account_group_member('data_admins') THEN email
        WHEN is_account_group_member('customer_service') THEN email
        ELSE mask(email)  -- Xxxx.xxxx@xxxxx.xxx
    END
);

ALTER TABLE adventureworks_silver.customer_detail
ALTER COLUMN EmailAddress SET MASK adventureworks_silver.mask_email;

-- Remover
ALTER TABLE adventureworks_silver.customer_detail
ALTER COLUMN EmailAddress DROP MASK;
```

---

## 8. Dynamic Views — Alternativa para Delta Sharing e Joins Seguros

Fonte: `05 - Enable/5.2 Lecture`, seção 8. Útil quando é preciso **juntar tabelas seguras** ou compartilhar dados read-only (inclusive via **Delta Sharing**).

| Função | Descrição |
|---|---|
| `current_user()` | Email do usuário atual |
| `is_account_group_member()` | `TRUE` se membro de grupo de conta |
| `current_recipient()` | Nome do destinatário quando acessado via **Delta Sharing** |

```sql
CREATE OR REPLACE VIEW adventureworks_silver.v_customer_secure AS
SELECT
    CustomerKey,
    FirstName,
    CASE
        WHEN is_account_group_member('data_admins') THEN EmailAddress
        ELSE regexp_extract(EmailAddress, '^.*@(.*)$', 1)
    END AS EmailAddress,
    CASE
        WHEN is_account_group_member('data_admins') THEN Phone
        ELSE CONCAT('***-***-', RIGHT(Phone, 4))
    END AS Phone,
    CountryRegionCode,
    SalesTerritoryGroup
FROM adventureworks_silver.customer_detail
WHERE
    is_account_group_member('data_admins')
    OR SalesTerritoryGroup = 'North America';
```

---

## 9. Mapeamento SQL Server → Unity Catalog (RLS/DDM → ABAC)

Fonte: `05 - Enable/5.2 Lecture`, tabelas "SQL Server vs Unity Catalog ABAC Comparison" e "Converting SQL Server Masking Policies".

| SQL Server | Unity Catalog | Nota |
|---|---|---|
| Fundamento | Sem equivalente nativo (RLS + DDM são os mais próximos) | ABAC é uma camada de governança distinta |
| `CREATE SECURITY POLICY` + `ADD FILTER PREDICATE` | `CREATE POLICY ... ROW FILTER ... MATCH COLUMNS hasTag(...)` | Vinculação policy↔tag |
| `ALTER COLUMN ... ADD MASKED WITH (FUNCTION = ...)` (DDM) | `CREATE POLICY ... COLUMN MASK ...` (ABAC) ou `ALTER TABLE ... SET MASK` (manual) | |
| Escopo de tag | Sem equivalente (policies aplicadas direto por tabela) | Governed tags em nível de conta (UI ou API) |
| Herança | Manual, por objeto | Automática para objetos filhos |
| `IS_MEMBER('db_owner') = 1` | `is_account_group_member('admins')` | |
| `IS_MEMBER('role_name') = 1` | `is_account_group_member('group')` | |
| `SUSER_SNAME()` | `current_user()` | |
| `HASHBYTES('SHA2_256', val)` | `sha2(val, 256)` | |
| DDM `partial()` | `mask(val)` | |
| `CONCAT('***', RIGHT(val, 4))` | `CONCAT('***', RIGHT(val, 4))` | idêntico |
| `IIF(condition, val, 'REDACTED')` | `IF(condition, val, 'REDACTED')` | |

**Extração de policies SQL Server para conversão** (`05 - Enable/5.2 Lecture`, seção 3):
```sql
-- Extrair RLS security policies e predicados
SELECT sp.name AS policy_name, sp.is_enabled, SCHEMA_NAME(sp.schema_id) AS policy_schema,
       pred.predicate_type_desc, OBJECT_SCHEMA_NAME(pred.target_object_id) AS target_schema_name,
       OBJECT_NAME(pred.target_object_id) AS target_object_name,
       pred.predicate_definition AS predicate_function
FROM sys.security_policies sp
JOIN sys.security_predicates pred ON sp.object_id = pred.object_id
ORDER BY policy_schema, policy_name;

-- Extrair colunas com Dynamic Data Masking
SELECT SCHEMA_NAME(t.schema_id) AS schema_name, t.name AS table_name,
       mc.name AS column_name, mc.masking_function, TYPE_NAME(mc.user_type_id) AS data_type
FROM sys.masked_columns mc
JOIN sys.tables t ON mc.object_id = t.object_id
WHERE mc.is_masked = 1
ORDER BY schema_name, table_name, column_name;
```

---

## 10. Auditoria de ABAC/PII

Fonte: `02 - Design/2.5 Demo`.

```sql
-- Mudanças recentes de permissão (inclui aplicação de tags/policies)
SELECT event_time, user_identity.email AS actor, action_name,
       request_params.securable_type, request_params.securable_full_name, request_params.changes
FROM system.access.audit
WHERE action_name = 'updatePermissions'
  AND event_date >= current_date() - INTERVAL 7 DAYS
ORDER BY event_time DESC
LIMIT 50;

-- View de auditoria de acesso a colunas PII, via governed tags
CREATE OR REPLACE VIEW adventureworks_gold.pii_access_audit AS
WITH pii_tables AS (
  SELECT DISTINCT CONCAT(catalog_name, '.', schema_name, '.', table_name) AS full_table_name
  FROM system.information_schema.column_tags
  WHERE tag_name = 'class.us_ssn'
)
SELECT a.event_time, a.event_date, a.user_identity.email AS user_email,
       a.request_params.full_name_arg AS table_accessed, a.source_ip_address, a.user_agent
FROM system.access.audit a
INNER JOIN pii_tables p ON a.request_params.full_name_arg = p.full_table_name
WHERE a.event_date >= current_date() - INTERVAL 90 DAYS;
```

---

## Anti-Padrões

| Anti-padrão | Por quê | Correção |
|---|---|---|
| `is_account_group_member()` dentro de UDF referenciada por uma ABAC `POLICY` | Duplica a resolução de "quem" — a `POLICY` já faz isso via `TO`; a UDF deve ser função pura do valor da coluna (seção 4) | UDF só recebe/retorna valor da coluna; grupo vai no `TO` da `POLICY` |
| Aplicar ABAC e row filter/mask manual na mesma tabela | Gera erro `UC_ABAC_MULTIPLE_ROW_FILTERS` (seção 2) — UC só aceita um row filter por tabela por usuário | Escolher um mecanismo por tabela; `DROP ROW FILTER` antes de migrar para ABAC |
| Tag regular (não-governed) usada para controle de acesso | Não tem efeito — ABAC só reconhece governed tags (seção 3) | Criar como governed tag via UI/API antes de referenciar em `POLICY` |
| **`GRANT ALL PRIVILEGES`** em catalog/schema por conveniência (ex.: para service principal) | Credencial comprometida expõe mais dados; trilha de auditoria perde significado; viola menor privilégio (`02 - Design/2.4 Lecture` §6 e `2.5 Demo`, quadro "Avoid Over-Privileging Service Principals") | Conceder apenas os privilégios mínimos por função (`USE CATALOG`, `USE SCHEMA`, `SELECT`/`MODIFY` pontuais) — usar ABAC/row filter/mask para refinar em vez de restringir via `GRANT` amplo |
| Ignorar herança de policy | Uma policy `ON CATALOG`/`ON SCHEMA` já cobre tabelas filhas — recriar por tabela é redundante e propenso a divergência | Aplicar no nível mais alto que fizer sentido; usar escopos mais estreitos só para exceções |

## Regras

1. **PII detectada em coluna/filtro → PARAR e escalar `governance-auditor`** (S6) antes de gerar `CREATE POLICY`/`CREATE FUNCTION` — mesma regra do `kb/ssas-migration/concepts/rls-and-security.md`.
2. UDF referenciada por ABAC `POLICY` nunca contém `is_account_group_member()` — o `TO` da policy já resolve QUEM (seção 4).
3. Verificar `UC_ABAC_MULTIPLE_ROW_FILTERS` antes de propor ABAC em tabela que já tem row filter manual — `DROP ROW FILTER` primeiro.
4. Preferir ABAC quando o mesmo padrão de filtro/máscara se repete em múltiplas tabelas (escala); manter row filter/mask manual só para casos isolados e pré-governed-tags.
5. Nunca propor `GRANT ALL PRIVILEGES` como atalho — sempre listar privilégios explícitos por persona/service principal.
6. Confirmar a versão mínima de DBR/serverless para ABAC na documentação oficial antes de bloquear uma migração por esse requisito (seção 6) — o número desta KB vem do curso e a GA de maio/2026 pode ter mudado.
7. Credenciais/segredos usados em qualquer automação de tag/policy → secret scope (nunca hardcode) — S5.
