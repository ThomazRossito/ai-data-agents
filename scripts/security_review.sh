#!/usr/bin/env bash
# security_review.sh — one-stop security audit for ai-data-agents.
#
# Phase 10: roda em sequência:
#   1. bandit     — detecção de padrões inseguros em código Python
#   2. pip-audit  — vulnerabilidades conhecidas (CVE) em dependências
#   3. secrets    — scan de chaves/tokens hardcoded (regex próprio)
#
# Cada step pode falhar independentemente; o exit code final é o OR de todos.
# Saída humana-amigável: cabeçalho colorido por step + summary no fim.
#
# Uso:
#   bash scripts/security_review.sh         # roda os 3
#   bash scripts/security_review.sh bandit  # roda apenas bandit
#   bash scripts/security_review.sh --no-pip-audit   # pular pip-audit (offline)
#
# Para CI: usar individual GitHub Actions (já existem em .github/workflows/).
# Este script é a versão "one command" para devs locais.

set -uo pipefail   # NOT -e: queremos continuar rodando os steps mesmo com falha

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Parse flags
SKIP_BANDIT=0
SKIP_PIP_AUDIT=0
SKIP_SECRETS=0
ONLY=""

for arg in "$@"; do
  case "$arg" in
    bandit|pip-audit|secrets) ONLY="$arg";;
    --no-bandit)              SKIP_BANDIT=1;;
    --no-pip-audit)           SKIP_PIP_AUDIT=1;;
    --no-secrets)             SKIP_SECRETS=1;;
    -h|--help)
      sed -n '2,/^set -uo/p' "$0" | sed 's/^# \?//'
      exit 0;;
    *) echo "Argumento desconhecido: $arg" >&2; exit 2;;
  esac
done

# If only is set, run only that step
if [[ -n "$ONLY" ]]; then
  case "$ONLY" in
    bandit)    SKIP_PIP_AUDIT=1; SKIP_SECRETS=1;;
    pip-audit) SKIP_BANDIT=1; SKIP_SECRETS=1;;
    secrets)   SKIP_BANDIT=1; SKIP_PIP_AUDIT=1;;
  esac
fi

# ─── Step 1: bandit ──────────────────────────────────────────────────────────
BANDIT_EXIT=0
if [[ "$SKIP_BANDIT" == "0" ]]; then
  echo -e "${BOLD}${CYAN}═══ 1/3 — bandit (Python security lint) ═══${NC}"
  if command -v bandit >/dev/null 2>&1; then
    bandit -r data_agents/ -ll --skip B101 --quiet \
      || BANDIT_EXIT=$?
  else
    echo -e "${YELLOW}⚠ bandit não instalado — pulando. Instale com: pip install \"bandit[toml]>=1.7\"${NC}"
    BANDIT_EXIT=127
  fi
  if [[ $BANDIT_EXIT -eq 0 ]]; then
    echo -e "${GREEN}✓ bandit: sem issues${NC}"
  elif [[ $BANDIT_EXIT -eq 127 ]]; then
    echo -e "${YELLOW}⚠ bandit não foi executado${NC}"
  else
    echo -e "${RED}✗ bandit: issues encontradas (exit $BANDIT_EXIT)${NC}"
  fi
  echo ""
else
  BANDIT_EXIT=-1   # marker for "skipped"
fi

# ─── Step 2: pip-audit ────────────────────────────────────────────────────────
PIP_AUDIT_EXIT=0
if [[ "$SKIP_PIP_AUDIT" == "0" ]]; then
  echo -e "${BOLD}${CYAN}═══ 2/3 — pip-audit (CVE em dependências) ═══${NC}"
  if command -v pip-audit >/dev/null 2>&1; then
    pip-audit --strict --vulnerability-service osv --desc on --format columns \
      || PIP_AUDIT_EXIT=$?
  else
    echo -e "${YELLOW}⚠ pip-audit não instalado — pulando. Instale com: pip install pip-audit${NC}"
    PIP_AUDIT_EXIT=127
  fi
  if [[ $PIP_AUDIT_EXIT -eq 0 ]]; then
    echo -e "${GREEN}✓ pip-audit: sem CVEs${NC}"
  elif [[ $PIP_AUDIT_EXIT -eq 127 ]]; then
    echo -e "${YELLOW}⚠ pip-audit não foi executado${NC}"
  else
    echo -e "${RED}✗ pip-audit: vulnerabilidades encontradas (exit $PIP_AUDIT_EXIT)${NC}"
  fi
  echo ""
else
  PIP_AUDIT_EXIT=-1
fi

# ─── Step 3: secrets scan (regex próprio — sem dep externa) ──────────────────
SECRETS_EXIT=0
if [[ "$SKIP_SECRETS" == "0" ]]; then
  echo -e "${BOLD}${CYAN}═══ 3/3 — secrets scan (regex) ═══${NC}"
  # Python script inline — sem dep externa (gitleaks/detect-secrets opcionais).
  python3 - <<'PY'
import re
import sys
from pathlib import Path

