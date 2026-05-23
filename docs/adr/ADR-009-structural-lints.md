# ADR-009: Structural lints as CI gate against declarative drift

> **Status**: Accepted
> **Date**: 2026-05-22
> **Deciders**: @ThomazRossito
> **Tags**: ci, quality, drift-prevention, governance

## Context

The project is heavily **declarative**:

- 15 agents declared as YAML frontmatter in `agents/registry/*.md`
- 17 MCPs registered in `config/mcp_servers.py::ALL_MCP_CONFIGS`
- 17 KB domains under `kb/<domain>/index.md` with optional `agents:` field
- 48 SKILL.md files indexed via `skill_domains` from agents
- 39 slash commands in `config/commands.yaml` referencing agents and skills

These metadata layers cross-reference each other at runtime:
- Agent's `mcp_servers:` must exist in `ALL_MCP_CONFIGS`
- Agent's `kb_domains:` must be a directory in `kb/`
- Agent's `skill_domains:` must be a directory in `skills/`
- KB's `agents:` list should match what agents actually declare
- Slash command's `agent:` must exist in the registry
- Slash command's `skills:` paths must exist on disk

**The problem**: when these cross-references break (typo in a domain name, KB
renamed without updating agents, MCP added without alias in `MCP_TOOL_SETS`),
the system **silently degrades**. The loader is defensive (skips missing KBs,
ignores unknown aliases), so users only discover the drift when an agent
behaves unexpectedly in production.

Examples found during the v3.0 refactor:
- `data-quality-steward` and `governance-auditor` were listed in
  `kb/industry/index.md::agents` but neither declared `industry` in their
  `kb_domains` — KB pretended to serve them, agents ignored the KB.
- `/python` slash command referenced `kb/python/index.md` but the actual KB is
  `kb/python-patterns/` — the skill reference was unreachable.
- 2 SKILL.md files used `skill:` instead of `name:` in frontmatter — the
  loader silently fell back to the directory name.
- 4 KBs had no frontmatter at all; 10 had only `mcp_validated:` (3 different
  styles coexisting).
- `memory_mcp` directory needed a function named `get_memory_mcp_config`
  (not the regular `get_<dir>_mcp_config` pattern) — typo-prone exception.

All of these were silent: code worked, tests passed, lint passed. Only manual
audit revealed them.

## Decision

**Add 5 structural lints as CI gate.** Each is a standalone Python script
under `scripts/lint_*.py`, with no third-party dependencies beyond what the
project already requires:

| Lint | Validates | Detects |
|---|---|---|
| `lint_registry.py` | 15 agents in `agents/registry/` | Missing fields, invalid tier/effort/permission_mode, MCP/KB/skill references that don't exist, duplicate agent names, KB↔agent cross-check |
| `lint_kb.py` | 17 KB domains | Missing `index.md`, invalid frontmatter, agent references that don't exist, stale `updated_at` (>180d), broken internal links |
| `lint_skills.py` | 48 SKILL.md files | Missing `name`/`description`, `skill:` typo (should be `name:`), `name` != directory name, orphan skill domains (no agent references) |
| `lint_mcp_configs.py` | 17 MCP server configs | Missing `get_<n>_mcp_config()` function, function raises on call, wrong return shape, tools without `mcp__<n>__` prefix, missing `<n>_all` alias in `MCP_TOOL_SETS` |
| `lint_commands.py` | 39 slash commands | Missing required fields, unknown agent, invalid `doma_mode`, broken skill paths, missing `{task}` placeholder |

Each lint:
- Has a clear severity model: `ERROR` (CI gate), `WARNING` (not blocking, but
  reported), `INFO` (informational only).
- Supports `--quiet`, `--strict` (warnings become errors), `--json` (machine
  output for tooling).
- Is invokable individually (`make lint-registry`, `make lint-kb`, etc) or as
  a bundle (`make lint-all`).
- Documents allow-lists for legitimate exceptions inline (e.g. `AGENT_NULL_BY_DESIGN`
  in `lint_commands.py` for `/plan`, `/workflow`, `/party`, etc).

CI runs them as a dedicated job `validate-structure` that the `test` job
depends on. CI failure prevents merge.

## Consequences

### Positive
- **Drift becomes impossible silently.** Every cross-reference is validated
  on every push and PR. The 7 silent debts discovered during the v3.0 refactor
  would have been caught at the moment of introduction.
- **Self-documenting invariants.** The lint code itself describes the
  expected structure — onboarding contributors can read the linters to
  understand the conventions.
- **Defensive coding becomes optional.** Now that lint catches references
  upstream, downstream code can be less paranoid about missing KBs, missing
  MCPs, etc.
- **Refactor safety.** Renaming a KB, a skill, or an agent will surface every
  consumer that breaks — no more "I think I updated everywhere".
- **No new dependencies.** All linters use only stdlib + `pyyaml` (already a
  project dep) + the project's own `utils/frontmatter.py`. CI overhead < 30s.

### Negative
- **Allow-lists need maintenance.** When a legitimate exception arises (e.g.
  a new multi-agent command), the linter must be updated to whitelist it.
  Mitigated by error messages that tell the contributor exactly which constant
  to update.
- **Lint logic itself can have bugs.** A lint that reports false positives
  blocks development. Mitigated by INFO/WARNING graduation, manual review
  before adding ERROR, and tests for the linters (Phase 3.8 — TODO).
- **Slightly slower CI** (~20-30 seconds added). Acceptable for the gain.

### Neutral / unknown
- **Should other declarative areas also have lints?** Candidates for future
  ADRs: `.env.example` (every documented var should map to a `Settings` field),
  `pyproject.toml` (entry points should match actual modules), `hooks/`
  registration (every hook in `supervisor.py` should exist on disk).
- **Should the linters be unified into a single `make lint-structure`?**
  Currently they're 5 separate scripts. Unified would be simpler to invoke but
  harder to maintain in parallel.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| **Runtime validation in loader** | Always-on | Errors only surface when user runs that path; many never trigger in test | Lint at CI time is earlier and covers untested paths |
| **Static analysis via `mypy --strict`** | Existing tool | mypy doesn't read YAML/Markdown frontmatter | Can't validate references that live outside Python |
| **Schema validation via `pydantic` models for each YAML** | Strongly typed | Heavy refactor of YAML parsing; loses round-trip preservation | Too invasive for current code |
| **Manual reviews / docs** | No tooling | Doesn't scale; humans forget | The 7 debts proved this insufficient |
| **Single mega-lint script** | One command | One bug breaks everything | 5 focused scripts are easier to maintain and reason about |

## References

- `scripts/lint_registry.py`, `scripts/lint_kb.py`, `scripts/lint_skills.py`,
  `scripts/lint_mcp_configs.py`, `scripts/lint_commands.py` — implementations
- `Makefile` — `lint-all`, `lint-registry`, etc. targets
- `.github/workflows/ci.yml` — `validate-structure` job
- `docs/refactor-v3/PLAN.md` Phase 3 — original plan
- Drift incidents discovered during this refactor (documented in commit
  messages of the corrections):
  - `kb/industry` ↔ `data-quality-steward`/`governance-auditor` (kb-missing-declaration)
  - `/python` → `kb/python/index.md` (skill-path-missing)
  - 2 SKILL.md with `skill:` typo (skill-key-typo)
  - 4 KBs without frontmatter (frontmatter-invalid)
  - 10 KBs with minimal vs structured style inconsistency
