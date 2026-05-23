# ═══════════════════════════════════════════════════════════════════
# AI Data Agents — Makefile
# Automação de tarefas comuns de desenvolvimento e deploy
# ═══════════════════════════════════════════════════════════════════

.PHONY: help install dev bootstrap demo evals test test-fast test-int test-e2e test-all lint format type-check security clean run health-databricks health-fabric fabric-env deploy-staging deploy-prod refresh-skills refresh-skills-dry refresh-skills-force

# Cores para output
CYAN := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RESET := \033[0m

help: ## Exibe esta ajuda
	@echo ""
	@echo "$(CYAN)AI Data Agents — Comandos disponíveis:$(RESET)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ─── Setup ────────────────────────────────────────────────────────

install: ## Instala dependências de produção
	pip install -e .

dev: ## Instala dependências de desenvolvimento + UI
	pip install -e ".[dev,ui,monitoring]"

bootstrap: ## Wizard interativo para criar .env mínimo (primeira vez)
	python scripts/bootstrap.py

demo: ## Executa query canônica (/geral) — smoke test end-to-end
	python scripts/demo.py

evals: ## Roda queries canônicas (~$$0.08) e gera scoreboard
	python -m evals.runner

# ─── Quality ──────────────────────────────────────────────────────

# Phase 6 test split — categorias auto-marcadas pelos conftest.py de cada subdir:
#   tests/unit/           → mock total, sem rede, sem MCP real, < 1s típico
#   tests/integration/    → toca SQLite/JSONL real, offline, ~1-10s
#   tests/e2e/            → LLM real, Databricks/Fabric real, exige credenciais
#
# Hierarquia:
#   make test-fast  → só unit (iteração rápida, pre-commit)
#   make test-int   → integration (PR check)
#   make test-e2e   → e2e (nightly cron, exige .env completo)
#   make test       → unit + integration (default — sem credenciais externas)
#   make test-all   → tudo, inclusive e2e

test: test-fast test-int ## Roda unit + integration com cobertura (default offline)

test-fast: ## Iteração rápida — só unit/ (< 30s alvo)
	TESTMON_DATAFILE=logs/.testmondata pytest tests/unit/ -v --tb=short \
		--cov=data_agents.agents --cov=data_agents.config --cov=data_agents.hooks --cov=data_agents.commands --cov=data_agents.utils \
		--cov-report=term-missing \
		--cov-fail-under=80

test-int: ## PR check — integration/ (toca SQLite/JSONL local, ~1-10s)
	pytest tests/integration/ -v --tb=short

test-e2e: ## Nightly — e2e/ (exige credenciais reais no .env)
	pytest tests/e2e/ -v --tb=short -m e2e

test-perf: ## Phase 10 — perf baselines (skipped by default, opt-in via -m perf)
	pytest tests/perf/ -v -m perf -s --tb=short

test-all: ## Todos os testes (unit + integration + e2e) — uso manual antes de release
	pytest tests/ -v --tb=short \
		--cov=data_agents.agents --cov=data_agents.config --cov=data_agents.hooks --cov=data_agents.commands --cov=data_agents.utils \
		--cov-report=term-missing \
		--cov-fail-under=80

lint: ## Executa linter (ruff check)
	ruff check . --output-format=full

format: ## Formata código (ruff format)
	ruff format .

type-check: ## Verifica tipos (mypy) — namespace data_agents.*
	mypy data_agents/

security: ## Scan de segurança (bandit apenas — rápido)
	bandit -r data_agents/ -ll --skip B101

security-review: ## Audit completo: bandit + pip-audit + secrets scan (Phase 10)
	bash scripts/security_review.sh

# ─── Structural lints (Phase 3 — drift prevention) ──────────────────
# Each linter validates a specific structural invariant. Run individually
# during development; run lint-all in CI to gate the whole bundle.

lint-registry: ## Valida frontmatter dos 15 agentes + referências
	python scripts/lint_registry.py

lint-kb: ## Valida estrutura das 16 KBs + cross-refs com agentes
	python scripts/lint_kb.py

lint-skills: ## Valida 48 SKILL.md + name/description + orphan domains
	python scripts/lint_skills.py

lint-mcp: ## Valida MCP server_configs + aliases no loader
	python scripts/lint_mcp_configs.py

lint-commands: ## Valida config/commands.yaml (39 slash commands)
	python scripts/lint_commands.py

lint-all: lint lint-registry lint-kb lint-skills lint-mcp lint-commands sync-docs-check ## ruff + 5 lints + doc sync (CI gate)

# ─── Inventory sync ─────────────────────────────────────────────────
# README/PRODUCT/CLAUDE.md declare auto-managed counts via
# <!-- INVENTORY:<key> -->...<!-- /INVENTORY:<key> --> markers.
# `sync-docs` rewrites the values from the live project state.
# `sync-docs-check` exits 1 if any value is stale (CI gate).

inventory: ## Imprime inventário live (agentes/MCPs/KBs/skills/commands)
	python scripts/gen_inventory.py --print

sync-docs: ## Reescreve blocos <!-- INVENTORY:* --> nos docs
	python scripts/gen_inventory.py --update

sync-docs-check: ## Falha se algum doc tem INVENTORY: stale (CI gate)
	python scripts/gen_inventory.py --check

# ─── Execução ─────────────────────────────────────────────────────

run: ## Inicia o AI Data Agents em modo interativo
	python -m data_agents.cli

ui: ## Inicia a UI de Chat + Monitoring (./start.sh)
	./start.sh

ui-chat: ## Inicia somente a UI de Chat Chainlit (porta 8513)
	./start.sh --chat-only

ui-monitor: ## Inicia somente o Monitoring (porta 8511)
	./start.sh --monitor-only

health-databricks: ## Verifica conectividade e credenciais do Databricks
	python tools/databricks_health_check.py

health-fabric: ## Verifica conectividade e credenciais do Microsoft Fabric
	python tools/fabric_health_check.py

fabric-env: ## Cria ambiente conda para Fabric Notebooks (fabric_environment.yml)
	conda env create -f fabric_environment.yml --force
	@echo "$(GREEN)Ambiente 'data_agents_fabric_env' criado. Ative com: conda activate data_agents_fabric_env$(RESET)"

# ─── Deploy ───────────────────────────────────────────────────────

deploy-staging: ## Deploy para Databricks Staging
	databricks bundle deploy --target staging

deploy-prod: ## Deploy para Databricks Production
	databricks bundle deploy --target production

# ─── Skill Refresh ────────────────────────────────────────────────

refresh-skills: ## Atualiza Skills desatualizadas (respeita SKILL_REFRESH_INTERVAL_DAYS)
	python scripts/refresh_skills.py

refresh-skills-dry: ## Lista Skills que seriam atualizadas (sem modificar)
	python scripts/refresh_skills.py --dry-run

refresh-skills-force: ## Força atualização de TODAS as Skills (ignora intervalo)
	python scripts/refresh_skills.py --force

skill-stats: ## Relatório de uso de Skills (últimos 7 dias)
	python scripts/skill_stats.py

skill-stats-full: ## Relatório completo: skills usadas + não usadas (30 dias)
	python scripts/skill_stats.py --days 30 --not-used

# ─── Limpeza ──────────────────────────────────────────────────────

clean: ## Remove arquivos temporários e cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .cache htmlcov coverage.xml
	rm -f logs/.coverage logs/.testmondata
	rm -rf dist build *.egg-info
	@echo "$(GREEN)Limpeza concluída.$(RESET)"
