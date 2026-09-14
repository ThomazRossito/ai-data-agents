# Proveniência das skills Databricks

Este diretório mistura **duas origens** com ciclos de vida diferentes. Saber qual
é qual evita perder trabalho local num update.

## 1. Upstream — geridas pela Databricks

A maioria das skills aqui veio do catálogo oficial, hoje mantido pela engenharia
da Databricks em [`databricks/databricks-agent-skills`](https://github.com/databricks/databricks-agent-skills)
e distribuído pela CLI:

```bash
databricks aitools list       # o que está instalado
databricks aitools update     # atualiza a partir do upstream
databricks aitools install    # instala/reinstala
```

Requer **Databricks CLI ≥ 1.0.0** (verificado: v1.12.1 funciona).

**Não edite estas à mão** — um `update` sobrescreve a alteração sem avisar.
Se precisar de comportamento diferente, crie uma skill custom (seção 2).

## 2. Custom — mantidas neste repositório

Estas **não existem no catálogo oficial**. Nasceram aqui e não voltam por
`aitools`. Se um update removê-las, o trabalho se perde.

| Skill | Por que é custom |
|---|---|
| `databricks-genie-health-check/` | Rubrica de pontuação de saúde de Genie Space, específica deste projeto |
| `databricks-observability-migration/` | Migração de observabilidade, com notas de rollout datadas |
| `pricing/` | Cálculo de custo DBU, consumido pelo agente `databricks-cost-calculator` |

**Proteção ativa:** `tests/unit/test_functional.py::TestCustomSkillsSurvive` falha
se qualquer uma delas sumir. Não é documentação passiva — é um gate.

## 3. Antes de rodar `aitools install` ou `update`

1. Confirme onde a CLI grava (o destino varia por agente: plugin oficial para
   Claude Code/Codex/Copilot, arquivos crus para Cursor/OpenCode/Antigravity).
2. Rode a suíte depois. Se `TestCustomSkillsSurvive` falhar, o update invadiu
   este diretório — restaure as custom pelo git antes de commitar.

## 4. Artefatos mortos

`install_skills.sh` neste diretório é do instalador **antigo** do `ai-dev-kit`.
Ele aponta para `.../main/databricks-skills/install_skills.sh`, caminho que hoje
retorna **404**, e declara um layout de arquivos que não corresponde mais ao que
está instalado. **Não execute** — usar `databricks aitools` em vez dele.
