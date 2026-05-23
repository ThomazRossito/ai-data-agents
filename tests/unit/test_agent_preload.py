"""
Testes para AgentMeta e preload_registry() em agents/loader.py (Ch. 12).

Cobre:
  - AgentMeta: estrutura de dados, campos esperados
  - preload_registry(): leitura apenas de frontmatter, sem carregar prompts
  - Tratamento de erros (arquivo inválido, frontmatter faltando)
  - Templates e arquivos com _ são ignorados
  - **Phase 5**: stop_conditions, escalation_rules, skill_domains, e a
    função build_escalation_graph_markdown() que consolida as regras
    em uma tabela Markdown para injeção no system prompt do Supervisor.
"""

from pathlib import Path


from agents.loader import AgentMeta, build_escalation_graph_markdown, preload_registry


# ─── Fixture: registry temporário ────────────────────────────────────────────


def _write_agent_file(registry_dir: Path, name: str, content: str) -> Path:
    path = registry_dir / f"{name}.md"
    path.write_text(content, encoding="utf-8")
    return path


VALID_AGENT_CONTENT = """\
---
name: test-agent
description: "Agente de teste para preload."
model: kimi-k2.6
tools: [Read, Grep]
tier: T2
mcp_servers: []
kb_domains: [sql-patterns]
max_turns: 10
effort: medium
---
# Test Agent
Este é o corpo do prompt que NÃO deve ser carregado no preload.
Com múltiplos parágrafos de conteúdo extenso...
"""

MINIMAL_AGENT_CONTENT = """\
---
name: minimal-agent
description: "Agente mínimo."
model: kimi-k2.6
tools: [Read]
---
# Minimal Agent
Corpo mínimo.
"""

INVALID_NO_NAME_CONTENT = """\
---
description: "Sem nome."
model: kimi-k2.6
tools: []
---
# Sem nome
"""

INVALID_NO_FRONTMATTER = """\
# Arquivo sem frontmatter
Apenas corpo sem delimitadores ---.
"""


# ─── AgentMeta ───────────────────────────────────────────────────────────────


class TestAgentMeta:
    def test_has_expected_fields(self):
        meta = AgentMeta(
            name="test",
            description="desc",
            model="kimi-k2.6",
            tier="T2",
        )
        assert meta.name == "test"
        assert meta.description == "desc"
        assert meta.model == "kimi-k2.6"
        assert meta.tier == "T2"

    def test_default_lists_are_empty(self):
        meta = AgentMeta(name="x", description="d", model="m", tier="T1")
        assert meta.tools == []
        assert meta.mcp_servers == []
        assert meta.kb_domains == []

    def test_optional_fields_default_to_none(self):
        meta = AgentMeta(name="x", description="d", model="m", tier="T1")
        assert meta.max_turns is None
        assert meta.effort is None

    def test_accepts_max_turns(self):
        meta = AgentMeta(name="x", description="d", model="m", tier="T1", max_turns=15)
        assert meta.max_turns == 15

    def test_accepts_effort(self):
        meta = AgentMeta(name="x", description="d", model="m", tier="T1", effort="high")
        assert meta.effort == "high"


# ─── preload_registry ────────────────────────────────────────────────────────


