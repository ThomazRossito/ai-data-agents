# MCP Servers (17)

MCP (Model Context Protocol) servers are the bridge between agents and external platforms. Each MCP is a separate subprocess; the agent invokes tools by name (e.g. `mcp__databricks__execute_sql`).

## Custom (8) — implemented in this repo

| Server | Purpose | Path |
|---|---|---|
| `databricks_genie` | Genie Conversation API + Space management | `data_agents/mcp_servers/databricks_genie/` |
| `fabric_sql` | Fabric SQL Analytics Endpoint via TDS (pyodbc) | `data_agents/mcp_servers/fabric_sql/` |
| `fabric_semantic` | TMDL introspection, DAX INFO functions, RLS | `data_agents/mcp_servers/fabric_semantic/` |
| `fabric_notebook` | Atomic notebook ops (encode + upload + LRO in one call) | `data_agents/mcp_servers/fabric_notebook/` |
| `fabric_onelake` | OneLake file ops via DFS API (bypasses fabric_official bug) | `data_agents/mcp_servers/fabric_onelake/` |
| `fabric_ontology` | Fabric IQ Ontology CRUD (entity types, relationships, bindings) | `data_agents/mcp_servers/fabric_ontology/` |
| `migration_source` | SQL Server / PostgreSQL: DDL + schema + stats extraction | `data_agents/mcp_servers/migration_source/` |
| `azure_pricing` | Azure Retail Prices API + fixed-cost validation | `data_agents/mcp_servers/azure_pricing/` |

## External (9) — third-party MCPs

| Server | Purpose | Source |
|---|---|---|
| `databricks` | Official Databricks MCP (50+ tools) | `databricks-mcp-server` (PyPI) |
| `fabric` | Fabric Community MCP (lineage, dependencies) | `npx @microsoft/fabric-mcp` |
| `fabric_official` | Microsoft Fabric MCP (workspaces, items, OneLake) | dotnet (local install) |
| `fabric_rti` | Fabric RTI / Kusto MCP | `microsoft-fabric-rti-mcp` |
| `context7` | Library documentation lookup (free, no credentials) | `npx @upstash/context7-mcp` |
| `tavily` | Web search + URL extraction | `uvx mcp-tavily` |
| `github` | GitHub repos, issues, PRs (free PAT) | `uvx mcp-github` |
| `firecrawl` | Structured web scraping | `uvx firecrawl-mcp` |
| `postgres` | Read-only PostgreSQL queries | `npx @modelcontextprotocol/server-postgres` |
| `memory_mcp` | Knowledge graph (entities + relations, free) | `npx @modelcontextprotocol/server-memory` |

## Always-active (no credentials required)

`context7` and `memory_mcp` are activated automatically — they don't need credentials. Useful for `python-expert` (lookup docs of `pandas`, `polars`, `fastapi` etc) and any agent that wants a persistent entity graph.

## Tool aliases

Agents declare `tools:` in YAML and the loader expands aliases:

```yaml
tools: [Read, Write, databricks_all, context7_all, memory_mcp_readonly]
```

`databricks_all` expands to the full list of `mcp__databricks__*` tools. The 24 aliases are defined in `data_agents/agents/loader.py::MCP_TOOL_SETS` and validated by `scripts/lint_mcp_configs.py`.

## Adding a new MCP

5-step process documented in [`.claude/CLAUDE.md`](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/.claude/CLAUDE.md):

1. `mkdir data_agents/mcp_servers/<name>/`
2. Create `server_config.py` with `get_<name>_mcp_config()` + `MCP_TOOLS` list
3. Register in `data_agents/config/mcp_servers.py::ALL_MCP_CONFIGS`
4. Add credentials in `data_agents/config/settings.py`
5. Add aliases in `data_agents/agents/loader.py::MCP_TOOL_SETS`

Lint validates the contract: missing step → CI fails.
