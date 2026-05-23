"""Testes do event_translator: raw JSONL → schema visual."""

from __future__ import annotations

from data_agents.visualization.event_translator import (
    normalize_agent_name,
    translate,
    translate_audit_event,
    translate_workflow_event,
)


class TestNormalizeAgentName:
    def test_already_canonical_passes(self):
        assert normalize_agent_name("python-expert") == "python-expert"
        assert normalize_agent_name("data-quality-steward") == "data-quality-steward"

    def test_title_case_with_spaces(self):
        assert normalize_agent_name("Python Expert") == "python-expert"
        assert normalize_agent_name("Data Quality Steward") == "data-quality-steward"

    def test_extra_whitespace_stripped(self):
        assert normalize_agent_name("  Python  Expert  ") == "python-expert"

    def test_none_returns_none(self):
        assert normalize_agent_name(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_agent_name("") is None


class TestTranslateWorkflowEvent:
    def test_workflow_step_produces_delegation(self):
        raw = {
            "timestamp": "2026-05-11T11:02:41.150977+00:00",
            "event": "workflow_step",
            "agent": "Python Expert",
            "tool_use_id": "Agent_24",
            "prompt_preview": "[USER_LANG: PT-BR]\n\n## Contexto\n...",
            "workflow": "WF-02",
        }
        result = translate_workflow_event(raw)
        assert result is not None
        assert result["type"] == "delegation"
        assert result["agent"] == "python-expert"
        assert result["metadata"]["workflow"] == "WF-02"
        assert result["metadata"]["tool_use_id"] == "Agent_24"

    def test_non_workflow_event_returns_none(self):
        raw = {"event": "tool_call", "agent": "Python Expert"}
        assert translate_workflow_event(raw) is None

    def test_missing_agent_returns_none(self):
        raw = {"event": "workflow_step", "agent": None}
        assert translate_workflow_event(raw) is None

    def test_prompt_preview_truncated(self):
        raw = {
            "event": "workflow_step",
            "agent": "Python Expert",
            "prompt_preview": "x" * 500,
        }
        result = translate_workflow_event(raw)
        assert result is not None
        assert len(result["metadata"]["prompt_preview"]) == 160


class TestTranslateAuditEvent:
    def test_tool_call_with_databricks_platform(self):
        raw = {
            "timestamp": "2026-05-11T11:07:48Z",
            "event": "tool_call",
            "tool_name": "mcp__databricks__execute_sql",
            "session_id": "cli-abc",
            "agent_name": "databricks-engineer",
            "has_error": False,
        }
        result = translate_audit_event(raw)
        assert result is not None
        assert result["type"] == "tool_call"
        assert result["agent"] == "databricks-engineer"
        assert result["tool"] == "mcp__databricks__execute_sql"
        assert result["platform"] == "databricks"

    def test_platform_inferred_when_not_set(self):
        raw = {
            "event": "tool_call",
            "tool_name": "mcp__fabric_sql__list_tables",
            "platform": None,
        }
        result = translate_audit_event(raw)
        assert result is not None
        assert result["platform"] == "fabric"

    def test_explicit_platform_wins_over_inference(self):
        raw = {
            "event": "tool_call",
            "tool_name": "mcp__databricks__execute_sql",
            "platform": "custom-platform",
        }
        result = translate_audit_event(raw)
        assert result["platform"] == "custom-platform"

    def test_noise_tool_filtered(self):
        # Apenas ExitPlanMode é filtrado (Todowrite/TodoWrite passam pra dar
        # sinal de vida quando supervisor está só planejando)
        raw = {"event": "tool_call", "tool_name": "ExitPlanMode"}
        assert translate_audit_event(raw) is None

    def test_todowrite_passes(self):
        """Todowrite/TodoWrite agora passam — antes filtradas como ruído."""
        for name in ("Todowrite", "TodoWrite"):
            raw = {"event": "tool_call", "tool_name": name}
            result = translate_audit_event(raw)
            assert result is not None
            assert result["tool"] == name

    def test_dispatcher_decision(self):
        raw = {
            "timestamp": "2026-05-11T11:00Z",
            "event": "dispatcher_decision",
            "session_id": "cli-xyz",
            "selected": ["databricks-engineer", "data-quality-steward"],
            "confidence": 0.87,
            "reason": "query menciona Spark + validação",
            "fallback_applied": False,
        }
        result = translate_audit_event(raw)
        assert result is not None
        assert result["type"] == "dispatcher_decision"
        assert result["metadata"]["selected"] == ["databricks-engineer", "data-quality-steward"]
        assert result["metadata"]["confidence"] == 0.87
        assert result["metadata"]["fallback_applied"] is False

    def test_session_end(self):
        raw = {
            "timestamp": "2026-05-11T11:10Z",
            "event": "session_end",
            "session_id": "cli-xyz",
            "cost_usd": 0.123,
            "turns": 16,
            "duration_s": 429.3,
        }
        result = translate_audit_event(raw)
        assert result is not None
        assert result["type"] == "session_end"
        assert result["metadata"]["cost_usd"] == 0.123
        assert result["metadata"]["turns"] == 16

    def test_agent_delegated_variant(self):
        raw = {
            "event": "agent_delegated",
            "agent_name": "Fabric Engineer",
            "tool_use_id": "Agent_1",
        }
        result = translate_audit_event(raw)
        assert result is not None
        assert result["type"] == "delegation"
        assert result["agent"] == "fabric-engineer"

    def test_unknown_event_returns_none(self):
        raw = {"event": "ledger_entry", "hash": "abc"}
        assert translate_audit_event(raw) is None


class TestTranslateDispatcher:
    def test_routes_to_workflow_translator(self):
        raw = {"event": "workflow_step", "agent": "Python Expert"}
        result = translate(raw, "workflow")
        assert result is not None
        assert result["type"] == "delegation"

    def test_routes_to_audit_translator(self):
        raw = {"event": "tool_call", "tool_name": "Read"}
        result = translate(raw, "audit")
        assert result is not None
        assert result["type"] == "tool_call"

    def test_unknown_source_returns_none(self):
        raw = {"event": "tool_call", "tool_name": "Read"}
        assert translate(raw, "bogus") is None
