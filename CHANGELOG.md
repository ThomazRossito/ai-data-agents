> All notable changes to this project are documented here.
>
> Format: [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/).
> Versioning: [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

# Changelog

## [Unreleased]

### Added — Phase 12: Claude Code plugin distribution

A third distribution channel: `ai-data-agents` is now available as a
[Claude Code plugin](https://code.claude.com/docs/en/plugin-marketplaces),
bringing the 15 agents + 48 skills into Claude Code natively for users who
prefer that over the Python CLI.

**Install (in Claude Code):**

```bash
claude plugin marketplace add ThomazRossito/ai-data-agents
claude plugin install ai-data-agents@thomazrossito-marketplace
```

**Scope (per ADR-011 — intentional minimal scope for v3.0-rc1):**

| Included | Excluded (Python CLI only) |
|---|---|
| 15 specialist agents | 39 slash commands |
| 48 operational skills | 17 MCP servers |
| | Hooks (security, cost guard, audit) |
| | Memory layer (SQLite + ledger) |

Plugin users invoke agents via natural language inside Claude Code. The
scope decision is documented in ADR-011 (defer commands + MCPs to v3.1+).

**New files:**

- `.claude-plugin/marketplace.json` — declares 1 plugin under owner
  Thomaz Rossito
- `plugins/ai-data-agents/.claude-plugin/plugin.json` — plugin metadata
  (name, description, version synced from `VERSION`, keywords, license)
- `plugins/ai-data-agents/README.md` — plugin-specific docs covering
  install, what's included vs excluded, sync workflow
- `plugins/ai-data-agents/agents/` — 15 generated agent `.md` files
  (synced from `data_agents/agents/registry/`)
- `plugins/ai-data-agents/skills/` — 48 generated skill directories
  (flattened from `skills/<domain>/<name>/` to `skills/<name>/`)
- `scripts/build_plugin.sh` — idempotent sync from canonical sources to
  plugin view; collision detection on flattened skill names; version
  injected from `VERSION` file
- `.github/workflows/plugin-validate.yml` — 2 jobs: JSON-validate manifests
  + assert `build_plugin.sh` produces zero diff against committed content
- `docs/adr/ADR-011-claude-code-plugin-scope.md` — scope decision
  documented per Michael Nygard format

**Extended files:**

- `.github/workflows/release.yml` — build step now also produces
  `dist/ai-data-agents-plugin-<version>.tar.gz`; GitHub Release attaches
  it alongside wheel/sdist (glob `dist/*.tar.gz` covers both)
- `README.md` — Início Rápido section adds tabs (Python CLI vs Plugin)
- `docs/site/index.md` — quickstart section adds tabs for both channels
- `docs/site/getting-started/installation.md` — new "Claude Code plugin"
  section with full feature comparison

### Added — Phase 11: Documentation site (MkDocs Material)

The project now publishes its docs as a navigable site at
https://thomazrossito.github.io/ai-data-agents/ — built with MkDocs Material
(see ADR-010 for the framework choice rationale).

**New files:**

- `mkdocs.yml` — site config with Material theme, light/dark palette,
  4-tab navigation + Migration tab
- `docs/site/` — source for the published site (14 pages):
    - `index.md` — landing + 60-second overview
    - `getting-started/` — installation, first query, slash commands
    - `concepts/` — architecture, constitution (S1–S7), memory, hooks, tier system
    - `tutorials/` — SQL Server → Databricks migration walkthrough, Medallion pipeline
    - `reference/` — agents (15), MCPs (17), slash commands (39), ADRs (10), security
    - `migration/v2-to-v3.md` — automated import rewrite for v2 consumers
- `docs/adr/ADR-010-docs-site-mkdocs-material.md` — framework decision
- `.github/workflows/docs.yml` — `mkdocs build --strict` on every push/PR;
  deploy to `gh-pages` only on main/refactor branches. Path filter narrow.

**New Makefile targets:**

- `make docs-serve` — local preview on http://127.0.0.1:8000
- `make docs-build` — strict static build to `site/`
- `make docs-deploy` — manual `mkdocs gh-deploy` (CI does this automatically)

**New pyproject extra:**

- `[docs]` — `mkdocs`, `mkdocs-material`, `pymdown-extensions`. Only the
  maintainer building the site needs it; end users consume the public URL.

**Deferred:**

- `mkdocstrings` (auto-generated API reference) — overhead of treating
  docstrings as a public contract is premature for v3.0-rc1. Reopen post-3.0.0
  if users ask. See ADR-010 for rationale.

### Added — Phase 10: Hardening (partial — pragmatic scope)

After auditing the original Phase 10 plan against the project's real use case
(open-source + CI&T consulting, single-user), 3 of 7 tasks were deliberately
skipped with documented justification in `docs/refactor-v3/PLAN.md`. The 4 that
landed:

- **Structured logging contract** — `data_agents/hooks/session_logger.py` now
  includes `session_id` in every entry, completing the canonical triplet
  (`session_id`, `agent_name`, `tool_use_id`) already enforced by
  `audit_hook.py`. New test `tests/unit/test_structured_logging.py` (4 cases)
  validates the contract per-file and protects against future hooks gaining
  JSONL writes without including canonical fields.

- **`make security-review`** — new `scripts/security_review.sh` running
  bandit + pip-audit + a custom regex-based secrets scan in sequence with
  per-step pass/fail and a consolidated summary. 8 well-known credential
  patterns (Anthropic, Moonshot, Databricks PAT, AWS, GitHub PAT, etc.) plus
  contextual `SECRET=value` heuristic. Negative markers (`placeholder`,
  `<your-token>`, `os.environ`, etc.) suppress false positives. Validated
  locally with zero hits on a 600+ file scan.

- **Performance baselines (skeleton)** — `tests/perf/` with auto-marker
  `@pytest.mark.perf` + `@pytest.mark.slow`, opt-in via `make test-perf`.
  3 baselines: `preload_registry` (~30ms target / 100ms gate), `build_escalation_graph`
  (~5ms / 20ms gate), `parse_yaml_frontmatter` (~2ms / 10ms gate). Not wired
  into main CI (perf is flaky on shared GitHub Actions runners); intended
  for local regression checks before releases. Marker `perf` registered in
  `pyproject.toml`.

- **STRIDE threat model** — `docs/SECURITY_THREAT_MODEL.md` documenting
  4 trust boundaries (User→Supervisor, Supervisor→Subagent, Subagent→MCP,
  MCP→Platform) + 2 cross-cutting concerns (Hooks layer, Memory layer).
  Each threat tagged with STRIDE category, likelihood, impact, current
  mitigation, and known debt. Top-3 priorities listed for future hardening
  (pre-commit gitleaks, SBOM/signing, hook-bypass audit on SDK upgrades).

### Skipped with justification

- **OpenTelemetry tracing** — `audit_hook.py` already produces filterable JSONL
  with session/agent/tool_use IDs. OTel would require Jaeger/Tempo standalone
  + manual instrumentation; cost > value for a single-process system.
- **Multi-tenancy module** — `settings.project_id` already provides filesystem
  isolation between executions. Reopen if ai-data-agents becomes SaaS.
- **SLA.md** — SLA is a commercial-service commitment. Open-source individual
  project doesn't ship operational promises. Reopen if/when scope changes.

### Changed — Phase 8: Optional extras isolation (lighter core)

The core install (`pip install ai-data-agents`) is now significantly lighter. Optional features moved behind extras with clear `ImportError` messages.

**What's now opt-in (was core or top-level imports):**

| Module | Required extra | Was |
|---|---|---|
| `data_agents.ui.chainlit_app` | `[ui]` | top-level `import chainlit` |
| `data_agents.ui.exporter` | `[ui]` (now bundles `markdown2`) | `markdown2` was core |
| `data_agents.monitoring.app` | `[monitoring]` | top-level `import streamlit` |
| `data_agents.visualization.server` | `[viz]` | top-level `import fastapi` |
| `data_agents.visualization.ws_broker` | `[viz]` | top-level `import fastapi` |
| `data_agents.visualization.watcher` | `[viz]` | top-level `import watchdog` |
| `data_agents.memory.embedder` (already gold standard) | `[memory]` | lazy + clean ImportError (no change) |

**Pattern applied to each top-level module:**

```python
# Phase 8: <pkg> é dep opcional do extra [X]
try:
    import <pkg>
except ImportError as _exc:
    raise ImportError(
        "<pkg> não instalado. Para habilitar <feature>:\n"
        "  pip install -e \".[<X>]\""
    ) from _exc
```

**`pyproject.toml` change:**
- `markdown2>=2.4` moved from `[project.dependencies]` to `[project.optional-dependencies.ui]`. Core install drops one dep.

**New CI workflow `.github/workflows/install-matrix.yml`:**
- Tests 6 install combinations: `core`, `[ui]`, `[ui,monitoring]`, `[viz]`, `[memory]`, `[all]`
- For each combination, verifies a list of modules that SHOULD import successfully AND a list that SHOULD fail with `ImportError` containing the string `pip install` (proves the message is user-friendly).
- Triggered on changes to `pyproject.toml` or any of the protected modules.

### **BREAKING — Phase 7: Python namespace migration (`data_agents/`)**

All top-level Python packages have been consolidated under the `data_agents` namespace. This is a **breaking change** for any external code that imports from the project.

**Before (v2.x):**
```python
from agents.loader import preload_registry
from config.settings import settings
from hooks.audit_hook import audit_tool_usage
```

**After (v3.0):**
```python
from data_agents.agents.loader import preload_registry
from data_agents.config.settings import settings
from data_agents.hooks.audit_hook import audit_tool_usage
```

**Migration command for existing code (run from project root):**

```bash
# Backup first
git stash

# Rewrite all imports (Python script — safer than sed because handles indented imports too)
python3 - << 'EOF'
import re
from pathlib import Path
PKGS = "agents config hooks commands memory compression workflow utils mcp_servers evals ui visualization monitoring".split()
for f in Path(".").rglob("*.py"):
    text = f.read_text(encoding="utf-8")
    new_text = text
    for line in text.splitlines(keepends=True):
        s = line.lstrip()
        if not (s.startswith("from ") or s.startswith("import ")):
            continue
        if "data_agents." in line:
            continue
        m = re.match(r"^(\s*)(from|import)\s+([\w.]+)", line)
        if m and m.group(3).split(".")[0] in PKGS:
            new_text = new_text.replace(line, line.replace(m.group(3), f"data_agents.{m.group(3)}", 1), 1)
    if new_text != text:
        f.write_text(new_text, encoding="utf-8")
EOF
```

**What moved:**
- `agents/` → `data_agents/agents/`
- `config/` → `data_agents/config/`
- `hooks/` → `data_agents/hooks/`
- `commands/` → `data_agents/commands/`
- `memory/` → `data_agents/memory/`
- `compression/` → `data_agents/compression/`
- `workflow/` → `data_agents/workflow/`
- `utils/` → `data_agents/utils/`
- `mcp_servers/` → `data_agents/mcp_servers/`
- `evals/` → `data_agents/evals/`
- `ui/` → `data_agents/ui/`
- `visualization/` → `data_agents/visualization/`
- `monitoring/` → `data_agents/monitoring/`
- `main.py` → `data_agents/cli.py`

**What did NOT move (stays at repo root):**
- `scripts/` — development tooling, not part of the installable package
- `tests/` — test suite
- `kb/`, `skills/`, `docs/`, `logs/`, `output/` — data and artifacts

**Entry points (pyproject.toml):**
- `ai-data-agents` now points to `data_agents.cli:main` (was `main:main`)
- 6 MCP server entry points renamed to `data_agents.mcp_servers.<name>.server:main`

**Migration notes for the CLI:**
- Old: `python main.py "<query>"` → New: `python -m data_agents.cli "<query>"`
- Old: `make test` ran everything → New: runs `unit + integration` only (Phase 6); use `make test-all` for everything including e2e

### Changed — Phase 6: Test suite reorganization (unit/integration/e2e)

- **`tests/` restructured** into three categorical subdirectories:
  - `tests/unit/` — 52 files (1242 tests). Mock-only, no network, no real MCP, < 1s typical. Auto-tagged `@pytest.mark.unit` via `tests/unit/conftest.py`.
  - `tests/integration/` — 5 files (150 tests). Touch local SQLite/JSONL as part of the contract (not just fixture storage). Auto-tagged `@pytest.mark.integration`.
  - `tests/e2e/` — 0 files (empty by design). Auto-tagged `@pytest.mark.e2e` + `@pytest.mark.requires_network`. README documents admission criteria and candidate future tests.
- **Files moved** preserve `tests/conftest.py` (global SQLite isolation fixture) at root — all subdirs inherit automatically.
- **`pyproject.toml`** registers 5 markers (`unit`, `integration`, `e2e`, `requires_network`, `slow`) with descriptive help text; eliminates `PytestUnknownMarkWarning`.

### Added — Phase 6 CI + Makefile targets

- **`.github/workflows/ci.yml`**: `test` job replaced by parallel `test-unit` (coverage gate ≥80%, testmon cache, 10min timeout) and `test-integration` (no coverage gate, runs in parallel, 10min timeout). Both gated by quality/structure/security jobs.
- **`.github/workflows/test-e2e.yml`** (NEW): nightly cron at `0 3 * * *` UTC + `workflow_dispatch` for manual triggering. Skips cleanly with a notice when `tests/e2e/` is empty. Injects credentials from repository secrets, uploads logs as artifacts (30-day retention).
- **`Makefile`**: 5 new test targets — `test` (unit + integration default), `test-fast` (unit only, < 30s alvo), `test-int` (integration only), `test-e2e` (real services), `test-all` (everything). Old `test` recipe replaced with `test: test-fast test-int` aggregation.

### Documentation

- **`docs/refactor-v3/test-classification.md`** (NEW): inventário completo dos 57 arquivos de teste com categoria, LOC, flags, e justificativa por arquivo. Documenta a heurística aplicada ("é débito ou foi feito assim de propósito?") e por que 0 e2e existem hoje no projeto.

### Added — Phase 5: Rich agent frontmatter + escalation graph injection

- **`utils/frontmatter.py` migrated to pyyaml** with `_SafeLoaderNoBoolAlias` — a custom
  SafeLoader subclass that removes YAML 1.1 boolean aliases (yes/no/on/off) so they
  remain strings. Resolves two real bugs: (a) folded scalars `description: >-` (used by
  `databricks-dbsql` and `databricks-execution-compute`) now parse as concatenated text
  instead of literal `>-`; (b) the YAML 1.1 trap `country: NO` becoming `False` is gone.
  Backward compatible — same `parse_yaml_frontmatter(content) -> tuple[dict, str]` signature.
- **`agents/registry/_template.md` extended** with `description: |` block scalar (Example 1/2/3 stanzas), `stop_conditions: []` (situations where the agent must halt), and `escalation_rules: []` (structured `{trigger, target, reason}` dicts).
- **`agents/loader.py::AgentMeta` extended** with new optional fields `stop_conditions: list[str]`, `escalation_rules: list[dict[str, str]]`, `skill_domains: list[str]`. Preload is defensive — malformed entries are coerced or skipped, never crash the loader (lint catches violations separately).
- **15/15 agents migrated** with rich frontmatter:
  - 93 stop_conditions total (avg ~6 per agent)
  - 66 escalation_rules total (avg ~4 per agent)
  - Every escalation target validated against the registry via `cross_check_escalation_targets()`
- **`agents/loader.py::build_escalation_graph_markdown()`** consolidates all escalation_rules into a single Markdown table at Supervisor build time. The Supervisor now sees the full escalation graph (Source → Target → Trigger → Reason) appended to its system prompt as an authoritative whitelist.
- **Supervisor Step 3.5 (Escalation Handling) upgraded** in `agents/prompts/supervisor_prompt.py` — references the injected graph as the source of truth, flags off-graph escalations in synthesis, and refuses to auto-substitute targets that don't exist in the registry.
- **`scripts/lint_registry.py` extended** with 7 new validation rules:
  - `stop-conditions-type` / `stop-conditions-item-type`
  - `escalation-rules-type` / `escalation-rule-not-dict` / `escalation-rule-missing-key` / `escalation-target-type`
  - `escalation-self-target` / `escalation-target-unknown` (cross-check phase)

### Added — Tests

- **`tests/test_frontmatter.py`** (NEW, 27 tests): YAML 1.1 boolean trap, block scalars (`>-`, `|`, `|-`), multiline lists, list-of-dicts, inline/block dicts, numeric types, edge cases (empty frontmatter, non-dict top-level, invalid YAML).
- **`tests/test_agent_preload.py` extended** (+19 tests): AgentMeta defaults for Phase 5 fields, preload parsing of stop_conditions/escalation_rules/skill_domains, multiline description preservation, defensive handling of malformed entries, and full coverage of `build_escalation_graph_markdown()` (empty graph, populated graph, pipe escaping, empty-target skipping, footer rule count, registry fallback).

### Changed

- **`agents/supervisor.py`** now injects the escalation graph into `system_prompt` at build time via `build_escalation_graph_markdown(preload_registry())`. Falls back gracefully (logged warning) if the graph cannot be generated — Step 3.5 then uses pattern-matching fallback only.

## [2.3.0] — 2026-05-09

### Added — Chainlit UI completeness: /workflow, /geral streaming, /sessions, /resume

- **`/workflow` na Chainlit UI** (`ui/chainlit_app.py`): `_handle_workflow()` executa
  workflows WF-01 a WF-05 com feedback em tempo real — um `cl.Step` por fase via novo
  `step_callback` no `WorkflowRunner`. Fases com `require_human_approval=True` pausam e
  exibem botões `cl.Action` (Aprovar/Abortar) resolvidos via `asyncio.Future` com timeout
  de 5 min. Action callbacks `wf_approve` / `wf_abort` registrados.
- **`StepCallback` em `WorkflowRunner`** (`commands/workflow.py`): novo parâmetro opcional
  `step_callback: StepCallback | None` chamado com status `"start"` / `"done"` / `"error"`
  por fase. Backward-compatible (default `None`). Tipo `StepCallback` exportado.
- **`/geral` streaming de tokens** (`commands/geral.py`, `ui/chainlit_app.py`): parâmetro
  `token_callback` em `run_geral_query()` — quando fornecido, usa `client.messages.stream()`
  e chama o callback com cada chunk de texto. Chainlit passa `response_msg.stream_token` como
  callback, exibindo tokens à medida que chegam. CLI sem callback continua usando
  `messages.create()` (backward-compatible).
- **`/sessions` na Chainlit UI** (`ui/chainlit_app.py`): `_handle_sessions()` formata lista
  de sessões como tabela Markdown. Suporta `/sessions`, `/sessions all` e `/sessions <id>`
  para ver transcript completo. Não requer modo Supervisor.
- **`/resume` na Chainlit UI** (`ui/chainlit_app.py`): `_handle_resume()` constrói prompt
  de retomada via `build_resume_prompt_for_session()` e envia ao Supervisor. Suporta
  `/resume last` (sessão mais recente) e `/resume <session-id>`. Ativa modo Supervisor
  automaticamente se necessário.
- **`/workflow`, `/sessions`, `/resume` no `COMMAND_GROUPS`** (`ui/ui_config.py`): grupos
  `"🎉 Multi-Agente"` e `"📂 Sessões"` atualizados para aparecer na tela de boas-vindas.
- **13 novos testes** (`tests/test_geral_command.py`): `TestRunGeralQuery` cobre path
  non-streaming, streaming com callback, acumulação de chunks e isolação do `messages.stream`.
- **5 novos testes** (`tests/test_workflow.py`): `StepCallback` start/done/error, None sem
  exceção, type annotation.

## [2.2.0] — 2026-05-09

### Added — Chainlit UI parity + Lições Aprendidas dashboard

- **`/analyze-project` como comando real** (`commands/analyze.py`): 5 grupos de agentes
  (default, quality, arch, databricks, fabric), prompts por agente com 5 seções estruturadas,
  relatório consolidado em `output/analyze-project/`. Antes existia apenas como comando
  Claude Code, causando alucinação no Supervisor.
- **Anti-alucinação no Supervisor** (`agents/prompts/supervisor_prompt.py`): seção
  `SLASH COMMANDS REFERENCE` com tabela de comandos reais e instrução explícita de nunca
  inventar comandos fora da lista.
- **`/analyze-project` na Chainlit UI** (`ui/chainlit_app.py`): `_handle_analyze_project()`
  intercepta o comando antes do Supervisor, roda agentes em paralelo via `asyncio.gather`,
  exibe um `cl.Step` por agente durante a execução e resultados como `cl.Message` individuais.
- **`/party` na Chainlit UI** (`ui/chainlit_app.py`): `_handle_party()` implementado com o
  mesmo padrão — suporta todos os flags (`--quality`, `--arch`, `--full`, `--engineering`,
  `--migration`) e listas explícitas de agentes. Antes caía no Supervisor com `doma_prompt`
  truncado.
- **`/geral` direct dispatch na Chainlit UI** (`ui/chainlit_app.py`): `_handle_geral()`
  chama `run_geral_query()` diretamente via `anthropic.AsyncAnthropic` com Haiku (T0) —
  sem Supervisor, sem Agent tool, ~95% mais barato. Mantém histórico de conversa
  (`_geral_history`) para follow-ups na sessão.
- **Página "🧠 Lições Aprendidas"** no Streamlit (`monitoring/app.py`): `load_lessons()`
  lê `memory/data/lesson_learned/*.md` via frontmatter. Exibe métricas (total ativas/expiradas,
  avg confidence, agentes com lições), distribuição por trigger e agente, lista filtrável com
  agente + trigger + show-expired, detalhe expandível por lição com conteúdo e tags.
- **`/party` e `/analyze-project` no `COMMAND_GROUPS`** (`ui/ui_config.py`): grupo
  `"🎉 Multi-Agente"` adicionado para aparecer no texto de boas-vindas do Chainlit.
- **26 novos testes** (`tests/test_analyze_command.py`): parser, grupos, prompts e
  consolidador de relatório.

### Fixed

- **Monitoring Observability**: `"analyze"` adicionado ao `_SUPERVISOR_LIKE` set para
  sessions do tipo `/analyze-project` aparecerem corretamente no dashboard.
- **Escape sequences**: `\|` em tabelas Markdown no `supervisor_prompt.py` corrigido para `|`.

## [2.1.0] — 2026-05-09

### Added — Autonomous Learning System + S4 Selective Relaxation

- **LESSON_LEARNED memory type** (`memory/types.py`): 8º tipo de memória com decay de 30 dias.
  Captura erros, operações de alto custo, retentativas e ops lentas como conhecimento estruturado.
- **Lesson capture pipeline** (`hooks/memory_hook.py`): detecção de 4 triggers (error, high_cost,
  retries, slow_op) via PostToolUse + PreToolUse. Sumarização via Haiku (~$0.001/lesson).
- **`pre_track_lesson_timing()`**: hook PreToolUse que registra t₀ de cada tool call para medir
  duração real (slow_op detection). Registrado em `supervisor.py`.
- **Anti-bloat**: `store.prune_lessons_by_agent()` limita a 50 lessons ativas por agente.
  `compiler.deduplicate_lessons()` consolida lessons com >60% de overlap por agente+task_type.
  `deduplicate_lessons()` agora é chamado automaticamente em `compile_daily_logs()`.
- **Lesson injection** (`memory/retrieval.py`): seção `### Lições Aprendidas ⚠️` no bloco
  injetado no system prompt no início de cada sessão.
- **Agent instructions**: `databricks-engineer`, `fabric-engineer`, `databricks-ai`,
  `migration-expert` — cada um recebeu instrução de consultar lessons antes de ops HIGH-risk.
- **S4 Autonomous Mode** (`config/settings.py`): 3 novos campos — `s4_autonomous_mode`,
  `s4_auto_approval_min_clarity_score`, `s4_auto_approval_max_cost_usd`. Default OFF.
- **`tracker.log_s4_decision()`** (`workflow/tracker.py`): loga evento `s4_decision` em
  `logs/workflows.jsonl` com mode, clarity_score, approved, reason e agents.
- **S4 constitution clause** (`kb/constitution.md`): §2.1 documenta critérios de auto-aprovação.
- **S4 supervisor prompt** (`agents/prompts/supervisor_prompt.py`): Step 2 atualizado com
  lógica condicional S4-AUTO.
- **22 novos testes**: `test_memory_lesson_learned.py` (14 testes, Fases 1–4) e
  `test_s4_relaxation.py` (8 testes, Fase 5).

### Gated (aguardando telemetria)

- **T1.7** — Decidir Caminho A vs B da memória (`logs/memory_usage.jsonl` 24-72h).
- **T2.5** — Dashboard de cache hit rate (`logs/audit.jsonl` acumulado).
- **T4.5** — Decisão final Caminho A da memória (6 semanas de métricas).

### Backlog

- ~~**T0.2.1**~~ — Issue aberta em
  [`anthropics/claude-agent-sdk-python#845`](https://github.com/anthropics/claude-agent-sdk-python/issues/845)
  pedindo passthrough de `extra_headers` para opt-in em `anthropic-beta: token-efficient-tools-2025-02-19`.
- **T5.1** — Prompt caching explícito no Supervisor. Confirmado bloqueado em SDK 0.1.63.

---

## [2.0.0] — 2026-05-09

### Removed — Consolidação 23 → 14 agentes (Phases 1–5)

- **12 agentes Fabric consolidados em 3** (Phase 1):
  - `semantic-modeler`, `catalog-intelligence`, `schema-designer`, `cost-optimizer`,
    `medallion-architect` → absorvidos por `fabric-engineer`
  - `ontology-engineer` → renomeado para `fabric-ontology`

- **7 agentes Databricks consolidados em 2** (Phase 2):
  - `sql-expert`, `spark-expert`, `pipeline-architect`, `cdc-specialist`,
    `spark-diagnostics` → consolidados em `databricks-engineer`
  - `ai-data-engineer`, `streaming-engineer` → consolidados em `databricks-ai`

- **Interface Streamlit de chat** (T5.4): `ui/chat.py` (964 LOC) removido.
  Chainlit (`ui/chainlit_app.py`) é agora a única UI de chat, ativada por
  `./start.sh` na porta 8503. Streamlit continua como dependência do
  dashboard de monitoramento (`monitoring/app.py`, porta 8501) e foi
  removido dos extras `[ui]` em `pyproject.toml` — permanece só em
  `[monitoring]`. Arquivos ajustados: `start.sh` (flag `--chainlit`
  removida, porta padrão 8503), `start_chainlit.sh`, `README.md`,
  `.claude/CLAUDE.md`, `Manual_Relatorio_Tecnico_Projeto_Data_Agents.md`,
  `commands/geral.py` (docstring), `main.py` (comentário),
  `ui/chainlit_app.py` (prompt do Dev Assistant), `ui/ui_config.py`
  (constantes `COMMANDS_NO_ARGS` e `STREAMLIT_CSS` removidas),
  `tests/test_functional.py` (removida a parametrização de `ui/chat.py`
  em `TestDOMARenamingNoBMADInCode` e o teste `test_chat_uses_doma_prompt`).

### Changed

- **`scripts/refresh_skills.py` migrado para Anthropic Batch API** (T5.2):
  todas as skills pendentes de refresh agora são submetidas em um único
  batch via `client.messages.batches.create()`, com 50% de desconto sobre
  input+output. O script faz polling a cada 10s (SLA máximo 24h, batches
  pequenos concluem em minutos) e escreve cada SKILL.md conforme os
  resultados retornam. Flag `--concurrent` removida (paralelismo é
  servidor-side). Custo estimado por rodada cai de `~$1-3` para `~$0.50-1.50`.
  20 testes novos em `tests/test_refresh_skills_batch.py` mockam o ciclo
  `create → retrieve → results` e cobrem custo, submissão única,
  propagação de erros e curto-circuito em `--dry-run`.

- **Skills migradas para o formato nativo Anthropic** (T5.3): cinco skills
  canônicas que viviam como arquivos flat em `skills/*.md` agora residem em
  `skills/patterns/<name>/SKILL.md` com frontmatter YAML (`name` +
  `description`):
  - `data_quality.md` → `patterns/data-quality/SKILL.md`
  - `pipeline_design.md` → `patterns/pipeline-design/SKILL.md`
  - `sql_generation.md` → `patterns/sql-generation/SKILL.md`
  - `spark_patterns.md` → `patterns/spark-patterns/SKILL.md`
  - `star_schema_design.md` → `patterns/star-schema-design/SKILL.md`

  `agents/loader.py::_load_skills_index` deixou de ter o branch especial
  `"root"` e usa `description` do frontmatter como hint (antes inferia a
  primeira linha do corpo). 8 agentes tiveram `skill_domains: [..., root]`
  atualizados para `[..., patterns]`; 25 testes novos em
  `tests/test_native_skills.py` cobrem descoberta e injeção.

### Added

- **Skills `async-patterns` e `cli-patterns`** em `skills/python/` (T6.4):
  cobertura completa de asyncio (`gather`, `Queue`, cancelamento, `httpx`
  async, `Semaphore`, `run_in_executor`) e de CLIs (`argparse`, Typer,
  Rich output, stdin/stdout/pipe, entry points, exit codes semânticos).
  `SKILL.md` do python-expert atualizado; agente passa a consultar ambos
  antes de gerar código async ou ferramentas de linha de comando.

- **`make bootstrap` com validação de ambiente** (T6.3):
  `scripts/bootstrap.py` ganhou `_check_system_deps()` — verifica
  presença de `uvx`, `npx`/`node`, `dotnet` e Python ≥ 3.11 antes de
  criar o `.env`, exibindo instrução de instalação por dep ausente.
  5 novos testes em `tests/test_bootstrap.py`.

- **Regression detection em `make evals`** (T6.2):
  `evals/runner.py` carrega o run anterior como baseline via
  `load_latest_run()` e detecta regressões via `detect_regressions()`.
  O sumário exibe queries que regrediram e o exit code é 1 quando
  qualquer query regrediu ou falhou. 10 novos testes em `tests/test_evals.py`.

- **Compactação autônoma do contexto** (T6.1): `context_budget_hook.py`
  monitora tokens acumulados; ao atingir 80% gera summary via Haiku 4.5
  e seta flag consumível `_compaction_pending`. Entry points (`main.py` e
  `ui/chainlit_app.py`) detectam o flag após cada resposta, injetam o
  summary no `base_system_prompt` e reconectam o cliente SDK — nova janela
  limpa, transparente ao usuário. Limiares: aviso a 70%, compacta a 80%,
  ERROR a 95%.

- **Página "🔭 Observabilidade"** em `monitoring/app.py` (T6.5): nova
  página do dashboard com 4 tabs — (1) **Custo por agente**: agrega
  `logs/sessions.jsonl` via mapa `session_type → agente`, soma
  `total_cost_usd` / `num_turns`, complementa com delegações reais do
  Supervisor a partir de `logs/workflows.jsonl` (event `agent_delegation`);
  (2) **Latência**: p50/p95/max/mean por agente em ms (filtra
  `duration_s > 0`); (3) **Erros por MCP**: taxa de erro por `platform`
  vindo de `logs/audit.jsonl` (`has_error=true`) com
  `st.column_config.ProgressColumn` + drill-down dos últimos 50 erros,
  mais erros de sessão (`sessions.jsonl.has_error`); (4) **Cache hit
  rate**: empty state gated em T2.5/SDK #626 que auto-ativa quando
  `cache_read_tokens` aparecer nos registros. Respeita o filtro de data
  da sidebar já existente.
- **`PRODUCT.md`** na raiz: tese de produto em uma página — ICP, JTBD,
  diferencial vs alternativas (Genie nativo, Copilot Fabric, dbt AI,
  LangChain, ChatGPT/Claude direto) e anti-escopo explícito.
- **`make bootstrap`** (`scripts/bootstrap.py`): wizard interativo que
  gera um `.env` mínimo a partir de 3 perguntas (Anthropic + Databricks
  opcional + Fabric opcional). Sem dependências extras; cross-platform.
  Defaults de sistema (DEFAULT_MODEL, MAX_BUDGET_USD, memória) vêm
  pré-configurados.
- **`make demo`** (`scripts/demo.py`): smoke test end-to-end chamando
  `commands/geral.run_geral_query` direto (Haiku 4.5, zero MCP, zero
  Supervisor). Custo ~$0.005 por execução. Valida que o sistema
  funciona antes de configurar Databricks/Fabric.
- **8 testes** em `tests/test_bootstrap.py` para `_render_env` e
  `_validate_anthropic_key` (funções puras do wizard).
- **`make evals`** (`evals/runner.py` + `evals/canonical_queries.yaml`):
  framework de regressão v1 com 15 queries canônicas e rubric
  determinística (`must_include`, `must_not_include`, `min_length`,
  `max_length`). Score 1.0 / 0.5 / 0.0 por query; exit 0 se tudo passa.
  Executa via `run_geral_query` (Haiku 4.5, ~$0.005 por query =
  ~$0.08 por rodada completa). Resultados persistidos em
  `logs/evals/<timestamp>.jsonl`. Filtros CLI: `--domain`, `--id`,
  `--limit`. **18 testes** em `tests/test_evals.py` cobrindo
  loader, scoring e filtros.

### Fixed

- `README.md`: removidas referências ao agente `skill-updater` (removido em
  T3.6 do Sprint 3). Refresh de Skills é agora `scripts/refresh_skills.py`.
- `.github/workflows/cd.yml`: removido trigger por tag (`push: tags: v*`);
  deploy exclusivamente via `workflow_dispatch` manual. Evita falhas de CD
  por secrets intencionalmente não configurados.

---

## [1.3.0] — 2026-05-07

### Added

- **9 novos agentes especialistas** no registry (`agents/registry/`):
  - `ai-data-engineer` (T1) — RAG pipelines, Vector Search, embeddings, chunking, LLMOps, AI Functions, feature stores
  - `streaming-engineer` (T1) — Kafka, Apache Flink, Spark Structured Streaming, Fabric RTI, CDC com Debezium
  - `cdc-specialist` (T1) — Change Data Capture: Debezium, Kafka Connect, AUTO CDC INTO, transactional outbox, CQRS
  - `data-contracts-engineer` (T2) — ODCS v3 authoring, SLA de qualidade, schema evolution, breaking change management, knowledge graph de contratos
  - `schema-designer` (T2) — Star Schema, Snowflake Schema, Data Vault 2.0, SCD tipos 1–6, grain definition, modelagem dimensional
  - `cost-optimizer` (T2) — Análise DBU/CU via system tables, rightsizing de clusters, otimização Delta Storage, budget forecasting
  - `data-mesh-architect` (T2) — mapeamento de domínios, Data Products, self-serve platform, governança federada, maturity assessment
  - `spark-diagnostics` (T2) — diagnóstico de jobs Spark: OOM, data skew, shuffle/spill, hangs, análise Spark UI, AQE tuning, falhas DLT
  - `medallion-architect` (T2) — design Bronze/Silver/Gold, seleção de artefatos (STREAMING TABLE vs MATERIALIZED VIEW), anti-pattern detection

- **9 novos slash commands** em `config/commands.yaml`:
  `/streaming`, `/ai`, `/cdc`, `/schema`, `/finops`, `/mesh`, `/diagnose`, `/medallion`, `/contract`

- **`governance-auditor` expandido** com capacidades de auditoria de segurança:
  - Auditoria de RLS (Row-Level Security) via `information_schema.row_filters`
  - Auditoria de Column Masking/OLS via `information_schema.column_masks`
  - Auditoria de Sensitivity Labels no Fabric e Microsoft Purview
  - Verificação de Workspace Roles e privilégios de tabela
  - 4 novos tipos de tarefa no Mapa KB+Skills

### Changed

- `agents/prompts/supervisor_prompt.py`: atualizado para 23 agentes com seções de roteamento para todos os novos especialistas
- `tests/test_agents.py`: lista de agentes esperados atualizada de 14 para 23
- `README.md`: badges, tabela de agentes e tabela de comandos atualizados para v1.3.0 com todos os 23 agentes e 38 slash commands
- `.claude/CLAUDE.md`: seções "MCPs por Agente", "Slash Commands", cabeçalho e lista de agentes no registry atualizados

---

## [1.0.0] — 2026-04-18

Primeira release versionada. Representa o estado após a execução dos sprints
S0-S4 do plano de enxugamento 2026: correções pontuais, sessão com memória
real, elevação da maturidade declarativa e refatoração arquitetural.

**Suite:** 1026 testes ✅ (0 falhas).

### Added

- **Transcript por sessão** (`hooks/transcript_hook.py`): persiste JSONL
  append-only em `logs/sessions/<session_id>.jsonl` com turnos
  user/assistant, tools usadas, custo e duração.
- **Slash `/sessions`** (`commands/sessions.py`): tabela Rich com todas as
  sessões — ID, timestamps, turns, custo, status (transcript 📝 ou
  checkpoint 💾), último prompt.
- **Slash `/resume <id>|last`**: reabre sessão injetando os últimos N turnos
  do transcript (default 30×2000 chars ≈ 8% do context budget); fallback
  para `build_resume_prompt` em sessões legadas.
- **Session Summarizer** (`utils/summarizer.py`): Haiku 4.5 via Anthropic
  Messages API direta, produz resumo em 7 campos GAPS G3 (Objetivo /
  Decisões / Artefatos / Pendências / Próximos passos / Contexto técnico /
  Descobertas-chave). Regra "Nunca invente" + `Nenhum(a)` para campos vazios.
- **Compactação autônoma** em `hooks/context_budget_hook.py`: dispara uma
  vez por sessão ao cruzar `context_budget_summarize_threshold` (0.80),
  persiste em `logs/summaries/<sid>.md` e reconecta o cliente com nova janela.
- **Emergency checkpoint em saídas normais**: `main.py` registra `atexit`,
  SIGINT, SIGTERM, SIGHUP; `hooks/checkpoint.py` grava
  `logs/sessions/<sid>.json` + espelho em `logs/checkpoint.json`.
- **Histórico múltiplo de sessões** via `list_sessions()` e
  `load_session_by_id()` em `hooks/checkpoint.py`.
- **Slash `/add-agent`** (`.claude/commands/add-agent.md`): scaffolda novo
  registry, sinaliza os dois pontos manuais (supervisor_prompt,
  test_agents), valida YAML e faz smoke test do loader.
- **Slash `/add-mcp`** (`.claude/commands/add-mcp.md`): guia pelos 5 passos
  do CLAUDE.md + checklist + 4 validações automáticas.
- **Matriz de delegação declarativa** (`agents/delegation_map.yaml` +
  `agents/delegation.py`): 25 routes, renderização de
  `kb/task_routing.md` §2 via markers, `classify()` determinístico.
- **Declaração de commands em YAML** (`config/commands.yaml`): 22 definições
  de slash commands, loader em `commands/parser.py` reduzido para ~120
  linhas.
- **Pacote `workflow/`**: extração de `hooks/workflow_tracker.py` em
  `dag.py` / `tracker.py` / `executor.py`.
- **Pacote `compression/`**: extração de `hooks/output_compressor_hook.py`
  em `constants.py` / `strategies.py` / `metrics.py` / `hook.py`.
- **`utils/tokenizer.py`**: `estimate_tokens_flat` e
  `estimate_tokens_adjusted` — fonte única de estimativa, substitui
  implementações inline em `context_budget_hook` e `compression/metrics`.
- **Scripts independentes do Supervisor:**
  - `scripts/refresh_skills.py` — chama Anthropic Messages API direta com
    tool nativo `web_search_20250305`.
  - `scripts/monitor_daemon.py` — executa SQL direto via
    `databricks-sdk`/`pymssql` (sem LLM).
- **`docs/mcp_fabric_guide.md`**: matriz de decisão para namespaces ATIVO
  (`mcp__fabric_community__*`) vs OFICIAL (`mcp__fabric__*`).
- **Telemetria de cache** em `hooks/audit_hook.py`:
  `cache_creation_input_tokens`, `cache_read_input_tokens`, `cache_hit_rate`
  gravados em `logs/audit.jsonl` quando o SDK expuser.
- **Telemetria de memória** em `memory/telemetry.py`: contadores em
  `store.read/write`, `compiler.compile`, `retrieval.retrieve`; grava
  `logs/memory_usage.jsonl`.
- **Testes para MCPs customizados**: `tests/test_databricks_genie_server.py`
  (22), `tests/test_fabric_sql_server.py` (21), `tests/test_transcript_hook.py`
  (21), `tests/test_sessions_command.py` (21), `tests/test_summarizer.py`
  (16).

### Changed

- **Supervisor thinking migrado para Opus 4.7**: `{type: adaptive, effort:
  high}` em `agents/supervisor.py` (era `{type: enabled, budget_tokens:
  8000}`, incompatível).
- **Agente `geral` em Haiku 4.5** (`bedrock/anthropic.claude-haiku-4-5`) —
  ~4× mais barato para Q&A conceitual.
- **`agents/prompts/supervisor_prompt.py` 361 → 150 linhas (-58%)**:
  descrições em prosa compactadas; tabelas de roteamento e KBs movidas para
  `kb/task_routing.md`.
- **Regras S1-S7 são fonte única em `kb/constitution.md`**: removidas das
  duplicações em `supervisor_prompt.py` e `cache_prefix.md`.
- **`commands/parser.py` 542 → 120 linhas (-78%)**: definições migradas para
  `config/commands.yaml` (228 linhas), API pública preservada
  (`COMMAND_REGISTRY`, `CommandDefinition`, `parse_command`,
  `get_help_text`).
- **`hooks/workflow_tracker.py` 492l → 45l (shim)**: re-exporta do novo
  pacote `workflow/`.
- **`hooks/output_compressor_hook.py` 437l → 52l (shim)**: re-exporta do
  novo pacote `compression/`.
- **Fabric MCPs reorganizados**: rename apenas de variáveis Python
  (`FABRIC_COMMUNITY_MCP_TOOLS` → `FABRIC_MCP_TOOLS` canônico;
  `FABRIC_MCP_TOOLS` oficial MS → `FABRIC_OFFICIAL_MCP_TOOLS`). Alias
  legado preservado.
- **`business-monitor` agente** é agora **somente Q&A interativo** —
  modo autônomo vive em `scripts/monitor_daemon.py`.
- **`skill-updater` removido do registry** — refresh é 100% script em
  `scripts/refresh_skills.py`.
- **`memory/types.py::Memory.normalized_summary`** — `@property` única,
  substitui lógica duplicada em `compiler.py` e `lint.py`.
- **Diagrama e contagem de agentes em `.claude/CLAUDE.md`** ajustados de
  "12 agentes" para "13 agentes" (sem contar `_template.md`).
- **`hooks/context_budget_hook.reset_context_budget`** aceita
  `session_id: str | None = None`, propagado por
  `hooks/session_lifecycle.on_session_start`.

### Removed

- `agents/registry/skill-updater.md` — virou script puro.
- `memory/decay.py` — marcado para remoção (aguarda decisão T1.7).
- `_run_via_agent` em `monitor_daemon.py` — 33 linhas de dead code legacy
  que acoplavam daemon ao agente.

### Fixed

- `agents/supervisor.py`: crash em `/plan` com Opus 4.7 (thinking syntax).
- `hooks/checkpoint.py`: double-save ao encerrar sessão
  (flag `_checkpoint_saved_for_session` + reset por iteração).
- `tests/test_memory_retrieval.py`: adaptado para a nova assinatura
  `_query_sonnet_for_ids → (ids, cost)`.
- `tests/test_agents.py::valid_models`: inclui
  `bedrock/anthropic.claude-haiku-4-5`.
- `tests/test_supervisor.py::test_build_thinking_enabled`: ajustado para
  `{type: adaptive, effort: high}`.
- `tests/test_output_compressor.py`: monkeypatch aponta para
  `compression.hook._compress_sql_result` (re-export binding resolvido em
  import time).

### Security

- Nenhuma alteração relevante nesta release.

### Observability

- `logs/audit.jsonl`: campos `cache_write_tokens`, `cache_read_tokens`,
  `cache_hit_rate`.
- `logs/memory_usage.jsonl`: hits, custo Sonnet, duração por função.
- `logs/compression.jsonl`: métricas de compressão por tool.
- `logs/sessions/<sid>.jsonl`: transcript completo append-only.
- `logs/sessions/<sid>.json`: checkpoint por sessão
  (`logs/checkpoint.json` continua como espelho da mais recente).
- `logs/summaries/<sid>.md`: resumo Haiku disparado a 80% do budget.

### Notes

- SDK `claude-agent-sdk==0.1.61` **não** expõe `extra_headers` nem
  `cache_control` — tarefas T0.2 (`token-efficient-tools` beta) e T5.1
  (prompt caching explícito) permanecem bloqueadas upstream
  (issue `anthropics/claude-agent-sdk-python#626`).
- O baseline de linhas de código pré-enxugamento está em
  `to_do/baseline_loc.txt` (2026-04-17): 52.314 LOC totais, 42.460
  prod-only, 13 agentes, 13 MCPs.

---

[Unreleased]: https://github.com/ThomazRossito/data-agents/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/ThomazRossito/data-agents/releases/tag/v1.0.0
