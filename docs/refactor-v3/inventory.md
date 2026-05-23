# Inventory Snapshot — pre-refactor v3.0

> **Captured at**: 2026-05-22
> **Baseline tag**: `v2.3.0-pre-refactor`
> **Source of truth**: este arquivo. Toda contagem em README/PRODUCT.md/CLAUDE.md deve casar com este snapshot ao fim da Fase 4.

---

## Agents (15)

Source: `agents/registry/*.md` (excluindo `_template.md`). Todos usam `model: kimi-k2.6`.

| # | Name | Tier | max_turns | effort | permission_mode |
|---|---|---|---|---|---|
| 1 | `azure-cost-calculator` | T2 | — | — | — |
| 2 | `business-analyst` | T3 | — | — | — |
| 3 | `data-contracts-engineer` | T2 | — | — | — |
| 4 | `data-mesh-architect` | T2 | — | — | — |
| 5 | `data-quality-steward` | T2 | — | — | — |
| 6 | `databricks-ai` | T1 | 20 | — | — |
| 7 | `databricks-engineer` | T1 | 25 | — | — |
| 8 | `dbt-expert` | T2 | — | — | — |
| 9 | `fabric-engineer` | T1 | 25 | — | — |
| 10 | `fabric-ontology` | T2 | — | — | bypassPermissions |
| 11 | `fabric-rti` | T2 | — | — | — |
| 12 | `geral` | T0 | — | — | — |
| 13 | `governance-auditor` | T2 | — | — | — |
| 14 | `migration-expert` | T1 | 25 | high | — |
| 15 | `python-expert` | T1 | — | — | — |

Distribuição por tier: T0=1, T1=5, T2=8, T3=1.

---

## MCP Servers (17)

Source: `config/mcp_servers.py::ALL_MCP_CONFIGS` + `mcp_servers/`.

### Custom (7) — implementação Python neste repo

| # | Name | Status | Entry point pyproject |
|---|---|---|---|
| 1 | `azure_pricing` | Custom | `azure-pricing-mcp` |
| 2 | `databricks_genie` | Custom | `databricks-genie-mcp` |
| 3 | `fabric_notebook` | Custom | `python -m mcp_servers.fabric_notebook.server` |
| 4 | `fabric_onelake` | Custom | `python -m mcp_servers.fabric_onelake.server` |
| 5 | `fabric_ontology` | Custom | `fabric-ontology-mcp` |
| 6 | `fabric_semantic` | Custom | `fabric-semantic-mcp` |
| 7 | `fabric_sql` | Custom | `fabric-sql-mcp` |
| 8 | `migration_source` | Custom | `migration-source-mcp` |

> NOTA: na verdade são 8 customs (azure_pricing, databricks_genie, fabric_notebook, fabric_onelake, fabric_ontology, fabric_semantic, fabric_sql, migration_source). Inventário a verificar na Fase 0.3 final.

### External (10) — pacotes/binários terceiros

| # | Name | Source |
|---|---|---|
| 1 | `context7` | `npx @upstash/context7-mcp@latest` |
| 2 | `databricks` | `databricks-mcp-server` (wrapper local em `run_server.py`) |
| 3 | `fabric` (community) | `microsoft-fabric-mcp` (pacote pip) |
| 4 | `fabric_official` | `npx @microsoft/fabric-mcp@1.0.0` |
| 5 | `fabric_rti` | `uvx microsoft-fabric-rti-mcp` |
| 6 | `firecrawl` | `npx firecrawl-mcp` |
| 7 | `github` | `npx @modelcontextprotocol/server-github` |
| 8 | `memory_mcp` | `npx @modelcontextprotocol/server-memory` |
| 9 | `postgres` | `npx @modelcontextprotocol/server-postgres` |
| 10 | `tavily` | `uvx tavily-mcp` |

> `fabric` na realidade registra **2 servidores** (`fabric_community` + `fabric_official`) na mesma chave em `ALL_MCP_CONFIGS`. Total real de **servidores registrados em runtime**: 17 chaves + 1 alias = 18 endpoints distintos.

### MCPs sempre ativos (sem credenciais)

`ALWAYS_ACTIVE_MCPS` em `config/mcp_servers.py`:
- `context7`
- `memory_mcp`
- `fabric_ontology` (auth via `az login`)
- `azure_pricing` (API pública)

---

## Knowledge Base domains (17)

Source: `kb/` excluindo `_templates/`. Arquivos raiz contam à parte: `kb/README.md`, `kb/constitution.md`, `kb/task_routing.md`, `kb/collaboration-workflows.md`.

