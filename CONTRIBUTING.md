# Contributing to ai-data-agents

Thank you for considering a contribution. This guide describes how to set up your environment, the workflow we follow, and the quality bars every change must clear before merging.

If you are reporting a security vulnerability, **do not open a public issue** — see [SECURITY.md](SECURITY.md).

---

## Table of contents

- [Code of Conduct](#code-of-conduct)
- [Ways to contribute](#ways-to-contribute)
- [Dev environment setup](#dev-environment-setup)
- [Branch strategy](#branch-strategy)
- [Making a change](#making-a-change)
- [Commit message convention](#commit-message-convention)
- [Pull Request checklist](#pull-request-checklist)
- [Code style](#code-style)
- [Testing](#testing)
- [Documentation](#documentation)
- [Adding a new agent / MCP / KB / skill](#adding-a-new-agent--mcp--kb--skill)
- [Release process](#release-process)

---

## Code of Conduct

This project follows the [Contributor Covenant v2.1](CODE_OF_CONDUCT.md). By participating, you agree to uphold this code. Report unacceptable behavior to **thomaz.rossito@terra.com.br**.

---

## Ways to contribute

- **File a bug** via [Issue → Bug Report](.github/ISSUE_TEMPLATE/bug.yml).
- **Propose a feature** via [Issue → Feature Request](.github/ISSUE_TEMPLATE/feature.yml).
- **Ask a question** via [Issue → Question](.github/ISSUE_TEMPLATE/question.yml) or GitHub Discussions.
- **Submit a Pull Request** — for non-trivial changes, please open an issue first to align on the approach.
- **Improve docs** — typo fixes, clearer examples, ADRs are always welcome.
- **Add a Knowledge Base or Skill** for a domain not yet covered.

---

## Dev environment setup

Requirements:

- Python ≥ 3.11
- `git`
- `make` (most macOS/Linux systems)
- For Fabric SQL / Migration MCPs: ODBC Driver 18 (see `.env.example`)

```bash
# 1. Fork and clone
git clone git@github.com:<your-username>/ai-data-agents.git
cd ai-data-agents

# 2. Create a virtualenv
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Install in editable mode with dev extras
pip install -e ".[dev,ui,monitoring]"

# 4. Install pre-commit hooks
pip install pre-commit
pre-commit install

# 5. Set up credentials (copy and fill)
cp .env.example .env
# Edit .env — ANTHROPIC_API_KEY is required to run anything.

# 6. Verify
make test          # full suite
make lint          # ruff check
make type-check    # mypy
```

---

## Branch strategy

| Branch | Purpose | Merges from | Protected? |
|---|---|---|---|
| `main` | Stable, released versions only | `develop` only via release PR | Yes |
| `develop` | Integration branch for next release | feature/* and fix/* | Yes |
| `refactor/v3.0` | Active v3.0 refactor | feature/* via PR | Yes |
| `feature/<name>` | New feature | branched from `develop` or `refactor/v3.0` | No |
| `fix/<name>` | Bug fix | branched from `develop` or `main` (for hotfix) | No |
| `docs/<name>` | Documentation only | branched from `develop` | No |

Until v3.0.0 ships, treat `refactor/v3.0` as the integration branch. All work targets it.

---

## Making a change

1. **Open an issue first** for anything non-trivial. Get alignment before coding.
2. **Branch off** the correct base (`develop` or `refactor/v3.0`).
3. **Make changes** in small, reviewable commits.
4. **Add or update tests** — every behavior change needs test coverage.
5. **Update documentation** in the same PR (README, ADR, docstrings).
6. **Run** `make lint type-check test` locally before pushing.
7. **Open a PR** against the correct base branch. Fill the PR template.
8. **Respond to review** promptly. Squash-merge is the default.

---

## Commit message convention

We follow **[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)**:

```
<type>(<scope>): <subject>

[body — what and why, not how]

[footer — BREAKING CHANGE, refs #123, etc.]
```

Allowed types:

| Type | Use for |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Docs-only change |
| `style` | Code style (no logic change) |
| `refactor` | Refactor without behavior change |
| `perf` | Performance improvement |
| `test` | Adding or fixing tests |
| `build` | Build system, dependencies |
| `ci` | CI config |
| `chore` | Maintenance, no source change |
| `revert` | Revert a previous commit |

Scope examples: `agents`, `mcp-fabric-sql`, `memory`, `hooks`, `ci`, `docs`.

Examples:

```
feat(agents): add stop_conditions field to AgentMeta
fix(hooks): security_hook missed DROP TABLE with backticks
docs(adr): ADR-009 — choose MkDocs Material for docs site
refactor(memory): move LongTermMemory FTS5 init to lazy property
```

Breaking changes go in the footer:

```
feat(api): rename build_supervisor_options to build_supervisor

BREAKING CHANGE: build_supervisor_options is removed.
Replace with build_supervisor in entry points.
```

---

## Pull Request checklist

The [PR template](.github/PULL_REQUEST_TEMPLATE.md) embeds this checklist. Every box must be checkable:

- [ ] Branch is up-to-date with the base branch.
- [ ] CI passes (ruff, mypy, pytest, linters).
- [ ] New code has unit tests; coverage does not decrease.
- [ ] Documentation updated (README, CHANGELOG, docstrings, ADRs).
- [ ] No new secrets, tokens, or credentials in the diff.
- [ ] Breaking changes flagged in title (`!`) and footer (`BREAKING CHANGE:`).
- [ ] `inventory.md` updated if agents/MCPs/skills/KBs were added or removed.
- [ ] Self-review done before requesting review.

---

## Code style

| Tool | Config | Run with |
|---|---|---|
| **ruff check** (lint) | `pyproject.toml [tool.ruff]` | `make lint` |
| **ruff format** | line-length 100 | `make format` |
| **mypy** (typing) | `pyproject.toml [tool.mypy]` | `make type-check` |
| **bandit** (security lint) | skip B101 | `make security` |
| **shellcheck** (shell) | `.shellcheckrc` *(future)* | shellcheck `start.sh` |

Style guidelines:

- Type hints on all public functions. Internal helpers may omit when obvious.
- Module-level docstrings explain *what* and *why*, not *how*.
- Settings are read locally inside functions (`from config.settings import settings`) to avoid circular imports — see `config/__init__.py`.
- `cache_prefix.md` must remain byte-identical across runs (no timestamps, no IDs).
- Absolute paths in agent prompts (the loader injects `cwd_note` automatically).

---

## Testing

```bash
# Full suite with coverage gate (≥80%)
make test

# Fast: only unit tests (after Phase 6)
make test-fast

# Only one file
pytest tests/unit/test_agents.py -v

# With a marker
pytest -m "integration" -v
pytest -m "requires_network" -v   # skipped by default
```

### Writing tests

- One test = one behavior. Name the test for the behavior, not the implementation.
- Use `tmp_path` fixture for filesystem tests. `tests/conftest.py` already isolates memory SQLite DBs.
- Mock external services (Anthropic API, Databricks, Fabric) — never hit real endpoints in unit tests.
- Mark integration tests with `@pytest.mark.integration`.
- Mark tests that need network with `@pytest.mark.requires_network` (skipped by default).

---

## Documentation

- Every public API has a docstring (Google or NumPy style).
- Significant architectural decisions get an ADR in `docs/adr/` — see [ADR template](docs/adr/_template.md).
- Counts in `README.md` / `PRODUCT.md` / `.claude/CLAUDE.md` are validated by `scripts/gen_inventory.py` (after Phase 4). Do not edit them by hand.

---

## Adding a new agent / MCP / KB / skill

### New agent

1. Create `agents/registry/<your-agent>.md` based on `agents/registry/_template.md`.
2. Fill the frontmatter completely: `name`, `description`, `model`, `tools`, `mcp_servers`, `kb_domains`, `skill_domains`, `tier`, `stop_conditions`, `escalation_rules`, `examples`.
3. Add the agent to `agents/prompts/supervisor_prompt.py` (Tier table).
4. Add tests in `tests/unit/test_agents.py` for the agent's invariants.
5. Run `make lint-registry` (after Phase 3) to validate.

### New MCP server

1. Copy `mcp_servers/_template/` to `mcp_servers/<name>/`.
2. Implement `server_config.py::get_<name>_mcp_config()` and export `<NAME>_MCP_TOOLS`.
3. Register in `config/mcp_servers.py::ALL_MCP_CONFIGS`.
4. Add credentials field in `config/settings.py::Settings` (default `""`).
5. Add alias in `agents/loader.py::MCP_TOOL_SETS` (`<name>_all`, `<name>_readonly`).
6. Add tests in `tests/unit/test_mcp_configs.py`.
7. Update `.env.example` with the new credential.
8. Run `make lint-mcp` (after Phase 3).

### New Knowledge Base domain

1. Copy `kb/_templates/` structure to `kb/<domain>/`.
2. Create `index.md` with frontmatter `domain`, `updated_at`, `agents:` (list of consumers).
3. Add at least one content file (concept, pattern, or anti-pattern).
4. Reference from at least one agent's `kb_domains:` in the registry.
5. Run `make lint-kb` (after Phase 3).

### New Skill

1. Create `skills/<domain>/<skill-name>/SKILL.md` with frontmatter `name`, `description`.
2. Reference from at least one agent's `skill_domains:`.
3. Run `make lint-skills` (after Phase 3).

---

## Release process

See [docs/refactor-v3/PLAN.md](docs/refactor-v3/PLAN.md) Phase 9 for the post-v3.0 release process.

Current process (manual until Phase 9):

```bash
# 1. Update version in pyproject.toml, VERSION (after Phase 9), README badge.
# 2. Update CHANGELOG.md (follow Keep a Changelog).
# 3. PR to main with title "release: vX.Y.Z".
# 4. After merge, tag the merge commit:
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
# 5. GitHub Release with notes copied from CHANGELOG.
```

---

## Getting help

- **Documentation**: [`docs/`](docs/) and [`kb/`](kb/)
- **Existing issues**: [GitHub Issues](https://github.com/ThomazRossito/ai-data-agents/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ThomazRossito/ai-data-agents/discussions)
- **Direct contact**: thomaz.rossito@terra.com.br

---

*Thank you for making `ai-data-agents` better.*
