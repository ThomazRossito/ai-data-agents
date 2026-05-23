# tests/e2e/ — End-to-End tests

> **Status**: Empty by design (no e2e tests exist yet — see
> `docs/refactor-v3/test-classification.md`).

---

## Critério de admissão

Um teste vive em `tests/e2e/` apenas se atender a **pelo menos um** dos critérios abaixo:

1. **LLM real** — chama Moonshot/Anthropic Messages API sem mock.
2. **Databricks real** — atinge um Databricks workspace via MCP oficial com `DATABRICKS_TOKEN` válido.
3. **Fabric real** — atinge um Microsoft Fabric workspace via MCP oficial com `AZURE_TENANT_ID` válido.
4. **Subprocess full-stack** — executa `python main.py "<query>"` em subprocess com I/O completo (CLI loop, hooks, MCPs).

Testes que apenas usam `unittest.mock.patch` para simular essas chamadas pertencem a `tests/unit/` ou `tests/integration/`.

---

## Padrões obrigatórios

### 1. Skip se credenciais ausentes

```python
import os
import pytest


@pytest.fixture
def databricks_token() -> str:
    token = os.environ.get("DATABRICKS_TOKEN", "").strip()
    if not token:
        pytest.skip("requires DATABRICKS_TOKEN in .env")
    return token
```

### 2. Marker automático

`tests/e2e/conftest.py` aplica automaticamente:
- `@pytest.mark.e2e`
- `@pytest.mark.requires_network`

Não é necessário decorar os testes manualmente — o `pytest_collection_modifyitems` cuida disso.

### 3. Timeout explícito

Use `@pytest.mark.timeout(120)` (em segundos) para evitar que falhas de rede travem o CI.

### 4. Cleanup de recursos criados

Se o teste cria recursos no workspace (jobs, tabelas, pipelines), use `try/finally` ou fixtures com `yield` para limpar — caso contrário, o workspace de teste acumula lixo entre execuções.

---

## Quando rodar

| Cenário | Comando |
|---|---|
| Local (dev tem .env completo) | `pytest tests/e2e/` |
| CI nightly (cron 03:00 UTC) | `.github/workflows/test-e2e.yml` |
| CI on-demand (manual trigger) | `workflow_dispatch` no mesmo workflow |
| **NUNCA em PR/push regular** | E2E é caro, lento e pode flake — não bloquear iteração |

---

## Candidatos futuros

Lista mantida para referência — testes que **deveriam** existir aqui:

- [ ] `test_e2e_smoke_main.py` — `python main.py "list catalogs"` retorna 0 e contém um catalog name
- [ ] `test_e2e_supervisor_eval.py` — 10 queries canônicas (em `evals/queries.yaml`) contra Moonshot real, checa rubric scores ≥ baseline
- [ ] `test_e2e_databricks_genie.py` — cria/lista/deleta um Genie Space em workspace de teste
- [ ] `test_e2e_fabric_list_workspaces.py` — autentica via SP e lista workspaces
- [ ] `test_e2e_full_workflow_wf01.py` — executa WF-01 ponta-a-ponta, valida artefatos em `output/`
