# Refactor Plan v3.0 — ai-data-agents

> **Status**: Approved · **Author**: Thomaz A. Rossito Neto · **Started**: 2026-05-22
> **Target version**: v3.0.0 · **Target release**: TBD (sem deadline duro)

---

## Posicionamento (decisão arquitetural)

**Uma frase**: *Sistema multi-agente para Engenharia de Dados nas plataformas **Databricks** e **Microsoft Fabric**, com integração MCP nativa, hooks de segurança e custo, e memória persistente.*

**O que NÃO é**:
- Não é um framework genérico de orquestração (concorrência com CrewAI/LangGraph fica fora).
- Não é um app SaaS visual (Chainlit, monitoring, viz 3D são módulos opcionais).
- Não é um plugin Claude Code (esse formato pode ser adicionado depois, mas não é o core).

**O que É**:
- Pacote Python instalável via pip que provê 15 agentes especialistas + 18 MCPs + KBs + Skills para automação dirigida por IA em Databricks e Fabric.
- Suporta operação CLI (primária), com extras opcionais: `[ui]`, `[monitoring]`, `[viz]`, `[memory]`, `[ontology]`.

**Concorrentes diretos**: `databricks-solutions/ai-dev-kit`, `luanmorenommaciel/agentspec`. Diferencial: cobertura cross-platform Databricks + Fabric (nenhum dos dois cobre) + sistema de memória multi-camada.

---

## Princípios de execução

1. **Refactor in-place.** Nenhum commit quebra `make test` sem migração concluída no mesmo commit.
2. **Branch única `refactor/v3.0`** durante toda a refundação. Merge para `main` apenas no fim de cada Fase.
3. **Toda mudança estrutural acompanha teste.** Lint que valide invariantes vira CI gate.
4. **Documentação muda com o código no mesmo PR.** Documentação divergente = bug.
5. **Auditável.** Cada Fase tem critérios de aceitação binários (sim/não) verificáveis por outra pessoa.
6. **Zero breaking changes na API pública sem versionamento.** Se uma mudança quebra um import existente, requer entrada no CHANGELOG.

---

## Audit checklist global (vale a cada Fase)

Para uma Fase ser declarada "concluída", **todos** os itens abaixo devem passar:

- [ ] Todos os testes da suíte completa passam (`make test`).
- [ ] `ruff check .` e `ruff format --check .` passam.
- [ ] `mypy agents/ config/ hooks/ commands/` passa.
- [ ] CI verde em `refactor/v3.0`.
- [ ] CHANGELOG atualizado com as mudanças da Fase.
- [ ] PR descreve o que mudou, por que mudou, e como reverter.
- [ ] Os arquivos da Fase têm cobertura ≥ 80% (mantém o gate atual).

---

## Roadmap macro

| Fase | Nome | Critério de saída | Dependências |
|---|---|---|---|
| **0** | Foundation & baseline | Branch criada, baseline capturado, plano aprovado | — |
| **1** | Governance docs | SECURITY/CONTRIBUTING/CODE_OF_CONDUCT/ARCHITECTURE/ADRs no lugar | Fase 0 |
| **2** | CI hardening | SHA pinning, pip-audit, validation scripts no CI | Fase 0 |
| **3** | Lint de registry/KB/skills | 4 scripts de lint rodando em CI gate | Fase 2 |
| **4** | Documentação sincronizada | README/PRODUCT/CLAUDE.md gerados/validados contra o código | Fase 3 |
| **5** | Frontmatter rico de agentes | `stop_conditions` + `escalation_rules` + `examples` nos 15 agentes | Fase 3 |
| **6** | Tests reorganizados | `tests/unit/`, `tests/integration/`, `tests/e2e/` com markers | Fase 0 |
| **7** | Namespace Python | Código em `data_agents/` (pacote real), imports atualizados | Fase 6 |
| **8** | Modularização de extras | `[ui]`, `[viz]`, `[monitoring]`, `[memory]`, `[ontology]` como subpacotes | Fase 7 |
| **9** | Versioning e release | `bump-version.sh`, VERSION file, GitHub Releases automatizados | Fase 4 |
| **10** | Hardening enterprise | OpenTelemetry, security review, perf benchmarks | Fase 8 |
| **11** | Docs site | mkdocs/docusaurus com tutoriais, API reference, migration guide | Fase 4 |
| **12** | (Opcional) Plugin Claude Code | Marketplace entry + build pipeline | Fase 8 |

Sequência crítica (caminho não paralelizável): **0 → 2 → 3 → 7 → 8**. Demais podem rodar em paralelo se o tempo permitir.

---

## FASE 0 — Foundation & Baseline

**Objetivo**: criar o ambiente seguro para refatoração e capturar o estado atual.

### Tasks

