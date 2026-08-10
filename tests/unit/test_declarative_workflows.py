"""
Testes para workflow.declarative.loader — workflows declarativos (YAML → WorkflowStep).

Cobre:
  - parse + validação puros (sem claude_agent_sdk);
  - interpolação de `params` preservando `{context}`;
  - o WF-01 em YAML produzindo steps EQUIVALENTES ao builder Python
    `build_wf01_pipeline_end_to_end()` (prova de que o YAML é substituto fiel);
  - `builder_from_yaml` plugável no WORKFLOW_REGISTRY.
"""

from __future__ import annotations

import pytest

from data_agents.workflow.declarative.loader import (
    DECLARATIVE_DIR,
    builder_from_yaml,
    load_workflow,
    parse_workflow_yaml,
    to_workflow_steps,
)


# ─── parser puro (não importa o SDK) ─────────────────────────────────────────


def test_parse_valid_minimal():
    parsed = parse_workflow_yaml("wf_id: WF-X\nsteps:\n  - agent: a\n    task: t\n")
    assert parsed["wf_id"] == "WF-X"
    assert parsed["steps"] == [
        {
            "agent": "a",
            "task": "t",
            "phase": "",
            "parallel_with": [],
            "require_human_approval": False,
            "output_key": "",
        }
    ]


def test_param_interpolation_preserves_context():
    yaml_text = (
        "wf_id: WF-X\n"
        "params:\n"
        "  plat: databricks\n"
        "steps:\n"
        "  - agent: a\n"
        "    task: 'alvo {plat}, ctx {context}'\n"
    )
    parsed = parse_workflow_yaml(yaml_text)
    assert parsed["steps"][0]["task"] == "alvo databricks, ctx {context}"


def test_reject_missing_wf_id():
    with pytest.raises(ValueError, match="wf_id"):
        parse_workflow_yaml("steps:\n  - agent: a\n    task: t\n")


def test_reject_empty_steps():
    with pytest.raises(ValueError, match="steps"):
        parse_workflow_yaml("wf_id: WF-X\nsteps: []\n")


def test_reject_unknown_field():
    with pytest.raises(ValueError, match="desconhecidos"):
        parse_workflow_yaml("wf_id: WF-X\nsteps:\n  - agent: a\n    task: t\n    foo: 1\n")


def test_reject_missing_required_field():
    with pytest.raises(ValueError, match="obrigatórios"):
        parse_workflow_yaml("wf_id: WF-X\nsteps:\n  - phase: p\n")


def test_reject_non_mapping_top_level():
    with pytest.raises(ValueError, match="mapping"):
        parse_workflow_yaml("- isto\n- é lista\n")


def test_wf01_yaml_parses_six_steps():
    parsed = load_workflow(DECLARATIVE_DIR / "wf01_pipeline.yaml")
    assert parsed["wf_id"] == "WF-01"
    assert len(parsed["steps"]) == 6
    assert parsed["steps"][2]["require_human_approval"] is True
    assert parsed["steps"][3]["parallel_with"] == ["Governance Audit"]


# ─── equivalência com o builder Python (importa o SDK — lazy) ────────────────


def _norm(text: str) -> str:
    """Normaliza whitespace (o YAML block-scalar difere do str concatenado em Python)."""
    return " ".join(text.split())


def test_wf01_yaml_equivalent_to_python_builder():
    from data_agents.commands.workflow import build_wf01_pipeline_end_to_end

    yaml_steps = to_workflow_steps(load_workflow(DECLARATIVE_DIR / "wf01_pipeline.yaml"))
    py_steps = build_wf01_pipeline_end_to_end()

    assert len(yaml_steps) == len(py_steps)
    for y, p in zip(yaml_steps, py_steps):
        assert y.agent == p.agent
        assert y.phase == p.phase
        assert y.parallel_with == p.parallel_with
        assert y.require_human_approval == p.require_human_approval
        assert y.output_key == p.output_key
        assert _norm(y.task) == _norm(p.task)


def test_builder_from_yaml_is_registry_compatible():
    builder = builder_from_yaml(DECLARATIVE_DIR / "wf01_pipeline.yaml")
    steps = builder()  # callable sem args, como os build_wfNN_*()
    assert len(steps) == 6
    assert steps[0].agent == "databricks-engineer"
