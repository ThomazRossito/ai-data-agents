# Test Classification — Phase 6

> Inventário e categorização dos 57 arquivos de teste atuais em
> `tests/test_*.py` para a Fase 6 do refactor v3.0.
>
> **Status**: Approved · **Author**: Thomaz A. Rossito Neto · **Date**: 2026-05-22

---

## Metodologia

Cada arquivo foi categorizado segundo três regras estritas:

| Categoria | Critério (qualquer um basta) | Tempo típico |
|---|---|---|
| **e2e** | Chama LLM real OU exige credenciais reais e atinge serviço externo. | > 10 s |
| **integration** | Toca DB local (SQLite), subprocess real, ou faz I/O significativo de arquivos JSONL/Delta que exercita persistência (não apenas write+read de tmp_path). | 1-10 s |
| **unit** | Lógica isolada — mock total, parser, dataclass, função pura. `tmp_path` ok desde que apenas valide read/write trivial. | < 1 s |

**Heurística aplicada** (do usuário: *"é débito ou foi feito assim de propósito?"*):
Antes de classificar como integration, verifiquei se o uso de SQLite/JSONL é *funcional* (parte do contrato testado) ou *acidental* (apenas armazenamento de fixture). Em caso de dúvida, fica como `unit` — uma promoção futura é mais barata do que uma classificação errada agora.

---

## Resultado

| Categoria | Arquivos | % |
|---|---|---|
| **unit** | 52 | 91 % |
| **integration** | 5 | 9 % |
| **e2e** | 0 | 0 % |
| **Total** | 57 | — |

### Por que zero e2e no estado atual?

O projeto não tem hoje nenhum teste que rode contra Databricks/Fabric reais. Os arquivos cujo nome sugeriria "e2e" — `test_databricks_genie_server`, `test_fabric_sql_server`, `test_fabric_semantic_server`, `test_migration_source_server`, `test_geral_command`, `test_summarizer`, `test_health_command`, `test_bootstrap`, `test_mlflow_wrapper` — todos têm o LLM/HTTP/MCP totalmente mockados via `unittest.mock.patch` e `urllib.request.urlopen` ou `requests.*` mockados.

Isso é uma **decisão consistente do projeto**, não um débito: testes são reprodutíveis offline e CI não exige credenciais.

A pasta `tests/e2e/` será criada vazia com um `README.md` explicando o critério, para receber testes futuros quando integrações reais forem adicionadas (ex: avaliação periódica do prompt do Supervisor contra Moonshot real, smoke test pós-deploy contra Databricks workspace de teste).

---

## Tabela completa

Flags: **M** = Mock · **T** = tmp_path · **A** = async · **N** = "network call" (sempre mockada) · **L** = LLM call (sempre mockada) · **D** = DB local · **S** = subprocess

### unit/ (52)