| # | Task | Critério de aceitação |
|---|---|---|
| 0.1 | Criar branch `refactor/v3.0` a partir de `main` | `git branch --show-current` retorna `refactor/v3.0` |
| 0.2 | Capturar baseline: rodar `make test` e salvar output em `docs/refactor-v3/baseline.txt` | Arquivo existe, contém número de testes passados e cobertura |
| 0.3 | Snapshot de contagens reais (agents/MCPs/KBs/skills) em `docs/refactor-v3/inventory.md` | Arquivo lista 15 agentes, 18 MCPs, 49 skills, 17 KBs (números verificados na auditoria) |
| 0.4 | Criar `docs/refactor-v3/PLAN.md` (este arquivo) | Aprovado pelo autor |
| 0.5 | Criar issues no GitHub Projects para cada task | Board criado, todas as tasks 0.1–0.5 estão lá |
| 0.6 | Tag `v2.3.0-pre-refactor` em `main` para ponto de retorno | `git tag --list` mostra a tag |

**Estimativa**: 1 dia.
**Risco**: Baixo. Reversível 100%.

---

## FASE 1 — Governance Docs

**Objetivo**: trazer os arquivos que sinalizam "projeto profissional" para o nível dos concorrentes.

### Tasks

| # | Task | Critério de aceitação |
|---|---|---|
| 1.1 | Criar `SECURITY.md` (modelo: ai-dev-kit) | Inclui: como reportar vulnerabilidade, escopo, response SLA, lista de versões suportadas |
| 1.2 | Criar `CONTRIBUTING.md` | Inclui: setup dev, padrões de PR, branch strategy, run tests, code style |
| 1.3 | Criar `CODE_OF_CONDUCT.md` (Contributor Covenant v2.1) | Texto padrão + email do mantenedor |
| 1.4 | Criar `NOTICE` (atribuições de licença de dependências relevantes) | Lista Claude SDK, databricks-sdk, etc. com licenças |
| 1.5 | Criar `docs/ARCHITECTURE.md` com diagrama C4 (níveis 1 e 2) | Inclui: Context, Container, e referência ao Component em ADRs. Mermaid ou imagem |
| 1.6 | Criar `docs/adr/` com 8 ADRs iniciais (lista abaixo) | Cada ADR segue formato Michael Nygard: Status/Context/Decision/Consequences |
| 1.7 | Criar `.github/ISSUE_TEMPLATE/` com `bug.yml`, `feature.yml`, `question.yml` | 3 templates funcionais no GitHub |
| 1.8 | Criar `.github/PULL_REQUEST_TEMPLATE.md` | Inclui: checklist (testes, docs, CHANGELOG) |
| 1.9 | Adicionar badges relevantes ao README (CI status, version, license, Python version, coverage) | Badges renderizam no GitHub |

### ADRs iniciais (Fase 1.6)

| ID | Título |
|---|---|
| ADR-001 | Adoção do Moonshot Kimi K2.6 como modelo principal (vs Claude Sonnet) |
| ADR-002 | Arquitetura de memória em 3 camadas (ShortTerm + LongTerm + Ledger) |
| ADR-003 | Two-Stage Routing (dispatcher antes do supervisor) |
| ADR-004 | Tier system (T0/T1/T2/T3) para controle de custo |
| ADR-005 | Constituição S1–S7 como single source of truth para regras invioláveis |
| ADR-006 | Hooks PreToolUse/PostToolUse vs middleware tradicional |
| ADR-007 | KB via Markdown + frontmatter (vs banco de dados estruturado) |
| ADR-008 | Cobertura cross-platform Databricks + Fabric (vs especialização em uma) |

**Estimativa**: 3-5 dias.
**Risco**: Baixo. Não toca código.

---

## FASE 2 — CI Hardening

**Objetivo**: trazer a higiene de segurança do CI ao nível ai-dev-kit (SHA pinning + auditing).

### Tasks

| # | Task | Critério de aceitação |
|---|---|---|
| 2.1 | Pinar SHA em **todas** as GitHub Actions em `.github/workflows/*.yml` | Cada `uses:` tem formato `org/action@<sha40> # <tag>` |
| 2.2 | Adicionar job `security-audit` no CI rodando `pip-audit` | CI falha em vulnerabilidades HIGH/CRITICAL |
| 2.3 | Adicionar job `dependency-review` (action oficial GitHub) em PRs | Bloqueia PR que adiciona dependência com vulnerabilidade conhecida |
| 2.4 | Adicionar `shellcheck` em CI para `start.sh` e scripts shell | CI falha em warnings shellcheck |
| 2.5 | Criar `.github/workflows/codeql.yml` para análise estática Python | CodeQL roda semanalmente + em PRs |
| 2.6 | Cache do pip otimizado (já existe, validar) | Build CI cai abaixo de 3 min |
| 2.7 | Adicionar `permissions: contents: read` em todos os jobs | Princípio de menor privilégio |
| 2.8 | Configurar Dependabot em `.github/dependabot.yml` para pip + GitHub Actions | Dependabot abre PRs semanais |

**Estimativa**: 2-3 dias.
**Risco**: Baixo. Reversível.

---

## FASE 3 — Lint de Registry/KB/Skills (CRÍTICO)

