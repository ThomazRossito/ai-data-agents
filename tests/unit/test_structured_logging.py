"""
Phase 10: invariante estrutural para hooks que escrevem JSONL.

Todo log_entry produzido por hooks que persistem em `logs/*.jsonl` DEVE conter
os 3 campos canônicos quando aplicáveis:

  - session_id  (rastreabilidade transversal — JOIN entre audit ↔ sessions ↔ transcript)
  - agent_name  (qual subagente fez a tool call; None para tools do Supervisor)
  - tool_use_id (correlação tool_use ↔ tool_result emitida pelo Anthropic SDK)

Não checamos formato de cada JSONL produzido em runtime (isso seria
integration test). Checamos sim que o CÓDIGO dos hooks REFERENCIA os campos
canônicos no payload — protege contra regressões silenciosas em refactors
futuros (alguém removendo um campo sem perceber que outro hook dependia).

Estratégia: source-code lint, não runtime. Lê cada arquivo de hook listado
em HOOKS_THAT_LOG e grep por substring textual.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Phase 7: hooks vivem em data_agents/hooks/ — repo root é 2 níveis acima.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOKS_DIR = REPO_ROOT / "data_agents" / "hooks"


# Hooks que escrevem JSONL e os campos canônicos exigidos.
# Cada chave: nome do arquivo. Cada valor: lista de campos canônicos que
# DEVEM aparecer no payload do log_entry. Use only_if_present=False para
# campos opcionais (ex: tool_use_id só faz sentido em hooks PostToolUse).
LOGGING_CONTRACT: dict[str, list[str]] = {
    "audit_hook.py": ["session_id", "agent_name", "tool_use_id"],
    "session_logger.py": ["session_id"],
    # transcript_hook escreve por session_id no path; o campo aparece como
    # "session_id" no payload tbm.
    "transcript_hook.py": ["session_id"],
}


@pytest.mark.parametrize(
    ("filename", "required_fields"),
    list(LOGGING_CONTRACT.items()),
    ids=list(LOGGING_CONTRACT.keys()),
)
def test_hook_logs_canonical_fields(filename: str, required_fields: list[str]) -> None:
    """Cada hook que loga JSONL referencia os campos canônicos no payload."""
    path = HOOKS_DIR / filename
    assert path.exists(), f"Hook {filename} não encontrado em {HOOKS_DIR}"

    src = path.read_text(encoding="utf-8")

    # Para cada campo canônico, exige aparição como chave de dict literal:
    #   "session_id": ...
    # Aceita variações com aspas simples também.
    for field in required_fields:
        patterns = [f'"{field}":', f"'{field}':"]
        present = any(p in src for p in patterns)
        assert present, (
            f"{filename} não tem chave '{field}' em nenhum log_entry. "
            f"Phase 10 contract: hooks que persistem JSONL devem incluir "
            f"session_id (+ agent_name/tool_use_id quando aplicável) para "
            f"permitir JOIN entre logs."
        )


def test_no_hook_writes_jsonl_without_being_in_contract() -> None:
    """
    Anti-regression: se alguém adicionar um novo hook que escreve JSONL,
    o teste falha avisando para adicionar ao LOGGING_CONTRACT. Garante que
    a auditoria não fica desatualizada quando hooks novos chegam.
    """
    new_hooks_writing_jsonl: list[str] = []
    for hook_file in HOOKS_DIR.glob("*.py"):
        if hook_file.name in ("__init__.py", "checkpoint.py"):
            continue  # checkpoint serializa state, não é log de evento
        src = hook_file.read_text(encoding="utf-8")
        # Indica que o hook escreve em JSONL (heurística: chama json.dumps
        # e contém ".jsonl" como literal string)
        writes_jsonl = "json.dumps" in src and ".jsonl" in src
        if writes_jsonl and hook_file.name not in LOGGING_CONTRACT:
            new_hooks_writing_jsonl.append(hook_file.name)

    assert not new_hooks_writing_jsonl, (
        f"Novos hooks gravam JSONL mas não estão em LOGGING_CONTRACT: "
        f"{new_hooks_writing_jsonl}. Adicione-os à constante com a lista "
        f"de campos canônicos que cada um deve incluir."
    )
