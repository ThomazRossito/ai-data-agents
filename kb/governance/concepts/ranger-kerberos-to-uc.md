# Ranger / Sentry / Kerberos → Unity Catalog — Mapeamento de Segurança (Hadoop)

> Catálogo normativo de conversão do modelo de segurança **Hadoop** (Kerberos, LDAP, Ranger/Sentry,
> HDFS ACLs, Hive `GRANT`) para **Unity Catalog** (Principals, Groups, Service Principals, Privileges,
> Row Filters, Column Masks). Irmão de `kb/governance/concepts/uc-abac-governed-tags.md` — aqui está
> o mapeamento **Hadoop → UC** (privilégios, identidade, extração de políticas); a mecânica completa
> de `CREATE POLICY`/ABAC/Governed Tags/Dynamic Views (comum a qualquer origem, já com sintaxe e
> exemplos validados) fica **na KB ABAC — não duplicada aqui**. Fonte: curso *Hadoop Migration* —
> `02 - Design/2.4 Lecture - Security and Access Design`, `05 - Enable/5.2 Lecture - Security and
> Fine-Grained Access`. As duas lições foram auditadas
> (`audits/2026-08-02-curso-hadoop-migration-vs-ai-data-agents.md` §0, H8) e **não** apresentam a
> contaminação do template SQL Server encontrada em outras lições do mesmo curso (Discovery 1.2,
> Lakebridge Reconcile 4.1, Cutover 4.3, FinOps 5.1, Observability/GitOps 6.1/6.2) — todo o conteúdo
> abaixo é Hadoop-válido (Ranger, Sentry, Kerberos, HDFS, Hive).

**Domínio:** Ranger/Sentry policies, Kerberos + LDAP identity, HDFS ACLs, Hive `GRANT` → Unity Catalog
privileges/principals/row filters/column masks. Extração de políticas Hadoop para conversão.

**Ver também:** `kb/governance/concepts/uc-abac-governed-tags.md` (sintaxe completa `CREATE POLICY`,
ABAC, Dynamic Views, Governed Tags), `kb/hadoop-migration/concepts/hive-ddl-conversion.md` (conversão
de schema), `kb/databricks/concepts/lakehouse-federation.md` §8 Hive Metastore Federation
(coexistência Hadoop↔Databricks durante a migração).

---

## 1. Modelo de Segurança — Visão Geral

Fonte: `2.4 Lecture`, seção 1 "Security Model Overview".

| Conceito Hadoop | Equivalente Databricks | Nota de Migração |
|---|---|---|
| Kerberos principal + LDAP user | User (sincronizado do IdP) | Mapear via provisionamento SCIM a partir de LDAP/AD |
| Ranger roles, Sentry roles, LDAP groups | Group (aninhado) | Achatar (flatten) hierarquias complexas de role |
| Kerberos keytab / service principal | Service Principal | Usar para automação e pipelines |
| Ranger policy ou Sentry `GRANT` em objeto | `GRANT privilege ON object TO principal` | Mesmo conceito, mecanismo diferente — ver nota de desambiguação em §3 |
| HDFS file owner, Hive table owner | Object owner (user/group) | Transferido durante a migração |
| Ranger database-level policy | Herdado via schema/catalog | Usar o modelo de herança |
| Ranger row-level filter policies | Row Filters (manual ou ABAC) | Definido por tabela — ver §6 e `uc-abac-governed-tags.md` |
| Ranger column masking policies | Column Masks (manual ou ABAC) | Baseado em função — ver §7 e `uc-abac-governed-tags.md` |

Cadeia de autorização (`2.4 Lecture`, diagrama "Security Model Comparison"):

```
Hadoop:     Kerberos (autenticação) → LDAP Groups (membership) → Ranger/Sentry (autorização) → Permissions (HDFS ACLs, table grants)
Databricks: Principals (Users/Groups/Service Principals) → Groups (hierarquia aninhada) → Privileges (UC grants)
```

---

## 2. Mapeamento de Papéis Administrativos