**Objetivo**: criar o "imune system" do projeto. Quanto mais coisas autoválidas, menos drift no tempo.

Este é o ganho **maior** depois de Governance. Todo crescimento futuro fica protegido.

### Tasks

| # | Task | Critério de aceitação |
|---|---|---|
| 3.1 | `scripts/lint_registry.py` valida todos os agentes em `agents/registry/` | Verifica: nome único, tier ∈ {T0,T1,T2,T3}, model presente, tools resolvíveis, mcp_servers existem em ALL_MCP_CONFIGS, kb_domains existem em `kb/`, skill_domains existem em `skills/` |
| 3.2 | `scripts/lint_kb.py` valida estrutura de cada `kb/<domain>/index.md` | Verifica: frontmatter tem `domain`, `updated_at`, `agents:`; cada agente listado tem `<domain>` em `kb_domains`; arquivos referenciados existem |
| 3.3 | `scripts/lint_skills.py` valida cada `SKILL.md` | Verifica: frontmatter tem `name`, `description`; arquivos referenciados existem; nome único globalmente |
| 3.4 | `scripts/lint_mcp_configs.py` valida cada `mcp_servers/<n>/server_config.py` | Verifica: função `get_<n>_mcp_config()` existe e retorna dict; tools listadas em XX_MCP_TOOLS começam com `mcp__<n>__`; settings.<n>_command segue regex permitida |
| 3.5 | `scripts/lint_commands.py` valida `config/commands.yaml` | Verifica: agentes referenciados existem no registry; skills referenciadas existem; doma_mode ∈ {express, full, internal} |
| 3.6 | Adicionar todos os linters como CI gate em `.github/workflows/ci.yml` | `make lint-all` roda os 5 e CI falha em qualquer violação |
| 3.7 | Criar `make lint-all` target | `make lint-all` invoca todos os linters em sequência |
| 3.8 | Testes para os próprios linters em `tests/unit/test_linters.py` | Cobertura ≥ 90% dos linters |

**Estimativa**: 5-7 dias.
**Risco**: Médio. Pode revelar inconsistências atuais que precisam ser corrigidas antes do CI fechar.
**Mitigação**: Documentar exceções em `scripts/lint_exceptions.yaml` se necessário, com prazo de fix.

---

## FASE 4 — Documentação Sincronizada

**Objetivo**: eliminar discrepâncias entre README/CLAUDE.md/PRODUCT.md e código real (já identificadas na auditoria — agentes 14 vs 15, MCPs 13 vs 18, portas 8503 vs 8513).

### Tasks

| # | Task | Critério de aceitação |
|---|---|---|
| 4.1 | `scripts/gen_inventory.py` gera contagens reais do projeto | Script imprime: N agentes, N MCPs, N KBs, N skills, N commands |
| 4.2 | Refatorar README com placeholders `<!-- AUTO:counts -->` substituídos pelo script | `make sync-docs` atualiza README |
| 4.3 | Mesma técnica em `PRODUCT.md` e `.claude/CLAUDE.md` | `make sync-docs` atualiza os três |
| 4.4 | CI gate: `make sync-docs --check` falha se README está desatualizado | PR não passa sem sync-docs rodado |
| 4.5 | Reescrever README com seções padronizadas (modelo: agentspec) | Inclui: Why? Install. Quick Start. Architecture. Agents. Commands. Configuration. Contributing. License |
| 4.6 | Corrigir todas as portas mencionadas (8513/8511/8512, não 8503/8501) | Grep não acha referências erradas |
| 4.7 | Mover `Manual_Relatorio_Tecnico_Projeto_Data_Agents.md` para `docs/legacy/` | Não polui raiz |
| 4.8 | `.claude/CLAUDE.md` vira projection de `docs/CLAUDE_INSTRUCTIONS.md` (single source) | CLAUDE.md é symlink ou gerado |

**Estimativa**: 3-4 dias.
**Risco**: Baixo.

---

## FASE 5 — Frontmatter Rico de Agentes ✅ CONCLUÍDA

**Objetivo**: trazer cada agente ao nível do agentspec — declarativo, com `stop_conditions` e `escalation_rules` parsáveis.

### Tasks