class TestPreloadRegistry:
    def test_returns_dict(self, tmp_path):
        _write_agent_file(tmp_path, "test-agent", VALID_AGENT_CONTENT)
        result = preload_registry(tmp_path)
        assert isinstance(result, dict)

    def test_loads_agent_by_name(self, tmp_path):
        _write_agent_file(tmp_path, "test-agent", VALID_AGENT_CONTENT)
        result = preload_registry(tmp_path)
        assert "test-agent" in result

    def test_loaded_meta_has_correct_name(self, tmp_path):
        _write_agent_file(tmp_path, "test-agent", VALID_AGENT_CONTENT)
        meta = preload_registry(tmp_path)["test-agent"]
        assert meta.name == "test-agent"

    def test_loaded_meta_has_correct_description(self, tmp_path):
        _write_agent_file(tmp_path, "test-agent", VALID_AGENT_CONTENT)
        meta = preload_registry(tmp_path)["test-agent"]
        assert "teste" in meta.description.lower() or "test" in meta.description.lower()

    def test_loaded_meta_has_correct_model(self, tmp_path):
        _write_agent_file(tmp_path, "test-agent", VALID_AGENT_CONTENT)
        meta = preload_registry(tmp_path)["test-agent"]
        assert meta.model == "kimi-k2.6"

    def test_loaded_meta_has_correct_tier(self, tmp_path):
        _write_agent_file(tmp_path, "test-agent", VALID_AGENT_CONTENT)
        meta = preload_registry(tmp_path)["test-agent"]
        assert meta.tier == "T2"

    def test_loaded_meta_has_correct_tools(self, tmp_path):
        _write_agent_file(tmp_path, "test-agent", VALID_AGENT_CONTENT)
        meta = preload_registry(tmp_path)["test-agent"]
        assert "Read" in meta.tools
        assert "Grep" in meta.tools

    def test_loaded_meta_has_max_turns(self, tmp_path):
        _write_agent_file(tmp_path, "test-agent", VALID_AGENT_CONTENT)
        meta = preload_registry(tmp_path)["test-agent"]
        assert meta.max_turns == 10

    def test_loaded_meta_has_effort(self, tmp_path):
        _write_agent_file(tmp_path, "test-agent", VALID_AGENT_CONTENT)
        meta = preload_registry(tmp_path)["test-agent"]
        assert meta.effort == "medium"

    def test_loaded_meta_has_path(self, tmp_path):
        _write_agent_file(tmp_path, "test-agent", VALID_AGENT_CONTENT)
        meta = preload_registry(tmp_path)["test-agent"]
        assert meta.path.exists()
        assert meta.path.name == "test-agent.md"

    def test_minimal_agent_loaded_without_optional_fields(self, tmp_path):
        _write_agent_file(tmp_path, "minimal-agent", MINIMAL_AGENT_CONTENT)
        result = preload_registry(tmp_path)
        assert "minimal-agent" in result
        meta = result["minimal-agent"]
        assert meta.max_turns is None
        assert meta.effort is None

    def test_ignores_files_starting_with_underscore(self, tmp_path):
        _write_agent_file(tmp_path, "_template", VALID_AGENT_CONTENT)
        result = preload_registry(tmp_path)
        assert "_template" not in result
        # Garante que o arquivo foi ignorado, não falhou
        assert len(result) == 0

    def test_ignores_agent_without_name(self, tmp_path):
        _write_agent_file(tmp_path, "no-name", INVALID_NO_NAME_CONTENT)
        result = preload_registry(tmp_path)
        assert len(result) == 0

    def test_handles_invalid_frontmatter_gracefully(self, tmp_path):
        _write_agent_file(tmp_path, "bad-file", INVALID_NO_FRONTMATTER)
        # Não deve levantar exceção — apenas ignorar o arquivo inválido
        result = preload_registry(tmp_path)
        assert isinstance(result, dict)

    def test_loads_multiple_agents(self, tmp_path):
        _write_agent_file(tmp_path, "agent-a", VALID_AGENT_CONTENT.replace("test-agent", "agent-a"))
        _write_agent_file(tmp_path, "agent-b", MINIMAL_AGENT_CONTENT)
        result = preload_registry(tmp_path)
        assert "agent-a" in result
        assert "minimal-agent" in result

    def test_empty_registry_returns_empty_dict(self, tmp_path):
        result = preload_registry(tmp_path)
        assert result == {}

    def test_uses_default_registry_dir_when_none_provided(self):
        """Sem registry_dir, usa o diretório padrão (agents/registry/)."""
        # Só verifica que não levanta exceção e retorna dict
        result = preload_registry()
        assert isinstance(result, dict)
        # O registry real deve ter pelo menos um agente
        assert len(result) > 0


# ─── Phase 5 — Rich frontmatter (stop_conditions, escalation_rules, skill_domains) ──


PHASE5_RICH_CONTENT = """\
---
name: rich-agent
description: |
  Multi-line description with examples for the Supervisor router.

  Example 1:
  - Context: simple case
  - user: "do X"
  - assistant: "rich-agent vai cuidar"
model: kimi-k2.6
tools: [Read]
tier: T2
skill_domains: [databricks, patterns]
stop_conditions:
  - "Out of scope A — escalate to target-a"
  - "Out of scope B — escalate to target-b"
escalation_rules:
  - trigger: "scope A triggered"
    target: target-a
    reason: "target-a owns scope A"
  - trigger: "scope B triggered"
    target: target-b
    reason: "target-b owns scope B"
---
# Rich Agent
Body content.
"""

