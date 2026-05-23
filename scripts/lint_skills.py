"""
lint_skills.py — Structural lint for the skills tree.

Validates each SKILL.md under ``skills/<domain>/<skill-name>/SKILL.md``
(or ``skills/<domain>/SKILL.md`` for root-level skills like
``skills/migration/SKILL.md``).

Checks performed per SKILL.md:

    REQUIRED FIELDS
      ERROR  — missing 'name' (loader falls back to directory name; we want it explicit)
      ERROR  — missing 'description' (loader falls back to first body line)
      ERROR  — uses 'skill:' instead of 'name:' (typo — loader silently ignores)

    SIMPLE VALIDATIONS
      ERROR    — 'name' is not a string
      ERROR    — 'description' is not a string
      ERROR    — frontmatter cannot be parsed at all
      WARNING  — 'name' differs from the parent directory name (consistency)
      WARNING  — 'description' is shorter than MIN_DESCRIPTION_CHARS (likely placeholder)
      WARNING  — 'updated_at' (when present) older than STALE_DAYS days

GLOBAL CHECKS

    ERROR    — duplicate 'name' across the entire skills tree
    WARNING  — skill_domain referenced by no agent in registry (orphan domain)

CONFIGURATION
    NATIVE_NAME_OVERRIDES — skills whose name intentionally differs from parent dir
                            (none today; add here if a legitimate case appears)
    MIN_DESCRIPTION_CHARS — minimum length for a description to be meaningful
    STALE_DAYS             — threshold for 'updated_at' staleness warning

Usage:
    python scripts/lint_skills.py
    python scripts/lint_skills.py --quiet
    python scripts/lint_skills.py --strict
    python scripts/lint_skills.py --json

Exit codes:
    0 — no errors
    1 — at least one error (or warning with --strict)
    2 — internal lint failure
"""

from __future__ import annotations

import argparse
import json
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

#: Minimum chars for a description to be considered meaningful (not a stub).
MIN_DESCRIPTION_CHARS: int = 40

#: Days after which 'updated_at' triggers a staleness WARNING for a skill.
STALE_DAYS: int = 180

#: Directories to ignore when discovering skills.
SKIP_DIR_NAMES: frozenset[str] = frozenset({"TEMPLATE", "_template"})

#: Allow-list of skill names that intentionally diverge from the parent dir.
#: Currently empty — every skill follows name=dir convention.
NAME_DIR_DIVERGENCE_OK: frozenset[str] = frozenset()


# ─── Issue model ──────────────────────────────────────────────────────────────


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Issue:
    severity: Severity
    skill: str
    check: str
    message: str
    file: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "skill": self.skill,
            "check": self.check,
            "message": self.message,
            "file": str(self.file) if self.file else None,
        }


@dataclass
class LintReport:
    issues: list[Issue] = field(default_factory=list)
    skills_scanned: int = 0

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


def _discover_skills() -> list[Path]:
    """Returns the list of SKILL.md paths under skills/, excluding templates."""
    skills_root = PROJECT_ROOT / "skills"
    if not skills_root.is_dir():
        return []
    results: list[Path] = []
    for path in skills_root.rglob("SKILL.md"):
        # Skip TEMPLATE/ and _template/ paths
        if any(part in SKIP_DIR_NAMES or part.startswith("_") for part in path.parts):
            continue
        results.append(path)
    return sorted(results)


def _expected_name(skill_path: Path) -> str:
    """The 'canonical' name for a SKILL.md is the parent directory name."""
    return skill_path.parent.name


def _skill_label(skill_path: Path) -> str:
    """Human-friendly label combining domain and skill name for reports."""
    try:
        rel = skill_path.relative_to(PROJECT_ROOT / "skills")
    except ValueError:
        return str(skill_path)
    # 'fabric/fabric-medallion/SKILL.md' → 'fabric/fabric-medallion'
    return rel.parent.as_posix()