| # | Domain | .md files | Tem `index.md`? |
|---|---|---|---|
| 1 | `azure-pricing` | 4 | Sim |
| 2 | `checklists` | 4 | Sim |
| 3 | `data-contracts` | 1 | Sim |
| 4 | `data-mesh` | 1 | Sim |
| 5 | `data-quality` | 11 | Sim |
| 6 | `databricks` | 11 | Sim |
| 7 | `fabric` | 9 | Sim |
| 8 | `governance` | 11 | Sim |
| 9 | `industry` | 11 | Sim |
| 10 | `migration` | 1 | Sim |
| 11 | `pipeline-design` | 9 | Sim |
| 12 | `python-patterns` | 9 | Sim |
| 13 | `semantic-modeling` | 9 | Sim |
| 14 | `semantic-web` | 5 | Sim |
| 15 | `shared` | 2 | Não (anti-padrões) |
| 16 | `spark-patterns` | 9 | Sim |
| 17 | `sql-patterns` | 8 | Sim |

Total de arquivos .md em KBs: **115** (excluindo `_templates/`).

---

## Skills (48)

Source: `skills/*/SKILL.md` excluindo `TEMPLATE/` e diretórios prefixados com `_`.

| Domain | Skills count | Skills |
|---|---|---|
| `databricks` | 28 | agent-bricks, ai-functions, aibi-dashboards, app-python, bundles, config, dbsql, docs, execution-compute, genie, genie-health-check, iceberg, jobs, lakebase-autoscale, lakebase-provisioned, lakeflow-connect, metric-views, mlflow-evaluation, model-serving, python-sdk, spark-declarative-pipelines, spark-structured-streaming, synthetic-data-gen, unity-catalog, unstructured-pdf-generation, vector-search, zerobus-ingest, spark-python-data-source |
| `fabric` | 10 | cross-platform, data-factory, deployment-pipelines, direct-lake, eventhouse-rti, git-integration, medallion, monitoring-dmv, notebook-manager, workspace-manager |
| `finops` | 1 | azure-pricing |
| `migration` | 1 | (root SKILL.md) |
| `ontology` | 2 | fabric-ontology-owl, owl-to-fabric-iq |
| `patterns` | 5 | data-quality, pipeline-design, spark-patterns, sql-generation, star-schema-design |
| `python` | 1 | (root SKILL.md) |

Total: **48 SKILL.md** (não 49 como antes informado — corrigir nas docs).

---

## Slash Commands (39)

Source: `config/commands.yaml`. Ver auditoria anterior para a lista completa com agent/doma_mode.

Resumo por modo:
- `express`: 24 commands
- `full`: 6 commands
- `internal`: 9 commands

---

## Hooks (11 arquivos .py)

Source: `hooks/*.py` excluindo `__init__.py`.

1. `audit_hook.py` — PostToolUse, logging JSONL com error categorization
2. `checkpoint.py` — save/restore de sessão
3. `context_budget_hook.py` — PostToolUse, monitora tokens da sessão
4. `cost_guard_hook.py` — PostToolUse, classifica HIGH/MEDIUM/LOW
5. `memory_hook.py` — PostToolUse, captura contexto
6. `output_compressor_hook.py` — shim que re-exporta de `compression/`
7. `security_hook.py` — PreToolUse, bloqueia destrutivos + SQL caro
8. `session_lifecycle.py` — start/end de sessão
9. `session_logger.py` — métricas JSONL por sessão
10. `transcript_hook.py` — append-only do transcript por sessão
11. `workflow_tracker.py` — shim que re-exporta de `workflow/`

Implementação real espalhada também em: `compression/hook.py`, `workflow/tracker.py`.

---

## Code metrics (atual)

| Metric | Value |
|---|---|
| Python source LOC (agents/, config/, hooks/, memory/, commands/, compression/, workflow/, ui/, utils/, mcp_servers/, main.py) | ~32,085 |
| Test files | 58 |
| Test functions | ~300 |
| Coverage target | ≥ 80% (gate em CI) |
| Top-level directories | 15+ |
| pyproject version | 2.3.0 |
| Python required | ≥ 3.11 |

---

## Documentation files at root

- `README.md` (31,925 bytes)
- `PRODUCT.md` (7,343 bytes)
- `CHANGELOG.md` (25,144 bytes)
- `Manual_Relatorio_Tecnico_Projeto_Data_Agents.md` (47,676 bytes) — **mover para `docs/legacy/`**
- `chainlit.md` (2,266 bytes)
- `LICENSE`

Missing (criar na Fase 1):
- `SECURITY.md`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `NOTICE`
- `docs/ARCHITECTURE.md`
- `docs/adr/` (8 ADRs iniciais)

---

## Discrepâncias conhecidas (a corrigir na Fase 4)

| Local | Valor declarado | Valor real |
|---|---|---|
| `.claude/CLAUDE.md` | "14 agentes" | **15** |
| `.claude/CLAUDE.md` | "13 MCPs" | **17** (8 custom + 9 external + 1 community/official duplicado na chave `fabric`) |
| `.claude/CLAUDE.md` (porta) | 8503 / 8501 | **8513 / 8511** |
| README | (verificar todas as contagens) | a sincronizar via `scripts/gen_inventory.py` |

---

*Este snapshot é referência durante o refactor. Atualizar ao fim da Fase 4 quando `scripts/gen_inventory.py` virar source of truth.*