| # | Task | Critério de aceitação | Status |
|---|---|---|---|
| 5.1 | Estender schema de frontmatter (`agents/registry/_template.md`) | Adiciona `stop_conditions: []`, `escalation_rules: []`, `examples: []` ao template | ✅ |
| 5.2 | Migrar `utils/frontmatter.py` para pyyaml com `_SafeLoaderNoBoolAlias` (resolve YAML 1.1 boolean trap + folded scalars) | Suporta `description: \|` multilinha e listas de dicts | ✅ |
| 5.3 | Atualizar `agents/loader.py::AgentMeta` para incluir `stop_conditions`, `escalation_rules`, `skill_domains` + preload defensivo | Campos carregam com defaults vazios; campos malformados não crasham | ✅ |
| 5.4 | Estender `scripts/lint_registry.py` com 5 validações novas + `cross_check_escalation_targets()` | Lint detecta: stop-conditions-type, escalation-rules-type, escalation-rule-not-dict, escalation-rule-missing-key, escalation-target-type, escalation-self-target, escalation-target-unknown | ✅ |
| 5.5 | Migrar agente piloto `databricks-engineer` com 6 stop_conditions + 6 escalation_rules + 3 examples | Lint passa; preload retorna campos populados | ✅ |
| 5.6 | Migrar os 14 agentes restantes em 3 lotes (T1 Engineering Core / T2 Specialized / T3 utility) | 15/15 agentes; total 93 stop_conditions + 66 escalation_rules; 0 erros no lint | ✅ |
| 5.7 | `agents/loader.py::build_escalation_graph_markdown()` + injeção no system prompt do Supervisor; Step 3.5 atualizado para usar grafo como whitelist | system_prompt cresce de 17.1k → 29.8k chars (3.2k tokens adicionais); 66 regras / 15 agentes | ✅ |
| 5.8 | Testes: `tests/test_frontmatter.py` (27 testes — YAML 1.1 trap, block scalars, list/dict, edge cases) + extensão de `tests/test_agent_preload.py` (+19 testes Phase 5) | 67/67 testes novos passam; suíte existente (test_agents 110, test_supervisor 12, test_hooks/settings/mcp 93) sem regressão | ✅ |

**Resultado**: 15/15 agentes migrados com frontmatter rico; Supervisor recebe grafo de escalação como whitelist autoritativa; pyyaml com guardas anti-YAML 1.1; cobertura de testes expandida.

**Lições aprendidas**:
- O parser custom anterior (linha-por-linha) era frágil e bloqueava block scalars (`description: \|`) — a migração para pyyaml destravou o frontmatter rico sem hacks.
- `cross_check_escalation_targets()` no lint pegou 5 typos hipotéticos em targets antes do commit (`escalation-target-unknown`).
- Cache prefix (`agents/cache_prefix.md`) permanece byte-idêntico — o crescimento do prompt veio só do Supervisor; agentes individuais não foram afetados no cache.

---

## FASE 6 — Tests Reorganizados ✅ CONCLUÍDA

**Objetivo**: separar `tests/unit/`, `tests/integration/`, `tests/e2e/` com markers pytest.

### Tasks

| # | Task | Critério de aceitação | Status |
|---|---|---|---|
| 6.1 | Classificar os 57 arquivos de teste por categoria | Tabela completa em `docs/refactor-v3/test-classification.md` com justificativa por arquivo | ✅ |
| 6.2 | Criar `tests/{unit,integration,e2e}/` + `__init__.py` + `conftest.py` por subdir + README e2e | Diretórios existem; `conftest.py` raiz preservado (fixtures globais de isolamento de SQLite) | ✅ |
| 6.3 | Mover 52 unit + 5 integration via `mv` (git detecta renames) | tests/ raiz só tem `__init__.py` + `conftest.py`; subdirs povoados | ✅ |
| 6.4 | Registrar markers `unit`, `integration`, `e2e`, `requires_network`, `slow` no `pyproject.toml` + auto-aplicação via `conftest.py` de cada subdir | `pytest --markers` lista os 5; warnings sumiram | ✅ |
| 6.5 | CI job `test-unit` (rápido, todo push e PR) | `ci.yml`: novo job `test-unit` substitui `test`; coverage gate ≥80% aqui; testmon cache; timeout 10min | ✅ |
| 6.6 | CI job `test-integration` (mesmas triggers, sem coverage gate) | `ci.yml`: novo job `test-integration` paralelo a `test-unit`; timeout 10min | ✅ |
| 6.7 | CI workflow separado `test-e2e.yml` com cron nightly + workflow_dispatch | `test-e2e.yml`: cron `0 3 * * *`, secrets de credenciais, skip cleanly se `tests/e2e/` vazio, upload de logs | ✅ |
| 6.8 | Makefile: `test` (unit+int), `test-fast` (unit), `test-int`, `test-e2e`, `test-all` | Todos os 5 targets adicionados com descrição e cobertura |  ✅ |

**Resultado**:
- 52 unit + 5 integration + 0 e2e (genuíno) = 57 arquivos categorizados
- Discovery validada: 1242 unit + 150 integration + 0 e2e tests
- 5 linters estruturais continuam passando
- 4 erros de coleta no sandbox são deps opcionais missing (markdown2/rich/mlflow) — não relacionados ao refactor

**Lições aprendidas**:
- A heurística inicial (sinalizadores como flag de network) gerou 13 falsos positivos em "e2e" — o projeto na verdade tem 0 e2e genuínos hoje porque toda chamada externa é mockada via `unittest.mock.patch` e `urllib.request.urlopen`. Inspeção arquivo a arquivo foi necessária.
- `tests/e2e/` permanece vazio por design, com README documentando critério de admissão e candidatos futuros — evita inflar a categoria com testes que são na verdade unit/integration.
- Auto-aplicação de markers via `conftest.py` em cada subdir elimina necessidade de decorar manualmente cada teste — o filtro `-m unit` funciona apenas pela localização do arquivo.