Fonte literal: `2.4 Lecture`, "Hadoop to Databricks Role Mapping".

| Papel Hadoop | Equivalente Databricks | Nota |
|---|---|---|
| Hadoop admin (HDFS superuser) | Account Admin | Controle total via Account Console |
| Ranger/Sentry admin | Metastore Admin | Gerencia catalogs, storage credentials, external locations |
| Kerberos admin | Account Admin + Metastore Admin | Funções de segurança divididas entre account e metastore |
| LDAP directory admin | Account Admin (Identity) | Gestão de usuário/grupo via Account Console ou SCIM |
| Ranger/Sentry custom roles | Groups | Databricks usa grupos para RBAC — **sem hierarquia de role** |
| LDAP group membership | Group nesting | Grupos podem conter outros grupos (herança) |

⚙️ Grupos devem ser criados no **nível de conta** (Account Console → *User management → Groups*, API
REST de conta, Databricks CLI, Python SDK, ou IaC) — nunca no nível de workspace, para consistência
entre workspaces (`2.4 Lecture`, quadro "Account-Level Group Management").

---

## 3. Mapeamento de Privilégios (`GRANT`)

Fonte literal: `2.4 Lecture`, "Hadoop to Databricks Privilege Mapping".

> **Desambiguação:** "Ranger/Sentry `GRANT`" aqui refere-se ao DCL padrão `GRANT ... ON ... TO ...`
> (ANSI SQL-92, confirmado em `5.2 Lecture` §1) do Unity Catalog — **não confundir** com o terceiro
> tipo de ABAC `CREATE POLICY ... GRANT` (concessão condicional por tag), cuja sintaxe exata não está
> no corpus do curso (ver `uc-abac-governed-tags.md` §5).

| Privilégio Hadoop | Equivalente Unity Catalog | Escopo |
|---|---|---|
| Ranger `USE` em database | `USE CATALOG` | Catalog |
| Ranger `SELECT` em database | `USE SCHEMA` | Schema |
| `SELECT` em Table/View | `SELECT` | Table/View |
| `INSERT`, `UPDATE`, `DELETE` (Hive ACID) | `MODIFY` | Table |
| `CREATE TABLE` (Ranger) | `CREATE TABLE` | Schema |
| `CREATE VIEW` (Ranger) | `CREATE VIEW` | Schema |
| HDFS owner / Hive `ALTER` | `OWNERSHIP` | Qualquer securable |
| Ranger database-level `SELECT` (aplica a novas tabelas) | `GRANT SELECT ON SCHEMA` | Schema (auto-herda para todos os objetos) |
| Ranger `ALL` em database | `GRANT USE CATALOG, CREATE SCHEMA ON CATALOG` | **Não existe privilégio `ALL` único** — preferir grants explícitos |
| N/A (Hadoop não separa compute) | Acesso a SQL Warehouse via permissões de workspace | — |

```sql
-- Padrão de GRANT em cascata (substitui recriar policy Ranger por database)
-- Nomes de catalog/schema/grupo conforme o diagrama "RBAC Grant Pattern" (2.4 Lecture §3)
GRANT USE CATALOG ON CATALOG migration_dev TO `data-engineers`;
GRANT USE CATALOG ON CATALOG migration_dev TO `data-analysts`;

GRANT USE SCHEMA, CREATE TABLE, MODIFY ON SCHEMA migration_dev.adventureworks_raw TO `data-engineers`;
GRANT USE SCHEMA, SELECT ON SCHEMA migration_dev.adventureworks_analytics TO `data-analysts`;
```

