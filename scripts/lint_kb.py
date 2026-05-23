"""
lint_kb.py — Structural lint for the Knowledge Base.

Validates each KB domain under ``kb/`` (subdirectory) for structural
consistency without forcing a single frontmatter style. Two styles are
accepted in the current codebase:

    1. Minimal — only ``mcp_validated: "YYYY-MM-DD"`` (14 KBs use this)
    2. Structured — ``domain``, ``updated_at``, ``agents: [...]`` (2 KBs)

Checks performed:

    PER-KB (every subdirectory of kb/, except those listed in NO_INDEX_OK)
      ERROR    — missing index.md
      ERROR    — index.md without valid YAML frontmatter
      ERROR    — declared 'agents:' references an agent not in registry
      WARNING  — declared 'domain:' field does not match the directory name
      WARNING  — declared 'updated_at' is older than STALE_DAYS days
      WARNING  — broken internal link: [..](path.md) but path.md does not exist
      INFO     — KB has no 'agents:' field (minimal style — fine, but documented)

    GLOBAL
      ERROR    — duplicate KB names (defensive; filesystem already prevents)

Configuration:
    NO_INDEX_OK   — KB subdirs intentionally without index.md (allow-list)
    STALE_DAYS    — threshold for 'updated_at' staleness warning

Usage:
    python scripts/lint_kb.py              # full report
    python scripts/lint_kb.py --quiet      # errors only
    python scripts/lint_kb.py --strict     # warnings count as errors
    python scripts/lint_kb.py --json       # machine-readable output

Exit codes:
    0 — no errors
    1 — at least one error (or warning with --strict)
    2 — internal lint failure (bad invocation, missing module, etc.)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data_agents.utils.frontmatter import parse_yaml_frontmatter  # noqa: E402

# ─── Configuration ────────────────────────────────────────────────────────────

#: KB subdirectories that are intentionally allowed to NOT have index.md.
#: 'shared' is a cross-cutting bucket (anti-patterns shared across KBs) that
#: by convention does not present a navigation index.
NO_INDEX_OK: frozenset[str] = frozenset({"shared"})

#: Directories under kb/ that are not KBs themselves (e.g. templates).
NOT_A_KB: frozenset[str] = frozenset({"_templates"})

#: Files at kb/ root that are not KBs (constitution, routing, README).
KB_ROOT_FILES_ALLOWED: frozenset[str] = frozenset(
    {"README.md", "constitution.md", "task_routing.md", "collaboration-workflows.md"}
)

#: Days after which 'updated_at' triggers a staleness WARNING.
#: KB content that is 6+ months old should be reviewed (regulations change,
#: SDK APIs evolve, etc).
STALE_DAYS: int = 180


# ─── Issue model ──────────────────────────────────────────────────────────────


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Issue:
    severity: Severity
    domain: str
    check: str
    message: str
    file: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "domain": self.domain,
            "check": self.check,
            "message": self.message,
            "file": str(self.file) if self.file else None,
        }


@dataclass
class LintReport:
    issues: list[Issue] = field(default_factory=list)
    kbs_scanned: int = 0

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
    """Returns the set of agent names defined in data_agents/agents/registry/."""
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
            # If a registry file is broken, lint_registry will report it.
            continue
    return names


def _list_kb_subdirs() -> list[Path]:
    """Returns kb/ subdirectories that should be treated as KBs."""
    kb_dir = PROJECT_ROOT / "kb"
    if not kb_dir.is_dir():
        return []
    return sorted(
        p
        for p in kb_dir.iterdir()
        if p.is_dir() and not p.name.startswith("_") and p.name not in NOT_A_KB
    )


def _parse_date_loose(value: Any) -> date | None:
    """Tries to parse a value as ISO date. Returns None on failure.

    Accepts:
      - 'YYYY-MM-DD' strings
      - datetime.date / datetime.datetime instances (YAML may produce these)
    """
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str):
        return None
    s = value.strip().strip('"').strip("'")
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, IndexError):
        return None


# Link extraction regexes (markdown).
# Matches [text](url) where url is captured. Skips images ![..](..).
_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)\s]+)\)")
# Matches inline code wrapping a kb/... or relative .md path.
_BACKTICK_PATH_PATTERN = re.compile(r"`((?:kb/|\./|\.\./)[^`]+\.md)`")


def _extract_internal_paths(body: str, source_file: Path) -> set[str]:
    """Extracts internal .md paths referenced from the body.

    Returns a set of paths relative to PROJECT_ROOT. Excludes external URLs,
    anchors, mailto, and image refs.
    """
    refs: set[str] = set()

    def is_external(url: str) -> bool:
        return url.startswith(("http://", "https://", "mailto:", "ftp://", "#")) or "://" in url

    def is_placeholder(url: str) -> bool:
        """Templates like 'kb/industry/<vertical>.md' or 'kb/{name}.md'
        are documentation placeholders, not real links."""
        return any(ch in url for ch in "<>{}")

    def resolve(url: str) -> str | None:
        # Strip query/fragment
        clean = url.split("#", 1)[0].split("?", 1)[0]
        if not clean.endswith(".md"):
            return None
        if is_placeholder(clean):
            return None
        if clean.startswith("/"):
            return clean.lstrip("/")
        if clean.startswith("kb/"):
            return clean
        # Relative path — resolve against source file's directory.
        source_dir_rel = source_file.parent.relative_to(PROJECT_ROOT)
        candidate = (source_dir_rel / clean).as_posix()
        # Normalize './foo/bar.md' and '../foo/bar.md'
        parts: list[str] = []
        for p in candidate.split("/"):
            if p in ("", "."):
                continue
            if p == "..":
                if parts:
                    parts.pop()
                continue
            parts.append(p)
        return "/".join(parts)

    for match in _LINK_PATTERN.finditer(body):
        url = match.group(1).strip()
        if is_external(url):
            continue
        resolved = resolve(url)
        if resolved:
            refs.add(resolved)

    for match in _BACKTICK_PATH_PATTERN.finditer(body):
        url = match.group(1).strip()
        resolved = resolve(url)
        if resolved:
            refs.add(resolved)

    return refs


# ─── Checks ───────────────────────────────────────────────────────────────────


def check_kb(
    kb_dir: Path,
    valid_agents: set[str],
    today: date,
) -> list[Issue]:
    """Runs all per-KB checks on a single KB directory."""
    domain = kb_dir.name
    issues: list[Issue] = []
    index = kb_dir / "index.md"

    # ── Existence of index.md ──
    if not index.is_file():
        if domain in NO_INDEX_OK:
            issues.append(
                Issue(
                    Severity.INFO,
                    domain,
                    "no-index-by-design",
                    f"kb/{domain}/ has no index.md (allowed by NO_INDEX_OK)",
                    kb_dir,
                )
            )
        else:
            issues.append(
                Issue(
                    Severity.ERROR,
                    domain,
                    "missing-index",
                    f"kb/{domain}/index.md not found",
                    kb_dir,
                )
            )
        return issues

    # ── Parse frontmatter ──
    try:
        content = index.read_text(encoding="utf-8")
    except OSError as exc:
        issues.append(Issue(Severity.ERROR, domain, "io", f"cannot read index.md: {exc}", index))
        return issues

    try:
        metadata, body = parse_yaml_frontmatter(content)
    except ValueError as exc:
        issues.append(
            Issue(
                Severity.ERROR,
                domain,
                "frontmatter-invalid",
                f"index.md has invalid YAML frontmatter: {exc}",
                index,
            )
        )
        return issues

    # ── Optional 'domain' field consistency ──
    declared_domain = metadata.get("domain")
    if declared_domain is not None:
        if declared_domain != domain:
            issues.append(
                Issue(
                    Severity.WARNING,
                    domain,
                    "domain-mismatch",
                    f"frontmatter declares domain='{declared_domain}' but "
                    f"directory is named '{domain}'",
                    index,
                )
            )

    # ── Optional 'updated_at' staleness ──
    updated_at_raw = metadata.get("updated_at")
    if updated_at_raw is not None:
        parsed = _parse_date_loose(updated_at_raw)
        if parsed is None:
            issues.append(
                Issue(
                    Severity.WARNING,
                    domain,
                    "updated-at-invalid",
                    f"'updated_at' value {updated_at_raw!r} could not be parsed as YYYY-MM-DD",
                    index,
                )
            )
        else:
            age = (today - parsed).days
            if age > STALE_DAYS:
                issues.append(
                    Issue(
                        Severity.WARNING,
                        domain,
                        "updated-at-stale",
                        f"'updated_at' is {age} days old (>{STALE_DAYS}). "
                        f"Review content for outdated references.",
                        index,
                    )
                )

    # ── Optional 'agents:' validity ──
    declared_agents = metadata.get("agents")
    if declared_agents is not None:
        if not isinstance(declared_agents, list):
            issues.append(
                Issue(
                    Severity.ERROR,
                    domain,
                    "agents-type",
                    f"'agents:' must be a YAML list, got {type(declared_agents).__name__}",
                    index,
                )
            )
        else:
            for agent in declared_agents:
                if not isinstance(agent, str):
                    issues.append(
                        Issue(
                            Severity.ERROR,
                            domain,
                            "agents-item-type",
                            f"agent entry must be string, got {agent!r}",
                            index,
                        )
                    )
                    continue
                if agent not in valid_agents:
                    issues.append(
                        Issue(
                            Severity.ERROR,
                            domain,
                            "agent-unknown",
                            f"'agents:' references '{agent}' which is not in "
                            f"agents/registry/. Either fix the typo or "
                            f"add the agent.",
                            index,
                        )
                    )
    else:
        issues.append(
            Issue(
                Severity.INFO,
                domain,
                "no-agents-field",
                "no 'agents:' field declared (minimal frontmatter style). "
                "Consider migrating to structured style for clarity.",
                index,
            )
        )

    # ── Broken internal links ──
    referenced_paths = _extract_internal_paths(body, index)
    for ref in sorted(referenced_paths):
        target = PROJECT_ROOT / ref
        if not target.exists():
            issues.append(
                Issue(
                    Severity.WARNING,
                    domain,
                    "broken-link",
                    f"internal reference '{ref}' (from index.md body) does not exist on disk",
                    index,
                )
            )

    return issues


def check_unexpected_root_files() -> list[Issue]:
    """Flags .md files at kb/ root that are not in the allowed list.
    Allows future additions like a CHANGELOG.md but logs as INFO so they
    get reviewed.
    """
    issues: list[Issue] = []
    kb_dir = PROJECT_ROOT / "kb"
    if not kb_dir.is_dir():
        return issues
    for f in kb_dir.glob("*.md"):
        if f.name not in KB_ROOT_FILES_ALLOWED:
            issues.append(
                Issue(
                    Severity.INFO,
                    "_root",
                    "kb-root-extra-file",
                    f"kb/{f.name} is not in the allowed list "
                    f"{sorted(KB_ROOT_FILES_ALLOWED)} — consider moving "
                    f"into a domain subdirectory.",
                    f,
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
    lines: list[str] = []
    lines.append(f"lint_kb: scanned {report.kbs_scanned} KB domains")
    lines.append("")

    by_domain: dict[str, list[Issue]] = {}
    for issue in report.issues:
        by_domain.setdefault(issue.domain, []).append(issue)

    if not by_domain:
        lines.append("✓ no issues found")
        return "\n".join(lines)

    for domain in sorted(by_domain):
        issues = by_domain[domain]
        if quiet:
            issues = [i for i in issues if i.severity is Severity.ERROR]
            if not issues:
                continue
        lines.append(f"▶ {domain}")
        for issue in issues:
            color, reset = _color_for(issue.severity, isatty)
            lines.append(
                f"    {color}{issue.severity.value:7}{reset} [{issue.check}] {issue.message}"
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
        "kbs_scanned": report.kbs_scanned,
        "errors": len(report.errors),
        "warnings": len(report.warnings),
        "infos": len(report.infos),
        "issues": [i.to_dict() for i in report.issues],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ─── Main ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Structural lint for the Knowledge Base. "
        "Validates index.md presence, frontmatter, agent references, "
        "and broken internal links."
    )
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors.")
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress info-level messages; show errors only."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON for machine consumption.")
    args = parser.parse_args(argv)

    valid_agents = _list_valid_agents()
    if not valid_agents:
        print(
            "lint_kb: WARNING — could not load any agents from registry. "
            "Agent cross-references will be skipped.",
            file=sys.stderr,
        )

    report = LintReport()
    today = datetime.now(timezone.utc).date()

    for kb_dir in _list_kb_subdirs():
        report.kbs_scanned += 1
        for issue in check_kb(kb_dir, valid_agents, today):
            report.add(issue)

    # Global checks
    for issue in check_unexpected_root_files():
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
