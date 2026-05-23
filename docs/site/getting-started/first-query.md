# First Query

## 1. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` and fill in at minimum:

```ini
# Required — Moonshot Kimi K2.6 via Anthropic-compat endpoint
ANTHROPIC_API_KEY=sk-...
ANTHROPIC_BASE_URL=https://api.moonshot.ai/anthropic

# Required for Databricks operations
DATABRICKS_HOST=https://adb-xxxxxxxx.azuredatabricks.net
DATABRICKS_TOKEN=dapi...

# Required for Fabric operations
AZURE_TENANT_ID=...
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
FABRIC_WORKSPACE_ID=...

# Optional (always-active MCPs)
TAVILY_API_KEY=tvly-...
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...
```

See the [Security threat model](../reference/security.md) for what each credential touches.

## 2. Run a query

```bash
ai-data-agents "liste as tabelas do schema silver no catálogo main"
```

What happens:

1. CLI loads `.env`, enriches the system prompt with relevant memories from past sessions.
2. **Supervisor** receives the prompt + an injected escalation graph (66 rules from agent registry).
3. Supervisor matches the prompt domain (Databricks discovery) → delegates to `databricks-engineer`.
4. `databricks-engineer` calls `mcp__databricks__list_tables(catalog="main", schema="silver")`.
5. PreToolUse hooks (security, cost guard) approve the call.
6. Result is returned; PostToolUse hooks log audit entry + capture session context.
7. Supervisor synthesizes the response and returns to you.

Expected output (truncated):

```
⚙️ Databricks Engineer — domain: SQL / Unity Catalog
- Platform: Databricks / Unity Catalog
- Scope: main.silver

📋 Análise:
Encontrei 14 tabelas no schema main.silver:

| name | type | rows |
| --- | --- | --- |
| customers | MANAGED | 1.2M |
| orders | MANAGED | 18.4M |
...

KB: kb/databricks/index.md | Confiança: ALTA (0.95) | MCP: confirmado
```

## 3. Common errors

| Error | Cause | Fix |
|---|---|---|
| `ANTHROPIC_API_KEY not configured` | `.env` missing or unset | `cp .env.example .env` + fill |
| `Failed to connect to Databricks` | `DATABRICKS_HOST` or `DATABRICKS_TOKEN` invalid | Run `make health-databricks` |
| `ModuleNotFoundError: No module named 'chainlit'` | Trying to start UI without `[ui]` extra | `pip install "ai-data-agents[ui]"` |
| `Supervisor timeout` | Network slow / Moonshot rate-limit | Retry; if persistent, see model failover in `agents/supervisor.py` |

## 4. Modes of invocation

```bash
# Interactive REPL (default)
ai-data-agents

# Single query
ai-data-agents "your prompt"

# Slash command (skip Supervisor for known intent)
ai-data-agents "/sql SELECT count(*) FROM main.silver.orders"

# Conceptual question (no MCP, ~95% cheaper, runs on geral agent)
ai-data-agents "/geral qual a diferença entre Lakehouse e Data Warehouse?"
```

→ **[Slash Commands](slash-commands.md)** for the full reference of `/sql`, `/fabric`, `/migrate`, `/quality`, `/governance`, etc.
