# Access Control — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** RBAC, princípios de acesso, Databricks UC, Fabric workspace roles

---

## Estrutura de Permissões Unity Catalog

| Objeto | Escopo | Padrão |
|--------|--------|--------|
| **Catalog** | Acesso ao catálogo inteiro | USAGE para todos |
| **Schema** | Acesso a esquema | USAGE padrão, CREATE para data engineers |
| **Table** | Leitura/escrita | SELECT para analistas, MODIFY para devs |
| **Volume** | Arquivos | WRITE apenas para pipelines |
| **Function** | Funções customizadas | EXECUTE para usuários |

---

## Fabric: Workspace Roles

| Papel | Criar Itens | Modificar | Executar | Publicar | Admin |
|-------|-------------|----------|----------|----------|-------|
| **Admin** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Contributor** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Member** | ❌ | Próprio | ✅ | ❌ | ❌ |
| **Viewer** | ❌ | ❌ | ✅ | ❌ | ❌ |

---

## 3 Princípios Críticos

### 1. Nunca Conceda Acesso Direto a Usuários
Sempre GRANT a **grupos** (AAD/Okta), nunca a usuários individuais.

**Razão:** Facilita offboarding (remover do grupo revoga acesso) e auditoria centralizada.

### 2. Princípio do Menor Privilégio (PoLP)

| Papel | Permissões |
|-------|-----------|
| **Analista** | SELECT nas tabelas Gold apenas |
| **Data Engineer** | MODIFY em Silver/Bronze, SELECT em Gold |
| **Admin** | Acesso irrestrito (documentado) |

### 3. Revogar Acesso em até 24h de Offboarding

---

## Ordem Obrigatória de Grants UC

```
1. GRANT USAGE ON CATALOG → Pré-requisito
2. GRANT USAGE ON SCHEMA  → Pré-requisito
3. GRANT SELECT/MODIFY    → Operação
```

**Gotcha:** GRANT sem USAGE no Catalog = sem efeito.

---

## Gotchas

| Gotcha | Solução |
|--------|---------|
| Permissões herdam de Catalog → Schema | USAGE no Catalog = acesso a todos Schema |
| GRANT sem USAGE = sem efeito | Sempre: GRANT USAGE FIRST |
| Revogar tabela não remove schema | Hierarquia é independente |
| Atraso em propagação AAD | Permitir até 2h para permissões em novo usuário |
