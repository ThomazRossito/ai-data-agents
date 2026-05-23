#!/usr/bin/env bash
# bump-version.sh — single command to bump version across all sync points.
#
# Phase 9: VERSION na raiz é a single source of truth. Este script:
#   1. Lê VERSION atual e calcula a próxima.
#   2. Atualiza VERSION, pyproject.toml, data_agents/__init__.py, README badge.
#   3. Migra a seção [Unreleased] do CHANGELOG.md para [novaversao] - <data>.
#   4. Commita as mudanças e cria tag vX.Y.Z (não dá push — você confirma).
#
# Uso:
#   scripts/bump-version.sh patch          # 3.0.0 → 3.0.1
#   scripts/bump-version.sh minor          # 3.0.1 → 3.1.0
#   scripts/bump-version.sh major          # 3.1.0 → 4.0.0
#   scripts/bump-version.sh rc             # 3.0.0-rc1 → 3.0.0-rc2
#                                          # 3.0.0 → 3.0.1-rc1
#   scripts/bump-version.sh final          # 3.0.0-rc7 → 3.0.0  (drop o -rcN)
#   scripts/bump-version.sh --dry-run …   # mostra o que mudaria sem aplicar
#   scripts/bump-version.sh --no-tag …    # commita mas não cria tag
#
# Após sucesso, lembra de fazer:
#   git push origin <branch> --tags
# (o workflow release.yml dispara em push da tag).

set -euo pipefail

# ─── Locate repo root ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# ─── Parse flags ──────────────────────────────────────────────────────────────
DRY_RUN=0
NO_TAG=0
BUMP=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)  DRY_RUN=1; shift;;
    --no-tag)   NO_TAG=1; shift;;
    --help|-h)  sed -n '2,/^set -/p' "$0" | sed 's/^# \?//'; exit 0;;
    patch|minor|major|rc|final)
                BUMP="$1"; shift;;
    *)          echo "Erro: argumento desconhecido: $1" >&2
                echo "Use: patch | minor | major | rc | final" >&2
                exit 2;;
  esac
done

if [[ -z "${BUMP}" ]]; then
  echo "Erro: especifique o tipo de bump (patch|minor|major|rc|final)" >&2
  exit 2
fi

# ─── Sanity: working tree limpo? ──────────────────────────────────────────────
if [[ "${DRY_RUN}" == "0" ]] && ! git diff-index --quiet HEAD --; then
  echo "Erro: working tree tem mudanças não commitadas. Faça stash/commit antes." >&2
  git status --short
  exit 3
fi

# ─── Read current version ─────────────────────────────────────────────────────
if [[ ! -f VERSION ]]; then
  echo "Erro: arquivo VERSION não existe na raiz." >&2
  exit 4
fi
CURRENT="$(tr -d '[:space:]' < VERSION)"
echo "Versão atual: ${CURRENT}"

# ─── Compute next version ─────────────────────────────────────────────────────
# Parse "X.Y.Z" ou "X.Y.Z-rcN"
if [[ "${CURRENT}" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)(-rc([0-9]+))?$ ]]; then
  MAJ="${BASH_REMATCH[1]}"
  MIN="${BASH_REMATCH[2]}"
  PAT="${BASH_REMATCH[3]}"
  RC="${BASH_REMATCH[5]:-}"
else
  echo "Erro: formato de versão não suportado: ${CURRENT}" >&2
  echo "Esperado: X.Y.Z ou X.Y.Z-rcN" >&2
  exit 5
fi

case "${BUMP}" in
  patch)  PAT=$((PAT + 1)); RC="";;
  minor)  MIN=$((MIN + 1)); PAT=0; RC="";;
  major)  MAJ=$((MAJ + 1)); MIN=0; PAT=0; RC="";;
  rc)
    if [[ -n "${RC}" ]]; then
      RC=$((RC + 1))
    else
      # Sem -rc → bump patch + começa em -rc1
      PAT=$((PAT + 1))
      RC=1
    fi
    ;;
  final)
    if [[ -z "${RC}" ]]; then
      echo "Erro: 'final' só faz sentido quando a versão atual tem sufixo -rcN." >&2
      exit 6
    fi
    RC=""
    ;;
esac

NEXT="${MAJ}.${MIN}.${PAT}"
if [[ -n "${RC}" ]]; then
  NEXT="${NEXT}-rc${RC}"
fi
echo "Próxima versão: ${NEXT}"

