#!/usr/bin/env bash
# build_plugin.sh — sync the Claude Code plugin view from canonical sources.
#
# Phase 12 (ADR-011 — pending): the .claude-plugin/ marketplace + plugins/
# directory expose ai-data-agents as a Claude Code plugin. The plugin content
# (agents/, skills/) is GENERATED from the canonical sources in the same repo:
#
#   data_agents/agents/registry/*.md      → plugins/ai-data-agents/agents/*.md
#   skills/<domain>/<name>/SKILL.md       → plugins/ai-data-agents/skills/<name>/SKILL.md
#                                           (flattened — plugin format is flat)
#
# Run after any change to agents or skills:
#   bash scripts/build_plugin.sh
#   git add plugins/ai-data-agents/
#   git commit -m "chore(plugin): sync agents + skills"
#
# CI (plugin-validate.yml) re-runs this and asserts no diff — drift fails CI.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PLUGIN_DIR="plugins/ai-data-agents"
SRC_AGENTS="data_agents/agents/registry"
SRC_SKILLS="skills"

# ─── Pre-flight ───────────────────────────────────────────────────────────────
if [[ ! -d "${SRC_AGENTS}" ]]; then
  echo "❌ source not found: ${SRC_AGENTS}" >&2
  exit 1
fi
if [[ ! -d "${SRC_SKILLS}" ]]; then
  echo "❌ source not found: ${SRC_SKILLS}" >&2
  exit 1
fi
if [[ ! -f "${PLUGIN_DIR}/.claude-plugin/plugin.json" ]]; then
  echo "❌ plugin manifest not found: ${PLUGIN_DIR}/.claude-plugin/plugin.json" >&2
  echo "   Did the marketplace + plugin scaffolding land?" >&2
  exit 1
fi

# ─── Clean and rebuild target dirs ────────────────────────────────────────────
# Preserve .claude-plugin/ and README.md (committed manually). Only nuke
# the generated content trees.
rm -rf "${PLUGIN_DIR}/agents"
rm -rf "${PLUGIN_DIR}/skills"
mkdir -p "${PLUGIN_DIR}/agents"
mkdir -p "${PLUGIN_DIR}/skills"

# ─── Sync agents ──────────────────────────────────────────────────────────────
# Copy each agent .md (skip _template.md). Layout is flat.
agent_count=0
for md in "${SRC_AGENTS}"/*.md; do
  fname="$(basename "${md}")"
  if [[ "${fname}" =~ ^_ ]]; then
    continue
  fi
  cp "${md}" "${PLUGIN_DIR}/agents/${fname}"
  agent_count=$((agent_count + 1))
done
echo "✓ synced ${agent_count} agents → ${PLUGIN_DIR}/agents/"

# ─── Sync skills (flatten the domain hierarchy) ───────────────────────────────
# Two source layouts coexist in skills/:
#   (a) skills/<domain>/<name>/SKILL.md   (most skills — grouped by domain)
#   (b) skills/<name>/SKILL.md            (top-level — e.g. migration, python)
#
# Plugin layout is always flat: plugins/.../skills/<name>/SKILL.md.
#
# Domains are dropped. Collision detection uses the filesystem: if the target
# dir already exists after we cleaned it in the rebuild step, that means two
# different source skills wrote to the same name = collision.
#
# Note: no `declare -A` here — must work on macOS bash 3.2 (Apple ships old
# bash for GPL licensing reasons).
skill_count=0

# Find every SKILL.md under skills/, regardless of depth. The skill directory
# is the parent of SKILL.md.
while IFS= read -r skill_md; do
  skill_dir="$(dirname "${skill_md}")"
  name="$(basename "${skill_dir}")"
  # Skip TEMPLATE (scaffolding only, not a real skill)
  if [[ "${name}" == "TEMPLATE" || "${name}" == "_template" ]]; then
    continue
  fi
  target_dir="${PLUGIN_DIR}/skills/${name}"
  # Collision check (filesystem-based — works on macOS bash 3.2 + linux bash 4+)
  if [[ -d "${target_dir}" ]]; then
    echo "❌ skill name collision: '${name}' written from multiple sources" >&2
    echo "   Already populated: ${target_dir}" >&2
    echo "   Current conflict:  ${skill_dir}" >&2
    echo "   Resolution: rename one of them, or extend build_plugin.sh to" >&2
    echo "   keep domain prefix (e.g. databricks__databricks-jobs)." >&2
    exit 2
  fi
  mkdir -p "${target_dir}"
  cp -R "${skill_dir}"/. "${target_dir}/"
  skill_count=$((skill_count + 1))
done < <(find "${SRC_SKILLS}" -name "SKILL.md" -type f | sort)

echo "✓ synced ${skill_count} skills → ${PLUGIN_DIR}/skills/"

# ─── Update plugin.json version from VERSION file ─────────────────────────────
# Single source of truth: VERSION → also flows into plugin.json so the plugin
# manifest never drifts from the pip version.
if [[ -f VERSION ]]; then
  VERSION="$(tr -d '[:space:]' < VERSION)"
  python3 - "${PLUGIN_DIR}/.claude-plugin/plugin.json" "$VERSION" <<'PY'
import json, sys
path, version = sys.argv[1], sys.argv[2]
data = json.loads(open(path).read())
data["version"] = version
open(path, "w").write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
PY
  echo "✓ plugin.json version synced to ${VERSION}"
fi

# Same for marketplace.json plugin entry
if [[ -f VERSION ]]; then
  python3 - "${REPO_ROOT}/.claude-plugin/marketplace.json" "$VERSION" <<'PY'
import json, sys
path, version = sys.argv[1], sys.argv[2]
data = json.loads(open(path).read())
for plugin in data.get("plugins", []):
    if plugin.get("name") == "ai-data-agents":
        plugin["version"] = version
open(path, "w").write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
PY
  echo "✓ marketplace.json plugin version synced to ${VERSION}"
fi

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "═══ Build summary ═══"
echo "  Plugin dir:  ${PLUGIN_DIR}"
echo "  Agents:      ${agent_count}"
echo "  Skills:      ${skill_count}"
echo ""
echo "Next steps:"
echo "  git status plugins/"
echo "  git add plugins/ .claude-plugin/marketplace.json"
echo "  git commit -m 'chore(plugin): sync agents + skills'"
