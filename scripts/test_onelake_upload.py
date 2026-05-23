#!/usr/bin/env python3
"""
scripts/test_onelake_upload.py — Diagnóstico de upload OneLake via REST direto.

Bypassa o MCP `@microsoft/fabric-mcp` pra isolar se o erro 400 é do MCP
ou da configuração tenant/SP. Usa a DFS API do OneLake (equivalente ADLS Gen2)
com 3 passos: create → append → flush.

Uso:
    python scripts/test_onelake_upload.py
    python scripts/test_onelake_upload.py --workspace poc-multiagent-fabric \
        --lakehouse medallion_lakehouse

Interpretação dos resultados:
    Todos 200/201    → MCP tem bug; vale criar fabric_onelake custom
    403 Forbidden    → Tenant setting "Service principals can use Fabric APIs" off
    404 Not Found    → Nome de workspace/lakehouse errado
    400 BadRequest   → PrincipalTypeNotSupported (raro no Trial)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _load_env() -> None:
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def main() -> int:
    p = argparse.ArgumentParser(description="Test OneLake upload via REST direto.")
    p.add_argument(
        "--workspace",
        default="poc-multiagent-fabric",
        help="Workspace name (default: poc-multiagent-fabric)",
    )
    p.add_argument(
        "--lakehouse",
        default="medallion_lakehouse",
        help="Lakehouse name (default: medallion_lakehouse)",
    )
    p.add_argument(
        "--filename",
        default="teste_diagnostico.txt",
        help="Filename to upload (default: teste_diagnostico.txt)",
    )
    args = p.parse_args()

    _load_env()
    for k in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"):
        if not os.environ.get(k):
            print(f"FATAL: {k} ausente no .env")
            return 2

    try:
        from azure.identity import ClientSecretCredential
        import requests
    except ImportError as e:
        print(f"FATAL: dependência faltando — {e}")
        return 2

    cred = ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
    )
    token = cred.get_token("https://storage.azure.com/.default").token

    content = b"hello onelake from python direct - diagnostico\n"
    base = (
        f"https://onelake.dfs.fabric.microsoft.com/"
        f"{args.workspace}/{args.lakehouse}.Lakehouse/Files"
    )
    headers = {"Authorization": f"Bearer {token}"}

    print(f"Workspace: {args.workspace}")
    print(f"Lakehouse: {args.lakehouse}")
    print(f"Filename:  {args.filename}")
    print(f"Base URL:  {base}")
    print(f"Content:   {len(content)} bytes")
    print()

    # Passo 1 — Create file (PUT ?resource=file)
    url1 = f"{base}/{args.filename}?resource=file"
    print("PASSO 1 — Create file")
    print(f"  PUT {url1}")
    r1 = requests.put(url1, headers=headers, timeout=30)
    print(f"  → HTTP {r1.status_code}")
    if r1.text:
        print(f"  body: {r1.text[:300]}")
    print()

    if r1.status_code >= 400:
        print(_diagnose(r1.status_code, r1.text))
        return 1

    # Passo 2 — Append content (PATCH ?action=append&position=0)
    url2 = f"{base}/{args.filename}?action=append&position=0"
    print("PASSO 2 — Upload bytes")
    print(f"  PATCH {url2}")
    r2 = requests.patch(
        url2,
        headers={**headers, "Content-Type": "application/octet-stream"},
        data=content,
        timeout=30,
    )
    print(f"  → HTTP {r2.status_code}")
    if r2.text:
        print(f"  body: {r2.text[:300]}")
    print()

    if r2.status_code >= 400:
        print(_diagnose(r2.status_code, r2.text))
        return 1

    # Passo 3 — Flush (PATCH ?action=flush&position=N)
    url3 = f"{base}/{args.filename}?action=flush&position={len(content)}"
    print("PASSO 3 — Flush (commit)")
    print(f"  PATCH {url3}")
    r3 = requests.patch(url3, headers=headers, timeout=30)
    print(f"  → HTTP {r3.status_code}")
    if r3.text:
        print(f"  body: {r3.text[:300]}")
    print()

    if r3.status_code >= 400:
        print(_diagnose(r3.status_code, r3.text))
        return 1

    print("=" * 60)
    print("✅ SUCESSO — upload via REST direto funcionou!")
    print("   Isso significa que:")
    print("   - Auth OK")
    print("   - Tenant settings OK")
    print("   - SP tem permissão suficiente")
    print("   - O MCP `@microsoft/fabric-mcp` tem bug")
    print("   → Vale criar mcp_servers/fabric_onelake/ custom")
    print("=" * 60)
    return 0


def _diagnose(status: int, body: str) -> str:
    lines = ["=" * 60]
    if status == 403:
        lines.append("❌ HTTP 403 Forbidden")
        lines.append("   Causa MAIS provável: Tenant setting desligada.")
        lines.append("   Fabric Admin Portal → Tenant settings → Developer")
        lines.append("   → 'Service principals can use Fabric APIs': Enable")
        lines.append("   Quem precisa: admin global do tenant (não admin do workspace).")
    elif status == 404:
        lines.append("❌ HTTP 404 Not Found")
        lines.append("   Causa: nome do workspace ou lakehouse errado.")
        lines.append("   Conferir nomes EXATOS (case-sensitive) na UI do Fabric.")
        lines.append("   Note: o sufixo '.Lakehouse' é obrigatório no path.")
    elif status == 400:
        if "PrincipalTypeNotSupported" in body:
            lines.append("❌ HTTP 400 PrincipalTypeNotSupported")
            lines.append("   Causa: Service Principal não suportado pra essa operação.")
            lines.append("   Solução: usar user delegation token (login interativo)")
            lines.append("   ou upload manual pela UI do Fabric.")
        else:
            lines.append("❌ HTTP 400 — verifique body acima.")
    elif status == 401:
        lines.append("❌ HTTP 401 Unauthorized")
        lines.append("   Token inválido ou expirado. Refaça o login do SP.")
    else:
        lines.append(f"❌ HTTP {status} — caso não catalogado.")
    lines.append("=" * 60)
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
