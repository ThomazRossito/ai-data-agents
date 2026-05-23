# Migration: v2.x → v3.0

v3 is a **breaking change** for any external code that imports from `ai-data-agents`. The good news: the breakage is mechanical and a one-liner Python script fixes it.

## What changed

### 1. Top-level packages moved into `data_agents/` namespace

All 13 Python packages that used to live at the repo root are now under `data_agents/`:

| v2.x import | v3.0 import |
|---|---|
| `from agents.loader import preload_registry` | `from data_agents.agents.loader import preload_registry` |
| `from config.settings import settings` | `from data_agents.config.settings import settings` |
| `from hooks.audit_hook import audit_tool_usage` | `from data_agents.hooks.audit_hook import audit_tool_usage` |
| `from commands.parser import parse_command` | `from data_agents.commands.parser import parse_command` |
| `from memory.store import MemoryStore` | `from data_agents.memory.store import MemoryStore` |
| `from mcp_servers.databricks_genie.server import ...` | `from data_agents.mcp_servers.databricks_genie.server import ...` |
| `from utils.frontmatter import parse_yaml_frontmatter` | `from data_agents.utils.frontmatter import parse_yaml_frontmatter` |
| (same for: `compression`, `workflow`, `evals`, `ui`, `visualization`, `monitoring`) |

### 2. CLI entry point

| v2.x | v3.0 |
|---|---|
| `python main.py "<query>"` | `python -m data_agents.cli "<query>"` |
| `ai-data-agents = "main:main"` in pyproject | `ai-data-agents = "data_agents.cli:main"` |

The `ai-data-agents` console script still works the same way after reinstalling. Only `python main.py` shell aliases break.

### 3. Optional extras are now strict

These features were always-on in v2 but are now opt-in:

| Feature | Old behavior | New behavior |
|---|---|---|
| Chainlit UI | always installed | `pip install "ai-data-agents[ui]"` |
| Streamlit monitoring | always installed | `pip install "ai-data-agents[monitoring]"` |
| FastAPI visualization | always installed | `pip install "ai-data-agents[viz]"` |
| `markdown2` (HTML export) | core dep | moved to `[ui]` |
| `fastembed` semantic embeddings | always-on if installed | `pip install "ai-data-agents[memory]"` |

If you try to use a feature without its extra, you get a clean `ImportError` telling you the right `pip install` command. Example:

```python
>>> from data_agents.ui.exporter import export_html
ImportError: markdown2 não instalado. Para habilitar export HTML de conversas:
  pip install -e ".[ui]"
  ou: pip install markdown2>=2.4
```

### 4. Memory paths

`Settings.derive_memory_db_paths` now generates paths under `data_agents/memory/data/<project_id>` (was `memory/data/<project_id>`).

If you had `.env` overrides for `LONG_TERM_DB_PATH` / `SHORT_TERM_DB_PATH` / `EMBEDDER_CACHE_DB_PATH` / `MEMORY_DATA_DIR`, **those remain in effect** — explicit values always win over derived defaults.

If you didn't override and have existing v2 data, you have two options:

- **Move the data** (preserves history):
    ```bash
    mkdir -p data_agents/memory/data
    mv memory/data/* data_agents/memory/data/
    rm -rf memory/data
    ```
- **Start fresh** (cleaner): leave v2 data behind; v3 generates new DBs on first run.

## Automated import rewrite

If you have your own code that imports from this project, run this Python snippet from your project root:

```bash
python3 - <<'EOF'
"""Rewrite imports from v2 to v3 namespace."""
import re
from pathlib import Path

PKGS = "agents config hooks commands memory compression workflow utils mcp_servers evals ui visualization monitoring".split()
PKGS_RE = "|".join(PKGS)

for f in Path(".").rglob("*.py"):
    # Skip your own venv / cache
    if any(p in f.parts for p in [".venv", "venv", "__pycache__", ".cache", "build", "dist"]):
        continue

    text = f.read_text(encoding="utf-8")
    new_text = text
    for line in text.splitlines(keepends=True):
        s = line.lstrip()
        if not (s.startswith("from ") or s.startswith("import ")):
            continue
        if "data_agents." in line:
            continue
        m = re.match(rf"^(\s*)(from|import)\s+({PKGS_RE})(\.|\s|$)", line)
        if m:
            indent, kw, pkg, sep = m.groups()
            new_line = line.replace(f"{kw} {pkg}", f"{kw} data_agents.{pkg}", 1)
            new_text = new_text.replace(line, new_line, 1)

    if new_text != text:
        f.write_text(new_text, encoding="utf-8")
        print(f"updated: {f}")
EOF
```

The script is **idempotent**: running it twice does nothing on the second pass (skips lines that already say `data_agents.`).

## String references in patches / mocks

If you have tests with `patch("agents.X")` strings, they need the same rewrite. Same script catches those too — see the [Phase 7 commits](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/CHANGELOG.md#breaking--phase-7-python-namespace-migration-data_agents) for what we did in our own tests (702 references rewritten across 86 files).

## What did NOT change

- Repository root layout for **data and config**: `kb/`, `skills/`, `tests/`, `scripts/`, `docs/`, `logs/`, `output/`, `.env` stay where they were.
- Agent definitions in `data_agents/agents/registry/*.md` keep the same YAML format (with Phase 5 enrichment in `stop_conditions` / `escalation_rules` / `examples`).
- Slash commands in `data_agents/config/commands.yaml` keep the same keys.
- Constitution rules (S1–S7).
- All MCP tool names (`mcp__<server>__<tool>`).

## After upgrading

1. Reinstall: `pip install --upgrade ai-data-agents` (or `pip install -e .` if dev-installed).
2. Run the import rewrite script above on your own code.
3. Run your tests — anything that still references `agents.X` from outside `data_agents/` will surface as `ModuleNotFoundError`.
4. Verify the CLI works:
    ```bash
    ai-data-agents "/health"   # platform connectivity check
    ```
5. Check `data_agents/memory/data/` exists and the `<project_id>` subdir starts populating after your first session.

## Questions?

- Open an issue on GitHub: <https://github.com/ThomazRossito/ai-data-agents/issues>
- For unrelated migrations (SQL Server → Databricks, on-prem → cloud), see [Tutorials](../tutorials/index.md) — the `migration-expert` agent handles those.
