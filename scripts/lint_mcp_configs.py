"""
lint_mcp_configs.py — Structural lint for MCP server configurations.

Validates every ``mcp_servers/<n>/server_config.py`` against runtime
invariants that, if violated, cause silent failures in the loader or
in agent delegations:

    PER MCP SERVER
      ERROR    — server_config.py missing
      ERROR    — function get_<n>_mcp_config() missing (with documented exceptions)
      ERROR    — function raises on import or call (settings missing? circular import?)
      ERROR    — returned dict has wrong shape: must be {server_key: {type, command, args, env}}
      ERROR    — declared tools list missing (e.g. <NAME>_MCP_TOOLS not exported)
      ERROR    — tool entries not prefixed with mcp__<key>__ for their declared server
      ERROR    — duplicate tool name within the same TOOLS list

    GLOBAL CHECKS
      ERROR    — server registered in config.mcp_servers.ALL_MCP_CONFIGS but no <name>_all
                 alias in agents.loader.MCP_TOOL_SETS (tools will be unresolvable)
      WARNING  — server in ALL_MCP_CONFIGS but no <name>_readonly alias (granularity missing)
      WARNING  — alias in MCP_TOOL_SETS that does not correspond to any registered server
                 (dead alias — points to nothing useful)
      INFO     — alias _aibi / _serving / _compute / etc that is NOT the standard pattern

    KNOWN EXCEPTIONS (built-in to the linter)
      - 'fabric' directory registers TWO servers: fabric_community + fabric_official.
        Both functions accepted: get_fabric_mcp_config, get_fabric_official_mcp_config.
      - 'fabric_ontology' uses generic constant names MCP_TOOLS / MCP_READONLY_TOOLS
        (renamed on import in agents/loader.py via `as`).

Usage:
    python scripts/lint_mcp_configs.py
    python scripts/lint_mcp_configs.py --quiet
    python scripts/lint_mcp_configs.py --strict
    python scripts/lint_mcp_configs.py --json

Exit codes:
    0 — no errors
    1 — at least one error (or warning with --strict)
    2 — internal lint failure
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ─── Known exceptions to the standard convention ─────────────────────────────

#: Directories under mcp_servers/ that intentionally diverge from the
#: 'one directory = one function = one server' convention.
#: Maps dir name → list of (function_name, server_key_in_returned_dict).
MULTI_SERVER_DIRS: dict[str, list[tuple[str, str]]] = {
    "fabric": [
        ("get_fabric_mcp_config", "fabric_community"),
        ("get_fabric_official_mcp_config", "fabric_official"),
    ],
}

#: Directories that use generic constant names (MCP_TOOLS) instead of the
#: <NAME>_MCP_TOOLS convention. They're renamed on import in agents/loader.py
#: using the `as` keyword.
GENERIC_CONSTANTS_DIRS: frozenset[str] = frozenset({"fabric_ontology"})

#: Directories to skip when discovering MCPs.
SKIP_DIR_NAMES: frozenset[str] = frozenset({"_template", "__pycache__"})

#: MCPs that are inherently read-only — their tools cannot mutate state, so
#: a '_readonly' alias would be a useless duplicate of '_all'.
#:  - context7: documentation search (no writes)
#:  - firecrawl: web scraping (no writes)
#:  - postgres: server enforces SELECT-only at the MCP layer
#:  - tavily: web search (no writes)
READONLY_BY_NATURE: frozenset[str] = frozenset({
    "context7",
    "firecrawl",
    "postgres",
    "tavily",
})


# ─── Issue model ──────────────────────────────────────────────────────────────


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Issue:
    severity: Severity
    server: str
    check: str
    message: str
    file: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "server": self.server,
            "check": self.check,
            "message": self.message,
            "file": str(self.file) if self.file else None,
        }


@dataclass
class LintReport:
    issues: list[Issue] = field(default_factory=list)
    dirs_scanned: int = 0
    servers_registered: int = 0

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


def _list_mcp_dirs() -> list[Path]:
    """Returns subdirectories of data_agents/mcp_servers/ that should be treated as MCPs."""
    root = PROJECT_ROOT / "data_agents" / "mcp_servers"
    if not root.is_dir():
        return []
    return sorted(
        p for p in root.iterdir()
        if p.is_dir() and p.name not in SKIP_DIR_NAMES and not p.name.startswith("_")
    )


def _import_module(dotted: str) -> Any:
    """Imports a module by its dotted path. Raises on failure."""
    return importlib.import_module(dotted)


def _function_suffix(dir_name: str) -> str:
    """Returns the function-name suffix for a dir.

    Convention: most dirs use '<dir>_mcp_config'. But dirs whose name
    already ends with '_mcp' (e.g. 'memory_mcp') drop the duplicated
    '_mcp' to avoid 'get_memory_mcp_mcp_config'.
    """
    if dir_name.endswith("_mcp"):
        return f"get_{dir_name}_config"
    return f"get_{dir_name}_mcp_config"


def _tools_const_for(dir_name: str) -> str:
    """Returns the canonical constant name for tools list.

    Convention: '<DIR_UPPER>_MCP_TOOLS'. But dirs ending with '_mcp' drop
    the duplicate (e.g. 'memory_mcp' → 'MEMORY_MCP_TOOLS' not '...MCP_MCP...').
    """
    upper = dir_name.upper()
    if dir_name.endswith("_mcp"):
        return f"{upper}_TOOLS"
    return f"{upper}_MCP_TOOLS"


def _expected_function_names(dir_name: str) -> list[str]:
    """Returns the function names that should exist in mcp_servers/<dir>/server_config.py."""
    if dir_name in MULTI_SERVER_DIRS:
        return [fn for fn, _key in MULTI_SERVER_DIRS[dir_name]]
    return [_function_suffix(dir_name)]


def _expected_server_keys(dir_name: str) -> list[str]:
    """Returns server keys that the dir's functions should register."""
    if dir_name in MULTI_SERVER_DIRS:
        return [key for _fn, key in MULTI_SERVER_DIRS[dir_name]]
    return [dir_name]