PHASE5_LEGACY_NO_RICH_FIELDS = """\
---
name: legacy-agent
description: "Plain string description without rich fields."
model: kimi-k2.6
tools: [Read]
tier: T1
---
# Legacy Agent
Body content.
"""

PHASE5_BAD_ESCALATION_TYPES = """\
---
name: typed-bad-agent
description: "Has malformed escalation_rules entries that should be filtered out."
model: kimi-k2.6
tools: [Read]
tier: T2
stop_conditions:
  - "valid string"
  - 12345
escalation_rules:
  - trigger: "real rule"
    target: real-target
    reason: "valid"
  - "not a dict — should be skipped"
  - trigger: "partial rule with non-string target"
    target: 42
    reason: "should still load because preload is defensive"
---
# Typed Bad Agent
"""


class TestPhase5AgentMetaFields:
    def test_agentmeta_has_stop_conditions_default_empty(self):
        meta = AgentMeta(name="x", description="d", model="m", tier="T1")
        assert meta.stop_conditions == []

    def test_agentmeta_has_escalation_rules_default_empty(self):
        meta = AgentMeta(name="x", description="d", model="m", tier="T1")
        assert meta.escalation_rules == []

    def test_agentmeta_has_skill_domains_default_empty(self):
        meta = AgentMeta(name="x", description="d", model="m", tier="T1")
        assert meta.skill_domains == []

    def test_agentmeta_accepts_stop_conditions(self):
        meta = AgentMeta(
            name="x", description="d", model="m", tier="T1",
            stop_conditions=["c1", "c2"],
        )
        assert meta.stop_conditions == ["c1", "c2"]

    def test_agentmeta_accepts_escalation_rules(self):
        rules = [{"trigger": "t", "target": "a", "reason": "r"}]
        meta = AgentMeta(
            name="x", description="d", model="m", tier="T1",
            escalation_rules=rules,
        )
        assert meta.escalation_rules == rules


class TestPhase5PreloadRegistry:
    def test_preload_parses_stop_conditions_as_list(self, tmp_path):
        _write_agent_file(tmp_path, "rich-agent", PHASE5_RICH_CONTENT)
        meta = preload_registry(tmp_path)["rich-agent"]
        assert isinstance(meta.stop_conditions, list)
        assert len(meta.stop_conditions) == 2
        assert all(isinstance(s, str) for s in meta.stop_conditions)

    def test_preload_parses_escalation_rules_as_list_of_dicts(self, tmp_path):
        _write_agent_file(tmp_path, "rich-agent", PHASE5_RICH_CONTENT)
        meta = preload_registry(tmp_path)["rich-agent"]
        assert isinstance(meta.escalation_rules, list)
        assert len(meta.escalation_rules) == 2
        for rule in meta.escalation_rules:
            assert isinstance(rule, dict)
            assert {"trigger", "target", "reason"} <= set(rule.keys())

    def test_preload_parses_skill_domains_as_list(self, tmp_path):
        _write_agent_file(tmp_path, "rich-agent", PHASE5_RICH_CONTENT)
        meta = preload_registry(tmp_path)["rich-agent"]
        assert meta.skill_domains == ["databricks", "patterns"]

    def test_preload_parses_multiline_description(self, tmp_path):
        _write_agent_file(tmp_path, "rich-agent", PHASE5_RICH_CONTENT)
        meta = preload_registry(tmp_path)["rich-agent"]
        # Multi-line description preserved
        assert "Example 1:" in meta.description
        assert len(meta.description.splitlines()) > 1

    def test_preload_legacy_agent_without_phase5_fields(self, tmp_path):
        """Agentes sem stop_conditions/escalation_rules continuam carregando — campos viram listas vazias."""
        _write_agent_file(tmp_path, "legacy-agent", PHASE5_LEGACY_NO_RICH_FIELDS)
        meta = preload_registry(tmp_path)["legacy-agent"]
        assert meta.stop_conditions == []
        assert meta.escalation_rules == []
        assert meta.skill_domains == []

    def test_preload_defensive_against_malformed_entries(self, tmp_path):
        """preload é defensivo: lint_registry pega erros, mas o load deve nunca crashar."""
        _write_agent_file(tmp_path, "typed-bad", PHASE5_BAD_ESCALATION_TYPES)
        meta = preload_registry(tmp_path)["typed-bad-agent"]
        # stop_conditions: int 12345 é coerced para string
        assert "12345" in meta.stop_conditions
        # escalation_rules: dicts são preservados; strings ("not a dict") são filtradas
        rule_count = len(meta.escalation_rules)
        assert rule_count == 2  # ambos os dicts ficam; a string é descartada
        # target=42 vira "42" porque o preload normaliza para str
        targets = [r.get("target") for r in meta.escalation_rules]
        assert "real-target" in targets


