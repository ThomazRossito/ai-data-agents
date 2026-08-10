# 📊 Dashboard — AI Data Agents

> Painéis **vivos**: o [Dataview](https://blacksmithgu.github.io/obsidian-dataview/) lê o frontmatter dos arquivos e monta as tabelas na hora — atualizam sozinhos quando você cria/edita um agente, skill ou KB. (Plugin Dataview já instalado neste vault.)
>
> Mapa da arquitetura: [[wiki/supervisor|Supervisor]] · Índice: [[wiki/index|Índice Central]] · KB: [[wiki/kb-map|Mapa de KB]] · Migração: [[wiki/migracao|Migração → Databricks]]

---

## 🤖 Agentes por Tier

```dataview
TABLE WITHOUT ID
  file.link AS "Agente",
  tier AS "Tier",
  model AS "Modelo",
  mcp_servers AS "MCP servers",
  kb_domains AS "Domínios de KB"
FROM "data_agents/agents/registry"
WHERE file.name != "_template"
SORT tier ASC, file.name ASC
```

---

## 🧩 Skills por domínio

```dataview
TABLE WITHOUT ID
  name AS "Skill",
  split(file.folder, "/")[1] AS "Domínio"
FROM "skills"
WHERE file.name = "SKILL"
SORT split(file.folder, "/")[1] ASC, name ASC
```

---

## 📚 Cobertura de Knowledge Base (notas por domínio)

```dataview
TABLE length(rows) AS "Notas"
FROM "kb"
GROUP BY split(file.folder, "/")[1] AS "Domínio KB"
SORT length(rows) DESC
```

---

## 🔀 Agentes de migração → Databricks

```dataview
TABLE WITHOUT ID
  file.link AS "Agente",
  kb_domains AS "KB",
  updated_at AS "Atualizado"
FROM "data_agents/agents/registry"
WHERE contains(file.name, "-to-databricks") OR file.name = "migration-expert"
SORT file.name ASC
```

> Geradores determinísticos que estes agentes usam (não são notas Obsidian, são scripts): `scripts/sqlserver_generate.py`, `scripts/hive_generate.py`, `scripts/teradata_generate.py`, `scripts/ssas_generate.py`, `scripts/reconcile_generate.py`.
