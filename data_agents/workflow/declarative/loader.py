"""
workflow.declarative.loader — Workflows declarativos (definição como dado).

Carrega uma definição de workflow em YAML e a converte em `list[WorkflowStep]`,
o mesmo tipo que os `build_wfNN_*()` de `data_agents/commands/workflow.py` produzem.
Permite adicionar/editar workflows (ex.: WF-06 SSIS) sem escrever Python nem
fazer redeploy — inspirado no padrão de workflows-como-dado do BMAD-METHOD
(auditoria 2026-07-26).

Integração retrocompatível: uma entrada YAML no `WORKFLOW_REGISTRY` usa
`builder_from_yaml(path)` no slot `builder`; os builders Python existentes
seguem inalterados.

    from data_agents.workflow.declarative.loader import builder_from_yaml
    WORKFLOW_REGISTRY["WF-06"] = {
        "name": "Migração SSIS",
        "description": "...",
        "builder": builder_from_yaml(DECLARATIVE_DIR / "wf06_ssis.yaml"),
        "when": "...",
    }

`parse_workflow_yaml` é PURA (só pyyaml + stdlib) — testável sem o claude_agent_sdk.
`to_workflow_steps` / `builder_from_yaml` fazem o import tardio de `WorkflowStep`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import yaml

# Diretório canônico das definições YAML deste package.
DECLARATIVE_DIR = Path(__file__).resolve().parent

# Campos aceitos por step — espelham a dataclass WorkflowStep
# (data_agents/commands/workflow.py). Qualquer chave fora disso é erro (pega typo).
_STEP_FIELDS = {
    "agent",
    "task",
    "phase",
    "parallel_with",
    "require_human_approval",
    "output_key",
}
_REQUIRED_FIELDS = {"agent", "task"}


def parse_workflow_yaml(text: str) -> dict[str, Any]:
    """Faz parse + validação do YAML declarativo (função pura).

    Retorna ``{wf_id, description, params, steps: [dict]}`` já com os ``params``
    interpolados no ``task`` (o placeholder ``{context}`` é preservado — ele é
    preenchido pelo WorkflowRunner em runtime). Levanta ``ValueError`` em qualquer
    violação de schema. NÃO constrói WorkflowStep (para não depender do SDK).
    """
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("workflow YAML deve ser um mapping no nível superior")

    wf_id = data.get("wf_id")
    if not isinstance(wf_id, str) or not wf_id.strip():
        raise ValueError("campo 'wf_id' (str não-vazia) é obrigatório")

    params = data.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("'params' deve ser um mapping (chave: valor)")

    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("'steps' deve ser uma lista não-vazia")

    steps: list[dict[str, Any]] = []
    for i, st in enumerate(raw_steps):
        if not isinstance(st, dict):
            raise ValueError(f"step[{i}] deve ser um mapping")
        unknown = set(st) - _STEP_FIELDS
        if unknown:
            raise ValueError(f"step[{i}]: campos desconhecidos {sorted(unknown)}")
        missing = _REQUIRED_FIELDS - set(st)
        if missing:
            raise ValueError(f"step[{i}]: faltam campos obrigatórios {sorted(missing)}")

        task = str(st["task"])
        for key, value in params.items():
            task = task.replace("{" + str(key) + "}", str(value))

        steps.append(
            {
                "agent": str(st["agent"]),
                "task": task,
                "phase": str(st.get("phase", "")),
                "parallel_with": list(st.get("parallel_with", []) or []),
                "require_human_approval": bool(st.get("require_human_approval", False)),
                "output_key": str(st.get("output_key", "")),
            }
        )

    return {
        "wf_id": wf_id,
        "description": str(data.get("description", "")),
        "params": params,
        "steps": steps,
    }


def to_workflow_steps(parsed: dict[str, Any]) -> list[Any]:
    """Converte o dict validado em ``list[WorkflowStep]`` (import tardio do SDK)."""
    from data_agents.commands.workflow import WorkflowStep

    return [
        WorkflowStep(
            agent=step["agent"],
            task=step["task"],
            phase=step["phase"],
            parallel_with=step["parallel_with"],
            require_human_approval=step["require_human_approval"],
            output_key=step["output_key"],
        )
        for step in parsed["steps"]
    ]


def load_workflow(path: str | Path) -> dict[str, Any]:
    """Lê um arquivo YAML e retorna o dict validado.

    Use ``to_workflow_steps(load_workflow(path))`` para obter os objetos prontos
    para o ``WorkflowRunner``.
    """
    return parse_workflow_yaml(Path(path).read_text(encoding="utf-8"))


def builder_from_yaml(path: str | Path) -> Callable[[], list[Any]]:
    """Retorna um ``builder`` (callable sem args → ``list[WorkflowStep]``) para
    plugar direto no ``WORKFLOW_REGISTRY``, espelhando a assinatura dos
    ``build_wfNN_*()`` existentes. O YAML é carregado e validado a cada chamada.
    """

    def _builder() -> list[Any]:
        return to_workflow_steps(load_workflow(path))

    return _builder