# ─── Phase 5 — build_escalation_graph_markdown ───────────────────────────────


class TestBuildEscalationGraph:
    def test_returns_empty_when_no_rules(self, tmp_path):
        # Registry com agente sem escalation_rules
        _write_agent_file(tmp_path, "legacy-agent", PHASE5_LEGACY_NO_RICH_FIELDS)
        metas = preload_registry(tmp_path)
        result = build_escalation_graph_markdown(metas)
        assert result == ""

    def test_returns_markdown_section_when_rules_present(self, tmp_path):
        _write_agent_file(tmp_path, "rich-agent", PHASE5_RICH_CONTENT)
        metas = preload_registry(tmp_path)
        result = build_escalation_graph_markdown(metas)
        assert "# ESCALATION GRAPH" in result
        assert "rich-agent" in result
        assert "target-a" in result
        assert "target-b" in result

    def test_includes_trigger_and_reason_columns(self, tmp_path):
        _write_agent_file(tmp_path, "rich-agent", PHASE5_RICH_CONTENT)
        metas = preload_registry(tmp_path)
        result = build_escalation_graph_markdown(metas)
        assert "scope A triggered" in result
        assert "target-a owns scope A" in result

    def test_escapes_pipe_in_trigger_and_reason(self, tmp_path):
        """Pipes em triggers/reasons quebrariam a tabela Markdown — devem ser escapados."""
        content = """\
---
name: pipe-agent
description: "Agent whose rules contain literal pipe characters."
model: kimi-k2.6
tools: [Read]
tier: T2
escalation_rules:
  - trigger: "a | b | c"
    target: t
    reason: "uses | pipe in reason"
---
# Pipe Agent
"""
        _write_agent_file(tmp_path, "pipe-agent", content)
        metas = preload_registry(tmp_path)
        result = build_escalation_graph_markdown(metas)
        # O pipe interno deve estar escapado (\|) para não quebrar a tabela
        assert "a \\| b \\| c" in result
        assert "uses \\| pipe" in result

    def test_skips_rules_with_empty_target(self, tmp_path):
        content = """\
---
name: empty-target
description: "Has a rule with empty target — should be skipped."
model: kimi-k2.6
tools: [Read]
tier: T2
escalation_rules:
  - trigger: "valid trigger"
    target: ""
    reason: "this one is incomplete"
  - trigger: "second"
    target: real-target
    reason: "this one is complete"
---
# Empty Target
"""
        _write_agent_file(tmp_path, "empty-target", content)
        metas = preload_registry(tmp_path)
        result = build_escalation_graph_markdown(metas)
        # A regra com target vazio é pulada; a outra entra
        assert "real-target" in result
        assert "this one is incomplete" not in result

    def test_includes_footer_with_rule_count(self, tmp_path):
        _write_agent_file(tmp_path, "rich-agent", PHASE5_RICH_CONTENT)
        metas = preload_registry(tmp_path)
        result = build_escalation_graph_markdown(metas)
        assert "2 rules across 1 source agents" in result

    def test_uses_registry_when_no_metas_passed(self):
        """Sem argumento, faz preload do registry real."""
        result = build_escalation_graph_markdown()
        # Registry real tem 15 agentes pós-Phase 5 — alguns deles têm rules
        assert "# ESCALATION GRAPH" in result
        # Pelo menos uma das edges canônicas deve estar lá
        assert "databricks-engineer" in result
        assert "fabric-engineer" in result
