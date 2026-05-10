# Unity Catalog — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** Hierarquia, grants, volumes, system tables

---

## Hierarquia Obrigatória: Catalog.Schema.Table

A três níveis é **mandatória**. Nunca use `hive_metastore` (legado).

```
main.analytics.users       ✅ Unity Catalog (3 níveis)
users                      ❌ Cai em hive_metastore legado
hive_metastore.default.x   ❌ Explicitamente legado
```

---

## Ordem de Grants

**Requer 3 grants em sequência:**

1. `GRANT USE CATALOG` (pré-requisito)
2. `GRANT USE SCHEMA` (pré-requisito)
3. `GRANT SELECT/MODIFY` (operação)

**Gotcha:** Se faltar `USE CATALOG` ou `USE SCHEMA`, a tabela não aparece mesmo com SELECT.

---

## Tabela de Grants por Nível

| Nível | Escopo | Sintaxe |
|-------|--------|---------|
| **Catalog** | Acesso ao catálogo inteiro | `GRANT USE CATALOG ON CATALOG main TO \`group\`` |
| **Schema** | Acesso a esquema | `GRANT USE SCHEMA ON SCHEMA main.analytics TO \`group\`` |
| **Table** | Leitura/escrita de tabela | `GRANT SELECT ON TABLE main.analytics.users TO \`group\`` |
| **Volume** | Arquivos em volume | `GRANT READ VOLUME ON VOLUME main.raw.data TO \`group\`` |

---

## Volumes: Onde Armazenar Arquivos

Sempre use volumes para arquivos não-tabulares (CSV, JSON, imagens, PDFs).

**Formato de caminho (mandatório):**
```
/Volumes/catalog/schema/volume_name/path/to/file
```

**Gotcha:** Path é CASE-SENSITIVE. `/Volumes/Main/Raw/...` falha se criado em minúsculas.

---

## System Tables

| Tabela | Descrição | Filtro Crítico |
|--------|-----------|-----------------|
| `system.access.audit` | Todas ações (GRANT, DELETE, etc.) | `event_date >= current_date() - 7` |
| `system.access.table_lineage` | Dependências entre tabelas | `event_date >= current_date() - 7` |
| `system.billing.usage` | Consumo de DBU por workspace | `usage_date >= current_date() - 30` |
| `system.access.applied_permissions` | Permissões ativas em recursos | Nenhum (tabela pequena) |

**Gotcha:** Sempre filtrar por `event_date` ou `usage_date`. Sem filtro → timeout.

---

## Onde Armazenar Dados

| Tipo de Dado | Armazenamento | Exemplo |
|--------------|---------------|---------|
| **Tabular estruturado** | Tabela UC (Parquet Delta) | Clientes, pedidos, logs |
| **Arquivo não-tabular** | Volume UC | CSV bruto, JSON, imagens, PDFs |
| **Dados temporários** | Tabela TEMP (sessão) | Cálculos intermediários |

---

## Checklist Implementação

- [ ] Todos os catalogs têm 3 níveis (catalog.schema.table)
- [ ] System tables habilitadas para data_engineers
- [ ] Lineage queries testadas e agendadas
- [ ] Volumes criados para arquivos não-tabulares
- [ ] Grants validados com `information_schema.applicable_privileges`
- [ ] Alertas configurados para mudanças em `system.access.audit`
