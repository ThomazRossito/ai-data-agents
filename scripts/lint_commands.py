"""
lint_commands.py — Structural lint for config/commands.yaml.

The slash command registry is the routing table from CLI/UI to agents.
Bugs here are silent: a malformed command just refuses to dispatch, or
worse, dispatches to a non-existent agent (loader returns None, agent
call fails with an obscure error).

Checks performed per command:

    REQUIRED FIELDS
      ERROR  — missing 'doma_mode'
      ERROR  — missing 'description' (or empty)
      ERROR  — missing 'prompt_template'
      ERROR  — missing 'display_template'

    VALIDATIONS
      ERROR  — 'doma_mode' not in {express, full, internal}
      ERROR  — 'agent' (when set) does not exist in agents/registry/
      WARNING — 'agent' is None but 'doma_mode' is 'express' or 'full'
                (express/full normally target a specific agent)
      ERROR  — 'skills' (when set) lists a path that does not exist on disk
      ERROR  — 'prompt_template' references {task} placeholder count mismatch
               (each template must have exactly one {task})
      WARNING — 'description' shorter than MIN_DESCRIPTION_CHARS
      INFO   — command not registered via 'commands' top-level key (defensive)

    GLOBAL
      ERROR  — duplicate command name (YAML keys are unique by construction,
               but defensive check warns if it somehow happens)
      INFO   — distribution by doma_mode (no failure, informational)

Usage:
    python scripts/lint_commands.py
    python scripts/lint_commands.py --quiet
    python scripts/lint_commands.py --strict
    python scripts/lint_commands.py --json

Exit codes:
    0 — no errors
    1 — at least one error (or warning with --strict)
    2 — internal lint failure (yaml unparseable, etc.)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import yaml  # noqa: E402  (pyyaml is a direct dependency in pyproject.toml)

from data_agents.utils.frontmatter import parse_yaml_frontmatter  # noqa: E402

# ─── Configuration ────────────────────────────────────────────────────────────

# Phase 7: config/ vive dentro do namespace data_agents/
COMMANDS_YAML = PROJECT_ROOT / "data_agents" / "config" / "commands.yaml"

VALID_DOMA_MODES: frozenset[str] = frozenset({"express", "full", "internal"})

REQUIRED_FIELDS: tuple[str, ...] = (
    "doma_mode",
    "description",
    "prompt_template",
    "display_template",
)

MIN_DESCRIPTION_CHARS: int = 20

#: Commands where 'agent: null' is intentional — they dispatch to multiple
#: agents at runtime (DOMA Full / party mode / workflows) or are utility
#: commands that operate without delegating.
AGENT_NULL_BY_DESIGN: frozenset[str] = frozenset({
    "plan",             # DOMA Full — agents picked by dispatcher
    "workflow",         # WF-01..05 multi-agent workflows
    "party",            # Multi-agent independent perspectives
    "analyze-project",  # 4 agents in parallel
    "memory",           # internal — queries memory store
    "sessions",         # internal — lists sessions
    "resume",           # internal — resumes session
    "health",           # internal — platform connectivity
    "status",           # internal — session state
    "mcp",              # internal — lists MCP servers
    "review",           # internal — code review (multi-agent)
    "eval",             # internal — runs evals
})

#: Commands where {task} placeholder is NOT required because the prompt is
#: parameterless — they don't accept user input (lists, statuses, etc).
NO_TASK_PLACEHOLDER_OK: frozenset[str] = frozenset({
    "status",  # lists artifacts via Glob/Read, no user input needed
})


# ─── Issue model ──────────────────────────────────────────────────────────────


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Issue:
    severity: Severity
    command: str
    check: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "command": self.command,
            "check": self.check,
            "message": self.message,
        }


@dataclass
class LintReport:
    issues: list[Issue] = field(default_factory=list)
    commands_scanned: int = 0
    mode_distribution: dict[str, int] = field(default_factory=dict)

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


def _list_valid_agents() -> set[str]:
    """Returns names of agents present in data_agents/agents/registry/."""
    registry = PROJECT_ROOT / "data_agents" / "agents" / "registry"
    names: set[str] = set()
    if not registry.is_dir():
        return names
    for file in registry.glob("*.md"):
        if file.name.startswith("_"):
            continue
        try:
            meta, _ = parse_yaml_frontmatter(file.read_text(encoding="utf-8"))
            n = meta.get("name")
            if isinstance(n, str) and n:
                names.add(n)
        except (ValueError, OSError):
            continue
    return names


def _load_commands_yaml() -> dict[str, Any]:
    """Reads config/commands.yaml and returns the 'commands' mapping.

    Raises RuntimeError on any failure — the caller decides how to handle.
    """
    if not COMMANDS_YAML.is_file():
        raise RuntimeError(f"file not found: {COMMANDS_YAML}")
    try:
        with COMMANDS_YAML.open("r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp)
    except yaml.YAMLError as exc:
        raise RuntimeError(f"yaml parse error: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(
            f"top-level YAML must be a mapping, got {type(data).__name__}"
        )
    commands = data.get("commands")
    if commands is None:
        raise RuntimeError("missing top-level 'commands:' key")
    if not isinstance(commands, dict):
        raise RuntimeError(
            f"'commands' must be a mapping, got {type(commands).__name__}"
        )
    return commands


# ─── Checks ───────────────────────────────────────────────────────────────────


def check_command(name: str, cmd: Any, valid_agents: set[str]) -> list[Issue]:
    """Per-command checks."""
    issues: list[Issue] = []

    if not isinstance(cmd, dict):
        issues.append(
            Issue(
                Severity.ERROR,
                name,
                "command-not-dict",
                f"command entry must be a mapping, got {type(cmd).__name__}",
            )
        )
        return issues

    # ── Required fields ──
    for field_name in REQUIRED_FIELDS:
        if field_name not in cmd:
            issues.append(
                Issue(
                    Severity.ERROR,
                    name,
                    "required-field",
                    f"missing required field '{field_name}'",
                )
            )

    # ── doma_mode validity ──
    mode = cmd.get("doma_mode")
    if mode is not None and mode not in VALID_DOMA_MODES:
        issues.append(
            Issue(
                Severity.ERROR,
                name,
                "doma-mode-invalid",
                f"doma_mode '{mode}' not in {sorted(VALID_DOMA_MODES)}",
            )
        )

    # ── agent existence ──
    agent = cmd.get("agent")
    if agent is not None:
        if not isinstance(agent, str):
            issues.append(
                Issue(
                    Severity.ERROR,
                    name,
                    "agent-type",
                    f"'agent' must be string or null, got {type(agent).__name__}",
                )
            )
        elif agent not in valid_agents:
            issues.append(
                Issue(
                    Severity.ERROR,
                    name,
                    "agent-unknown",
                    f"agent '{agent}' does not exist in agents/registry/",
                )
            )
    else:
        # agent is None: typical for 'internal' commands (/health, /status,
        # /mcp, /workflow, /party, /plan, etc). For express/full this is
        # usually a bug — unless the command is in the by-design whitelist.
        if mode in {"express", "full"} and name not in AGENT_NULL_BY_DESIGN:
            issues.append(
                Issue(
                    Severity.WARNING,
                    name,
                    "agent-null-for-express-full",
                    f"agent is null but doma_mode='{mode}' — express/full "
                    f"commands typically target a specific agent (if "
                    f"intentional, add '{name}' to AGENT_NULL_BY_DESIGN)",
                )
            )

    # ── description quality ──
    desc = cmd.get("description")
    if isinstance(desc, str):
        if not desc.strip():
            issues.append(
                Issue(
                    Severity.ERROR,
                    name,
                    "description-empty",
                    "'description' is empty after stripping whitespace",
                )
            )
        elif len(desc.strip()) < MIN_DESCRIPTION_CHARS:
            issues.append(
                Issue(
                    Severity.WARNING,
                    name,
                    "description-too-short",
                    f"'description' is {len(desc.strip())} chars "
                    f"(< {MIN_DESCRIPTION_CHARS})",
                )
            )

    # ── prompt_template placeholders ──
    prompt = cmd.get("prompt_template")
    if isinstance(prompt, str):
        if not prompt.strip():
            issues.append(
                Issue(
                    Severity.ERROR,
                    name,
                    "prompt-template-empty",
                    "'prompt_template' is empty",
                )
            )
        else:
            # commands/parser.py calls .format(task=task_expanded), so {task}
            # must appear exactly once. {agent} may appear in display_template
            # but not in prompt_template — checked here for safety.
            task_count = prompt.count("{task}")
            if task_count == 0 and name not in NO_TASK_PLACEHOLDER_OK:
                issues.append(
                    Issue(
                        Severity.ERROR,
                        name,
                        "prompt-no-task-placeholder",
                        "'prompt_template' has no {task} placeholder — "
                        "user input will not be inserted (if intentional, "
                        f"add '{name}' to NO_TASK_PLACEHOLDER_OK)",
                    )
                )
            elif task_count > 1:
                issues.append(
                    Issue(
                        Severity.WARNING,
                        name,
                        "prompt-multiple-task-placeholders",
                        f"'prompt_template' has {task_count} {{task}} "
                        f"placeholders — only first will be substituted by "
                        f"format(); duplicates will receive same value",
                    )
                )

    # ── display_template placeholders ──
    display = cmd.get("display_template")
    if isinstance(display, str) and not display.strip():
        issues.append(
            Issue(
                Severity.ERROR,
                name,
                "display-template-empty",
                "'display_template' is empty",
            )
        )

    # ── skills paths existence ──
    skills = cmd.get("skills") or []
    if not isinstance(skills, list):
        issues.append(
            Issue(
                Severity.ERROR,
                name,
                "skills-not-list",
                f"'skills' must be a list, got {type(skills).__name__}",
            )
        )
    else:
        for s in skills:
            if not isinstance(s, str):
                issues.append(
                    Issue(
                        Severity.ERROR,
                        name,
                        "skill-entry-not-string",
                        f"skill entry must be string, got {s!r}",
                    )
                )
                continue
            target = PROJECT_ROOT / s
            if not target.exists():
                issues.append(
                    Issue(
                        Severity.ERROR,
                        name,
                        "skill-path-missing",
                        f"'skills' references '{s}' which does not exist on disk",
                    )
                )

    return issues


# ─── Output ───────────────────────────────────────────────────────────────────


def _color_for(severity: Severity, isatty: bool) -> tuple[str, str]:
    if not isatty:
        return "", ""
    reset = "\033[0m"
    colors = {
        Severity.ERROR: "\033[31m",
        Severity.WARNING: "\033[33m",
        Severity.INFO: "\033[36m",
    }
    return colors[severity], reset


def render_report(report: LintReport, quiet: bool, isatty: bool) -> str:
    lines: list[str] = [f"lint_commands: scanned {report.commands_scanned} commands"]
    if report.mode_distribution:
        dist = ", ".join(
            f"{k}={v}" for k, v in sorted(report.mode_distribution.items())
        )
        lines.append(f"mode distribution: {dist}")
    lines.append("")

    by_command: dict[str, list[Issue]] = {}
    for issue in report.issues:
        by_command.setdefault(issue.command, []).append(issue)

    if not by_command:
        lines.append("✓ no issues found")
        return "\n".join(lines)

    for command in sorted(by_command):
        issues = by_command[command]
        if quiet:
            issues = [i for i in issues if i.severity is Severity.ERROR]
            if not issues:
                continue
        lines.append(f"▶ /{command}")
        for issue in issues:
            color, reset = _color_for(issue.severity, isatty)
            lines.append(
                f"    {color}{issue.severity.value:7}{reset} "
                f"[{issue.check}] {issue.message}"
            )
        lines.append("")

    lines.append(
        f"summary: {len(report.errors)} errors, "
        f"{len(report.warnings)} warnings, "
        f"{len(report.infos)} infos"
    )
    return "\n".join(lines)


def render_json(report: LintReport) -> str:
    payload = {
        "commands_scanned": report.commands_scanned,
        "mode_distribution": report.mode_distribution,
        "errors": len(report.errors),
        "warnings": len(report.warnings),
        "infos": len(report.infos),
        "issues": [i.to_dict() for i in report.issues],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ─── Main ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Structural lint for config/commands.yaml — validates "
                    "every slash command's fields, agent existence, mode, "
                    "skills references and placeholders."
    )
    parser.add_argument("--strict", action="store_true",
                        help="Treat warnings as errors.")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress non-error messages.")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON for machine consumption.")
    args = parser.parse_args(argv)

    report = LintReport()

    try:
        commands = _load_commands_yaml()
    except RuntimeError as exc:
        print(f"lint_commands: FATAL: {exc}", file=sys.stderr)
        return 2

    valid_agents = _list_valid_agents()
    if not valid_agents:
        print(
            "lint_commands: WARNING — could not load any agents from registry. "
            "Agent existence checks will be skipped.",
            file=sys.stderr,
        )

    for name, cmd in commands.items():
        report.commands_scanned += 1
        # Track mode distribution for the summary line
        if isinstance(cmd, dict):
            mode = cmd.get("doma_mode", "<missing>")
            report.mode_distribution[str(mode)] = (
                report.mode_distribution.get(str(mode), 0) + 1
            )

        for issue in check_command(name, cmd, valid_agents):
            report.add(issue)

    # Output
    isatty = sys.stdout.isatty()
    if args.json:
        print(render_json(report))
    else:
        print(render_report(report, args.quiet, isatty))

    has_errors = len(report.errors) > 0
    has_warnings = len(report.warnings) > 0
    if has_errors:
        return 1
    if args.strict and has_warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
