#!/usr/bin/env python3
"""
scripts/cleanup_fabric_test_notebooks.py — Limpa notebooks de teste no Fabric workspace.

Motivado pelo anti-pattern observado em produção: o agente fabric-engineer cria
múltiplos notebooks vazios quando o `core_create-item` falha em incluir o `definition`.
Em 2 tentativas separadas (POC BTG, 2026-05-13/14), o workspace acumulou 13 notebooks
lixo (test_notebook_content, _content2, _content3, _content4, _content5, _with_def,
_api_direct, test_api_direct, etc).

Uso:

    # Dry-run — lista os notebooks que SERIAM apagados, sem deletar nada
    python scripts/cleanup_fabric_test_notebooks.py

    # Confirma e apaga
    python scripts/cleanup_fabric_test_notebooks.py --apply

    # Filtros customizados (padrão regex)
    python scripts/cleanup_fabric_test_notebooks.py --pattern "test_.*" --apply

Auth: usa DefaultAzureCredential (mesma cadeia dos outros MCPs Fabric — Service
Principal via .env, az login, Managed Identity, etc).

Pré-requisitos: pip install azure-identity requests
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


def _load_env() -> None:
    """Carrega .env do projeto (mesmo parser que start.sh usa)."""
    root = Path(__file__).resolve().parent.parent
    env_file = root / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _fabric_token() -> str:
    """Obtém Bearer token pro escopo da Fabric API."""
    from azure.identity import DefaultAzureCredential

    cred = DefaultAzureCredential()
    return cred.get_token("https://api.fabric.microsoft.com/.default").token


def list_notebooks(workspace_id: str, pattern: re.Pattern) -> list[dict]:
    """Lista notebooks do workspace cujo displayName bate com o padrão."""
    import requests

    token = _fabric_token()
    url = (
        f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items"
        f"?type=Notebook"
    )
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    items = resp.json().get("value", [])
    return [it for it in items if pattern.match(it.get("displayName", ""))]


def delete_item(workspace_id: str, item_id: str, display_name: str) -> tuple[bool, str]:
    """Deleta um item do workspace. Retorna (sucesso, mensagem)."""
    import requests

    token = _fabric_token()
    url = (
        f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items/{item_id}"
    )
    try:
        resp = requests.delete(
            url, headers={"Authorization": f"Bearer {token}"}, timeout=30
        )
        if resp.status_code in (200, 204):
            return True, f"deletado: {display_name} ({item_id})"
        return False, f"falha {resp.status_code}: {display_name} — {resp.text[:200]}"
    except Exception as e:  # noqa: BLE001
        return False, f"erro: {display_name} — {e}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Limpa notebooks de teste/lixo no workspace Fabric.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--workspace-id",
        help="Workspace ID (default: lê de FABRIC_WORKSPACE_ID no .env)",
    )
    parser.add_argument(
        "--pattern",
        default=r"^test_(notebook|api).*",
        help="Regex que casa displayName a deletar (default: '^test_(notebook|api).*')",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplica a deleção. Sem essa flag, faz dry-run (só lista).",
    )
    args = parser.parse_args()

    _load_env()
    workspace_id = args.workspace_id or os.environ.get("FABRIC_WORKSPACE_ID")
    if not workspace_id:
        print("ERROR: --workspace-id não fornecido e FABRIC_WORKSPACE_ID não está no .env")
        return 2

    pattern = re.compile(args.pattern)
    print(f"workspace: {workspace_id}")
    print(f"pattern:   {args.pattern}")
    print(f"mode:      {'APPLY (deletando)' if args.apply else 'DRY-RUN (só lista)'}")
    print()

    try:
        candidates = list_notebooks(workspace_id, pattern)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR ao listar: {e}")
        return 1

    if not candidates:
        print("Nenhum notebook bate com o padrão. Workspace limpo.")
        return 0

    print(f"Encontrados {len(candidates)} notebook(s):\n")
    for it in candidates:
        print(f"  - {it['displayName']:<40s}  id={it['id']}")
    print()

    if not args.apply:
        print("DRY-RUN: nada foi deletado. Use --apply pra confirmar.")
        return 0

    confirm = input(f"Confirma deletar {len(candidates)} notebook(s)? [y/N] ").strip().lower()
    if confirm != "y":
        print("Cancelado.")
        return 0

    failures = 0
    for it in candidates:
        ok, msg = delete_item(workspace_id, it["id"], it["displayName"])
        prefix = "OK " if ok else "FAIL"
        print(f"  [{prefix}] {msg}")
        if not ok:
            failures += 1

    print()
    print(f"Resumo: {len(candidates) - failures} deletados, {failures} falhas.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
