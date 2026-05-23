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

## FASE 5 — Frontmatter Rico de Agentes

**Objetivo**: trazer cada agente ao nível do agentspec — declarativo, com `stop_conditions` e `escalation_rules` parsáveis.

### Tasks

| # | Task | Critério de aceitação |
|---|---|---|
| 5.1 | Estender schema de frontmatter (`agents/registry/_template.md`) | Adiciona `stop_conditions: []`, `escalation_rules: []`, `examples: []` ao template |
| 5.2 | Atualizar `agents/loader.py::AgentMeta` para incluir novos campos | Tests passam |
| 5.3 | Atualizar `_parse_frontmatter` para validar tipos dos novos campos | Lint Fase 3 valida estrutura |
| 5.4 | Migrar os 15 agentes: adicionar `stop_conditions` baseado no que hoje está em prosa | Cada agente tem ≥2 stop_conditions |
| 5.5 | Migrar os 15 agentes: adicionar `escalation_rules` baseado em S6 da Constituição | Cada agente tem ≥1 escalation_rule onde aplicável |
| 5.6 | Migrar os 15 agentes: adicionar 2-3 `examples` na description (estilo agentspec) | Cada agente tem `examples` em prosa estruturada |
| 5.7 | Supervisor consome `escalation_rules` para automatizar Step 3.5 (Escalation Handling) | Hooks ou prompt enrichment usa o campo declarativo |
| 5.8 | Tests em `tests/unit/test_agent_metadata.py` validando consistência | Cada agente tem todos os campos obrigatórios |

**Estimativa**: 5-7 dias.
**Risco**: Médio. Mexer em 15 arquivos exige cuidado para não quebrar o prompt cache (cache_prefix.md byte-idêntico).

---

## FASE 6 — Tests Reorganizados

**Objetivo**: separar `tests/unit/`, `tests/integration/`, `tests/e2e/` com markers pytest.

### Tasks

| # | Task | Critério de aceitação |
|---|---|---|
| 6.1 | Criar `tests/unit/`, `tests/integration/`, `tests/e2e/`, mover `conftest.py` | Diretórios existem |
| 6.2 | Classificar os 58 arquivos de teste atuais por categoria | Tabela em `docs/refactor-v3/test-classification.md` |
| 6.3 | Mover arquivos para o diretório correto | Estrutura final em `tests/` |
| 6.4 | Adicionar markers no `pyproject.toml`: `unit`, `integration`, `e2e`, `requires_network`, `slow` | `pytest --markers` lista todos |
| 6.5 | CI job `test-unit` (rápido, todo push) | Roda só `tests/unit/`, < 2 min |
| 6.6 | CI job `test-integration` (push em main/develop e PRs) | Roda `tests/integration/`, < 10 min |
| 6.7 | CI job `test-e2e` (nightly via cron) | Roda `tests/e2e/`, pode ser lento |
| 6.8 | Atualizar `make test` para rodar tudo localmente, `make test-fast` para só unit | Comandos funcionam |

**Estimativa**: 3-5 dias.
**Risco**: Médio. Pode descobrir testes mal classificados (unit que é integration disfarçado).

---

## FASE 7 — Namespace Python (estruturalmente importante)

**Objetivo**: empacotar como pacote Python real (`data_agents/`) em vez de pastas top-level achatadas.

### Tasks

| # | Task | Critério de aceitação |
|---|---|---|
| 7.1 | Criar `data_agents/` como pacote namespace na raiz | `data_agents/__init__.py` existe |
| 7.2 | Mover `agents/` → `data_agents/agents/` | Importações funcionam |
| 7.3 | Mover `config/` → `data_agents/config/` | Importações funcionam |
| 7.4 | Mover `hooks/` → `data_agents/hooks/` | Importações funcionam |
| 7.5 | Mover `memory/` → `data_agents/memory/` | Importações funcionam |
| 7.6 | Mover `commands/` → `data_agents/commands/` | Importações funcionam |
| 7.7 | Mover `compression/`, `workflow/`, `utils/` → `data_agents/` | Importações funcionam |
| 7.8 | Mover `mcp_servers/` → `data_agents/mcp_servers/` | Importações funcionam, entry points em pyproject.toml atualizados |
| 7.9 | `main.py` vira `data_agents/cli.py`; entry point `ai-data-agents = "data_agents.cli:main"` | `pip install -e .` cria comando |
| 7.10 | Atualizar **todos** os imports via `ruff --fix` + revisão manual | Suíte de testes passa, ruff sem violações |
| 7.11 | Atualizar `pyproject.toml`: `packages = ["data_agents"]` | Build wheel funciona |
| 7.12 | Atualizar `.claude/CLAUDE.md` com nova estrutura | Diff visível |
| 7.13 | Atualizar paths em CI workflows | CI verde |
| 7.14 | Atualizar todos os `kb/*/index.md` que referenciam paths | grep não acha caminhos antigos |
| 7.15 | Comando de migração para usuários existentes em `CHANGELOG.md` | Migration note presente |

