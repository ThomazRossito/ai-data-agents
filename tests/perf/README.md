# tests/perf/ — Performance baselines

> Phase 10 (skeleton). Não roda em CI principal ainda — só quando solicitado
> via `pytest -m perf` ou `make test-perf`.

---

## Critério de aceitação por teste

Cada teste em `tests/perf/test_*.py` deve:

1. Cronometrar uma operação realista do projeto (load do registry, parse de
   frontmatter em batch, build do supervisor options, etc.) usando
   `time.perf_counter()` ou `pytest-benchmark` quando disponível.
2. Comparar contra um **baseline** documentado no docstring do teste.
3. **Falhar** se exceder o baseline em mais de **20%** (gate de regressão).

O baseline foi medido em **MacBook Pro M1 Pro / Python 3.12 / SSD interno**
em condições não-controladas (não é gate científico — é tripwire de
regressão grosseira).

---

## Quando rodar

| Cenário | Comando |
|---|---|
| Smoke local antes de release | `make test-perf` |
| Pesquisa: comparar before/after de uma mudança | `pytest tests/perf/ -v` (note o baseline impresso) |
| **NUNCA em PR/push regular** | Perf é flaky em GitHub Actions runners (CPU-shared). Skip por default. |

---

## Sobre baselines

Para tornar mais robusto no futuro:
- Adicionar `pytest-benchmark` (gera JSON de stats por teste) + comparação
  contra arquivo `tests/perf/baseline.json` versionado.
- Workflow `.github/workflows/perf.yml` rodando weekly cron numa máquina
  consistente (ou bare-metal runner) e atualizando o baseline.json
  automaticamente via PR.

Hoje, é manual: rode, anote o número, atualize o docstring se a operação
ficou genuinamente mais rápida (não regressão).