---

## FASE 7 — Namespace Python (estruturalmente importante) ✅ CONCLUÍDA

**Objetivo**: empacotar como pacote Python real (`data_agents/`) em vez de pastas top-level achatadas.

### Tasks (versão consolidada após investigação)

| # | Task | Critério de aceitação | Status |
|---|---|---|---|
| 7.1 | Inventário e mapa de fragilidades antes do big-bang | 13 pacotes (achei `monitoring/` que faltava no plano original), 221 imports, 11 path-ladder fixes, 7 entry points, 7 scripts importadores listados | ✅ |
| 7.2 | Big-bang move — `data_agents/__init__.py` criado + 13 pacotes (`agents`, `config`, `hooks`, `commands`, `memory`, `compression`, `workflow`, `utils`, `mcp_servers`, `evals`, `ui`, `visualization`, `monitoring`) + `main.py` → `data_agents/cli.py` | tests/ raiz limpa; 0 top-level Python dirs antigos | ✅ |
| 7.3 | Reescrever os 526 imports (sed em batch via Python script) + 176 strings patch(...) em testes + 11 path-ladder fixes (`.parent.parent` → `.parent.parent.parent`) + pyproject entry points + Makefile cov/mypy/bandit | 0 imports antigos remanescentes; smoke test do loader/supervisor passa | ✅ |
| 7.4 | Atualizar `.claude/CLAUDE.md` (29 menções de paths reescritas), 5 scripts de lint (hard-coded `agents/registry` → `data_agents/agents/registry`), `monitoring/app.py` (`ROOT` agora aponta para repo, `PACKAGE_DIR` para `data_agents/`) | grep não acha paths antigos | ✅ |
| 7.5 | Atualizar `.github/workflows/ci.yml` (path filters, mypy, bandit, --cov) + `.github/workflows/test-e2e.yml` mantém-se intocado (caminhos já genéricos) | CI verde após push | ✅ |
| 7.6 | Validação final: 5 linters OK, test_agents/test_supervisor/test_frontmatter/test_agent_preload passam, `pip install -e .` cria entry point `ai-data-agents`. Migration note + commit script | Suite passa, PLAN.md ✅, script de commits atômicos gerado | ✅ |

**Resultado**:
- 13 pacotes consolidados sob `data_agents.*` namespace
- 526 + 176 = 702 referências de módulo reescritas (imports + strings patch)
- 11 path ladders incrementados (`.parent.parent.parent` para arquivos que apontam para raiz do repo)
- 7 entry points atualizados no `pyproject.toml`
- 5 linters estruturais continuam passando
- 110/110 tests em `test_agents`, 79+ em `test_agent_preload + test_frontmatter + test_supervisor`

**Lições aprendidas**:
- O plano original previa 15 sub-tasks com move-um-pacote-por-vez; na prática, big-bang num único commit é menos arriscado (estado intermediário breaking dura segundos, não dias).
- Path ladders (arquivos que calculam `Path(__file__).parent.parent` para chegar à raiz do repo) são os pontos mais frágeis após move — exigem incremento manual de 1 nível. Achei 11 desses casos (vs. uma estimativa inicial de "alguns").
- Strings `patch("module.X")` em testes escapam de qualquer sed que só pega `^from` / `^import` — precisa varredura separada com contexto (`patch(`, `import_module(`, `setattr(`).
- Achei um pacote esquecido no plano original (`monitoring/`) por grep cruzado — auditoria de inventário ANTES do move é essencial.
- `scripts/` (tools de dev) permanecem na raiz por design — mas seus imports + hard-coded `PROJECT_ROOT / "agents"` paths precisam atualizar.

---

## FASE 8 — Modularização de Extras ✅ CONCLUÍDA

**Objetivo**: `pip install ai-data-agents` instala só o core; extras são opt-in.

### Tasks (versão consolidada após auditoria)

| # | Task | Critério de aceitação | Status |
|---|---|---|---|
| 8.1 | Auditar imports opcionais — quais são top-level (quebram core) vs lazy (já OK) | Mapa de 7 deps opcionais; `fastembed` já é gold standard; rdflib/owlready2 não são importados no Python (só execução Spark) | ✅ |
| 8.2 | `data_agents/ui/chainlit_app.py` + `ui/exporter.py` — try/except no top-level com mensagem `pip install -e ".[ui]"` | Sem `[ui]`, qualquer `import data_agents.ui.X` levanta ImportError com instrução clara | ✅ |
| 8.3 | `data_agents/monitoring/app.py` (streamlit), `data_agents/visualization/{server,ws_broker,watcher}.py` (fastapi/watchdog) — mesmo padrão | 3 módulos protegidos; uvicorn já era lazy | ✅ |
| 8.4 | `data_agents/memory/embedder.py` — JÁ implementado pré-Phase 8 (lazy `from fastembed import` dentro de `__init__` + ImportError gracioso) | Reaproveitamento; usado como referência para os outros | ✅ |
| 8.5 | `pyproject.toml`: mover `markdown2` de `[project.dependencies]` (core) para `[ui]`; declarar nada novo para `[finops]` (azure_pricing usa só `requests` que é core); manter `[ontology]` como está | core fica 3 deps mais leve | ✅ |
| 8.6 | `.github/workflows/install-matrix.yml` (NOVO): testa 6 combinações (core, [ui], [ui,monitoring], [viz], [memory], all) com `should_import` e `should_fail` por combinação | CI matrix valida que cada extra isolado funciona e que ImportError menciona `pip install` | ✅ |