**Estimativa**: 7-10 dias.
**Risco**: Alto. Esta é a fase mais arriscada — mexe em tudo. Mitigação: branch dedicada `refactor/v3.0-namespace`, merge em pedaços testáveis.

---

## FASE 8 — Modularização de Extras

**Objetivo**: `pip install data-agents-databricks-fabric` instala só o core; extras são opt-in.

### Tasks

| # | Task | Critério de aceitação |
|---|---|---|
| 8.1 | Subpacote `data_agents.ui` (Chainlit) só importável com `[ui]` | `pip install .[ui]` ativa, sem `[ui]` ImportError claro |
| 8.2 | Subpacote `data_agents.monitoring` (Streamlit) só com `[monitoring]` | idem |
| 8.3 | Subpacote `data_agents.visualization` (FastAPI 3D) só com `[viz]` | idem |
| 8.4 | Subpacote `data_agents.memory.embedder` (fastembed) só com `[memory]` | idem |
| 8.5 | Subpacote `data_agents.mcp_servers.fabric_ontology` (rdflib/owlready2) só com `[ontology]` | idem |
| 8.6 | Subpacote `data_agents.mcp_servers.azure_pricing` só com `[finops]` | idem |
| 8.7 | Cada extra tem `README.md` próprio em seu subpacote | Documentação local |
| 8.8 | CI matrix testa instalações: `core`, `[ui]`, `[ui,monitoring]`, `[all]` | Job CI dedicado para install matrix |
| 8.9 | Renomear pacote PyPI para `data-agents-databricks-fabric` (mais descritivo) | Reservar nome no PyPI ainda nesta fase |

**Estimativa**: 5-7 dias.
**Risco**: Médio.

---

## FASE 9 — Versioning e Release

**Objetivo**: release process repetível, sem editar manualmente versão em 5 lugares.

### Tasks

| # | Task | Critério de aceitação |
|---|---|---|
| 9.1 | Criar arquivo `VERSION` (single source) | Existe, contém `3.0.0-rc1` |
| 9.2 | `scripts/bump-version.sh patch|minor|major|rc` atualiza VERSION + pyproject.toml + README badge | Funciona, commitando em uma operação |
| 9.3 | CI gate: `make sync-version --check` falha se VERSION ≠ pyproject.toml version | Gate ativo |
| 9.4 | `.github/workflows/release.yml`: ao push de tag `vX.Y.Z`, builda wheel + cria GitHub Release com changelog | Tag dispara release |
| 9.5 | (Opcional) `release.yml` também publica em PyPI via `pypi-publish` action com OIDC | Publish funciona |
| 9.6 | Auto-changelog via `git-cliff` ou conventional commits | CHANGELOG.md atualizado por script |

**Estimativa**: 2-3 dias.
**Risco**: Baixo.

---

## FASE 10 — Hardening Enterprise

**Objetivo**: nível de maturidade para uso em clientes CI&T / produção corporativa.

### Tasks

| # | Task | Critério de aceitação |
|---|---|---|
| 10.1 | Adicionar OpenTelemetry tracing nos hooks principais | Traces visíveis em Jaeger local |
| 10.2 | Refinar structured logging: cada log tem `session_id`, `agent_name`, `tool_use_id` | grep no JSONL retorna sessões filtráveis |
| 10.3 | Adicionar `data_agents.tenancy` para isolamento de credenciais por workspace | Tests multi-tenant passam |
| 10.4 | `make security-review`: bandit + safety + pip-audit + secrets-scan | Comando único roda tudo |
| 10.5 | Performance benchmarks em `tests/perf/` (custo médio por query) | Baseline documentado, regressão acima de 20% falha CI |
| 10.6 | Adicionar `SLA.md` documentando promessas operacionais | Documento existe |
| 10.7 | Threat model em `docs/SECURITY_THREAT_MODEL.md` | STRIDE applied to ai-data-agents |

**Estimativa**: 7-10 dias.
**Risco**: Médio.

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
