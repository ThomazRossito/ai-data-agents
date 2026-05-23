"""
Testes para utils/frontmatter.py — parser YAML compartilhado.

Cobre a migração feita na Phase 5 (substituição do parser custom linha-por-linha
por pyyaml com SafeLoader customizado que desabilita os aliases booleanos
do YAML 1.1).

Testes principais:
  - YAML 1.1 boolean trap: 'yes'/'no'/'on'/'off' devem permanecer string
  - Block scalars (>- folded, |- literal) funcionam corretamente
  - Listas multilinha (- item) carregam como list
  - Dicts inline ({a: b}) e em bloco (key:\n  sub: val) carregam como dict
  - Frontmatter ausente → ValueError
  - Frontmatter vazio (--- ... ---) → dict vazio + body
  - Top-level que não é dict (ex: lista) → ValueError
"""

import pytest

from data_agents.utils.frontmatter import parse_yaml_frontmatter


# ─── Boolean alias trap (YAML 1.1 vs 1.2) ────────────────────────────────────


class TestYAML11BooleanTrap:
    """
    O YAML 1.1 (padrão do pyyaml) interpreta yes/no/on/off como booleanos.
    Nosso _SafeLoaderNoBoolAlias remove esses aliases. Strings que parecem
    booleanas no YAML 1.1 devem ficar como string.
    """

    def test_yes_stays_string(self):
        content = "---\nflag: yes\n---\n"
        meta, _ = parse_yaml_frontmatter(content)
        assert meta["flag"] == "yes"
        assert isinstance(meta["flag"], str)

    def test_no_stays_string(self):
        content = "---\ncountry: NO\n---\n"
        meta, _ = parse_yaml_frontmatter(content)
        assert meta["country"] == "NO"
        assert isinstance(meta["country"], str)

    def test_on_stays_string(self):
        content = "---\nstatus: on\n---\n"
        meta, _ = parse_yaml_frontmatter(content)
        assert meta["status"] == "on"

    def test_off_stays_string(self):
        content = "---\nfeature: off\n---\n"
        meta, _ = parse_yaml_frontmatter(content)
        assert meta["feature"] == "off"

    def test_true_remains_boolean(self):
        """Apenas true/True/TRUE devem ser interpretados como bool (YAML 1.2 style)."""
        content = "---\nenabled: true\n---\n"
        meta, _ = parse_yaml_frontmatter(content)
        assert meta["enabled"] is True

    def test_false_remains_boolean(self):
        content = "---\nenabled: false\n---\n"
        meta, _ = parse_yaml_frontmatter(content)
        assert meta["enabled"] is False

    def test_True_uppercase_first_remains_boolean(self):
        content = "---\nenabled: True\n---\n"
        meta, _ = parse_yaml_frontmatter(content)
        assert meta["enabled"] is True


# ─── Block scalars ───────────────────────────────────────────────────────────


class TestBlockScalars:
    """
    Block scalars (`>-`, `|-`, `|`, `>`) eram impossíveis de expressar no parser
    custom linha-por-linha — bugs reais no projeto (databricks-dbsql,
    databricks-execution-compute) usavam `description: >-` que era interpretado
    como literal `>-` em vez do conteúdo concatenado.
    """

    def test_folded_scalar_with_strip(self):
        """`>-` concatena linhas em uma só, sem newline final."""
        content = """---
description: >-
  This is a folded scalar
  that spans multiple lines
  but becomes one line.
---
body
"""
        meta, _ = parse_yaml_frontmatter(content)
        assert "\n" not in meta["description"].strip()
        assert "folded scalar" in meta["description"]
        assert "spans multiple lines" in meta["description"]

    def test_literal_scalar_preserves_newlines(self):
        """`|` preserva newlines literais."""
        content = """---
description: |
  Line one
  Line two

  Paragraph 2
---
body
"""
        meta, _ = parse_yaml_frontmatter(content)
        assert "Line one" in meta["description"]
        assert "Line two" in meta["description"]
        assert "Paragraph 2" in meta["description"]
        # Newlines preservadas — o conteúdo tem múltiplas linhas
        assert len(meta["description"].splitlines()) >= 3

    def test_literal_scalar_strip_no_trailing_newline(self):
        """`|-` preserva newlines internas mas strip do trailing."""
        content = """---
description: |-
  No trailing newline here
---
"""
        meta, _ = parse_yaml_frontmatter(content)
        # |- não tem newline final
        assert not meta["description"].endswith("\n")


# ─── Listas e dicts ──────────────────────────────────────────────────────────


