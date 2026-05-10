"""
Shim de compatibilidade — a implementação foi movida para `workflow/`.

Mantido apenas para preservar imports existentes:
  - `from hooks.workflow_tracker import pre_track_workflow_events, track_workflow_events`

Novos módulos:
  - `workflow.dag`       — constantes, regexes, display names
  - `workflow.tracker`   — hooks PreToolUse / PostToolUse + callbacks de progresso
  - `workflow.executor`  — leitura e sumarização de `logs/workflows.jsonl`
"""

from workflow import (  # noqa: F401 — re-exports
    CLARITY_PATTERN,
    KNOWN_AGENTS,
    PRD_PATTERN,
    SPEC_FILE_PATTERN,
    SPEC_PATTERN,
    WORKFLOW_PATTERN,
    WORKFLOWS_LOG_PATH,
    clear_progress_callbacks,
    get_workflow_summary,
    load_workflow_history,
    pre_track_workflow_events,
    register_progress_callback,
    track_workflow_events,
    unregister_progress_callback,
)

__all__ = [
    "CLARITY_PATTERN",
    "KNOWN_AGENTS",
    "PRD_PATTERN",
    "SPEC_FILE_PATTERN",
    "SPEC_PATTERN",
    "WORKFLOW_PATTERN",
    "WORKFLOWS_LOG_PATH",
    "clear_progress_callbacks",
    "get_workflow_summary",
    "load_workflow_history",
    "pre_track_workflow_events",
    "register_progress_callback",
    "track_workflow_events",
    "unregister_progress_callback",
]