**Herança substitui policy por database do Ranger** (`2.4 Lecture`, quadro "Inheritance Simplifies
Migration"): um único `GRANT SELECT ON SCHEMA` cobre toda tabela atual e futura — não recrie a policy
por tabela.

| Concedido em | Aplica-se a |
|---|---|
| Catalog | Todos os schemas/tabelas/views/volumes do catalog |
| Schema | Todas as tabelas/views/volumes do schema |
| Object | Só a tabela/view/volume específica |

### RBAC por persona (`2.4 Lecture`, seção 3)

| Persona | Privilégios recomendados |
|---|---|
| Data Engineer | `USE CATALOG`, `USE SCHEMA`, `CREATE TABLE`, `MODIFY` em bronze/silver |
| Data Analyst | `USE CATALOG`, `USE SCHEMA`, `SELECT` em silver/gold |
| Data Scientist | `USE CATALOG`, `USE SCHEMA`, `SELECT` em tudo, `CREATE TABLE` em sandbox |
| BI Developer | `USE CATALOG`, `USE SCHEMA`, `SELECT` em gold |
| Platform Admin | Metastore admin, workspace admin |

---

## 4. Identidade: Kerberos + LDAP → UC User/Group/Service Principal

Fonte: `2.4 Lecture` §1-2, `5.2 Lecture` §1.

| Hadoop | Unity Catalog | Mecanismo |
|---|---|---|
| Kerberos principal + LDAP user | User | Provisionamento **SCIM** a partir de LDAP/AD (ou Microsoft Entra ID) |
| LDAP group / Ranger role / Sentry role | Group (achatado) | SCIM sync ou criação manual no Account Console |
| Kerberos keytab / conta de serviço | Service Principal | Criado via Account Console; credencial própria (OAuth) |
| Contexto de identidade em policy: Ranger user/group, Kerberos principal (`hadoop.security.auth_to_local`) | `current_user()`, `is_account_group_member()` | Funções de contexto usadas em Row Filter/Column Mask/Dynamic View |

⚠️ **Duas funções de grupo no UC — usar a correta:** o quadro comparativo do curso (`5.2 Lecture` §1)
cita `is_member()`, mas **100% dos exemplos de código** do mesmo curso (`2.4`/`5.2`, seções 6-9) usam
`is_account_group_member()`. `is_member()` é a função legada, avaliada contra grupos **locais do
workspace** — não é a recomendada para Unity Catalog. Usar sempre
`is_account_group_member('nome-do-grupo')`.

**keytab/service account → Service Principal:** contas de serviço Hadoop (keytabs) usadas por
pipelines/jobs migram para Service Principals com escopo mínimo (ver §11) — nunca para um usuário
humano.

---

## 5. HDFS ACLs / Ownership → UC Grants/Owner

| Hadoop | Unity Catalog |
|---|---|
| HDFS file owner | Object owner (transferido na migração) |
| Hive table owner / permissão `ALTER` | `OWNERSHIP` |
| HDFS ACL (`setfacl`, POSIX ACL, grupo Unix) | `GRANT`/`REVOKE` no objeto UC equivalente (catalog/schema/table/volume) |
| `hdfs groups <user>` (grupo efetivo do usuário no HDFS) | `is_account_group_member()` — ver §4 |

```sql
-- Transferir ownership de uma tabela migrada
ALTER TABLE adventureworks_silver.customer_detail OWNER TO `data-engineers`;
```

---

## 6. Row-Level Security: Ranger Row Filter → UC Row Filter

Fonte: `2.4 Lecture` §4, `5.2 Lecture` §6.

| Aspecto | Ranger | Unity Catalog |
|---|---|---|
| Definição | Row filter policy com expressão de filtro, por tabela/grupo | UDF SQL retornando `BOOLEAN` |
| Aplicação | Ranger Admin UI ou REST, por recurso Hive | `ALTER TABLE ... SET ROW FILTER` (manual) ou `CREATE POLICY ... ROW FILTER` (ABAC — `uc-abac-governed-tags.md` §5) |
| Contexto | Variável `{USER}` do Ranger | `is_account_group_member()` (não `is_member()` — ver §4) |
| Gestão | Policy por recurso na Ranger Admin UI | Por tabela (manual) ou ABAC com herança catalog/schema |

```sql
-- Row filter manual convertido de uma Ranger row-level filter policy por território
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

Para policies Ranger repetidas em múltiplas tabelas (tag-based), preferir **ABAC com Governed Tags**
em vez de recriar a função por tabela — sintaxe completa de `CREATE POLICY ... MATCH COLUMNS
hasTag(...)` em `uc-abac-governed-tags.md` §5.

**Performance** (`5.2 Lecture`): preferir `is_account_group_member()` a joins/mapping tables; manter a
coluna do filtro na chave de Liquid Clustering; usar funções determinísticas que não lançam erro.

---

## 7. Column Masking: Ranger Masking Policy → UC Column Mask

Fonte literal: `5.2 Lecture` §7, quadro "Converting Hadoop Masking Policies" (verbatim do curso — não
confundir com a tabela de conversão DDM do SQL Server em `uc-abac-governed-tags.md` §9, que usa
`partial()`/`HASHBYTES` em vez dos mask types nativos do Ranger).

| Tipo de máscara Ranger | Unity Catalog |
|---|---|
| `MASK` | `mask(val)` |
| `MASK_SHOW_LAST_4` | `CONCAT('***', RIGHT(val, 4))` |
| `MASK_HASH` | `sha2(val, 256)` |
| `MASK_NULL` | `NULL` |
| Expressão de máscara customizada | UDF SQL customizada |
| Condição `{USER}` do Ranger | `current_user()` |
| Checagem de grupo (policy item do Ranger) | `is_account_group_member('group')` |

```sql
-- Column mask manual convertido de uma Ranger column masking policy (parcial + condição de grupo)
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
```

Para PII repetida em múltiplas tabelas, preferir **ABAC** (tags `class.us_ssn`, `class.email_address`
etc. + `CREATE POLICY ... COLUMN MASK`) — sintaxe completa em `uc-abac-governed-tags.md` §3 e §5.

---

## 8. Tag-Based Policies: Ranger (Atlas) → UC Governed Tags/ABAC — Referência

Fonte literal: `5.2 Lecture`, quadro "Hadoop vs Unity Catalog ABAC Comparison".

| Aspecto | Ranger | Unity Catalog |
|---|---|---|
| Fundamento | Ranger tag-based policies (equivalente mais próximo) — requer **Apache Atlas** para classificação | ABAC é uma camada de governança distinta — não requer produto externo |
| Escopo da tag | Tags Atlas/Navigator (escopo de cluster) | Governed Tags de nível de conta (UI ou API) |
| Atribuição de tag | Classificação Atlas ou Ranger tag service | `SET TAGS (...)` — ver `uc-abac-governed-tags.md` §3 |
| Vínculo policy↔tag | Ranger tag-based policy com atributos de tag | `CREATE POLICY ... MATCH COLUMNS hasTag(...)` — ver `uc-abac-governed-tags.md` §5 |
| Contexto de identidade | Ranger user/group, Kerberos principal | `is_account_group_member()`, `current_user()` |
| Herança | Manual, por recurso, no Ranger | Automática para objetos filhos (catalog → schema → table) |

**Não duplicar aqui:** toda a mecânica de `CREATE POLICY`, os três tipos (`ROW FILTER`/`COLUMN
MASK`/`GRANT`), Governed vs Regular Tags, o erro `UC_ABAC_MULTIPLE_ROW_FILTERS`, o requisito de
runtime (DBR 16.4+/serverless — ⚠️ confirmar se a GA de maio/2026 relaxou) e as Dynamic Views estão em
`kb/governance/concepts/uc-abac-governed-tags.md`. Este arquivo cobre só o lado Hadoop/Ranger do
mapeamento.

---

## 9. Extração de Políticas Hadoop para Conversão

Fonte: `2.4 Lecture` §6, `5.2 Lecture` §3 e §9.

### 9.1 Ranger — políticas de acesso, row filter e column masking

```bash
# Exportar todas as políticas Hive via API REST do Ranger
curl -u admin:admin -k \
  "http://ranger-host:6080/service/plugins/policies/exportJson?serviceName=hive" \
  -o ranger_hive_policies.json

# Exportar todas as políticas HDFS
curl -u admin:admin -k \
  "http://ranger-host:6080/service/plugins/policies/exportJson?serviceName=hdfs" \
  -o ranger_hdfs_policies.json

# Filtrar policies de row-level filter
python3 -c "import json; data=json.load(open('ranger_hive_policies.json'));
[print(json.dumps(p, indent=2)) for p in data.get('policies', []) if p.get('rowFilterPolicyItems')]" \
  > row_filter_policies.json

# Filtrar policies de column masking
python3 -c "import json; data=json.load(open('ranger_hive_policies.json'));
[print(json.dumps(p, indent=2)) for p in data.get('policies', []) if p.get('dataMaskPolicyItems')]" \
  > masking_policies.json

# Listar contas de serviço (svc_/service_) e seus acessos — para dimensionar Service Principals (§11)
python3 -c "
import json
data = json.load(open('ranger_hive_policies.json'))
for policy in data.get('policies', []):
    for item in policy.get('policyItems', []):
        for user in item.get('users', []):
            if user.startswith('svc_') or user.startswith('service_'):
                accesses = [a['type'] for a in item.get('accesses', [])]
                print(f'{user}: {policy[\"name\"]} -> {accesses}')
"
```

⚠️ **Trilha de auditoria Ranger:** exportar o histórico de acesso (Ranger Audit) para a baseline de
compliance antes do cutover — tipicamente via um endpoint REST do tipo `.../service/plugins/audit` no
Ranger Admin. **Este path específico não está demonstrado literalmente no corpus do curso** (que só
cobre `policies/exportJson`) — o backend de audit do Ranger pode ser Solr ou um banco relacional
dependendo da instalação (standalone, CDP, Ambari), então **confirme o endpoint exato na documentação
da distribuição em uso** antes de automatizar. O destino no UC após a migração é sempre
`system.access.audit`, independente do mecanismo de extração na origem (ver §10).

### 9.2 Hive `GRANT` / roles (HiveQL via Beeline)

```sql
-- Grants de nível de banco/tabela
SHOW GRANT USER alice ON DATABASE adventureworks_dw;
SHOW GRANT GROUP data_engineers ON DATABASE adventureworks_dw;
SHOW GRANT ON TABLE adventureworks_dw.fact_internet_sales;

-- Grants de role (Sentry/Hive roles)
SHOW ROLE GRANT USER alice;
SHOW ROLE GRANT GROUP data_engineers;
```

### 9.3 Kerberos principals e LDAP groups

```bash
# Listar principals Kerberos (MIT Kerberos)
kadmin.local -q "list_principals" > kerberos_principals.txt

# Extrair grupos LDAP (exemplo Active Directory)
ldapsearch -x -H ldap://ldap-host:389 \
  -b "ou=groups,dc=example,dc=com" \
  "(objectClass=groupOfNames)" cn member > ldap_groups.txt

# Extrair o grupo efetivo do Hadoop para um ou mais usuários
hdfs groups alice bob charlie > hadoop_group_mappings.txt
```

Esses três comandos alimentam o mapeamento SCIM (§4): `kerberos_principals.txt` + `ldap_groups.txt`
definem quais Users/Groups provisionar; `hadoop_group_mappings.txt` valida o grupo efetivo esperado
por usuário, para comparar contra o resultado de `is_account_group_member()` pós-migração.

---

## 10. Auditoria — Ranger/HDFS/YARN Logs → System Tables

Fonte literal: `2.4 Lecture` §5.

| Fonte Hadoop | System Table Databricks | Propósito |
|---|---|---|
| Ranger audit logs | `system.access.audit` | Todos os eventos de auditoria |
| HDFS audit logs / Kerberos auth logs | `system.access.audit` (filtrado) | Eventos de autenticação |
| YARN resource usage logs | `system.billing.usage` | Consumo de recursos |
| N/A (sem equivalente Hadoop nativo) | `system.access.table_lineage` | Linhagem em nível de tabela |
| N/A (sem equivalente Hadoop nativo) | `system.access.column_lineage` | Linhagem em nível de coluna |

```sql
-- Mudanças de permissão nos últimos 7 dias (equivalente a auditar mudanças de policy no Ranger)
SELECT event_time, user_identity.email AS actor, action_name,
       request_params.securable_type, request_params.securable_full_name, request_params.changes
FROM system.access.audit
WHERE action_name = 'updatePermissions'
  AND event_date >= current_date() - INTERVAL 7 DAYS
ORDER BY event_time DESC
LIMIT 50;
```

Auditoria completa de PII via governed tags (view `pii_access_audit`, join com
`information_schema.column_tags`) já documentada em `uc-abac-governed-tags.md` §10 — não duplicar
aqui.

---

## 11. Service Principals — Contas de Serviço Hadoop (Keytabs)

Fonte: `2.4 Lecture` §6.

| Caso de uso | Identidade | Escopo recomendado |
|---|---|---|
| Scripts de migração | Service Principal | Read na origem, Write nos schemas de destino |
| Lakeflow Pipelines | Service Principal | Ownership do catalog/schema ou grants `MODIFY` |
| Conexões de ferramenta de BI | Service Principal | `SELECT` só na camada gold |
| Deploys CI/CD | Service Principal | Workspace admin ou grants limitados |

```sql
-- Escopo mínimo para um Service Principal de ingestão (substitui um keytab de conta de serviço)
GRANT USE CATALOG, USE SCHEMA, READ VOLUME, CREATE TABLE, MODIFY
ON SCHEMA migration_dev.adventureworks_raw
TO `<service-principal-application-id>`;
```

⚠️ **Anti-padrão** (curso, quadro "Avoid Over-Privileging Service Principals"): conceder `ALL
PRIVILEGES` em catalog a um Service Principal por conveniência expõe mais dados se a credencial for
comprometida, esvazia a trilha de auditoria e viola o menor privilégio — mesma regra já documentada em
`uc-abac-governed-tags.md` (Anti-Padrões).

---

## 12. Checklist de Migração de Segurança

Fonte: `2.4 Lecture` §7 (condensado).

**Pré-migração:** documentar principals Kerberos + usuários/grupos LDAP + memberships Ranger/Sentry;
identificar contas de serviço (keytabs) e seus padrões de acesso; mapear roles/grupos Hadoop → grupos
Databricks; documentar policies de row-level filter e column masking do Ranger; exportar amostra de
audit log para baseline de compliance.

**Durante a migração:** criar grupos no Databricks (SCIM sync do LDAP ou manual); estabelecer grants
em nível de catalog/schema; implementar row filters para tabelas com Ranger row-level policy;
implementar column masks para colunas PII; criar Service Principals para processos automatizados;
testar acesso com personas diferentes.

**Pós-migração:** verificar equivalência de privilégio com as policies Ranger originais; habilitar
monitoramento de audit log; criar dashboards de compliance; documentar o modelo de segurança para o
time de operações; agendar revisões periódicas de acesso.

---

## Fontes Oficiais (verificadas)

**Lado Unity Catalog:**
- [Unity Catalog Privileges](https://docs.databricks.com/en/data-governance/unity-catalog/manage-privileges/privileges.html)
- [Row Filters and Column Masks](https://docs.databricks.com/aws/en/data-governance/unity-catalog/filters-and-masks/)
- [Unity Catalog ABAC](https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/)
- [Governed Tags](https://docs.databricks.com/aws/en/admin/governed-tags/)
- [System Tables — Audit Logs](https://docs.databricks.com/en/administration-guide/system-tables/audit-logs.html)
- [Service Principals](https://docs.databricks.com/en/admin/users-groups/service-principals.html)
- [`GRANT` (DCL)](https://docs.databricks.com/aws/en/sql/language-manual/security-grant)
- [`information_schema`](https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-information-schema)

**Lado Hadoop (Ranger/Sentry, citados no curso):**
- [Ranger Row-Level Filtering](https://docs.cloudera.com/cdp-private-cloud-base/latest/security-ranger-authorization/topics/security-ranger-row-level-filtering.html)
- [Ranger Column Masking](https://docs.cloudera.com/cdp-private-cloud-base/latest/security-ranger-authorization/topics/security-ranger-column-masking.html)
- [Ranger Authorization Overview](https://docs.cloudera.com/cdp-private-cloud-base/latest/security-ranger-authorization/topics/security-ranger-provide-authorization-cdp.html)
- [Apache Sentry](https://sentry.apache.org/) (projeto retirado/attic — mantido só como referência histórica para migrações que ainda usam Sentry)

---

## Anti-Padrões

| Anti-padrão | Por quê | Correção |
|---|---|---|
| Recriar uma policy Ranger por database/tabela em vez de usar herança UC | Unity Catalog herda automaticamente catalog→schema→table; recriar por objeto é redundante e diverge com o tempo (§3) | `GRANT ... ON SCHEMA`/`ON CATALOG` uma vez; usar escopo mais estreito só para exceções |
| Usar `is_member()` em vez de `is_account_group_member()` | `is_member()` é a função legada de grupo **workspace-local**; não é a semântica de conta usada no restante do curso e do UC (§4) | Sempre `is_account_group_member('grupo')` |
| Mapear Ranger `ALL` em database para um único privilégio UC | UC não tem privilégio `ALL` — o curso é explícito nisso (§3) | Listar `USE CATALOG`, `CREATE SCHEMA` etc. explicitamente |
| Migrar keytab de conta de serviço como usuário pessoal | Perde a distinção de automação; keytabs eram identidade de serviço no Hadoop (§4, §11) | Sempre criar Service Principal dedicado, nunca reusar/criar usuário humano |
| `GRANT ALL PRIVILEGES` em catalog para Service Principal "por conveniência" | Credencial comprometida expõe mais dados; audit trail perde sentido; viola menor privilégio (§11) | Grants explícitos mínimos por função |
| Tratar Ranger tag-based policy (Atlas) como idêntica a UC ABAC | Ranger tag-based exige Atlas para classificação; UC ABAC (Governed Tags) é nativo e não requer produto externo (§8) | Migrar classificação Atlas para Governed Tags via UI/API — não assumir conversão 1:1 automática |
| Assumir que `.../service/plugins/audit` é o path fixo do Ranger em qualquer instalação | O endpoint de audit REST varia por versão/distribuição (Ranger standalone vs CDP vs Ambari) e pode depender de um backend Solr (§9.1) | Confirmar o endpoint exato na documentação da distribuição Ranger em uso antes de automatizar a extração |

## Regras

1. **PII detectada em coluna/policy Ranger → PARAR e escalar `governance-auditor`** (S6) antes de gerar
   `CREATE FUNCTION`/`ALTER TABLE ... SET MASK`/`CREATE POLICY` — mesma regra de
   `uc-abac-governed-tags.md`, Regra 1.
2. Sempre usar `is_account_group_member()`, nunca `is_member()`, em row filter, column mask ou dynamic
   view convertidos de uma policy Ranger (§4).
3. Nunca mapear Ranger `ALL` para um único grant UC — listar privilégios explícitos (§3).
4. Toda conta de serviço/keytab Hadoop migra para um Service Principal dedicado com escopo mínimo —
   nunca `ALL PRIVILEGES` (§11).
5. Preferir ABAC (Governed Tags + `CREATE POLICY`) quando a mesma row-filter/masking policy do Ranger
   se repete em múltiplas tabelas; usar row filter/mask manual só para casos isolados — sintaxe
   completa em `uc-abac-governed-tags.md` (não duplicar aqui).
6. Extração de políticas (Ranger REST, `SHOW GRANT`, `kadmin.local`, `hdfs groups`, `ldapsearch`) é
   **leitura, não execução destrutiva** — mas sempre rodar contra a origem com credencial read-only
   quando disponível.
7. Confirmar o endpoint exato de audit REST do Ranger na documentação da distribuição em uso antes de
   automatizar (§9.1) — não está demonstrado no corpus do curso.
8. Credenciais Ranger/Kerberos/LDAP usadas em scripts de extração → secret scope, nunca hardcode (S5).