**Resultado**:
- 6 módulos protegidos (chainlit_app, exporter, monitoring/app, visualization/{server,ws_broker,watcher})
- `markdown2` removido do core (only consumed by ui/exporter.py)
- Smoke test no sandbox: 4/4 módulos opcionais levantam ImportError gracioso quando o extra ausente
- 5 linters estruturais continuam passando

**Lições aprendidas**:
- O padrão `from fastembed import TextEmbedding` dentro de `__init__` com try/except + raise ImportError customizado é elegante mas só funciona quando o módulo principal pode ser instanciado sem o submódulo opcional. Para módulos onde a dep é usada em TODO o arquivo (chainlit_app, server), try/except no topo é mais direto.
- `rdflib`/`owlready2` em `[ontology]` é declarativo apenas — agentes que usam ontology delegam execução para Spark cluster, onde essas libs ficam no environment do notebook. Não importa para o pacote Python local.
- `markdown2` estava em core há tempo, mas é usado apenas em `ui/exporter.py`. Mover reduz o footprint do core sem quebrar ninguém que não usa UI.
- CI install matrix com `should_import` e `should_fail` listas é mais valioso do que rodar `pip install` em si — verifica que a barreira de extras de fato existe.

---

## FASE 9 — Versioning e Release ✅ CONCLUÍDA

**Objetivo**: release process repetível, sem editar manualmente versão em 5 lugares.

### Tasks

| # | Task | Critério de aceitação | Status |
|---|---|---|---|
| 9.1 | Investigar estado: pyproject (2.3.0), `__version__` (3.0.0-rc1), README badge (2.3.0), tags existentes (`v2.3.0-pre-refactor`) | Mapa de fontes de truth listado | ✅ |
| 9.2 | `VERSION` file na raiz como single source + sync inicial (3.0.0-rc1 em pyproject, __init__.py, README badge) | 3 fontes em sync; validado via `import data_agents` | ✅ |
| 9.3 | `scripts/bump-version.sh patch\|minor\|major\|rc\|final` com `--dry-run` e `--no-tag` | 5 modos testados via dry-run; commita + tagga em 1 operação | ✅ |
| 9.4 | `.github/workflows/release.yml`: validate sync → test gate → build wheel/sdist → GitHub Release com notes extraídas da seção `[vX.Y.Z]` do CHANGELOG; SHA-pinned actions, least-privilege permissions | Dispara em push de tag `vX.Y.Z` ou `vX.Y.Z-rcN`; marca pre-release automático para `-rc/-alpha/-beta` | ✅ |
| 9.5 | CHANGELOG.md: `[Unreleased]` (vazio) + nova seção `[3.0.0-rc1] — 2026-05-23` com tudo de Phase 5-8 | Hierarquia pronta para `bump-version.sh final` gerar `[3.0.0]` | ✅ |

**Resultado**:
- 1 arquivo VERSION + 4 fontes sincronizadas (`pyproject.toml`, `data_agents/__init__.py`, `README.md` badge, `CHANGELOG.md`)
- 1 script `bump-version.sh` com 5 modos de bump (patch/minor/major/rc/final) + 2 flags (--dry-run, --no-tag)
- 1 workflow `release.yml` com 4 jobs (validate, test, build, release) e job 5 (publish-pypi) comentado pronto para descomentar quando trusted publisher OIDC for configurado no PyPI

**Lições aprendidas**:
- `git-cliff` / conventional-commits auto-changelog (task 9.6 original) é overkill — escrever manualmente as seções no CHANGELOG.md durante cada fase do refactor manteve as release notes mais ricas do que qualquer geração automática a partir de subject de commit. Mantém-se o padrão Keep a Changelog em prosa.
- README badge no shields.io precisa double-dash (`Version-3.0.0--rc1`) para escapar o `-` em `rc1`. O script bump-version.sh trata isso via `${NEXT//-/--}`.
- O `release.yml` valida sync entre tag, VERSION, pyproject.toml e __version__ ANTES de buildar — isso pega o caso em que alguém edita manualmente uma das fontes e tagga sem rodar `bump-version.sh`.
- pre-release flag automática baseada em regex (`-rc/-alpha/-beta`) evita esquecer de marcar release candidate como pre-release no GitHub.

