# Installation

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

## Next step

→ **[First Query](first-query.md)** for credential setup and your first prompt.
