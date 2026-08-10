# Roles / RLS (SSAS) → Unity Catalog (Databricks)

> Roles do SSAS com filtros DAX → **Unity Catalog row filters / column masks** (ou dynamic views). RLS
> simples é conversível; RLS complexo (bidirecional/multi-tabela/contextual) → **⚠️ revisão manual**.

## Roles → mecanismos de segurança Databricks

| Construto SSAS | Equivalente Databricks | Quando usar |
|---|---|---|
| **Role** (`members` + `tablePermissions`) | GRANTs de Unity Catalog + row filter/mask | Base do modelo de acesso |
| **Filtro DAX de tabela** (`filter`, ex.: `[Email] = USERPRINCIPALNAME()`) | **UC Row Filter** (função + `ROW FILTER`) usando `current_user()` | RLS por usuário |
| Mascaramento de coluna sensível | **UC Column Mask** (`MASK`) | Ocultar/redigir PII por grupo |
| RLS por lookup em dimensão (ex.: `rls_comercial` por e-mail) | Row filter com `EXISTS`/join, ou **dynamic view** filtrando por `current_user()` | Replica o filtro DAX sem duplicar dados |
| Pertencimento a grupo/organização | `is_account_group_member('grupo')` | Mapear membros de role → grupos do Entra ID |

## Row Filter (UC) — padrão

```sql
-- Função de row filter: mantém só as linhas do usuário atual
CREATE OR REPLACE FUNCTION catalog.gold.rls_venda(rls_sid STRING)
RETURN EXISTS (
  SELECT 1 FROM catalog.gold.rls_comercial r
  WHERE r.rls_comercial_sid = rls_sid
    AND r.email = current_user()          -- ajustar para UPN do Entra ID se necessário
);

ALTER TABLE catalog.gold.fact_venda_realizada
  SET ROW FILTER catalog.gold.rls_venda ON (rls_comercial_sid);
```

Alternativa (dynamic view) quando row filter não se aplica:

```sql
CREATE OR REPLACE VIEW catalog.gold.venda_realizada_rls AS
SELECT f.* FROM catalog.gold.fact_venda_realizada f
WHERE EXISTS (
  SELECT 1 FROM catalog.gold.rls_comercial r
  WHERE f.rls_comercial_sid = r.rls_comercial_sid AND r.email = current_user()
);
```

## Column Mask (UC) — PII

```sql
CREATE OR REPLACE FUNCTION catalog.gold.mask_email(v STRING)
RETURN CASE WHEN is_account_group_member('pii_reader') THEN v ELSE '***' END;

ALTER TABLE catalog.gold.dim_cliente ALTER COLUMN email SET MASK catalog.gold.mask_email;
```

## ⚠️ Bloqueado / revisão manual

| Construto | Por quê | Mitigação |
|---|---|---|
| RLS **bidirecional** / cross-filter em várias tabelas | Semântica de propagação diferente em SQL | Redesenhar filtros; caso a caso |
| Filtro DAX com **medidas/contexto dinâmico** | Depende do contexto de avaliação DAX | Reescrever como predicado SQL explícito |
| **Mapeamento e-mail SSAS ↔ UPN Databricks** divergente | `current_user()` retorna o UPN do Entra ID | Validar que os e-mails do SSAS batem com os UPNs |
| **Object/metadata permissions** (perspectives por persona) | Sem objeto nativo | Views por persona + GRANTs |

## Regras

1. **PII** (CPF, e-mail, cartão) em colunas/filtros → **PARAR e escalar `governance-auditor`** (S6) antes de gerar.
2. Nunca duplicar dados por persona/role — usar row filter/mask/dynamic view.
3. Credenciais de `dataSources` → **secret scope**; nunca hardcode nem imprimir (S5).
4. Toda role convertida entra na **reconciliação** (contagem por usuário SSAS × Databricks).
5. RLS complexo alegado como "convertido" só se estiver no código — honestidade relatório×código.