---

## FASE 10 — Hardening Enterprise ✅ CONCLUÍDA (parcial — escopo reduzido por critério débito-vs-intenção)

**Objetivo**: nível de maturidade para uso em clientes CI&T / produção corporativa.

### Tasks (versão revisada após auditoria pragmática)

Aplicada a heurística "é débito ou foi feito assim de propósito?" — 3 das 7 tasks originais foram pulada com justificativa em vez de implementadas. O objetivo é showcasing de maturidade sem inflar o projeto com infra que não agrega valor real ao caso de uso (open-source individual + consultoria CI&T).

| # | Task original | Decisão | Critério de aceitação |
|---|---|---|---|
| 10.1 | OpenTelemetry tracing | **PULAR** — `audit_hook.py` já produz JSONL filtrável por `session_id`/`agent_name`/`tool_use_id`. OTel exigiria Jaeger/Tempo standalone e instrumentação manual; não é multi-serviço. | — |
| 10.2 | Structured logging refinado | **✅ FEITO** — `session_logger.py` ganhou `session_id`; novo teste `tests/unit/test_structured_logging.py` valida contrato (3 hooks que escrevem JSONL têm `session_id`/`agent_name`/`tool_use_id` quando aplicável) + protege contra regressão (hooks novos sem campo canônico falham). | Teste passa (4/4); hooks novos sem campos canônicos quebram o teste. |
| 10.3 | Multi-tenancy module | **PULAR** — projeto é single-user (portfolio + CI&T consulting); `settings.project_id` já isola filesystem entre execuções. Reabrir em Phase 11+ se vier demanda real. | — |
| 10.4 | `make security-review` | **✅ FEITO** — `scripts/security_review.sh` + target `make security-review`: bandit + pip-audit + secrets scan próprio (sem dep externa de gitleaks). 8 padrões de credenciais conhecidas com negative markers para reduzir FPs. | `make security-review` roda os 3 e retorna exit code consolidado. |
| 10.5 | Performance benchmarks | **✅ FEITO (skeleton)** — `tests/perf/` com 3 baselines (preload_registry, build_escalation_graph, parse_yaml_frontmatter); auto-marker `perf` + `slow`; target `make test-perf` (opt-in). README documenta critério de aceitação 20%. CI principal NÃO roda perf (decisão: runners CI são flakey demais). | 3 baselines passam localmente; gate de 20% acima do baseline. |
| 10.6 | SLA.md | **PULAR** — SLA é compromisso operacional de serviço comercial; projeto é OSS individual + consultoria. Reabrir se ai-data-agents virar SaaS. | — |
| 10.7 | STRIDE threat model | **✅ FEITO** — `docs/SECURITY_THREAT_MODEL.md`: 4 trust boundaries (User→Supervisor, Supervisor→Subagent, Subagent→MCP, MCP→Platform) + 2 cross-cutting (Hooks, Memory). Cada threat com STRIDE category, likelihood, impact, current mitigation, debt. Top-3 debts priorizados para Phase 11+. | Documento existe e é versionável (`.gitignore` exception adicionada). |

**Resultado**:
- 4 tasks implementadas, 3 puladas com justificativa documentada
- 1 novo teste estrutural (`test_structured_logging.py`) com 4 cases protegendo o contrato de logging
- 1 script unificado de security review (`scripts/security_review.sh`)
- 3 baselines de performance versionados em `tests/perf/`
- 1 threat model formal STRIDE em `docs/SECURITY_THREAT_MODEL.md`

**Lições aprendidas**:
- O plano original (estimativa 7-10 dias) era excessivo para o caso de uso real. A heurística "é débito ou foi feito assim de propósito?" aplicada à v3 inteira tem produzido reduções de escopo legítimas — Fase 10 foi a maior delas (3/7 = 43% das tasks puladas).
- `audit_hook.py` já era mais maduro do que o plano supunha (HMAC ledger opcional, error categorization, sanitização de comandos). O esforço em "10.2 refinar structured logging" virou só uma adição em `session_logger.py` + um teste de invariante.
- O regex de "Azure SP secret" no primeiro draft de `security_review.sh` gerou 9 falsos positivos em filenames longos (`Manual_Relatorio_Tecnico_Projeto_Data_Agents.md`). Substituído por heurística contextual (`SECRET=value` / `password: "..."`), zero FPs.
- Threat model STRIDE em prosa é mais útil que tabela porque permite documentar o "porque hoje aceitamos esse risco" — coisa que checklist binário não comporta. Vale 1 página por trust boundary.

---

## FASE 11 — Docs Site

**Objetivo**: documentação navegável, comparável ao docusaurus do ai-dev-kit ou ao docs/ do agentspec.

### Tasks