def _parse_date_loose(value: Any) -> date | None:
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


def _list_referenced_skill_domains() -> set[str]:
    """Returns the set of skill_domains declared by any agent in the registry."""
    registry = PROJECT_ROOT / "data_agents" / "agents" / "registry"
    domains: set[str] = set()
    if not registry.is_dir():
        return domains
    for file in registry.glob("*.md"):
        if file.name.startswith("_"):
            continue
        try:
            meta, _ = parse_yaml_frontmatter(file.read_text(encoding="utf-8"))
            declared = meta.get("skill_domains") or []
            if isinstance(declared, list):
                for d in declared:
                    if isinstance(d, str):
                        domains.add(d)
        except (ValueError, OSError):
            continue
    return domains


# ─── Checks ───────────────────────────────────────────────────────────────────


def check_skill(skill_path: Path, today: date) -> tuple[str | None, list[Issue]]:
    """Per-skill checks. Returns (declared_name_or_None, issues)."""
    label = _skill_label(skill_path)
    issues: list[Issue] = []

    try:
        content = skill_path.read_text(encoding="utf-8")
    except OSError as exc:
        issues.append(Issue(Severity.ERROR, label, "io", f"cannot read: {exc}", skill_path))
        return None, issues

    try:
        meta, _body = parse_yaml_frontmatter(content)
    except ValueError as exc:
        issues.append(
            Issue(
                Severity.ERROR,
                label,
                "frontmatter-invalid",
                f"SKILL.md has invalid YAML frontmatter: {exc}",
                skill_path,
            )
        )
        return None, issues

    # ── 'skill:' typo guard ──
    if "skill" in meta and "name" not in meta:
        issues.append(
            Issue(
                Severity.ERROR,
                label,
                "skill-key-typo",
                "frontmatter uses 'skill:' instead of 'name:'. "
                "The loader silently ignores 'skill:' and falls back to "
                "the directory name.",
                skill_path,
            )
        )

    # ── 'name' validation ──
    name = meta.get("name")
    if name is None:
        issues.append(
            Issue(
                Severity.ERROR,
                label,
                "missing-name",
                "frontmatter is missing 'name'. Loader uses directory name as "
                "fallback but explicit name is required for stable references.",
                skill_path,
            )
        )
    elif not isinstance(name, str):
        issues.append(
            Issue(
                Severity.ERROR,
                label,
                "name-type",
                f"'name' must be a string, got {type(name).__name__}",
                skill_path,
            )
        )
        name = None  # don't use a non-string downstream
    else:
        expected = _expected_name(skill_path)
        if name != expected and name not in NAME_DIR_DIVERGENCE_OK:
            issues.append(
                Issue(
                    Severity.WARNING,
                    label,
                    "name-dir-mismatch",
                    f"'name' is '{name}' but parent directory is '{expected}'. "
                    f"Convention: name == dir.",
                    skill_path,
                )
            )

    # ── 'description' validation ──
    description = meta.get("description")
    if description is None:
        issues.append(
            Issue(
                Severity.ERROR,
                label,
                "missing-description",
                "frontmatter is missing 'description'. Loader uses first body "
                "line as fallback (uncurated).",
                skill_path,
            )
        )
    elif not isinstance(description, str):
        issues.append(
            Issue(
                Severity.ERROR,
                label,
                "description-type",
                f"'description' must be a string, got {type(description).__name__}",
                skill_path,
            )
        )
    elif len(description.strip()) < MIN_DESCRIPTION_CHARS:
        issues.append(
            Issue(
                Severity.WARNING,
                label,
                "description-too-short",
                f"'description' is {len(description.strip())} chars "
                f"(< {MIN_DESCRIPTION_CHARS}). Likely a placeholder.",
                skill_path,
            )
        )

    # ── 'updated_at' staleness ──
    updated_at_raw = meta.get("updated_at")
    if updated_at_raw is not None:
        parsed = _parse_date_loose(updated_at_raw)
        if parsed is None:
            issues.append(
                Issue(
                    Severity.WARNING,
                    label,
                    "updated-at-invalid",
                    f"'updated_at' value {updated_at_raw!r} could not be "
                    f"parsed as YYYY-MM-DD",
                    skill_path,
                )
            )
        else:
            age = (today - parsed).days
            if age > STALE_DAYS:
                issues.append(
                    Issue(
                        Severity.WARNING,
                        label,
                        "updated-at-stale",
                        f"'updated_at' is {age} days old (>{STALE_DAYS}). "
                        f"Consider running scripts/refresh_skills.py for this domain.",
                        skill_path,
                    )
                )

    return name if isinstance(name, str) else None, issues