class TestListsAndDicts:
    def test_multiline_list(self):
        content = """---
tools:
  - Read
  - Write
  - Grep
---
"""
        meta, _ = parse_yaml_frontmatter(content)
        assert meta["tools"] == ["Read", "Write", "Grep"]

    def test_inline_list_still_works(self):
        """Backward compat — listas inline `[a, b]` ainda parsam como list."""
        content = "---\ntools: [Read, Write, Grep]\n---\n"
        meta, _ = parse_yaml_frontmatter(content)
        assert meta["tools"] == ["Read", "Write", "Grep"]

    def test_list_of_dicts(self):
        """Caso real da Phase 5 — escalation_rules é lista de dicts."""
        content = """---
escalation_rules:
  - trigger: scope A
    target: agent-a
    reason: reason A
  - trigger: scope B
    target: agent-b
    reason: reason B
---
"""
        meta, _ = parse_yaml_frontmatter(content)
        assert len(meta["escalation_rules"]) == 2
        assert meta["escalation_rules"][0]["target"] == "agent-a"
        assert meta["escalation_rules"][1]["reason"] == "reason B"

    def test_inline_dict(self):
        content = "---\nconfig: {a: 1, b: 2}\n---\n"
        meta, _ = parse_yaml_frontmatter(content)
        assert meta["config"] == {"a": 1, "b": 2}

    def test_block_dict(self):
        content = """---
config:
  a: 1
  b: 2
---
"""
        meta, _ = parse_yaml_frontmatter(content)
        assert meta["config"] == {"a": 1, "b": 2}


# ─── Tipos numéricos ─────────────────────────────────────────────────────────


class TestNumericTypes:
    def test_int_remains_int(self):
        content = "---\nmax_turns: 25\n---\n"
        meta, _ = parse_yaml_frontmatter(content)
        assert meta["max_turns"] == 25
        assert isinstance(meta["max_turns"], int)

    def test_float_remains_float(self):
        content = "---\nthreshold: 0.95\n---\n"
        meta, _ = parse_yaml_frontmatter(content)
        assert meta["threshold"] == 0.95
        assert isinstance(meta["threshold"], float)

    def test_numeric_string_stays_string(self):
        """Quoted numerics ficam string."""
        content = '---\nversion: "1.0"\n---\n'
        meta, _ = parse_yaml_frontmatter(content)
        assert meta["version"] == "1.0"
        assert isinstance(meta["version"], str)


# ─── Edge cases ──────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_returns_tuple_of_dict_and_str(self):
        content = "---\nname: x\n---\nbody"
        result = parse_yaml_frontmatter(content)
        assert isinstance(result, tuple)
        assert len(result) == 2
        meta, body = result
        assert isinstance(meta, dict)
        assert isinstance(body, str)

    def test_body_preserved(self):
        content = "---\nname: x\n---\nthis is the body"
        _, body = parse_yaml_frontmatter(content)
        assert body == "this is the body"

    def test_body_multiline_preserved(self):
        content = "---\nname: x\n---\nline 1\nline 2\nline 3"
        _, body = parse_yaml_frontmatter(content)
        assert "line 1" in body
        assert "line 3" in body

    def test_no_frontmatter_raises_valueerror(self):
        with pytest.raises(ValueError):
            parse_yaml_frontmatter("# Just a markdown file with no frontmatter\nBody.")

    def test_empty_frontmatter_returns_empty_dict(self):
        """`--- \\n --- \\n body` → ({}, body)."""
        content = "---\n\n---\nthe body"
        meta, body = parse_yaml_frontmatter(content)
        assert meta == {}
        assert "the body" in body

    def test_non_dict_top_level_raises(self):
        """Frontmatter que é uma lista (não dict) deve falhar."""
        content = "---\n- item1\n- item2\n---\nbody"
        with pytest.raises(ValueError):
            parse_yaml_frontmatter(content)

    def test_invalid_yaml_raises_valueerror(self):
        """YAML mal-formado dentro do frontmatter deve virar ValueError (não YAMLError)."""
        content = "---\nname: [unclosed bracket\n---\n"
        with pytest.raises(ValueError):
            parse_yaml_frontmatter(content)

    def test_non_string_input_raises(self):
        with pytest.raises(ValueError):
            parse_yaml_frontmatter(123)  # type: ignore[arg-type]


# ─── Caso real do projeto ────────────────────────────────────────────────────


class TestRealProjectFrontmatter:
    """Sanity check com um frontmatter representativo do projeto pós-Phase 5."""

    def test_real_agent_frontmatter_parses(self):
        content = """---
name: example-agent
description: |
  A multi-line description.

  Example 1:
  - Context: User wants X
  - user: "do X"
  - assistant: "example-agent will handle"
model: kimi-k2.6
tools: [Read, Write, Grep, databricks_all, context7_all]
mcp_servers: [databricks, context7]
kb_domains: [databricks, sql-patterns]
skill_domains: [databricks]
tier: T1
max_turns: 20
stop_conditions:
  - "Out of scope X — escalate to other-agent"
escalation_rules:
  - trigger: "trigger phrase"
    target: other-agent
    reason: "why escalate"
---
# Example Agent

Body of the prompt.
"""
        meta, body = parse_yaml_frontmatter(content)
        assert meta["name"] == "example-agent"
        assert meta["tier"] == "T1"
        assert meta["max_turns"] == 20
        assert isinstance(meta["tools"], list)
        assert len(meta["tools"]) == 5
        assert isinstance(meta["stop_conditions"], list)
        assert isinstance(meta["escalation_rules"], list)
        assert meta["escalation_rules"][0]["target"] == "other-agent"
        assert "Example Agent" in body