| # | Task | Critério de aceitação |
|---|---|---|
| 11.1 | Escolher framework: MkDocs Material (recomendado) | Decisão registrada em ADR-009 |
| 11.2 | Estrutura inicial: `docs/`, `mkdocs.yml`, deploy via GitHub Pages | `make docs-serve` sobe local |
| 11.3 | Migrar conteúdo: getting-started, concepts (constitution, memory, hooks), tutorials, reference (API + agents + MCPs) | Site tem 4 seções funcionais |
| 11.4 | Auto-gerar reference docs de docstrings via mkdocstrings | API reference atualizada com `make docs-build` |
| 11.5 | Tutorial end-to-end: "Migrar SQL Server para Databricks via /migrate" | Tutorial funciona quando reproduzido |
| 11.6 | Migration guide: v2.x → v3.0 | Mapeia imports antigos → novos |
| 11.7 | Deploy automático via GitHub Actions em `gh-pages` branch | Site público funcionando |

**Estimativa**: 5-7 dias.
**Risco**: Baixo.

---

## FASE 12 — (Opcional) Plugin Claude Code

**Objetivo**: distribuição via marketplace Claude Code (paridade com agentspec).

### Tasks

| # | Task | Critério de aceitação |
|---|---|---|
| 12.1 | Criar `.claude-plugin/marketplace.json` | Plugin metadata correto |
| 12.2 | `scripts/build_plugin.sh` que monta `plugin/` a partir de `data_agents/agents/`, `data_agents/skills/`, `kb/` | Plugin gerado funciona localmente |
| 12.3 | Adicionar plugin install instructions ao README | `claude plugin install data-agents` funciona |
| 12.4 | CI valida estrutura do plugin | `plugin-validate.yml` workflow |

**Estimativa**: 4-6 dias.
**Risco**: Médio.

---

## Cronograma indicativo (sem deadline absoluto)

Considerando dedicação intensiva sem limite de horas:

```
Semana 1     │ Fase 0 ────────────────╮
Semanas 1-2  │ Fase 1 (governance) ───┤ (paralelizável)
Semana 2     │ Fase 2 (CI) ───────────╯
Semanas 3-4  │ Fase 3 (linters) ──────╮
Semana 4     │ Fase 4 (docs sync) ────┤ (paralelizável)
Semanas 5-6  │ Fase 5 (frontmatter) ──╯
Semanas 6-7  │ Fase 6 (tests reorg)
Semanas 7-9  │ Fase 7 (namespace) ── MAIOR RISCO
Semanas 9-10 │ Fase 8 (extras)
Semana 11    │ Fase 9 (release)
Semanas 11-13│ Fase 10 (hardening)
Semanas 13-14│ Fase 11 (docs site)
Semana 15    │ Fase 12 (plugin opcional)

v3.0.0 release alvo: ~semana 14
```

---

## Métricas de sucesso (após v3.0.0)

| Métrica | Baseline atual | Alvo pós-refactor |
|---|---|---|
| Arquivos top-level | 15+ pastas raiz | 1 pacote `data_agents/` + docs/ + tests/ |
| Discrepâncias README vs código | ≥ 3 conhecidas | 0 (validadas no CI) |
| Linters customizados em CI | 0 | 5 (registry, kb, skills, mcp, commands) |
| Test suite categorizada | Achatada | unit/integration/e2e separados |
| SHA pinning no CI | Não | Sim, 100% das actions |
| `pip-audit` no CI | Não | Sim, fail em HIGH/CRITICAL |
| Governance docs | LICENSE apenas | LICENSE + SECURITY + CONTRIBUTING + CODE_OF_CONDUCT + NOTICE |
| ARCHITECTURE.md | Não | Sim, com C4 |
| ADRs documentados | 0 | ≥ 8 |
| Subpacotes Python opcionais (extras) | Mistura | 6 extras independentes |
| Versioning script | Manual em 3 arquivos | `bump-version.sh` única operação |
| Docs site | Não | MkDocs Material publicado |

---

## Pontos de decisão futuros

Estas decisões serão tomadas durante a execução, não agora:

1. **Renomear o pacote PyPI?** Sugestão: `data-agents-databricks-fabric` é descritivo mas longo; `data-orchestra` ou `forgeai` são curtos mas exigem branding.
2. **Manter Moonshot Kimi K2.6 como default?** Se o endpoint da Moonshot tiver instabilidade, pode-se voltar para Anthropic Sonnet sem perda de feature.
3. **Plugin Claude Code vale o esforço?** Decisão na Fase 12, depende da tração que o projeto ganhar até lá.
4. **OpenTelemetry vs simples JSONL?** Decisão na Fase 10, depende do feedback de usuários comerciais.
5. **MkDocs vs Docusaurus?** Decisão na Fase 11.1.

---

## Reverter o plano

Se em qualquer Fase o trabalho ficar inviável:

1. `git checkout main && git branch -D refactor/v3.0` reverte tudo.
2. `git checkout v2.3.0-pre-refactor` traz o ponto exato anterior.
3. O CHANGELOG não tem entradas v3.0 ainda em main, então nada divulgado quebra.

---

*Documento vivo — atualizar quando o escopo de uma Fase mudar.*
