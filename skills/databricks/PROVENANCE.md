# Proveniência das skills Databricks

Este diretório mistura **duas origens** com ciclos de vida diferentes. Saber qual
é qual evita perder trabalho local num update.

## 1. Upstream — geridas pela Databricks

A maioria das skills aqui veio do catálogo oficial, mantido pela engenharia da
Databricks em [`databricks/databricks-agent-skills`](https://github.com/databricks/databricks-agent-skills)
e distribuído pela CLI (≥ 1.0.0). Entram no repositório por este fluxo:

```bash
databricks aitools install --path /tmp/dbx-skills     # CLI grava os arquivos crus
make refresh-databricks-skills SRC=/tmp/dbx-skills    # scripts/sync_databricks_skills.py
```

O CLI não rastreia instalações feitas com `--path` (`aitools list` não as vê).
O rastreio é nosso: **`UPSTREAM.json`** registra versão do catálogo, data e a
lista exata de skills upstream. `make check-databricks-skills SRC=...` compara
o repo com o que o CLI baixaria e falha se divergir.

**Não edite estas à mão** — o próximo sync sobrescreve sem avisar. Se precisar
de comportamento diferente, crie uma skill custom (seção 2).

Por que `--path` + sync e não `--scope project`: o `--scope project` instala
como plugin do Claude Code em `.claude/`, que não é onde `agents/loader.py` lê
(`skills/<domínio>/<nome>/SKILL.md`) e contorna `skill_domains`, o espelho
`plugins/` e os lints. Versionar as skills no repo mantém a arquitetura e a CI.

## 2. Custom — mantidas neste repositório

Estas **não existem no catálogo oficial**. Nasceram aqui e não voltam por
`aitools`. Se um update removê-las, o trabalho se perde.

| Skill | Por que é custom |
|---|---|
| `databricks-genie-health-check/` | Rubrica de pontuação de saúde de Genie Space, específica deste projeto |
| `databricks-observability-migration/` | Migração de observabilidade, com notas de rollout datadas |
| `databricks-pricing/` | Cálculo de custo DBU, consumido pelo agente `databricks-cost-calculator` |

**Proteção ativa:** `tests/unit/test_functional.py::TestCustomSkillsSurvive` falha
se qualquer uma delas sumir. Não é documentação passiva — é um gate.

## 3. Antes de sincronizar

1. Rode `make check-databricks-skills SRC=<dir>` e leia o diff: `+` novas, `-`
   removidas (renomes oficiais aparecem como `-` antigo / `+` novo), `~` mudou.
2. Todo `-` exige revisar referências explícitas (`commands.yaml`, registry,
   `kb/task_routing.md`, `cd.yml`) — `make lint-commands` acusa caminho morto.
3. Depois do sync: `make lint-skills && make test-fast`. Se
   `TestCustomSkillsSurvive` falhar, restaure as custom pelo git antes de commitar.

Histórico: o instalador antigo do `ai-dev-kit` (`install_skills.sh`, URL 404)
foi removido em 2026-09-22 junto com a adoção do `aitools` (versão 0.2.10).
