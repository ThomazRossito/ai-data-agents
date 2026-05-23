"""
lint_registry.py — Structural lint for agent registry.

Validates that every file under ``agents/registry/`` (except templates) declares
the minimum required frontmatter and that every cross-reference points to
something that actually exists.

Checks performed (one per agent unless noted):

    REQUIRED FIELDS
      - frontmatter has 'name', 'description', 'model', 'tools', 'tier'

    SIMPLE VALIDATIONS
      - 'tier' in {T0, T1, T2, T3}
      - 'model' is a non-empty string
      - 'tools' is a list (not a dict, not a string)
      - 'permission_mode' (when present) is a valid Claude Agent SDK value
      - 'effort' (when present) in {low, medium, high, max}
      - 'max_turns' (when present) is a positive integer

    REFERENTIAL INTEGRITY
      - 'mcp_servers' items exist in config.mcp_servers.ALL_MCP_CONFIGS
        (plus the documented 'fabric_community' alias for 'fabric')
      - 'kb_domains' items exist as directories under kb/
      - 'skill_domains' items exist as directories under skills/
      - 'tools' items: each entry is either a native Claude SDK tool, a
        registered alias from agents.loader.MCP_TOOL_SETS, or a fully-qualified
        MCP tool string starting with 'mcp__'

    GLOBAL UNIQUENESS
      - 'name' is unique across the registry

    CROSS-CHECK (agent <-> kb)
      - For each agent listed in kb/<domain>/index.md::agents, that agent must
        declare <domain> in its kb_domains. Reverse direction is INFO only
        (it is acceptable for an agent to read a KB without the KB knowing).

Usage:
    python scripts/lint_registry.py              # human-friendly report
    python scripts/lint_registry.py --quiet      # errors only
    python scripts/lint_registry.py --strict     # warnings count as errors
    python scripts/lint_registry.py --json       # machine-readable output

Exit codes:
    0 — no errors (warnings allowed unless --strict)
    1 — at least one error (or warning with --strict)
    2 — internal lint failure (bad invocation, missing module, etc.)

Designed to run in CI via ``make lint-registry`` and also locally during
development. No third-party dependencies — uses only stdlib plus the project's
own ``utils.frontmatter``.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# Resolve project root robustly: this file lives in <root>/scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Local imports must come after sys.path manipulation
from data_agents.utils.frontmatter import parse_yaml_frontmatter  # noqa: E402

# ─── Constants — single source of truth for valid values ─────────────────────

VALID_TIERS: frozenset[str] = frozenset({"T0", "T1", "T2", "T3"})

VALID_PERMISSION_MODES: frozenset[str] = frozenset(
    {"default", "acceptEdits", "plan", "bypassPermissions", "dontAsk", "auto"}
)

VALID_EFFORTS: frozenset[str] = frozenset({"low", "medium", "high", "max"})

# Native Claude Agent SDK tools that can appear in 'tools:' without being aliases.
# This list is intentionally conservative — only tools we have seen used.
NATIVE_CLAUDE_TOOLS: frozenset[str] = frozenset(
    {
        "Read",
        "Write",
        "Edit",
        "Grep",
        "Glob",
        "Bash",
        "TodoWrite",
        "WebSearch",
        "Task",
        "AskUserQuestion",
        "NotebookEdit",
        "Agent",
        "WebFetch",
    }
)

REQUIRED_FIELDS: tuple[str, ...] = ("name", "description", "model", "tools", "tier")


# ─── Issue model ──────────────────────────────────────────────────────────────


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Issue:
    severity: Severity
    agent: str
    check: str
    message: str
    file: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "agent": self.agent,
            "check": self.check,
            "message": self.message,
            "file": str(self.file) if self.file else None,
        }


@dataclass
class LintReport:
    issues: list[Issue] = field(default_factory=list)
    agents_count: int = 0
    files_scanned: int = 0

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.WARNING]

    @property
    def infos(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.INFO]

    def add(self, issue: Issue) -> None:
        self.issues.append(issue)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _load_valid_mcps() -> set[str]:
    """Returns the set of MCP server names registered in ALL_MCP_CONFIGS,
    plus the documented 'fabric_community' alias which agents reference
    (config/mcp_servers.py::PLATFORM_TO_SERVER_ALIASES)."""
    from data_agents.config.mcp_servers import ALL_MCP_CONFIGS

    valid = set(ALL_MCP_CONFIGS.keys())
    # Documented alias: 'fabric' platform registers a server named
    # 'fabric_community'. Agents declare mcp_servers: [fabric_community] and
    # the loader aliases it back to 'fabric' at runtime.
    valid.add("fabric_community")
    return valid


def _load_valid_aliases() -> set[str]:
    """Returns the set of tool aliases registered in MCP_TOOL_SETS."""
    from data_agents.agents.loader import MCP_TOOL_SETS

    return set(MCP_TOOL_SETS.keys())


def _list_kb_domains() -> set[str]:
    """Returns the set of KB domains (subdirectories of kb/, excluding templates)."""
    kb_dir = PROJECT_ROOT / "kb"
    if not kb_dir.is_dir():
        return set()
    return {
        p.name
        for p in kb_dir.iterdir()
        if p.is_dir() and not p.name.startswith("_")
    }


def _list_skill_domains() -> set[str]:
    """Returns the set of skill domains (subdirectories of skills/)."""
    skills_dir = PROJECT_ROOT / "skills"
    if not skills_dir.is_dir():
        return set()
    return {
        p.name
        for p in skills_dir.iterdir()
        if p.is_dir() and not p.name.startswith("_") and p.name != "TEMPLATE"
    }


def _parse_kb_index_agents(kb_domain: str) -> list[str] | None:
    """Returns the 'agents:' list declared in kb/<domain>/index.md, or None
    if the index has no such field (which is acceptable for shared/utility KBs)."""
    index = PROJECT_ROOT / "kb" / kb_domain / "index.md"
    if not index.is_file():
        return None
    try:
        meta, _ = parse_yaml_frontmatter(index.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    value = meta.get("agents")
    if not isinstance(value, list):
        return None
    return [str(a) for a in value]


# ─── Checks ───────────────────────────────────────────────────────────────────


def check_agent(
    agent_file: Path,
    valid_mcps: set[str],
    valid_aliases: set[str],
    valid_kbs: set[str],
    valid_skills: set[str],
) -> tuple[str | None, list[Issue]]:
    """Runs all single-agent checks. Returns (agent_name_or_none, issues)."""
    issues: list[Issue] = []
    name_for_report = agent_file.stem  # fallback when 'name:' is missing/broken

    try:
        content = agent_file.read_text(encoding="utf-8")
    except OSError as exc:
        issues.append(
            Issue(Severity.ERROR, name_for_report, "io", f"cannot read file: {exc}", agent_file)
        )
        return None, issues

    try:
        metadata, _body = parse_yaml_frontmatter(content)
    except ValueError as exc:
        issues.append(
            Issue(
                Severity.ERROR,
                name_for_report,
                "frontmatter",
                f"invalid YAML frontmatter: {exc}",
                agent_file,
            )
        )
        return None, issues

    # ── Required fields ──
    declared_name = metadata.get("name")
    if isinstance(declared_name, str) and declared_name:
        name_for_report = declared_name

    for field_name in REQUIRED_FIELDS:
        if field_name not in metadata:
            issues.append(
                Issue(
                    Severity.ERROR,
                    name_for_report,
                    "required-field",
                    f"missing required field '{field_name}'",
                    agent_file,
                )
            )

    # Without a name we cannot continue meaningful checks; bail with what we have.
    if not isinstance(declared_name, str) or not declared_name:
        return None, issues

    # ── Tier ──
    tier = metadata.get("tier")
    if tier is not None and tier not in VALID_TIERS:
        issues.append(
            Issue(
                Severity.ERROR,
                declared_name,
                "tier",
                f"tier '{tier}' is not in {sorted(VALID_TIERS)}",
                agent_file,
            )
        )

    # ── Model ──
    model = metadata.get("model")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        issues.append(
            Issue(
                Severity.ERROR,
                declared_name,
                "model",
                f"model must be a non-empty string, got {model!r}",
                agent_file,
            )
        )

    # ── Tools ──
    tools = metadata.get("tools")
    if tools is not None:
        if not isinstance(tools, list):
            issues.append(
                Issue(
                    Severity.ERROR,
                    declared_name,
                    "tools-type",
                    f"'tools' must be a YAML list, got {type(tools).__name__}",
                    agent_file,
                )
            )
        else:
            for tool in tools:
                if not isinstance(tool, str):
                    issues.append(
                        Issue(
                            Severity.ERROR,
                            declared_name,
                            "tools-item-type",
                            f"tool entry must be string, got {tool!r}",
                            agent_file,
                        )
                    )
                    continue
                # Three valid forms:
                #  1) Native Claude SDK tool (Read, Bash, Agent, ...)
                #  2) Registered alias (databricks_all, fabric_readonly, ...)
                #  3) Fully-qualified MCP tool (mcp__<server>__<tool>)
                if tool in NATIVE_CLAUDE_TOOLS:
                    continue
                if tool in valid_aliases:
                    continue
                if tool.startswith("mcp__"):
                    # Format validation only; tool existence checked by lint_mcp_configs.
                    parts = tool.split("__")
                    if len(parts) < 3 or not parts[1] or not parts[2]:
                        issues.append(
                            Issue(
                                Severity.ERROR,
                                declared_name,
                                "tool-format",
                                f"malformed MCP tool name '{tool}' "
                                f"(expected 'mcp__<server>__<tool>')",
                                agent_file,
                            )
                        )
                    continue
                # Unknown
                issues.append(
                    Issue(
                        Severity.ERROR,
                        declared_name,
                        "tool-unknown",
                        f"tool '{tool}' is not a native Claude tool, "
                        f"not in MCP_TOOL_SETS aliases, and does not start "
                        f"with 'mcp__'",
                        agent_file,
                    )
                )

    # ── permission_mode (optional) ──
    perm = metadata.get("permission_mode")
    if perm is not None and perm not in VALID_PERMISSION_MODES:
        issues.append(
            Issue(
                Severity.ERROR,
                declared_name,
                "permission-mode",
                f"permission_mode '{perm}' not in {sorted(VALID_PERMISSION_MODES)}",
                agent_file,
            )
        )

    # ── effort (optional) ──
    effort = metadata.get("effort")
    if effort is not None and effort not in VALID_EFFORTS:
        issues.append(
            Issue(
                Severity.ERROR,
                declared_name,
                "effort",
                f"effort '{effort}' not in {sorted(VALID_EFFORTS)}",
                agent_file,
            )
        )

    # ── max_turns (optional) ──
    max_turns = metadata.get("max_turns")
    if max_turns is not None:
        if not isinstance(max_turns, int) or max_turns <= 0:
            issues.append(
                Issue(
                    Severity.ERROR,
                    declared_name,
                    "max-turns",
                    f"max_turns must be a positive integer, got {max_turns!r}",
                    agent_file,
                )
            )

    # ── mcp_servers referential integrity ──
    mcps = metadata.get("mcp_servers") or []
    if isinstance(mcps, list):
        for mcp in mcps:
            if not isinstance(mcp, str):
                continue  # type already flagged above conceptually
            if mcp not in valid_mcps:
                issues.append(
                    Issue(
                        Severity.ERROR,
                        declared_name,
                        "mcp-server-unknown",
                        f"mcp_servers references '{mcp}' which is not in "
                        f"ALL_MCP_CONFIGS (valid: {sorted(valid_mcps)[:5]}...)",
                        agent_file,
                    )
                )

    # ── kb_domains referential integrity ──
    kbs = metadata.get("kb_domains") or []
    if isinstance(kbs, list):
        for kb in kbs:
            if not isinstance(kb, str):
                continue
            if kb not in valid_kbs:
                issues.append(
                    Issue(
                        Severity.ERROR,
                        declared_name,
                        "kb-domain-unknown",
                        f"kb_domains references '{kb}' which is not a "
                        f"directory under kb/",
                        agent_file,
                    )
                )

    # ── skill_domains referential integrity ──
    skills = metadata.get("skill_domains") or []
    if isinstance(skills, list):
        for skill in skills:
            if not isinstance(skill, str):
                continue
            if skill not in valid_skills:
                issues.append(
                    Issue(
                        Severity.ERROR,
                        declared_name,
                        "skill-domain-unknown",
                        f"skill_domains references '{skill}' which is not a "
                        f"directory under skills/",
                        agent_file,
                    )
                )

    # ── stop_conditions validation (Phase 5) ──
    stop_conds = metadata.get("stop_conditions")
    if stop_conds is not None:
        if not isinstance(stop_conds, list):
            issues.append(
                Issue(
                    Severity.ERROR,
                    declared_name,
                    "stop-conditions-type",
                    f"'stop_conditions' must be a list, got {type(stop_conds).__name__}",
                    agent_file,
                )
            )
        else:
            for i, entry in enumerate(stop_conds):
                if not isinstance(entry, str):
                    issues.append(
                        Issue(
                            Severity.ERROR,
                            declared_name,
                            "stop-conditions-item-type",
                            f"stop_conditions[{i}] must be a string, "
                            f"got {type(entry).__name__}",
                            agent_file,
                        )
                    )

    # ── escalation_rules validation (Phase 5) ──
    escalation_rules = metadata.get("escalation_rules")
    if escalation_rules is not None:
        if not isinstance(escalation_rules, list):
            issues.append(
                Issue(
                    Severity.ERROR,
                    declared_name,
                    "escalation-rules-type",
                    f"'escalation_rules' must be a list, got "
                    f"{type(escalation_rules).__name__}",
                    agent_file,
                )
            )
        else:
            required_keys = {"trigger", "target", "reason"}
            for i, rule in enumerate(escalation_rules):
                if not isinstance(rule, dict):
                    issues.append(
                        Issue(
                            Severity.ERROR,
                            declared_name,
                            "escalation-rule-not-dict",
                            f"escalation_rules[{i}] must be a dict with "
                            f"keys {sorted(required_keys)}",
                            agent_file,
                        )
                    )
                    continue
                missing = required_keys - set(rule.keys())
                if missing:
                    issues.append(
                        Issue(
                            Severity.ERROR,
                            declared_name,
                            "escalation-rule-missing-key",
                            f"escalation_rules[{i}] missing key(s) {sorted(missing)} "
                            f"— required: {sorted(required_keys)}",
                            agent_file,
                        )
                    )
                target = rule.get("target")
                # The target agent must exist in the registry. We can't check
                # it here (the registry isn't fully loaded yet); the cross-check
                # phase below will catch it. We just type-check now.
                if target is not None and not isinstance(target, str):
                    issues.append(
                        Issue(
                            Severity.ERROR,
                            declared_name,
                            "escalation-target-type",
                            f"escalation_rules[{i}].target must be string, "
                            f"got {type(target).__name__}",
                            agent_file,
                        )
                    )

    return declared_name, issues


def check_uniqueness(names: list[str], files: list[Path]) -> list[Issue]:
    """Reports duplicate agent names across the registry."""
    issues: list[Issue] = []
    seen: dict[str, Path] = {}
    for name, file in zip(names, files):
        if not name:
            continue
        if name in seen:
            issues.append(
                Issue(
                    Severity.ERROR,
                    name,
                    "name-uniqueness",
                    f"agent name '{name}' is also declared in {seen[name].name}",
                    file,
                )
            )
        else:
            seen[name] = file
    return issues


def cross_check_escalation_targets(
    agent_metadata: dict[str, dict[str, Any]],
) -> list[Issue]:
    """Each escalation_rules.target must reference a real agent in the registry.
    A dangling target is a silent bug — the supervisor cannot auto-escalate.
    """
    issues: list[Issue] = []
    known_agents = set(agent_metadata.keys())

    for agent_name, meta in agent_metadata.items():
        rules = meta.get("escalation_rules") or []
        if not isinstance(rules, list):
            continue
        for i, rule in enumerate(rules):
            if not isinstance(rule, dict):
                continue
            target = rule.get("target")
            if not isinstance(target, str) or not target:
                continue
            if target == agent_name:
                issues.append(
                    Issue(
                        Severity.ERROR,
                        agent_name,
                        "escalation-self-target",
                        f"escalation_rules[{i}].target='{target}' refers to "
                        f"the agent itself — escalation must point elsewhere",
                    )
                )
                continue
            if target not in known_agents:
                issues.append(
                    Issue(
                        Severity.ERROR,
                        agent_name,
                        "escalation-target-unknown",
                        f"escalation_rules[{i}].target='{target}' is not in "
                        f"the registry (typo? renamed?)",
                    )
                )
    return issues


def cross_check_kb_vs_agents(
    agent_metadata: dict[str, dict[str, Any]],
    valid_kbs: set[str],
) -> list[Issue]:
    """Checks that:
        ERROR — every agent listed in kb/<X>/index.md::agents declares X in kb_domains
        INFO  — every agent declaring kb_domains: [X] is listed in kb/X/index.md::agents
    """
    issues: list[Issue] = []

    for kb_domain in sorted(valid_kbs):
        expected_agents = _parse_kb_index_agents(kb_domain)
        if expected_agents is None:
            continue  # KB has no 'agents:' field declared — fine, skip

        # Direction A (ERROR): KB → agent
        for agent_name in expected_agents:
            if agent_name not in agent_metadata:
                issues.append(
                    Issue(
                        Severity.ERROR,
                        agent_name,
                        "kb-orphan-reference",
                        f"kb/{kb_domain}/index.md lists agent '{agent_name}' "
                        f"which does not exist in agents/registry/",
                    )
                )
                continue
            declared_kbs = agent_metadata[agent_name].get("kb_domains") or []
            if not isinstance(declared_kbs, list):
                continue
            if kb_domain not in declared_kbs:
                issues.append(
                    Issue(
                        Severity.ERROR,
                        agent_name,
                        "kb-missing-declaration",
                        f"kb/{kb_domain}/index.md lists this agent but agent "
                        f"does not declare '{kb_domain}' in kb_domains",
                    )
                )

        # Direction B (INFO): agent → KB index
        for agent_name, meta in agent_metadata.items():
            declared_kbs = meta.get("kb_domains") or []
            if not isinstance(declared_kbs, list):
                continue
            if kb_domain in declared_kbs and agent_name not in expected_agents:
                issues.append(
                    Issue(
                        Severity.INFO,
                        agent_name,
                        "kb-asymmetric-declaration",
                        f"agent declares kb_domains: [{kb_domain}] but "
                        f"kb/{kb_domain}/index.md does not list this agent",
                    )
                )

    return issues


# ─── Output ───────────────────────────────────────────────────────────────────


def _color_for(severity: Severity, isatty: bool) -> tuple[str, str]:
    if not isatty:
        return "", ""
    reset = "\033[0m"
    colors = {
        Severity.ERROR: "\033[31m",  # red
        Severity.WARNING: "\033[33m",  # yellow
        Severity.INFO: "\033[36m",  # cyan
    }
    return colors[severity], reset


def render_report(report: LintReport, quiet: bool, isatty: bool) -> str:
    lines: list[str] = []
    lines.append(f"lint_registry: scanned {report.agents_count} agents in "
                 f"{report.files_scanned} files")
    lines.append("")

    by_agent: dict[str, list[Issue]] = {}
    for issue in report.issues:
        by_agent.setdefault(issue.agent, []).append(issue)

    if not by_agent:
        lines.append("✓ no issues found")
        return "\n".join(lines)

    for agent in sorted(by_agent):
        issues = by_agent[agent]
        if quiet:
            issues = [i for i in issues if i.severity is Severity.ERROR]
            if not issues:
                continue
        lines.append(f"▶ {agent}")
        for issue in issues:
            color, reset = _color_for(issue.severity, isatty)
            lines.append(f"    {color}{issue.severity.value:7}{reset} "
                         f"[{issue.check}] {issue.message}")
        lines.append("")

    lines.append(f"summary: {len(report.errors)} errors, "
                 f"{len(report.warnings)} warnings, "
                 f"{len(report.infos)} infos")
    return "\n".join(lines)


def render_json(report: LintReport) -> str:
    payload = {
        "agents_count": report.agents_count,
        "files_scanned": report.files_scanned,
        "errors": len(report.errors),
        "warnings": len(report.warnings),
        "infos": len(report.infos),
        "issues": [i.to_dict() for i in report.issues],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ─── Main ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Structural lint for agent registry. "
                    "Validates frontmatter, referential integrity, and cross-checks."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (CI gate stricter).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress info-level messages; show errors only.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON for machine consumption.",
    )
    parser.add_argument(
        "--registry-dir",
        type=Path,
        default=PROJECT_ROOT / "data_agents" / "agents" / "registry",
        help="Override the registry directory (default: data_agents/agents/registry).",
    )
    args = parser.parse_args(argv)

    # Load whitelists once
    try:
        valid_mcps = _load_valid_mcps()
        valid_aliases = _load_valid_aliases()
    except Exception as exc:  # noqa: BLE001 — surface any import failure clearly
        print(
            f"lint_registry: FATAL: could not load project metadata: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2

    valid_kbs = _list_kb_domains()
    valid_skills = _list_skill_domains()

    report = LintReport()

    if not args.registry_dir.is_dir():
        print(
            f"lint_registry: FATAL: registry directory not found: {args.registry_dir}",
            file=sys.stderr,
        )
        return 2

    # Phase 1: per-agent checks
    agent_files: list[Path] = []
    agent_names: list[str] = []
    agent_metadata: dict[str, dict[str, Any]] = {}

    for file in sorted(args.registry_dir.glob("*.md")):
        if file.name.startswith("_"):
            continue  # skip _template.md and similar
        report.files_scanned += 1
        name, issues = check_agent(file, valid_mcps, valid_aliases, valid_kbs, valid_skills)
        for issue in issues:
            report.add(issue)
        if name:
            agent_files.append(file)
            agent_names.append(name)
            try:
                meta, _ = parse_yaml_frontmatter(file.read_text(encoding="utf-8"))
                agent_metadata[name] = meta
                report.agents_count += 1
            except (ValueError, OSError):
                pass  # already reported by check_agent

    # Phase 2: cross-checks
    for issue in check_uniqueness(agent_names, agent_files):
        report.add(issue)
    for issue in cross_check_kb_vs_agents(agent_metadata, valid_kbs):
        report.add(issue)
    for issue in cross_check_escalation_targets(agent_metadata):
        report.add(issue)

    # Output
    isatty = sys.stdout.isatty()
    if args.json:
        print(render_json(report))
    else:
        print(render_report(report, args.quiet, isatty))

    # Exit code
    has_errors = len(report.errors) > 0
    has_warnings = len(report.warnings) > 0
    if has_errors:
        return 1
    if args.strict and has_warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
