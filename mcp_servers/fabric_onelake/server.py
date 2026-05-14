"""
Fabric OneLake MCP — operações determinísticas de arquivo em OneLake via DFS API.

Existe pra contornar bug observado em produção no MCP oficial
`@microsoft/fabric-mcp` (`mcp__fabric_official__onelake_upload_file`):
retornava HTTP 400 mesmo com Service Principal Admin no workspace, tenant
settings OK e tokens válidos pra todos os scopes (storage.azure.com,
fabric.microsoft.com, powerbi/api).

Validado por scripts/test_onelake_upload.py: a DFS API direta (`onelake.dfs.fabric.microsoft.com`)
funciona 100% — create (201) → append (202) → flush (200). Esse MCP encapsula
exatamente esse fluxo de 3 passos, deixando o agente chamar 1 tool atômica.

Tools expostas:

  - fabric_onelake_upload_file       — upload de bytes inline
  - fabric_onelake_upload_local_file — upload de arquivo do filesystem local
  - fabric_onelake_download_file     — download de bytes
  - fabric_onelake_list_files        — lista arquivos/dirs de um path
  - fabric_onelake_file_exists       — checa existência sem baixar
  - fabric_onelake_create_directory  — cria diretório vazio
  - fabric_onelake_delete_file       — apaga arquivo ou diretório

Auth: ClientSecretCredential com scope https://storage.azure.com/.default
(compartilha .env com fabric_semantic, fabric_notebook, fabric_sql).

Variáveis necessárias: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET,
FABRIC_WORKSPACE_NAME (nome do workspace pro path da DFS URL).

Rodar standalone:
    python -m mcp_servers.fabric_onelake.server

Pré-requisitos: pip install azure-identity requests mcp[cli]
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("fabric_onelake_mcp")

try:
    from azure.identity import ClientSecretCredential, DefaultAzureCredential

    AZURE_IDENTITY_AVAILABLE = True
except ImportError:
    AZURE_IDENTITY_AVAILABLE = False

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


mcp = FastMCP("fabric-onelake")

_STORAGE_SCOPE = "https://storage.azure.com/.default"
_BASE_URL = "https://onelake.dfs.fabric.microsoft.com"


# ─── Auth + HTTP helpers ─────────────────────────────────────────────────────


def _get_token() -> str:
    if not AZURE_IDENTITY_AVAILABLE:
        raise RuntimeError("azure-identity não instalado. pip install azure-identity")
    tenant = os.environ.get("AZURE_TENANT_ID", "").strip()
    client_id = os.environ.get("AZURE_CLIENT_ID", "").strip()
    secret = os.environ.get("AZURE_CLIENT_SECRET", "").strip()
    if tenant and client_id and secret:
        cred = ClientSecretCredential(tenant_id=tenant, client_id=client_id, client_secret=secret)
    else:
        cred = DefaultAzureCredential()
    return cred.get_token(_STORAGE_SCOPE).token


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    h = {"Authorization": f"Bearer {_get_token()}"}
    if extra:
        h.update(extra)
    return h


def _resolve_workspace(workspace_name: str | None) -> str:
    """Workspace name vem do parâmetro ou de FABRIC_WORKSPACE_NAME no .env.

    OneLake DFS usa NAME do workspace (slug), não o GUID. Se FABRIC_WORKSPACE_NAME
    não estiver setado, cai pra FABRIC_WORKSPACE_ID — mas isso costuma falhar
    porque a DFS API não aceita GUID no path.
    """
    ws = (workspace_name or "").strip()
    if ws:
        return ws
    ws = os.environ.get("FABRIC_WORKSPACE_NAME", "").strip()
    if ws:
        return ws
    raise RuntimeError(
        "workspace_name não fornecido e FABRIC_WORKSPACE_NAME não está no .env. "
        "DFS API requer o NAME (slug) do workspace, não o GUID."
    )


def _build_url(
    workspace_name: str,
    lakehouse: str,
    path: str,
    item_type: str = "Lakehouse",
) -> str:
    """Constrói URL OneLake DFS pra um path dentro do lakehouse.

    Args:
        workspace_name: slug do workspace (ex: 'poc-multiagent-fabric')
        lakehouse:      nome do lakehouse (sem sufixo)
        path:           caminho dentro de Files/ (ex: 'raw/relatorio.docx')
        item_type:      'Lakehouse' (default) ou 'Warehouse', etc.
    """
    # Permite passar com ou sem prefixo 'Files/'
    p = path.strip("/")
    if not p.startswith("Files/") and not p.startswith("Tables/"):
        p = f"Files/{p}"
    return f"{_BASE_URL}/{workspace_name}/{lakehouse}.{item_type}/{p}"


# ─── Tools ───────────────────────────────────────────────────────────────────


@mcp.tool()
def fabric_onelake_upload_file(
    lakehouse: str,
    remote_path: str,
    content_b64: str,
    workspace_name: str | None = None,
    overwrite: bool = True,
) -> dict[str, Any]:
    """
    Upload de bytes pra um arquivo em Files/ do Lakehouse. Fluxo de 3 passos:
    create (PUT) → append (PATCH) → flush (PATCH).

    Args:
        lakehouse:      nome do Lakehouse (sem '.Lakehouse')
        remote_path:    caminho destino dentro do lakehouse (ex: 'raw/doc.txt')
                        prefixo 'Files/' opcional — é adicionado se faltar
        content_b64:    conteúdo em base64. Use base64.b64encode(bytes).decode()
        workspace_name: NAME do workspace (não GUID). Padrão: FABRIC_WORKSPACE_NAME.
        overwrite:      Se False e o arquivo existir, falha em vez de sobrescrever

    Returns:
        {"status": "uploaded", "url", "bytes_written"} | {"error": ..., "detail": ...}
    """
    import base64

    if not REQUESTS_AVAILABLE:
        return {"error": "requests não instalado"}
    try:
        content = base64.b64decode(content_b64)
    except Exception as e:  # noqa: BLE001
        return {"error": f"content_b64 inválido: {e}"}

    ws = _resolve_workspace(workspace_name)
    url = _build_url(ws, lakehouse, remote_path)

    # Verifica existência se overwrite=False
    if not overwrite:
        head = requests.head(url, headers=_headers(), timeout=20)
        if head.status_code == 200:
            return {"error": "file_exists", "detail": f"{url} já existe e overwrite=False"}

    # Passo 1: create
    r1 = requests.put(f"{url}?resource=file", headers=_headers(), timeout=30)
    if r1.status_code not in (200, 201):
        return {"error": f"create_failed HTTP {r1.status_code}", "detail": r1.text[:500]}

    # Passo 2: append (pode ser feito em chunks se for grande; aqui faz 1 chunk)
    r2 = requests.patch(
        f"{url}?action=append&position=0",
        headers=_headers({"Content-Type": "application/octet-stream"}),
        data=content,
        timeout=60,
    )
    if r2.status_code not in (200, 202):
        return {"error": f"append_failed HTTP {r2.status_code}", "detail": r2.text[:500]}

    # Passo 3: flush
    r3 = requests.patch(
        f"{url}?action=flush&position={len(content)}",
        headers=_headers(),
        timeout=30,
    )
    if r3.status_code not in (200, 201):
        return {"error": f"flush_failed HTTP {r3.status_code}", "detail": r3.text[:500]}

    return {
        "status": "uploaded",
        "url": url,
        "bytes_written": len(content),
        "workspace": ws,
        "lakehouse": lakehouse,
        "remote_path": remote_path,
    }


@mcp.tool()
def fabric_onelake_upload_local_file(
    lakehouse: str,
    local_path: str,
    remote_path: str | None = None,
    workspace_name: str | None = None,
    overwrite: bool = True,
) -> dict[str, Any]:
    """
    Faz upload de um arquivo do filesystem local pro OneLake. Trata binários
    (PDF, .docx, .png) ou texto. Lê o arquivo aqui dentro do servidor, sem
    precisar que o LLM faça base64.

    Args:
        local_path:  Path absoluto do arquivo local.
        remote_path: Path destino. Se None, usa o basename do local_path em Files/raw/.
    """
    import base64

    p = Path(local_path).expanduser()
    if not p.is_file():
        return {"error": "file_not_found", "detail": str(p)}
    try:
        content = p.read_bytes()
    except Exception as e:  # noqa: BLE001
        return {"error": f"read_failed: {e}"}

    if not remote_path:
        remote_path = f"raw/{p.name}"

    return fabric_onelake_upload_file(
        lakehouse=lakehouse,
        remote_path=remote_path,
        content_b64=base64.b64encode(content).decode("ascii"),
        workspace_name=workspace_name,
        overwrite=overwrite,
    )


@mcp.tool()
def fabric_onelake_download_file(
    lakehouse: str,
    remote_path: str,
    workspace_name: str | None = None,
    as_text: bool = False,
) -> dict[str, Any]:
    """
    Baixa um arquivo do OneLake.

    Args:
        as_text: True = retorna `content_text` (decode utf-8). False = `content_b64`.

    Returns:
        {"bytes", "content_b64" | "content_text", "url"}
    """
    if not REQUESTS_AVAILABLE:
        return {"error": "requests não instalado"}
    ws = _resolve_workspace(workspace_name)
    url = _build_url(ws, lakehouse, remote_path)

    r = requests.get(url, headers=_headers(), timeout=60)
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}", "detail": r.text[:500], "url": url}

    out: dict[str, Any] = {"bytes": len(r.content), "url": url}
    if as_text:
        try:
            out["content_text"] = r.content.decode("utf-8")
        except UnicodeDecodeError:
            out["error"] = "not_utf8"
            import base64

            out["content_b64"] = base64.b64encode(r.content).decode("ascii")
    else:
        import base64

        out["content_b64"] = base64.b64encode(r.content).decode("ascii")
    return out


@mcp.tool()
def fabric_onelake_list_files(
    lakehouse: str,
    directory: str = "Files",
    workspace_name: str | None = None,
    recursive: bool = False,
) -> dict[str, Any]:
    """
    Lista arquivos e diretórios dentro do lakehouse.

    Args:
        directory: path relativo (ex: 'Files/raw'). Default lista tudo em Files/.
        recursive: lista recursivamente subdiretórios.

    Returns:
        {"count", "items": [{"name", "isDirectory", "contentLength", "lastModified"}, ...]}
    """
    if not REQUESTS_AVAILABLE:
        return {"error": "requests não instalado"}
    ws = _resolve_workspace(workspace_name)
    # DFS API: lista via GET no filesystem (workspace/lakehouse.Lakehouse) com query
    fs_url = f"{_BASE_URL}/{ws}/{lakehouse}.Lakehouse"
    params = {
        "resource": "filesystem",
        "recursive": "true" if recursive else "false",
        "directory": directory,
    }
    r = requests.get(fs_url, headers=_headers(), params=params, timeout=30)
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}", "detail": r.text[:500]}
    data = r.json() if r.text else {}
    paths = data.get("paths", [])
    return {
        "count": len(paths),
        "items": [
            {
                "name": p.get("name"),
                "isDirectory": p.get("isDirectory") == "true",
                "contentLength": p.get("contentLength", "0"),
                "lastModified": p.get("lastModified"),
            }
            for p in paths
        ],
    }


@mcp.tool()
def fabric_onelake_file_exists(
    lakehouse: str,
    remote_path: str,
    workspace_name: str | None = None,
) -> dict[str, Any]:
    """Verifica se um arquivo existe sem baixar conteúdo (HEAD)."""
    if not REQUESTS_AVAILABLE:
        return {"error": "requests não instalado"}
    ws = _resolve_workspace(workspace_name)
    url = _build_url(ws, lakehouse, remote_path)
    r = requests.head(url, headers=_headers(), timeout=20)
    return {"exists": r.status_code == 200, "status_code": r.status_code, "url": url}


@mcp.tool()
def fabric_onelake_create_directory(
    lakehouse: str,
    remote_path: str,
    workspace_name: str | None = None,
) -> dict[str, Any]:
    """Cria um diretório vazio (PUT ?resource=directory)."""
    if not REQUESTS_AVAILABLE:
        return {"error": "requests não instalado"}
    ws = _resolve_workspace(workspace_name)
    url = _build_url(ws, lakehouse, remote_path)
    r = requests.put(f"{url}?resource=directory", headers=_headers(), timeout=30)
    if r.status_code in (200, 201):
        return {"status": "created", "url": url}
    return {"error": f"HTTP {r.status_code}", "detail": r.text[:500], "url": url}


@mcp.tool()
def fabric_onelake_delete_file(
    lakehouse: str,
    remote_path: str,
    workspace_name: str | None = None,
    recursive: bool = False,
) -> dict[str, Any]:
    """Apaga um arquivo ou diretório (DELETE). recursive=True pra dirs com conteúdo."""
    if not REQUESTS_AVAILABLE:
        return {"error": "requests não instalado"}
    ws = _resolve_workspace(workspace_name)
    url = _build_url(ws, lakehouse, remote_path)
    params = {"recursive": "true"} if recursive else {}
    r = requests.delete(url, headers=_headers(), params=params, timeout=30)
    if r.status_code in (200, 204):
        return {"status": "deleted", "url": url}
    return {"error": f"HTTP {r.status_code}", "detail": r.text[:500], "url": url}


# ─── Entry point ─────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    # Silencia logs verbose do azure (não quebra MCP via stdio)
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    mcp.run()


if __name__ == "__main__":
    main()
