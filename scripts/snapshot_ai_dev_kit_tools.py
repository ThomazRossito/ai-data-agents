#!/usr/bin/env python3
"""
snapshot_ai_dev_kit_tools.py — extrai os nomes de tool do servidor MCP do ai-dev-kit.

Por que um snapshot
-------------------
A CI não instala o extra `databricks-admin` (compila C++), então não pode
importar o servidor para perguntar "quais tools você tem?". Este script lê o
FONTE do servidor — os decoradores `@mcp.tool` em `databricks_mcp_server/tools/`
— e grava a lista em `tests/fixtures/ai_dev_kit_tools.txt`, junto com o SHA do
commit lido. `tests/unit/test_mcp_configs.py` compara `DATABRICKS_MCP_TOOLS` com
esse arquivo.

É exatamente o descasamento de 26 tools fantasmas (2026-07 → 2026-09) que este
gate impede de voltar: qualquer nome em `server_config.py` que não exista no
snapshot reprova.

Uso:
    python scripts/snapshot_ai_dev_kit_tools.py /caminho/para/ai-dev-kit
    python scripts/snapshot_ai_dev_kit_tools.py /caminho/para/ai-dev-kit --check

Com --check, não grava: só compara com o fixture existente e sai 1 se divergir.
Quando o pin do pyproject subir, rode sem --check para regravar, revise o diff
e ajuste `server_config.py` no mesmo commit.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "ai_dev_kit_tools.txt"

#: `@mcp.tool` (com ou sem parênteses/kwargs), possivelmente seguido de outros
#: decoradores, e então `def nome(` ou `async def nome(`.
_TOOL_RE = re.compile(
    r"@mcp\.tool(?:\([^)]*\))?[^\n]*\n(?:\s*@[^\n]*\n)*\s*(?:async\s+)?def\s+([a-z_][a-z0-9_]*)\s*\(",
    re.MULTILINE,
)


def extract_tool_names(ai_dev_kit_root: Path) -> list[str]:
    tools_dir = ai_dev_kit_root / "databricks-mcp-server" / "databricks_mcp_server" / "tools"
    if not tools_dir.is_dir():
        raise SystemExit(f"não achei {tools_dir} — o caminho aponta para a raiz do ai-dev-kit?")
    nomes: set[str] = set()
    for py in sorted(tools_dir.glob("*.py")):
        src = py.read_text(encoding="utf-8", errors="replace")
        nomes.update(_TOOL_RE.findall(src))
    if not nomes:
        raise SystemExit("regex não achou nenhuma tool — o padrão de registro mudou?")
    return sorted(nomes)


def git_sha(repo: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def render(sha: str, nomes: list[str]) -> str:
    cab = [
        "# Tools do servidor MCP do ai-dev-kit (databricks-solutions), extraídas do fonte.",
        "# Gerado por scripts/snapshot_ai_dev_kit_tools.py — NÃO edite à mão.",
        f"# commit: {sha}",
        f"# total: {len(nomes)}",
    ]
    return "\n".join(cab + nomes) + "\n"


def parse_fixture(texto: str) -> tuple[str, list[str]]:
    sha = "unknown"
    nomes: list[str] = []
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if linha.startswith("# commit:"):
            sha = linha.split(":", 1)[1].strip()
        elif not linha.startswith("#"):
            nomes.append(linha)
    return sha, nomes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ai_dev_kit_root", type=Path, help="raiz do clone do ai-dev-kit")
    ap.add_argument("--check", action="store_true", help="só compara com o fixture; não grava")
    args = ap.parse_args(argv)

    nomes = extract_tool_names(args.ai_dev_kit_root)
    sha = git_sha(args.ai_dev_kit_root)

    if args.check:
        if not FIXTURE.is_file():
            print(f"fixture ausente: {FIXTURE}", file=sys.stderr)
            return 1
        sha_fix, nomes_fix = parse_fixture(FIXTURE.read_text(encoding="utf-8"))
        novos = sorted(set(nomes) - set(nomes_fix))
        sumiram = sorted(set(nomes_fix) - set(nomes))
        if novos or sumiram or (sha_fix != sha and sha != "unknown"):
            print("snapshot DIVERGE do fonte:")
            if sha_fix != sha:
                print(f"  commit  fixture={sha_fix[:7]}  fonte={sha[:7]}")
            for n in novos:
                print(f"  + {n}  (no fonte, não no fixture)")
            for n in sumiram:
                print(f"  - {n}  (no fixture, não no fonte)")
            print("rode sem --check para regravar e ajuste server_config.py no mesmo commit")
            return 1
        print(f"✓ snapshot em dia ({len(nomes)} tools, commit {sha[:7]})")
        return 0

    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(render(sha, nomes), encoding="utf-8")
    print(f"✓ {FIXTURE.relative_to(PROJECT_ROOT)}: {len(nomes)} tools, commit {sha[:7]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