# Padrões de segredos hardcoded reais (sem placeholder de doc).
# Os negative_markers são strings que indicam que a hit é provavelmente
# placeholder/doc e não credencial real.
# Patterns conservadores: prefixos públicos bem-conhecidos só.
# Não tentamos detectar "Azure SP secret" genérico — gera muitos FPs em strings
# longas com ponto (filenames, paths, código). Detectar só Azure SP em contexto
# AZURE_CLIENT_SECRET= (KEY=value) abaixo.
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("Anthropic API key", re.compile(r"sk-ant-api03-[A-Za-z0-9_-]{50,}")),
    ("Moonshot API key",  re.compile(r"\bsk-[a-zA-Z0-9]{40,}\b")),
    ("Databricks PAT",    re.compile(r"\bdapi[0-9a-f]{32}\b")),
    ("AWS access key",    re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub PAT",        re.compile(r"\b(ghp_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{82})\b")),
    ("Bearer token",      re.compile(r"Bearer\s+[A-Za-z0-9_\-.=]{40,}")),
    ("Private key PEM",   re.compile(r"-----BEGIN (RSA|EC|DSA|OPENSSH|PRIVATE) (PRIVATE )?KEY-----")),
    # Heurística contextual: SECRET/PASSWORD/KEY = <value> com value não-placeholder
    ("Hardcoded credential",
     re.compile(
         r"(?:password|secret|token|api[_-]?key|client[_-]?secret)\s*[=:]\s*"
         r"['\"]([A-Za-z0-9_\-./+=]{20,})['\"]",
         re.IGNORECASE,
     )),
]

NEGATIVE_MARKERS = {
    "test", "fake", "placeholder", "example", "your-", "<your", "xxxx",
    "redacted", "secret-here", "api-key-here", "todo", "fixme",
    "dummy", "sample", "demo", "mock", "<token>", "<secret>",
    "${", "{{", "os.environ", "getenv", "vault", "secretsmanager",
}

SCAN_PATHS = ["data_agents", "scripts", "tests", "docs", ".github", "kb", "skills"]
SKIP_DIRS = {".venv", "__pycache__", ".cache", "build", "dist", "node_modules",
             "output", "inputs"}
SKIP_FILES = {".env.example"}

hits: list[tuple[str, str, int, str, str]] = []  # (file, type, lineno, line, match)
for top in SCAN_PATHS:
    base = Path(top)
    if not base.exists():
        continue
    for f in base.rglob("*"):
        if not f.is_file():
            continue
        if any(part in SKIP_DIRS for part in f.parts):
            continue
        if f.name in SKIP_FILES:
            continue
        # Skip binaries
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        for name, pat in PATTERNS:
            for m in pat.finditer(text):
                # Find line number
                lineno = text[:m.start()].count("\n") + 1
                line_start = text.rfind("\n", 0, m.start()) + 1
                line_end = text.find("\n", m.end())
                line = text[line_start:line_end if line_end != -1 else None]
                # Skip if a negative marker is on the same line
                if any(marker in line.lower() for marker in NEGATIVE_MARKERS):
                    continue
                hits.append((str(f), name, lineno, line.strip()[:120], m.group(0)[:30]))

if hits:
    print(f"\n  Possíveis segredos detectados ({len(hits)} hits):\n")
    for f, kind, lineno, line, match in hits[:50]:
        print(f"  ✗ {kind} em {f}:{lineno}")
        print(f"    {line}")
    if len(hits) > 50:
        print(f"  ... e mais {len(hits) - 50}")
    sys.exit(1)
else:
    print("  ✓ nenhum padrão de segredo conhecido encontrado")
    sys.exit(0)
PY
  SECRETS_EXIT=$?
  if [[ $SECRETS_EXIT -eq 0 ]]; then
    echo -e "${GREEN}✓ secrets scan: clean${NC}"
  else
    echo -e "${RED}✗ secrets scan: possíveis segredos encontrados${NC}"
  fi
  echo ""
else
  SECRETS_EXIT=-1
fi

# ─── Summary ──────────────────────────────────────────────────────────────────
echo -e "${BOLD}═══ Summary ═══${NC}"
status() {
  case "$1" in
    -1) echo "skipped";;
    0)  echo -e "${GREEN}pass${NC}";;
    127) echo -e "${YELLOW}not-installed${NC}";;
    *)  echo -e "${RED}fail${NC}";;
  esac
}
printf "  %-12s : %s\n" "bandit"    "$(status $BANDIT_EXIT)"
printf "  %-12s : %s\n" "pip-audit" "$(status $PIP_AUDIT_EXIT)"
printf "  %-12s : %s\n" "secrets"   "$(status $SECRETS_EXIT)"
echo ""

# Final exit: 0 só se todos foram pass OR skipped (127 = not installed conta como warning)
FAIL=0
for code in $BANDIT_EXIT $PIP_AUDIT_EXIT $SECRETS_EXIT; do
  if [[ $code -gt 0 && $code -ne 127 ]]; then FAIL=1; fi
done
exit $FAIL