if [[ "${DRY_RUN}" == "1" ]]; then
  echo "(dry-run — nenhum arquivo modificado)"
  exit 0
fi

# ─── Compute README badge variant (encode '-' → '--' for shields.io) ────────
BADGE_NEXT="${NEXT//-/--}"
BADGE_CURR="${CURRENT//-/--}"

# ─── Apply substitutions ──────────────────────────────────────────────────────
echo "${NEXT}" > VERSION

# pyproject.toml — match the [project] version line specifically
# (use a stricter regex to avoid hitting dependency version specs)
python3 - "$NEXT" <<'PY'
import re, sys
nv = sys.argv[1]
p = open("pyproject.toml").read()
# Replace ONLY the [project] version (first 'version = "..."' inside [project])
p = re.sub(
    r'(\[project\][^\[]*?version\s*=\s*")([^"]+)(")',
    lambda m: m.group(1) + nv + m.group(3),
    p,
    count=1,
    flags=re.DOTALL,
)
open("pyproject.toml", "w").write(p)
PY

# data_agents/__init__.py
python3 - "$NEXT" <<'PY'
import re, sys
nv = sys.argv[1]
p = open("data_agents/__init__.py").read()
p = re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{nv}"', p, count=1)
open("data_agents/__init__.py", "w").write(p)
PY

# README.md badge
python3 - "$BADGE_CURR" "$BADGE_NEXT" <<'PY'
import sys
curr, new = sys.argv[1], sys.argv[2]
p = open("README.md").read()
p = p.replace(f"Version-{curr}-brightgreen", f"Version-{new}-brightgreen")
open("README.md", "w").write(p)
PY

# CHANGELOG.md — move [Unreleased] → [vX.Y.Z] — <date>
TODAY="$(date +%Y-%m-%d)"
python3 - "$NEXT" "$TODAY" <<'PY'
import re, sys
nv, today = sys.argv[1], sys.argv[2]
p = open("CHANGELOG.md").read()

# Find the [Unreleased] section
m = re.search(r'^## \[Unreleased\]\s*\n', p, flags=re.MULTILINE)
if not m:
    print("Aviso: CHANGELOG.md sem seção [Unreleased]. Pulando.", file=sys.stderr)
    sys.exit(0)

# Insert new header right after [Unreleased] (keeps Unreleased empty for next cycle)
insert_at = m.end()
new_section = f"\n## [{nv}] — {today}\n"
p = p[:insert_at] + new_section + p[insert_at:]
open("CHANGELOG.md", "w").write(p)
PY

echo ""
echo "✓ Arquivos atualizados:"
echo "  - VERSION"
echo "  - pyproject.toml"
echo "  - data_agents/__init__.py"
echo "  - README.md (badge)"
echo "  - CHANGELOG.md (Unreleased → [${NEXT}])"

# ─── Sync Claude Code plugin manifests (Phase 12) ─────────────────────────────
# build_plugin.sh propaga a versão para:
#   - plugins/ai-data-agents/.claude-plugin/plugin.json
#   - .claude-plugin/marketplace.json (plugins[].version)
# Sem isso, o marketplace exposto via `claude plugin install` mostraria
# versão antiga, mesmo após o bump do pip package.
if [[ -x "${SCRIPT_DIR}/build_plugin.sh" ]]; then
  echo ""
  echo "─── Syncing plugin manifests ───"
  bash "${SCRIPT_DIR}/build_plugin.sh" >/dev/null 2>&1 || {
    echo "⚠ build_plugin.sh falhou — manifests do plugin podem ficar fora de sync." >&2
    echo "  Investigue antes do commit." >&2
  }
  echo "✓ Plugin manifests synced to v${NEXT}"
fi

# ─── Commit + tag ─────────────────────────────────────────────────────────────
git add VERSION pyproject.toml data_agents/__init__.py README.md CHANGELOG.md \
        plugins/ai-data-agents/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json
git commit -m "chore(release): bump to v${NEXT}"

if [[ "${NO_TAG}" == "0" ]]; then
  git tag "v${NEXT}" -m "Release v${NEXT}"
  echo ""
  echo "✓ Commit + tag v${NEXT} criados."
  echo ""
  echo "Próximo passo:"
  echo "  git push origin \$(git branch --show-current) --tags"
  echo ""
  echo "Isso vai disparar .github/workflows/release.yml e criar a GitHub Release"
  echo "automaticamente com as notes da seção [${NEXT}] do CHANGELOG."
else
  echo ""
  echo "✓ Commit criado (sem tag, --no-tag)."
fi