def check_uniqueness(skills: list[tuple[str, Path]]) -> list[Issue]:
    """Reports duplicate skill names across the whole tree."""
    issues: list[Issue] = []
    seen: dict[str, Path] = {}
    for name, path in skills:
        if not name:
            continue
        if name in seen:
            issues.append(
                Issue(
                    Severity.ERROR,
                    _skill_label(path),
                    "name-uniqueness",
                    f"skill name '{name}' is also used by "
                    f"{_skill_label(seen[name])}",
                    path,
                )
            )
        else:
            seen[name] = path
    return issues


def check_orphan_domains(skill_paths: list[Path]) -> list[Issue]:
    """A skill_domain that no agent references is an orphan — its skills
    will never be injected. WARNING only."""
    issues: list[Issue] = []
    referenced = _list_referenced_skill_domains()
    skills_root = PROJECT_ROOT / "skills"

    # Discover the actual skill domains by inspecting first-level subdirs.
    discovered: set[str] = set()
    for path in skill_paths:
        try:
            rel = path.relative_to(skills_root)
            domain = rel.parts[0]
            discovered.add(domain)
        except (ValueError, IndexError):
            continue

    for domain in sorted(discovered - referenced):
        issues.append(
            Issue(
                Severity.WARNING,
                f"<domain:{domain}>",
                "orphan-domain",
                f"skill_domain '{domain}' is not declared by any agent's "
                f"skill_domains. Its skills will never be injected into "
                f"any agent's prompt.",
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
    lines: list[str] = [f"lint_skills: scanned {report.skills_scanned} skills", ""]
    by_skill: dict[str, list[Issue]] = {}
    for issue in report.issues:
        by_skill.setdefault(issue.skill, []).append(issue)

    if not by_skill:
        lines.append("✓ no issues found")
        return "\n".join(lines)

    for label in sorted(by_skill):
        issues = by_skill[label]
        if quiet:
            issues = [i for i in issues if i.severity is Severity.ERROR]
            if not issues:
                continue
        lines.append(f"▶ {label}")
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
        "skills_scanned": report.skills_scanned,
        "errors": len(report.errors),
        "warnings": len(report.warnings),
        "infos": len(report.infos),
        "issues": [i.to_dict() for i in report.issues],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ─── Main ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Structural lint for SKILL.md files. Validates frontmatter, "
                    "name/dir consistency, description quality, and orphan domains."
    )
    parser.add_argument("--strict", action="store_true",
                        help="Treat warnings as errors.")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress non-error messages.")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON for machine consumption.")
    args = parser.parse_args(argv)

    report = LintReport()
    today = datetime.now(timezone.utc).date()

    skill_paths = _discover_skills()
    names_collected: list[tuple[str, Path]] = []

    for skill_path in skill_paths:
        report.skills_scanned += 1
        name, issues = check_skill(skill_path, today)
        for issue in issues:
            report.add(issue)
        if name:
            names_collected.append((name, skill_path))

    # Global checks
    for issue in check_uniqueness(names_collected):
        report.add(issue)
    for issue in check_orphan_domains(skill_paths):
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