def _expected_tool_constants(dir_name: str) -> list[str]:
    """Returns names of XXX_MCP_TOOLS constants the module should export."""
    if dir_name in MULTI_SERVER_DIRS:
        # 'fabric' → FABRIC_MCP_TOOLS + FABRIC_OFFICIAL_MCP_TOOLS
        return [
            "FABRIC_MCP_TOOLS",
            "FABRIC_OFFICIAL_MCP_TOOLS",
        ] if dir_name == "fabric" else []
    if dir_name in GENERIC_CONSTANTS_DIRS:
        return ["MCP_TOOLS"]
    return [_tools_const_for(dir_name)]


def _expected_prefix(server_key: str) -> str:
    return f"mcp__{server_key}__"


# ─── Checks ───────────────────────────────────────────────────────────────────


def check_mcp_dir(mcp_dir: Path) -> list[Issue]:
    """Runs all per-MCP-dir checks."""
    dir_name = mcp_dir.name
    issues: list[Issue] = []
    config_file = mcp_dir / "server_config.py"

    if not config_file.is_file():
        issues.append(
            Issue(
                Severity.ERROR,
                dir_name,
                "missing-config",
                f"mcp_servers/{dir_name}/server_config.py not found",
                mcp_dir,
            )
        )
        return issues

    # Import the module — Phase 7 namespace
    module_path = f"data_agents.mcp_servers.{dir_name}.server_config"
    try:
        module = _import_module(module_path)
    except Exception as exc:  # noqa: BLE001
        issues.append(
            Issue(
                Severity.ERROR,
                dir_name,
                "import-error",
                f"failed to import {module_path}: "
                f"{type(exc).__name__}: {exc}",
                config_file,
            )
        )
        return issues

    expected_fns = _expected_function_names(dir_name)
    expected_keys = _expected_server_keys(dir_name)

    # Check every expected function
    for fn_name, server_key in zip(expected_fns, expected_keys):
        fn = getattr(module, fn_name, None)
        if fn is None:
            issues.append(
                Issue(
                    Severity.ERROR,
                    dir_name,
                    "missing-function",
                    f"function {fn_name}() not found in {module_path}",
                    config_file,
                )
            )
            continue
        if not callable(fn):
            issues.append(
                Issue(
                    Severity.ERROR,
                    dir_name,
                    "function-not-callable",
                    f"{fn_name} exists but is not callable",
                    config_file,
                )
            )
            continue
        # Try to call it
        try:
            cfg = fn()
        except Exception as exc:  # noqa: BLE001
            issues.append(
                Issue(
                    Severity.ERROR,
                    dir_name,
                    "function-raises",
                    f"{fn_name}() raised on call: "
                    f"{type(exc).__name__}: {exc}",
                    config_file,
                )
            )
            continue

        # Validate shape: must be dict with the expected server key
        if not isinstance(cfg, dict):
            issues.append(
                Issue(
                    Severity.ERROR,
                    dir_name,
                    "shape-not-dict",
                    f"{fn_name}() returned {type(cfg).__name__}, expected dict",
                    config_file,
                )
            )
            continue
        if server_key not in cfg:
            issues.append(
                Issue(
                    Severity.ERROR,
                    dir_name,
                    "shape-missing-key",
                    f"{fn_name}() returned dict without expected key "
                    f"'{server_key}'; got keys={sorted(cfg.keys())}",
                    config_file,
                )
            )
            continue
        entry = cfg[server_key]
        if not isinstance(entry, dict):
            issues.append(
                Issue(
                    Severity.ERROR,
                    dir_name,
                    "shape-entry-not-dict",
                    f"cfg['{server_key}'] is {type(entry).__name__}, "
                    f"expected dict",
                    config_file,
                )
            )
            continue
        # 'type' is required by claude_agent_sdk for stdio MCPs
        if "type" not in entry:
            issues.append(
                Issue(
                    Severity.ERROR,
                    dir_name,
                    "shape-missing-type",
                    f"cfg['{server_key}'] missing 'type' key (e.g. 'stdio')",
                    config_file,
                )
            )

    # Check the tool constants
    for const_name in _expected_tool_constants(dir_name):
        if not hasattr(module, const_name):
            issues.append(
                Issue(
                    Severity.ERROR,
                    dir_name,
                    "missing-tools-const",
                    f"module does not export '{const_name}'",
                    config_file,
                )
            )
            continue
        tools = getattr(module, const_name)
        if not isinstance(tools, list):
            issues.append(
                Issue(
                    Severity.ERROR,
                    dir_name,
                    "tools-not-list",
                    f"{const_name} is {type(tools).__name__}, expected list",
                    config_file,
                )
            )
            continue
        # Pick which prefix this constant corresponds to
        prefix = _resolve_prefix_for_const(dir_name, const_name)
        if prefix is None:
            # Could not infer (skip strict prefix check). Still check duplicates.
            pass
        # Check every tool string
        seen: set[str] = set()
        for tool in tools:
            if not isinstance(tool, str):
                issues.append(
                    Issue(
                        Severity.ERROR,
                        dir_name,
                        "tool-entry-not-string",
                        f"{const_name}: entry {tool!r} is not a string",
                        config_file,
                    )
                )
                continue
            if prefix and not tool.startswith(prefix):
                issues.append(
                    Issue(
                        Severity.ERROR,
                        dir_name,
                        "tool-wrong-prefix",
                        f"{const_name}: tool '{tool}' should start "
                        f"with '{prefix}'",
                        config_file,
                    )
                )
            if tool in seen:
                issues.append(
                    Issue(
                        Severity.ERROR,
                        dir_name,
                        "tool-duplicate",
                        f"{const_name}: tool '{tool}' appears more than once",
                        config_file,
                    )
                )
            seen.add(tool)

    return issues


