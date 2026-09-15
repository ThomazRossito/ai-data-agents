#!/usr/bin/env bash
# build_plugin.sh — sync the Claude Code plugin view from canonical sources.
#
# Thin wrapper around scripts/sync_plugin_mirror.py. All the logic lives there.
#
# WHY IT IS A WRAPPER NOW
# -----------------------
# Until 2026-09-13 this file reimplemented the mirroring in bash while
# sync_plugin_mirror.py did it in Python — two generators for one target, with
# split responsibilities:
#
#   build_plugin.sh        propagated VERSION, ignored the description counts
#   sync_plugin_mirror.py  updated the counts, ignored VERSION
#
# Neither one alone left the repo green, and the two CI gates told you to run
# different commands for the same failure:
#
#   plugin-validate.yml            "run 'bash scripts/build_plugin.sh'"
#   test_plugin_mirror_sync.py     "rode `python scripts/sync_plugin_mirror.py`"
#
# That cost a CI round-trip on PR #45. Now there is one implementation, it is
# the testable one (tests/unit/test_plugin_mirror_sync.py imports its
# functions directly), and either command does the whole job.
#
# The mapping, unchanged:
#   data_agents/agents/registry/*.md  → plugins/ai-data-agents/agents/*.md
#   skills/<domain>/<name>/SKILL.md   → plugins/ai-data-agents/skills/<name>/
#                                       (flattened — plugin format is flat)
#   VERSION                           → plugin.json + marketplace.json
#
# Run after any change to agents or skills:
#   bash scripts/build_plugin.sh
#   git add plugins/ai-data-agents/ .claude-plugin/marketplace.json
#   git commit -m "chore(plugin): sync agents + skills"
#
# CI (plugin-validate.yml) re-runs this and asserts no diff — drift fails CI.
#
# Exit codes (preserved from the bash implementation):
#   0 — synced
#   1 — missing source or manifest
#   2 — skill name collision in the flattened layout

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PLUGIN_DIR="plugins/ai-data-agents"

# ─── Pre-flight ───────────────────────────────────────────────────────────────
# sync_plugin_mirror.py checks these too, but failing here gives the same
# message the bash version always gave, before spending a Python startup.
if [[ ! -d "data_agents/agents/registry" ]]; then
  echo "❌ source not found: data_agents/agents/registry" >&2
  exit 1
fi
if [[ ! -d "skills" ]]; then
  echo "❌ source not found: skills" >&2
  exit 1
fi
if [[ ! -f "${PLUGIN_DIR}/.claude-plugin/plugin.json" ]]; then
  echo "❌ plugin manifest not found: ${PLUGIN_DIR}/.claude-plugin/plugin.json" >&2
  echo "   Did the marketplace + plugin scaffolding land?" >&2
  exit 1
fi

# ─── Delegate ─────────────────────────────────────────────────────────────────
python3 scripts/sync_plugin_mirror.py

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "Next steps:"
echo "  git status plugins/"
echo "  git add plugins/ .claude-plugin/marketplace.json"
echo "  git commit -m 'chore(plugin): sync agents + skills'"
