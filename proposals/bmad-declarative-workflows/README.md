# Proposta (POC): Workflows declarativos

**Status:** ✅ **PROMOVIDO a módulo de produção.** O código canônico agora vive em
`data_agents/workflow/declarative/loader.py`, com testes em
`tests/unit/test_declarative_workflows.py` (inclui prova de equivalência: o WF-01
em YAML gera steps idênticos ao `build_wf01_pipeline_end_to_end()`). Este diretório
permanece como **design doc**. Origem: auditoria BMAD-METHOD × ai-data-agents
(`audits/2026-07-26-auditoria-bmad-databricks.md`, recomendação B2/#2).

**Ainda NÃO wired no `WORKFLOW_REGISTRY` vivo** (sua decisão qual workflow adicionar).
Para registrar um workflow YAML, é uma linha em `data_agents/commands/workflow.py`:

```python
from data_agents.workflow.declarative.loader import builder_from_yaml, DECLARATIVE_DIR
WORKFLOW_REGISTRY["WF-06"] = {
    "name": "Migração SSIS",
    "description": "...",
    "builder": builder_from_yaml(DECLARATIVE_DIR / "wf06_ssis.yaml"),
    "when": "...",
}
```

## Problema

Hoje os workflows WF-01..05 são **funções Python hardcoded** em
`data_agents/commands/workflow.py` (`build_wf01_pipeline_end_to_end()`, etc.,
a partir da linha 383). Adicionar ou editar um workflow (ex.: um WF-06 de migração
SSIS) exige mexer no código e fazer redeploy. O BMAD-METHOD prova que workflows
podem viver como **dados** (markdown/YAML), editáveis por engenheiros sem tocar
o motor de execução.

## Solução

Externalizar a **definição** para YAML, mantendo o **motor** (`WorkflowRunner`)
intacto. O `loader.py` deste diretório converte o YAML em `list[WorkflowStep]` —
exatamente o tipo que os `build_wfNN_*()` já produzem. Zero invenção: mapeamento
1:1 com a dataclass real.

### Mapeamento YAML ↔ `WorkflowStep`

| Campo YAML | Campo `WorkflowStep` | Obrigatório | Default |
|---|---|---|---|
| `agent` | `agent: str` | sim | — |
| `task` | `task: str` | sim | — |
| `phase` | `phase: str` | não | `""` |
| `parallel_with` | `parallel_with: list[str]` | não | `[]` |
| `require_human_approval` | `require_human_approval: bool` | não | `false` |
| `output_key` | `output_key: str` | não | `""` |

Extras do formato declarativo (não vão para `WorkflowStep`, são resolvidos na carga):
`wf_id`, `description`, e `params` (interpolados no `task` — ex.: `{target_platform}`).
O placeholder `{context}` é **preservado** (o `WorkflowRunner` o preenche em runtime).

## Uso

```python
from loader import load_workflow, to_workflow_steps

parsed = load_workflow("wf01_pipeline.yaml")   # dict validado (função pura)
steps = to_workflow_steps(parsed)              # list[WorkflowStep] (import tardio do SDK)
# runner = WorkflowRunner(wf_id=parsed["wf_id"], steps=steps)
# await runner.run(query="...")
```

`parse_workflow_yaml` é **pura** (só pyyaml) — dá pra testar sem o `claude_agent_sdk`.
Validação embutida: rejeita `wf_id` ausente, `steps` vazio e campos desconhecidos
(pega typos de campo).

## Como promover a produção (wiring sugerido)

1. Mover `loader.py` para `data_agents/workflow/declarative/loader.py` (com testes
   em `tests/unit/test_declarative_workflows.py` cobrindo `parse_workflow_yaml`).
2. Criar `data_agents/workflow/declarative/*.yaml` com os WF-01..05 (portados) +
   novos (ex.: `wf06_ssis_migration.yaml`).
3. Em `data_agents/commands/workflow.py`, no `WORKFLOW_REGISTRY`, permitir entradas
   que carregam de YAML via `to_workflow_steps(load_workflow(path))` em vez de só
   `build_wfNN_*()`. Manter as funções Python existentes (retrocompatível).
4. Estender `scripts/lint_*` para validar os YAML (schema + agentes referenciados
   existem no registry) no CI — a validação já existe em `parse_workflow_yaml`.

## Benefícios

- Autoria de workflows sem redeploy nem Python.
- Diff limpo e revisável (dados vs. código).
- Validação de schema no CI (reaproveita `parse_workflow_yaml`).
- Alinha com o padrão BMAD (`src/bmm-skills/*/steps/*.md`) mantendo os diferenciais
  do ai-data-agents (context-chain, paralelismo, human-pause) que o BMAD não tem.

## Evidência

- Motor real: `data_agents/commands/workflow.py` (`WorkflowRunner` L204, `WorkflowStep` L63, `build_wf01..05` L383+).
- Padrão BMAD: `BMAD-METHOD-main/src/bmm-skills/*/SKILL.md` + `steps/step-NN.md`.
- Porte fiel: `wf01_pipeline.yaml` reproduz `build_wf01_pipeline_end_to_end`.
