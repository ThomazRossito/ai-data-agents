#!/usr/bin/env python3
"""
lint_bundle.py — Structural lint for the Declarative Automation Bundle (databricks.yml).

"Declarative Automation Bundles" is the current name; it was "Databricks Asset
Bundles" until the 2026-03-16 rename. The rename is non-breaking — the
`databricks bundle` command and the config schema are unchanged.

WHY THIS EXISTS
---------------
The 2026-09-13 audit found ``databricks.yml`` broken in a way that had survived
for months and silently poisoned every CLI invocation from the repo root::

    workspace:
      host: ${workspace.host}      # self-referential — cannot resolve

The CLI enters "bundle mode" whenever it finds a databricks.yml, tried to
resolve that reference, gave up, and passed the literal string as the host::

    parse "https://${workspace.host}": invalid character "{" in host name

That broke ``databricks current-user me``, ``databricks aitools ...`` and
``databricks bundle deploy`` — anything run from the project directory.

It was never caught because ``databricks bundle validate`` was never run in CI.
And it cannot be run in CI here: ``bundle validate`` needs workspace
authentication, and this project deliberately does not store Databricks
credentials in GitHub (see the header of .github/workflows/cd.yml).

So this linter does the part that *can* run offline and with zero credentials:
the structural checks that would have caught the bug.

Checks performed
----------------
    BUNDLE-01  databricks.yml is valid YAML and has a `bundle.name`
    BUNDLE-02  no self-referential variable (`a.b: ${a.b}`)
    BUNDLE-03  `include:` globs resolve to at least one existing file
    BUNDLE-04  `${var.X}` references a declared entry under `variables:`
    BUNDLE-05  `spark_version` is not an end-of-life Databricks Runtime

Usage:
    python scripts/lint_bundle.py            # human-friendly report
    python scripts/lint_bundle.py --quiet    # errors only
    python scripts/lint_bundle.py --strict   # warnings count as errors
    python scripts/lint_bundle.py --json     # machine-readable output

Exit codes:
    0 — no errors (warnings allowed unless --strict)
    1 — at least one error (or warning with --strict)
    2 — internal lint failure (missing file, unreadable YAML, bad invocation)

Complements, but does not replace, ``databricks bundle validate`` — run that
locally, where credentials exist.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: Menor DBR que ainda recebe suporte. Runtimes abaixo disto viram WARNING.
#: DBR 17.3 é o LTS atual (suporte até out/2028); 16.4 é o LTS anterior.
_MIN_SUPPORTED_DBR = (16, 4)

#: `spark_version: "17.3.x-scala2.12"` -> captura (17, 3)
_SPARK_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.")

#: Qualquer `${alguma.coisa}` dentro de um valor.
_REF_RE = re.compile(r"\$\{([a-zA-Z0-9_.]+)\}")


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Issue:
    severity: Severity
    check: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity.value, "check": self.check, "message": self.message}


@dataclass
class LintReport:
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.WARNING]

    def add(self, severity: Severity, check: str, message: str) -> None:
        self.issues.append(Issue(severity, check, message))


def _walk(node: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    """Achata o YAML em pares (caminho, valor escalar)."""
    out: list[tuple[tuple[str, ...], Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            out.extend(_walk(value, path + (str(key),)))
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            out.extend(_walk(value, path + (str(idx),)))
    else:
        out.append((path, node))
    return out


def check_bundle(bundle_path: Path) -> LintReport:
    """Roda todas as checagens sobre um databricks.yml."""
    import yaml

    report = LintReport()
    raw = bundle_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}

    if not isinstance(data, dict):
        report.add(Severity.ERROR, "BUNDLE-01", "top-level YAML is not a mapping")
        return report

    # BUNDLE-01 — identidade do bundle
    if not (data.get("bundle") or {}).get("name"):
        report.add(Severity.ERROR, "BUNDLE-01", "missing `bundle.name`")

    declared_vars = set((data.get("variables") or {}).keys())
    scalars = _walk(data)

    for path, value in scalars:
        if not isinstance(value, str):
            continue
        dotted = ".".join(path)

        for ref in _REF_RE.findall(value):
            # BUNDLE-02 — auto-referência: `a.b: ${a.b}`
            if ref == dotted:
                report.add(
                    Severity.ERROR,
                    "BUNDLE-02",
                    f"`{dotted}` is self-referential (`${{{ref}}}`) — the CLI cannot "
                    f"resolve it, passes the literal string through, and every "
                    f"`databricks` command run from the repo root fails. "
                    f"Remove the key (let auth supply it) or set a real value.",
                )
            # BUNDLE-04 — ${var.X} precisa existir em `variables:`
            if ref.startswith("var."):
                nome = ref.split(".", 1)[1]
                if nome not in declared_vars:
                    report.add(
                        Severity.ERROR,
                        "BUNDLE-04",
                        f"`{dotted}` references `${{{ref}}}` but `{nome}` is not "
                        f"declared under `variables:`",
                    )

        # BUNDLE-05 — runtime fora de suporte
        if path and path[-1] == "spark_version":
            m = _SPARK_VERSION_RE.match(value)
            if m:
                versao = (int(m.group(1)), int(m.group(2)))
                if versao < _MIN_SUPPORTED_DBR:
                    atual = ".".join(str(p) for p in _MIN_SUPPORTED_DBR)
                    report.add(
                        Severity.WARNING,
                        "BUNDLE-05",
                        f"`{dotted}` pins DBR {value} — below the oldest supported "
                        f"LTS ({atual}). Bump it, or prefer "
                        f"`select_spark_version(latest=True, long_term_support=True)` "
                        f"when creating clusters from code.",
                    )

    # BUNDLE-03 — includes que apontam para o vazio
    includes = data.get("include") or []
    if isinstance(includes, str):
        includes = [includes]
    for padrao in includes:
        if not isinstance(padrao, str):
            continue
        if not list(bundle_path.parent.glob(padrao)):
            report.add(
                Severity.ERROR,
                "BUNDLE-03",
                f"`include: {padrao}` matches no file — the include is dead. "
                f"Create the target or remove the entry.",
            )

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Structural lint for databricks.yml (offline, no credentials)."
    )
    parser.add_argument("--strict", action="store_true", help="warnings count as errors")
    parser.add_argument("--quiet", action="store_true", help="errors only")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--bundle",
        type=Path,
        default=PROJECT_ROOT / "databricks.yml",
        help="path to databricks.yml (default: repo root)",
    )
    args = parser.parse_args(argv)

    if not args.bundle.is_file():
        # Sem bundle não há o que validar — não é erro.
        print(f"lint_bundle: no bundle at {args.bundle} — nothing to check")
        return 0

    try:
        report = check_bundle(args.bundle)
    except Exception as exc:  # noqa: BLE001 — surface any parse failure clearly
        print(
            f"lint_bundle: FATAL: could not lint {args.bundle.name}: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2

    if args.json:
        print(json.dumps({"issues": [i.to_dict() for i in report.issues]}, indent=2))
    else:
        for issue in report.issues:
            if args.quiet and issue.severity is not Severity.ERROR:
                continue
            print(f"    {issue.severity.value:<8}[{issue.check}] {issue.message}")
        if not report.issues:
            print("✓ no issues found")
        print(f"summary: {len(report.errors)} errors, {len(report.warnings)} warnings")

    if report.errors:
        return 1
    if args.strict and report.warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
