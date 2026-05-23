# Installation

Three ways to install, picked by what you want to do:

| Channel | When to use |
|---|---|
| **Python CLI** (this page, below) | Full feature set — Supervisor, hooks, memory, audit, MCPs. Use for production work, automation, CLI scripts. |
| **Claude Code plugin** ([install instructions](#claude-code-plugin)) | If you already use Claude Code and want the 15 agents + 48 skills available natively inside it. |
| **From source** | Contributors who want to develop on the project. `git clone && pip install -e ".[dev]"` |

---

## Core install

Only what's needed to run the Supervisor + 15 agents + 17 MCPs in CLI mode:

```bash
pip install ai-data-agents
```

You get: `claude-agent-sdk`, `anthropic`, `mcp[cli]`, `databricks-sdk`, `databricks-mcp-server`,
`microsoft-fabric-rti-mcp`, `mlflow`, `azure-identity`, `openai`, `pyodbc`, `psycopg2-binary`,
`pydantic-settings`, `rich`, `prompt_toolkit`, `pyyaml`, `requests`.

After install, the entry point `ai-data-agents` is available:

```bash
which ai-data-agents
ai-data-agents --help
```

## Optional extras

Each extra is opt-in. Modules under it raise a clean `ImportError` with the right install command if you try to use them without the extra (see [ADR-010](../reference/adrs.md) for the design).

| Extra | Adds | What it unlocks |
|---|---|---|
| `[dev]` | pytest, ruff, mypy, bandit, types-PyYAML | Local development + tests |
| `[ui]` | chainlit, markdown2, pandas, pyyaml | Web chat UI (`./start.sh --chat-only`) + HTML export |
| `[monitoring]` | streamlit, streamlit-agraph, pandas | Real-time dashboard (`make ui-monitor`) |
| `[viz]` | fastapi, uvicorn, watchdog | 3D visualization of the agent office (`python -m data_agents.visualization.server`) |
| `[memory]` | fastembed | Semantic embeddings for ShortTermMemory (complements FTS5/BM25) |
| `[ontology]` | rdflib, owlready2 | OWL/RDF processing in Spark notebooks (used by `fabric-ontology` agent) |
| `[docs]` | mkdocs, mkdocs-material | Build the docs site locally (only the maintainer needs this) |

Install combinations:

```bash
# Full dev environment
pip install "ai-data-agents[dev,ui,monitoring]"

# Everything
pip install "ai-data-agents[dev,ui,monitoring,viz,memory,ontology,docs]"

# Source install (for contributors)
git clone https://github.com/ThomazRossito/ai-data-agents.git
cd ai-data-agents
pip install -e ".[dev]"
```

## Conda environment

If you use conda for isolation:

```bash
conda create -n ai-data-agents python=3.12 -y
conda activate ai-data-agents
pip install ai-data-agents
```

## Verify install

```bash
python -c "from data_agents.agents.loader import preload_registry; print(len(preload_registry()), 'agents loaded')"
# expected: 15 agents loaded
```

## Claude Code plugin

If you already use [Claude Code](https://docs.claude.com/en/docs/claude-code) and want the 15 agents + 48 skills available natively (without `pip install`), use the plugin distribution:

```bash
# 1. Add the marketplace
claude plugin marketplace add ThomazRossito/ai-data-agents

# 2. Install the plugin
claude plugin install ai-data-agents@thomazrossito-marketplace
```

Restart your Claude Code session. The 15 specialist agents and 48 skills become available.

### What the plugin does NOT include (vs Python CLI)

To keep the plugin minimal and resilient to spec changes, the v3.0-rc1 plugin includes only **agents** and **skills**. These features are Python-CLI-only:

| Feature | Why not in plugin |
|---|---|
| 39 slash commands (`/sql`, `/fabric`, `/migrate`, ...) | Plugin spec uses individual `.md` files per command; mapping from `commands.yaml` waits for v3.1+ |
| 17 MCP servers (Databricks, Fabric, Genie, ...) | Users configure their own MCPs in Claude Code separately — these are platform-coupled and need user credentials |
| Hooks (security, cost guard, audit, output compression) | Tightly coupled to the Python orchestration loop |
| Memory layer (ShortTerm + LongTerm + Ledger) | Stateful SQLite DBs; not portable as plugin content |

If you want all of this, use the Python CLI install above. **The two channels coexist** — you can install both, and they share the same source-of-truth agents/skills.

## Next step

→ **[First Query](first-query.md)** for credential setup and your first prompt.
