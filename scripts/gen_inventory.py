"""
gen_inventory.py — Single source of truth for project counts in docs.

Computes the live inventory of the project (agents, MCPs, KBs, skills,
commands, hooks, tests) by walking the filesystem and inspecting the
registered configs. Then either prints, updates docs in place, or checks
that docs are still in sync.

Why this exists
---------------
README/PRODUCT/CLAUDE.md routinely drift away from reality:
- "14 agentes" while the registry has 15.
- "13 MCPs" while ALL_MCP_CONFIGS has 17.
- "1326+ testes" while CI runs 1446.
Manual edits to these numbers are error-prone. This script makes the
docs themselves declare which numbers come from code, then substitutes
them mechanically.

How it works
------------
Docs annotate auto-managed regions with HTML comments:

    <!-- INVENTORY:agents_total -->15<!-- /INVENTORY:agents_total -->

`gen_inventory.py --update` rewrites the value inside every such region.
`gen_inventory.py --check` exits 1 if any region holds a stale value.
`gen_inventory.py --print` outputs the inventory as JSON for inspection.

The list of "tracked" keys is centralized in INVENTORY_KEYS at the top
of the file. Add a new key here + add `<!-- INVENTORY:<key> -->` in any
doc and the script picks it up.

Usage
-----
    python scripts/gen_inventory.py                # print inventory (default)
    python scripts/gen_inventory.py --print        # explicit print
    python scripts/gen_inventory.py --json         # machine-readable JSON
    python scripts/gen_inventory.py --update       # rewrite docs in place
    python scripts/gen_inventory.py --check        # fail if docs are stale

Files watched (relative to project root):
    README.md, PRODUCT.md, .claude/CLAUDE.md, docs/refactor-v3/inventory.md

Exit codes:
    0 — success (print/update/check all clean)
    1 — --check found drift (one or more files have stale INVENTORY blocks)
    2 — internal error (cannot import config, cannot read file, etc.)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.frontmatter import parse_yaml_frontmatter  # noqa: E402

# ─── Configuration ────────────────────────────────────────────────────────────

#: Documents that may contain <!-- INVENTORY:* --> blocks to keep in sync.
#: Add new doc paths here; the script automatically scans them.
WATCHED_DOCS: tuple[str, ...] = (
    "README.md",
    "PRODUCT.md",
    ".claude/CLAUDE.md",
    "docs/refactor-v3/inventory.md",
)

#: Regex that captures auto-managed inventory blocks.
#: Format: <!-- INVENTORY:<key> -->VALUE<!-- /INVENTORY:<key> -->
INVENTORY_BLOCK = re.compile(
    r"<!--\s*INVENTORY:([\w.-]+)\s*-->(.*?)<!--\s*/INVENTORY:\1\s*-->",
    re.DOTALL,
)


# ─── Inventory collection ─────────────────────────────────────────────────────


def _list_agents() -> list[dict[str, Any]]:
    """Returns [{'name': ..., 'tier': ...}] for each agent in registry."""
    registry = PROJECT_ROOT / "agents" / "registry"
    items: list[dict[str, Any]] = []
    if not registry.is_dir():
        return items
    for f in sorted(registry.glob("*.md")):
        if f.name.startswith("_"):
            continue
        try:
            meta, _ = parse_yaml_frontmatter(f.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        items.append({
            "name": meta.get("name", f.stem),
            "tier": meta.get("tier", ""),
        })
    return items


def _list_mcps() -> dict[str, list[str]]:
    """Returns {'custom': [...], 'external': [...]} based on server.py presence.

    A custom MCP has its own server.py (implementation in this repo).
    An external MCP only declares a server_config.py and shells out to
    a third-party process (via npx/uvx).
    """
    root = PROJECT_ROOT / "mcp_servers"
    result: dict[str, list[str]] = {"custom": [], "external": []}
    if not root.is_dir():
        return result
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("_") or d.name == "__pycache__":
            continue
        if (d / "server.py").is_file():
            result["custom"].append(d.name)
        elif (d / "server_config.py").is_file():
            result["external"].append(d.name)
    return result


def _list_all_mcp_configs() -> list[str]:
    """Returns the keys registered in config.mcp_servers.ALL_MCP_CONFIGS.
    Falls back to an empty list if the module cannot be imported (e.g. in
    a stripped-down environment without pydantic)."""
    try:
        from config.mcp_servers import ALL_MCP_CONFIGS
        return sorted(ALL_MCP_CONFIGS.keys())
    except Exception:  # noqa: BLE001 — defensive: never let import errors break --print
        return []


def _list_kb_domains() -> list[str]:
    kb_dir = PROJECT_ROOT / "kb"
    if not kb_dir.is_dir():
        return []
    return sorted(
        d.name for d in kb_dir.iterdir()
        if d.is_dir() and not d.name.startswith("_") and d.name not in {"_templates"}
    )


def _count_kbs_with_index() -> int:
    return sum(
        1
        for d in (PROJECT_ROOT / "kb").iterdir()
        if d.is_dir() and not d.name.startswith("_")
        and d.name not in {"_templates"}
        and (d / "index.md").is_file()
    )


def _list_skills() -> list[str]:
    """Returns list of skill identifiers (relative paths like
    'fabric/fabric-medallion')."""
    root = PROJECT_ROOT / "skills"
    if not root.is_dir():
        return []
    paths: list[str] = []
    for p in sorted(root.rglob("SKILL.md")):
        # Skip TEMPLATE/, _template/
        if any(part in {"TEMPLATE", "_template"} or part.startswith("_")
               for part in p.parts):
            continue
        paths.append(p.parent.relative_to(root).as_posix())
    return paths


def _list_skill_domains() -> list[str]:
    root = PROJECT_ROOT / "skills"
    if not root.is_dir():
        return []
    return sorted(
        d.name for d in root.iterdir()
        if d.is_dir() and not d.name.startswith("_") and d.name != "TEMPLATE"
    )


def _list_commands() -> dict[str, list[str]]:
    """Returns {mode: [command_names]} from config/commands.yaml."""
    import yaml
    cmds_file = PROJECT_ROOT / "config" / "commands.yaml"
    by_mode: dict[str, list[str]] = {"express": [], "full": [], "internal": []}
    if not cmds_file.is_file():
        return by_mode
    try:
        with cmds_file.open("r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
    except (yaml.YAMLError, OSError):
        return by_mode
    for name, cmd in (data.get("commands") or {}).items():
        if not isinstance(cmd, dict):
            continue
        mode = cmd.get("doma_mode", "?")
        by_mode.setdefault(mode, []).append(name)
    for m in by_mode:
        by_mode[m].sort()
    return by_mode


def _count_hooks() -> int:
    """Counts hook .py files (excluding __init__.py)."""
    hooks_dir = PROJECT_ROOT / "hooks"
    if not hooks_dir.is_dir():
        return 0
    return sum(
        1 for f in hooks_dir.glob("*.py")
        if f.name != "__init__.py"
    )


def _count_tests() -> int:
    """Counts test files (test_*.py) excluding conftest and __init__."""
    tests_dir = PROJECT_ROOT / "tests"
    if not tests_dir.is_dir():
        return 0
    return sum(1 for f in tests_dir.glob("test_*.py"))


def collect_inventory() -> dict[str, Any]:
    """Returns a flat dict of inventory values keyed by INVENTORY block name.

    Keys here MUST match the placeholders used in docs. Add new keys here
    when you want to expose a new metric to the docs.
    """
    agents = _list_agents()
    mcps_by_kind = _list_mcps()
    all_mcp_configs = _list_all_mcp_configs()
    kb_domains = _list_kb_domains()
    skills = _list_skills()
    skill_domains = _list_skill_domains()
    commands_by_mode = _list_commands()

    by_tier: dict[str, int] = {"T0": 0, "T1": 0, "T2": 0, "T3": 0}
    for a in agents:
        t = a.get("tier")
        if t in by_tier:
            by_tier[t] += 1

    return {
        # Agents
        "agents_total": len(agents),
        "agents_t0": by_tier["T0"],
        "agents_t1": by_tier["T1"],
        "agents_t2": by_tier["T2"],
        "agents_t3": by_tier["T3"],
        # MCPs
        "mcps_dirs": len(mcps_by_kind["custom"]) + len(mcps_by_kind["external"]),
        "mcps_custom": len(mcps_by_kind["custom"]),
        "mcps_external": len(mcps_by_kind["external"]),
        "mcps_registered": len(all_mcp_configs),
        # KBs
        "kbs_total": len(kb_domains),
        "kbs_with_index": _count_kbs_with_index(),
        # Skills
        "skills_total": len(skills),
        "skill_domains": len(skill_domains),
        # Slash commands
        "commands_total": sum(len(v) for v in commands_by_mode.values()),
        "commands_express": len(commands_by_mode.get("express", [])),
        "commands_full": len(commands_by_mode.get("full", [])),
        "commands_internal": len(commands_by_mode.get("internal", [])),
        # Hooks
        "hooks_total": _count_hooks(),
        # Tests
        "tests_files": _count_tests(),
    }


# ─── Doc sync (update / check) ────────────────────────────────────────────────


def _iter_doc_files() -> list[Path]:
    return [PROJECT_ROOT / p for p in WATCHED_DOCS if (PROJECT_ROOT / p).is_file()]


def _process_file(path: Path, inventory: dict[str, Any], mode: str
                  ) -> tuple[bool, list[str]]:
    """Returns (changed_or_drift, list_of_diff_messages).

    mode='update' rewrites the file in place if any block was stale.
    mode='check' only reports — does not modify the file.
    """
    try:
        original = path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, [f"{path}: read error — {exc}"]

    messages: list[str] = []
    changed = False

    def replace_block(match: re.Match) -> str:
        nonlocal changed
        key = match.group(1)
        current = match.group(2).strip()
        if key not in inventory:
            messages.append(
                f"{path}:<!-- INVENTORY:{key} --> — unknown key (no value to inject)"
            )
            return match.group(0)
        new_value = str(inventory[key])
        if current != new_value:
            changed = True
            messages.append(
                f"{path}:<!-- INVENTORY:{key} --> {current!r} → {new_value!r}"
            )
        return f"<!-- INVENTORY:{key} -->{new_value}<!-- /INVENTORY:{key} -->"

    new_content = INVENTORY_BLOCK.sub(replace_block, original)

    if mode == "update" and changed:
        try:
            path.write_text(new_content, encoding="utf-8")
        except OSError as exc:
            messages.append(f"{path}: write error — {exc}")
            return changed, messages

    return changed, messages


# ─── Output renderers ────────────────────────────────────────────────────────


def render_print(inventory: dict[str, Any]) -> str:
    """Human-readable inventory."""
    lines: list[str] = [
        "═══ AI Data Agents — Live Inventory ═══",
        "",
        f"AGENTS:    {inventory['agents_total']:>4}  "
        f"(T0={inventory['agents_t0']}, T1={inventory['agents_t1']}, "
        f"T2={inventory['agents_t2']}, T3={inventory['agents_t3']})",
        f"MCPS:      {inventory['mcps_dirs']:>4}  "
        f"(custom={inventory['mcps_custom']}, "
        f"external={inventory['mcps_external']}, "
        f"registered={inventory['mcps_registered']})",
        f"KBS:       {inventory['kbs_total']:>4}  "
        f"(with index={inventory['kbs_with_index']})",
        f"SKILLS:    {inventory['skills_total']:>4}  "
        f"(domains={inventory['skill_domains']})",
        f"COMMANDS:  {inventory['commands_total']:>4}  "
        f"(express={inventory['commands_express']}, "
        f"full={inventory['commands_full']}, "
        f"internal={inventory['commands_internal']})",
        f"HOOKS:     {inventory['hooks_total']:>4}",
        f"TESTS:     {inventory['tests_files']:>4}  (test files)",
        "",
        "Use --update to refresh <!-- INVENTORY:* --> blocks in docs.",
        "Use --check  to verify docs are in sync (CI gate).",
    ]
    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compute live project inventory and sync docs."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--print", action="store_true",
                       help="Print human-readable inventory (default).")
    group.add_argument("--json", action="store_true",
                       help="Print inventory as JSON.")
    group.add_argument("--update", action="store_true",
                       help="Rewrite <!-- INVENTORY:* --> blocks in docs in place.")
    group.add_argument("--check", action="store_true",
                       help="Exit 1 if any doc has stale <!-- INVENTORY:* --> "
                            "values (CI gate).")
    args = parser.parse_args(argv)

    try:
        inventory = collect_inventory()
    except Exception as exc:  # noqa: BLE001
        print(f"gen_inventory: FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(inventory, indent=2, ensure_ascii=False))
        return 0

    if args.update:
        any_change = False
        for doc in _iter_doc_files():
            changed, messages = _process_file(doc, inventory, mode="update")
            if changed:
                any_change = True
                for m in messages:
                    print(f"updated: {m}")
            elif messages:  # warnings without changes
                for m in messages:
                    print(f"warning: {m}", file=sys.stderr)
        if not any_change:
            print("gen_inventory: all watched docs already in sync — no changes")
        return 0

    if args.check:
        drift = False
        for doc in _iter_doc_files():
            changed, messages = _process_file(doc, inventory, mode="check")
            if changed:
                drift = True
                for m in messages:
                    print(f"DRIFT: {m}", file=sys.stderr)
        if drift:
            print(
                "\ngen_inventory: docs are out of sync. "
                "Run: python scripts/gen_inventory.py --update",
                file=sys.stderr,
            )
            return 1
        print("gen_inventory: all watched docs in sync ✓")
        return 0

    # Default: --print
    print(render_print(inventory))
    return 0


if __name__ == "__main__":
    sys.exit(main())