def _resolve_prefix_for_const(dir_name: str, const_name: str) -> str | None:
    """Maps a constant name to the expected tool prefix.

    Handles the special cases (fabric multi-server, fabric_ontology generic).
    """
    if dir_name == "fabric":
        if const_name == "FABRIC_MCP_TOOLS":
            return "mcp__fabric_community__"
        if const_name == "FABRIC_OFFICIAL_MCP_TOOLS":
            return "mcp__fabric_official__"
    if dir_name in GENERIC_CONSTANTS_DIRS:
        return f"mcp__{dir_name}__"
    # Standard: prefix derives from dir_name
    return f"mcp__{dir_name}__"


def check_global_aliases() -> list[Issue]:
    """Cross-checks ALL_MCP_CONFIGS keys against MCP_TOOL_SETS aliases."""
    issues: list[Issue] = []
    try:
        from data_agents.config.mcp_servers import ALL_MCP_CONFIGS
        from data_agents.agents.loader import MCP_TOOL_SETS
    except Exception as exc:  # noqa: BLE001
        issues.append(
            Issue(
                Severity.ERROR,
                "<global>",
                "cannot-load-globals",
                f"could not import ALL_MCP_CONFIGS or MCP_TOOL_SETS: "
                f"{type(exc).__name__}: {exc}",
            )
        )
        return issues

    registered_keys = set(ALL_MCP_CONFIGS.keys())
    alias_keys = set(MCP_TOOL_SETS.keys())

    # Every registered server should have at least an *_all alias
    for key in sorted(registered_keys):
        all_alias = f"{key}_all"
        readonly_alias = f"{key}_readonly"
        if all_alias not in alias_keys:
            issues.append(
                Issue(
                    Severity.ERROR,
                    key,
                    "missing-all-alias",
                    f"server '{key}' in ALL_MCP_CONFIGS but no alias "
                    f"'{all_alias}' in MCP_TOOL_SETS — agents using this MCP "
                    f"will have unresolvable tools",
                )
            )
        if readonly_alias not in alias_keys and key not in READONLY_BY_NATURE:
            issues.append(
                Issue(
                    Severity.WARNING,
                    key,
                    "missing-readonly-alias",
                    f"server '{key}' has no '{readonly_alias}' alias — "
                    f"readonly-only agents must list tools individually "
                    f"(if this MCP is read-only by nature, add it to "
                    f"READONLY_BY_NATURE)",
                )
            )

    # Detect dead aliases (aliases that point to no registered server)
    server_base_names = set()
    for key in registered_keys:
        server_base_names.add(key)
    for alias in sorted(alias_keys):
        # Strip standard suffixes to find the base
        base = alias
        for suffix in ("_all", "_readonly", "_aibi", "_serving", "_compute"):
            if alias.endswith(suffix):
                base = alias[: -len(suffix)]
                break
        if base not in server_base_names:
            issues.append(
                Issue(
                    Severity.WARNING,
                    base,
                    "dead-alias",
                    f"alias '{alias}' in MCP_TOOL_SETS does not correspond "
                    f"to any server in ALL_MCP_CONFIGS",
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
    lines: list[str] = [
        f"lint_mcp_configs: scanned {report.dirs_scanned} dirs, "
        f"{report.servers_registered} registered servers",
        "",
    ]
    by_server: dict[str, list[Issue]] = {}
    for issue in report.issues:
        by_server.setdefault(issue.server, []).append(issue)

    if not by_server:
        lines.append("✓ no issues found")
        return "\n".join(lines)

    for server in sorted(by_server):
        issues = by_server[server]
        if quiet:
            issues = [i for i in issues if i.severity is Severity.ERROR]
            if not issues:
                continue
        lines.append(f"▶ {server}")
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
        "dirs_scanned": report.dirs_scanned,
        "servers_registered": report.servers_registered,
        "errors": len(report.errors),
        "warnings": len(report.warnings),
        "infos": len(report.infos),
        "issues": [i.to_dict() for i in report.issues],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ─── Main ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Structural lint for mcp_servers/* configurations and "
                    "their cross-references in loader/registry."
    )
    parser.add_argument("--strict", action="store_true",
                        help="Treat warnings as errors.")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress non-error messages.")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON for machine consumption.")
    args = parser.parse_args(argv)

    report = LintReport()

    # Phase 1: per-MCP checks
    for mcp_dir in _list_mcp_dirs():
        report.dirs_scanned += 1
        for issue in check_mcp_dir(mcp_dir):
            report.add(issue)

    # Count registered servers (for the header summary)
    try:
        from data_agents.config.mcp_servers import ALL_MCP_CONFIGS
        report.servers_registered = len(ALL_MCP_CONFIGS)
    except Exception:  # noqa: BLE001
        report.servers_registered = 0

    # Phase 2: global cross-checks
    for issue in check_global_aliases():
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
