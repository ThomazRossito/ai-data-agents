# Skills Databricks

Duas origens, dois ciclos de vida. Leia `PROVENANCE.md` antes de editar qualquer coisa aqui.

## Upstream (26 skills) — não edite à mão

Vêm do catálogo oficial [`databricks/databricks-agent-skills`](https://github.com/databricks/databricks-agent-skills),
distribuído pela Databricks CLI (≥ 1.0.0). O que está instalado, e de qual versão, está em
`UPSTREAM.json` — é a fonte de verdade, não a memória de ninguém.

Para atualizar:

```bash
databricks aitools install --path /tmp/dbx-skills          # CLI baixa o catálogo estável
make refresh-databricks-skills SRC=/tmp/dbx-skills          # sincroniza + grava UPSTREAM.json
make lint-skills && make test-fast                          # gates
```

`make check-databricks-skills SRC=...` só compara (exit 1 se divergir) — use antes de abrir PR.

Skills **experimentais** do catálogo (`--experimental`) ficam de fora por decisão do projeto.

## Custom (3 skills) — nasceram aqui

`databricks-genie-health-check/`, `databricks-observability-migration/`, `databricks-pricing/`.
O script de sync nunca as toca; `tests/unit/test_functional.py::TestCustomSkillsSurvive`
falha se sumirem.

## Renomes oficiais já aplicados (0.2.10, 2026-09-22)

| Antes | Agora |
|---|---|
| `databricks-bundles` | `databricks-dabs` |
| `databricks-config` | `databricks-core` |
| `databricks-spark-declarative-pipelines` | `databricks-pipelines` |
| `databricks-lakebase-autoscale` + `-provisioned` | `databricks-lakebase` |
| `databricks-genie` | coberto por `databricks-data-discovery` (consulta) — criação de Spaces só no experimental |
| `spark-python-data-source` | saiu do catálogo estável |
