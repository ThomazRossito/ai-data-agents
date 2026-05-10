"""Testes da hierarquia de exceções customizadas."""

import pytest
from config.exceptions import (
    DataAgentsError,
    MCPConnectionError,
    MCPToolExecutionError,
    AuthenticationError,
    BudgetExceededError,
    MaxTurnsExceededError,
    SecurityViolationError,
    SkillNotFoundError,
    ConfigurationError,
)


class TestExceptionHierarchy:
    """Testes para a hierarquia de exceções."""

    def test_all_inherit_from_base(self):
        """Todas as exceções devem herdar de DataAgentsError."""
        exceptions = [
            MCPConnectionError("test"),
            MCPToolExecutionError("test"),
            AuthenticationError("test"),
            BudgetExceededError(1.0, 0.5),
            MaxTurnsExceededError(50),
            SecurityViolationError("cmd", "pattern"),
            SkillNotFoundError("path"),
            ConfigurationError("msg"),
        ]
        for exc in exceptions:
            assert isinstance(exc, DataAgentsError)

    def test_can_catch_by_base_class(self):
        """Deve ser possível capturar qualquer exceção pela classe base."""
        with pytest.raises(DataAgentsError):
            raise MCPConnectionError("databricks", "timeout")

    def test_mcp_connection_error_has_platform(self):
        exc = MCPConnectionError("databricks", "timeout")
        assert exc.platform == "databricks"
        assert "databricks" in str(exc)
        assert "timeout" in str(exc)

    def test_mcp_connection_error_with_cause(self):
        cause = ConnectionError("refused")
        exc = MCPConnectionError("fabric", "falha", cause=cause)
        assert exc.cause is cause
        assert "ConnectionError" in str(exc)

    def test_authentication_error_lists_fields(self):
        exc = AuthenticationError("databricks", ["DATABRICKS_HOST", "DATABRICKS_TOKEN"])
        assert exc.platform == "databricks"
        assert "DATABRICKS_HOST" in str(exc)
        assert "DATABRICKS_TOKEN" in str(exc)

    def test_budget_exceeded_has_values(self):
        exc = BudgetExceededError(5.50, 5.00)
        assert exc.current_cost == 5.50
        assert exc.max_budget == 5.00
        assert "5.5" in str(exc)

    def test_max_turns_exceeded(self):
        exc = MaxTurnsExceededError(50)
        assert exc.max_turns == 50
        assert "50" in str(exc)

    def test_security_violation_has_details(self):
        exc = SecurityViolationError("rm -rf /", "rm.*-rf")
        assert exc.command == "rm -rf /"
        assert exc.pattern == "rm.*-rf"

    def test_skill_not_found_has_path(self):
        exc = SkillNotFoundError("skills/nonexistent/SKILL.md")
        assert exc.skill_path == "skills/nonexistent/SKILL.md"
        assert "nonexistent" in str(exc)