| Arquivo | LOC | Flags | Notas |
|---|---:|---|---|
| test_agent_preload | 445 | T | preload + AgentMeta + build_escalation_graph (Phase 5) |
| test_agents | 1100 | T | Carregamento dos 15 agentes do registry |
| test_analyze_command | 160 | — | Parser de /analyze-project |
| test_azure_pricing_server | 444 | M | Helpers do server MCP, sem HTTP real |
| test_bootstrap | 136 | M | "Funções puras (sem I/O interativo)" |
| test_commands | 188 | — | Registry de slash commands |
| test_config_snapshot | 214 | M | Save/restore de snapshot |
| test_context_budget_hook | 444 | MTA | Contador de tokens, hook puro |
| test_databricks_genie_server | 224 | M | Server helpers com HTTP mockado |
| test_delegation | 93 | — | Roteamento declarativo YAML |
| test_dispatcher | 362 | MA | Two-stage routing, `urllib.urlopen` mockado |
| test_embedder | 141 | T | Helpers determinísticos |
| test_eval | 128 | MT | save/load/summary com tmp file |
| test_evals | 268 | T | Loader + scoring determinístico |
| test_exceptions | 77 | — | Hierarquia de exceções |
| test_exporter | 175 | — | Markdown/HTML rendering (req. `markdown2`) |
| test_fabric_ontology_server | 178 | — | Server helpers |
| test_fabric_semantic_server | 409 | M | TMDL parsers, HTTP mockado |
| test_fabric_sql_server | 212 | M | Server helpers com pyodbc mockado |
| test_frontmatter | 301 | — | Parser pyyaml (NOVO Phase 5) |
| test_functional | 680 | — | Smoke checks estruturais (string match em código) |
| test_geral_command | 271 | MAL | Handler com LLM mockado via `AsyncMock` |
| test_health_command | 266 | M | `_tcp_reachable` mockado |
| test_hooks | 546 | MTA | 22 padrões de security, audit, cost guard |
| test_ledger | 259 | T | HMAC ledger com tmp file |
| test_logging_config | 226 | — | structlog setup |
| test_long_term | 289 | MT | LongTerm memory com mocks |
| test_mcp_command | 122 | M | Parser do comando /mcp |
| test_mcp_configs | 68 | — | Formato dos MCP configs |
| test_memory_compiler | 571 | MT | LLM mockado via `urllib.urlopen` |
| test_memory_decay | 194 | M | Temporal decay determinístico |
| test_memory_extractor | 237 | M | LLM mockado |
| test_memory_hook | 368 | MA | Hook puro |
| test_memory_lesson_learned | 298 | T | Lessons CRUD |
| test_memory_lint | 328 | T | Validação de integridade |
| test_memory_lint_stale | 277 | T | Edge case de lint |
| test_memory_manager | 305 | M | Manager facade |
| test_memory_retrieval | 152 | MT | Retrieval com mock LLM |
| test_memory_store_stale | 225 | T | Edge case de store |
| test_memory_types | 271 | — | Dataclasses |
| test_migration_source_server | 218 | M | Server helpers com pyodbc mockado |
| test_mlflow_wrapper | 214 | M | Wrapper inteiramente mockado (`mlflow` é dep opcional) |
| test_native_skills | 158 | T | Listagem de skills |
| test_output_compressor | 492 | MA | Compression strategies |
| test_refresh_skills_batch | 382 | MTA | Script com `subprocess.run` mockado |
| test_s4_relaxation | 118 | MT | Auto-approval rules |
| test_session_lifecycle | 142 | M | Lifecycle hook |
| test_sessions_command | 368 | MT | Listagem de sessões persistidas |
| test_settings | 333 | MT | Pydantic BaseSettings |
| test_summarizer | 207 | MA | LLM mockado |
| test_supervisor | 241 | M | build_supervisor_options com mocks |
| test_transcript_hook | 330 | MT | Hook puro |
| test_workflow | 369 | MA | DAG + executor com agentes mockados |

### integration/ (5)

Tocam DB local (SQLite) ou exercitam JSONL persistente como contrato — não apenas como fixture descartável.

| Arquivo | LOC | Justificativa |
|---|---:|---|
| test_short_term | 207 | Usa `sqlite3.connect` direto sobre `stm._db_path` — testa o contrato de schema SQLite e migrations. |
| test_session_logger | 435 | Escreve JSONL real em `tmp_path/sessions.jsonl` e valida read-back de múltiplos registros. Tempo dominado por I/O. |
| test_checkpoint | 345 | Save/restore de estado completo — serializa/desserializa em ciclo. |
| test_memory_store | 370 | Persistência JSON com mocks de relógio + writes reais. |
| test_long_term | 289 | (Promovido para integration — TBD na revisão final, depende de SQLite real ou só MT) |

> **Nota sobre `test_long_term`**: tem flag `MT` e usa mock para LLM, mas testa persistência. Será revisado durante a movimentação física dos arquivos — se for puro mock, vai para `unit/`.

### e2e/ (0)

A pasta `tests/e2e/` será criada com `README.md` explicando o critério de admissão:

> Um teste vive em `tests/e2e/` apenas se: (a) chama LLM real via Moonshot/Anthropic,
> (b) atinge um Databricks workspace real, (c) atinge um Fabric workspace real, ou
> (d) executa o binário `python main.py` em subprocess com I/O real.

Testes futuros candidatos a e2e (não existem hoje):
- Smoke test `python main.py "list catalogs"` contra workspace de teste
- Eval semanal do prompt do Supervisor contra Moonshot real (10 queries)

---

## Plano de movimentação

Ordem de execução (commit atômico por grupo):

1. Criar diretórios `tests/{unit,integration,e2e}/` com `__init__.py` vazio
2. Criar `tests/e2e/README.md` (critério de admissão)
3. `git mv` dos 5 arquivos integration (revisar `test_long_term` durante o move)
4. `git mv` dos 52 arquivos unit (em lote — preserva history)
5. Verificar que `conftest.py` (se existir em `tests/`) ainda é descoberto pelo pytest
6. `make test` deve passar igual ao baseline

---

## Esperado pós-Fase 6

| Comando | Tempo alvo | Roda quando |
|---|---:|---|
| `make test-fast` (= `pytest tests/unit/`) | < 30 s | Todo push, pre-commit |
| `make test-int` (= `pytest tests/integration/`) | < 2 min | PR + main |
| `make test-e2e` (= `pytest tests/e2e/`) | (vazio hoje) | nightly cron |
| `make test` (= `pytest tests/`) | < 3 min | Local sanity |
