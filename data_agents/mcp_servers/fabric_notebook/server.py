"""
Fabric Notebook MCP — operações determinísticas em notebooks Microsoft Fabric.

Existe pra resolver um anti-pattern observado em produção (POC BTG, 2026-05-13/14):
o agente fabric-engineer, ao usar `mcp__fabric_official__core_create-item`, tem
3 caminhos pra falhar:

  1. Chamar SEM o parâmetro `definition` → cria notebook vazio (shell)
  2. Tentar montar base64 do .ipynb via Bash + python3 inline → loop iterativo
     consumindo dezenas de turnos e gerando notebooks de teste (`_v2`, `_with_def`,
     `_api_direct`, etc.) a cada falha
  3. Não saber lidar com LRO (Long Running Operation) do updateDefinition

Este MCP encapsula TUDO isso em tools determinísticas — 1 chamada, ~5 segundos,
sem necessidade de o LLM montar JSON nem codificar base64.

Tools expostas:

  - fabric_notebook_create      — cria notebook COM cells inicial
  - fabric_notebook_list        — lista notebooks do workspace
  - fabric_notebook_get_cells   — lê células de notebook existente
  - fabric_notebook_replace     — substitui todas as células
  - fabric_notebook_add_cell    — adiciona célula (posição opcional)
  - fabric_notebook_update_cell — modifica célula por índice
  - fabric_notebook_delete_cell — remove célula por índice
  - fabric_notebook_delete      — apaga o notebook
  - fabric_notebook_cleanup_test_items — utilitário pós-experimento

Auth: ClientSecretCredential (compartilha .env com fabric_semantic, fabric_sql).
Variáveis: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, FABRIC_WORKSPACE_ID.

Scope OAuth: https://api.fabric.microsoft.com/.default

Rodar standalone:
    python -m mcp_servers.fabric_notebook.server

Pré-requisitos: pip install azure-identity requests mcp[cli]
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from typing import Any

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("fabric_notebook_mcp")

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


# ─── FastMCP server ──────────────────────────────────────────────────────────

mcp = FastMCP("fabric-notebook")

_FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
_BASE_URL = "https://api.fabric.microsoft.com/v1"


# ─── Auth + HTTP helpers ─────────────────────────────────────────────────────


def _get_token() -> str:
    """Pega Bearer token. Prefere Service Principal (.env), cai pra DefaultAzureCredential."""
    if not AZURE_IDENTITY_AVAILABLE:
        raise RuntimeError("azure-identity não instalado. pip install azure-identity")
    tenant = os.environ.get("AZURE_TENANT_ID", "").strip()
    client_id = os.environ.get("AZURE_CLIENT_ID", "").strip()
    secret = os.environ.get("AZURE_CLIENT_SECRET", "").strip()
    if tenant and client_id and secret:
        cred = ClientSecretCredential(tenant_id=tenant, client_id=client_id, client_secret=secret)
    else:
        cred = DefaultAzureCredential()
    return cred.get_token(_FABRIC_SCOPE).token


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Content-Type": "application/json",
    }


def _resolve_workspace_id(workspace_id: str | None) -> str:
    """Workspace explícito ganha; fallback é FABRIC_WORKSPACE_ID do .env."""
    ws = (workspace_id or "").strip() or os.environ.get("FABRIC_WORKSPACE_ID", "").strip()
    if not ws:
        raise RuntimeError("workspace_id não fornecido e FABRIC_WORKSPACE_ID não está no .env")
    return ws


def _wait_lro(operation_url: str, timeout_s: int = 180, poll_s: float = 2.0) -> dict[str, Any]:
    """Polling de Long Running Operation. Retorna o último JSON ou levanta TimeoutError."""
    if not REQUESTS_AVAILABLE:
        raise RuntimeError("requests não instalado")
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        resp = requests.get(operation_url, headers=_headers(), timeout=30)
        if resp.status_code == 200:
            data = resp.json() if resp.text else {}
            status = data.get("status", "")
            if status in ("Succeeded", "Completed"):
                return data
            if status in ("Failed", "Cancelled"):
                raise RuntimeError(f"LRO falhou ({status}): {data}")
        time.sleep(poll_s)
    raise TimeoutError(f"LRO não concluiu em {timeout_s}s")


# ─── Notebook .ipynb builder ─────────────────────────────────────────────────


def _normalize_source(source: str | list[str]) -> list[str]:
    """Converte source pra lista de linhas no formato Jupyter (preservando \\n)."""
    if isinstance(source, str):
        return [line + "\n" for line in source.split("\n")[:-1]] + (
            [source.split("\n")[-1]] if source.split("\n")[-1] else []
        )
    return list(source)


def _make_cell(source: str | list[str], cell_type: str = "code") -> dict[str, Any]:
    """Monta uma célula no formato Jupyter Notebook .ipynb."""
    cell: dict[str, Any] = {
        "cell_type": cell_type,
        "source": _normalize_source(source),
        "metadata": {},
    }
    if cell_type == "code":
        cell["outputs"] = []
        cell["execution_count"] = None
    return cell


def _build_ipynb(cells: list[dict[str, Any]]) -> dict[str, Any]:
    """Monta um .ipynb completo a partir de uma lista de células."""
    normalized = []
    for c in cells:
        normalized.append(_make_cell(c.get("source", ""), c.get("cell_type", "code")))
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "language_info": {"name": "python"},
            "kernelspec": {
                "display_name": "Synapse PySpark",
                "language": "Python",
                "name": "synapse_pyspark",
            },
        },
        "cells": normalized,
    }


def _encode_definition(ipynb: dict[str, Any]) -> dict[str, Any]:
    """Monta o campo `definition` do create/update-item com o .ipynb em base64."""
    raw = json.dumps(ipynb, ensure_ascii=False).encode("utf-8")
    payload_b64 = base64.b64encode(raw).decode("ascii")
    return {
        "format": "ipynb",
        "parts": [
            {
                "path": "artifact/notebook-content.py",
                "payload": payload_b64,
                "payloadType": "InlineBase64",
            }
        ],
    }


def _decode_definition(definition: dict[str, Any]) -> dict[str, Any]:
    """Inverso de _encode_definition: extrai o .ipynb JSON da resposta do getDefinition."""
    for part in definition.get("parts", []):
        if part.get("payloadType") == "InlineBase64":
            raw = base64.b64decode(part["payload"])
            return json.loads(raw.decode("utf-8"))
    raise ValueError("definition sem InlineBase64 — formato inesperado")


# ─── Tools ───────────────────────────────────────────────────────────────────


@mcp.tool()
def fabric_notebook_create(
    display_name: str,
    cells: list[dict[str, Any]],
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """
    Cria um notebook NOVO com o conteúdo já embarcado. 1 chamada, atômica.

    Args:
        display_name: Nome do notebook (ex: "btg_bronze_to_silver"). Deve ser único
                      no workspace — esta tool falha se já existir item com esse nome.
        cells: Lista de dicts no formato [{"source": "...", "cell_type": "code|markdown"}].
               source aceita string ou lista de linhas.
        workspace_id: Override do workspace. Padrão: FABRIC_WORKSPACE_ID.

    Returns:
        {"item_id": str, "display_name": str, "total_cells": int, "status": "created"}
    """
    if not REQUESTS_AVAILABLE:
        return {"error": "requests não instalado"}
    if not cells:
        return {"error": "cells não pode ser vazio — passe pelo menos 1 célula"}

    ws = _resolve_workspace_id(workspace_id)
    body = {
        "displayName": display_name,
        "type": "Notebook",
        "definition": _encode_definition(_build_ipynb(cells)),
    }
    resp = requests.post(
        f"{_BASE_URL}/workspaces/{ws}/items",
        headers=_headers(),
        json=body,
        timeout=60,
    )
    if resp.status_code == 202:
        op_url = resp.headers.get("Location") or resp.headers.get("Operation-Location")
        if op_url:
            result = _wait_lro(op_url)
            item_id = result.get("resourceId") or result.get("id") or ""
        else:
            item_id = ""
    elif resp.status_code in (200, 201):
        item_id = resp.json().get("id", "")
    else:
        return {
            "error": f"HTTP {resp.status_code}",
            "detail": resp.text[:500],
        }

    return {
        "item_id": item_id,
        "display_name": display_name,
        "total_cells": len(cells),
        "status": "created",
        "workspace_id": ws,
    }


@mcp.tool()
def fabric_notebook_list(workspace_id: str | None = None) -> dict[str, Any]:
    """
    Lista todos os notebooks de um workspace.

    Returns:
        {"count": int, "notebooks": [{"id", "displayName", "description"}, ...]}
    """
    if not REQUESTS_AVAILABLE:
        return {"error": "requests não instalado"}
    ws = _resolve_workspace_id(workspace_id)
    resp = requests.get(
        f"{_BASE_URL}/workspaces/{ws}/items?type=Notebook",
        headers=_headers(),
        timeout=30,
    )
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}", "detail": resp.text[:500]}
    items = resp.json().get("value", [])
    return {
        "count": len(items),
        "notebooks": [
            {
                "id": it.get("id"),
                "displayName": it.get("displayName"),
                "description": it.get("description", ""),
            }
            for it in items
        ],
    }


@mcp.tool()
def fabric_notebook_get_cells(
    item_id: str,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """
    Lê as células de um notebook existente.

    Returns:
        {"item_id", "total_cells", "cells": [{"index", "cell_type", "source", "preview"}]}
    """
    if not REQUESTS_AVAILABLE:
        return {"error": "requests não instalado"}
    ws = _resolve_workspace_id(workspace_id)
    resp = requests.post(
        f"{_BASE_URL}/workspaces/{ws}/items/{item_id}/getDefinition?format=ipynb",
        headers=_headers(),
        timeout=30,
    )
    if resp.status_code == 202:
        op_url = resp.headers.get("Location") or resp.headers.get("Operation-Location")
        if not op_url:
            return {"error": "LRO sem Location header"}
        # Polling com result fetch
        data = _wait_lro(op_url)
        definition = data.get("definition") or {}
        if not definition:
            # Algumas variantes retornam result url separado
            result_url = data.get("resultUrl") or op_url.rstrip("/") + "/result"
            r2 = requests.get(result_url, headers=_headers(), timeout=30)
            definition = r2.json().get("definition", {}) if r2.status_code == 200 else {}
    elif resp.status_code == 200:
        definition = resp.json().get("definition", {})
    else:
        return {"error": f"HTTP {resp.status_code}", "detail": resp.text[:500]}

    ipynb = _decode_definition(definition)
    cells = ipynb.get("cells", [])
    out_cells = []
    for i, c in enumerate(cells):
        src = c.get("source", [])
        src_str = "".join(src) if isinstance(src, list) else str(src)
        out_cells.append(
            {
                "index": i,
                "cell_type": c.get("cell_type", "code"),
                "source": src_str,
                "preview": src_str[:120],
            }
        )
    return {"item_id": item_id, "total_cells": len(out_cells), "cells": out_cells}


@mcp.tool()
def fabric_notebook_replace(
    item_id: str,
    cells: list[dict[str, Any]],
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """
    Substitui todas as células de um notebook existente. NÃO cria item novo.

    Use isso quando precisar 'consertar' um notebook vazio criado antes —
    em vez de criar outro com sufixo (anti-pattern).
    """
    if not REQUESTS_AVAILABLE:
        return {"error": "requests não instalado"}
    if not cells:
        return {"error": "cells não pode ser vazio"}
    ws = _resolve_workspace_id(workspace_id)
    body = {"definition": _encode_definition(_build_ipynb(cells))}
    resp = requests.post(
        f"{_BASE_URL}/workspaces/{ws}/items/{item_id}/updateDefinition",
        headers=_headers(),
        json=body,
        timeout=60,
    )
    if resp.status_code == 202:
        op_url = resp.headers.get("Location") or resp.headers.get("Operation-Location")
        if op_url:
            _wait_lro(op_url)
    elif resp.status_code not in (200, 204):
        return {"error": f"HTTP {resp.status_code}", "detail": resp.text[:500]}
    return {"item_id": item_id, "total_cells": len(cells), "status": "replaced"}


@mcp.tool()
def fabric_notebook_add_cell(
    item_id: str,
    source: str,
    cell_type: str = "code",
    position: int | None = None,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """
    Adiciona uma célula ao notebook. Sem `position` = no fim.

    Internamente: getDefinition → adiciona célula → updateDefinition → LRO.
    """
    current = fabric_notebook_get_cells(item_id, workspace_id=workspace_id)
    if "error" in current:
        return current
    cells_raw = current["cells"]
    new = {"source": source, "cell_type": cell_type}
    if position is None or position >= len(cells_raw):
        cells_raw.append(new)
    else:
        cells_raw.insert(max(0, position), new)
    return fabric_notebook_replace(item_id, cells_raw, workspace_id=workspace_id)


@mcp.tool()
def fabric_notebook_update_cell(
    item_id: str,
    cell_index: int,
    new_source: str,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """Modifica o conteúdo de uma célula identificada por índice."""
    current = fabric_notebook_get_cells(item_id, workspace_id=workspace_id)
    if "error" in current:
        return current
    cells_raw = current["cells"]
    if cell_index < 0 or cell_index >= len(cells_raw):
        return {"error": f"cell_index {cell_index} fora do range (0..{len(cells_raw) - 1})"}
    cells_raw[cell_index]["source"] = new_source
    return fabric_notebook_replace(item_id, cells_raw, workspace_id=workspace_id)


@mcp.tool()
def fabric_notebook_delete_cell(
    item_id: str,
    cell_index: int,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """Remove uma célula pelo índice."""
    current = fabric_notebook_get_cells(item_id, workspace_id=workspace_id)
    if "error" in current:
        return current
    cells_raw = current["cells"]
    if cell_index < 0 or cell_index >= len(cells_raw):
        return {"error": f"cell_index {cell_index} fora do range"}
    cells_raw.pop(cell_index)
    return fabric_notebook_replace(item_id, cells_raw, workspace_id=workspace_id)


@mcp.tool()
def fabric_notebook_delete(
    item_id: str,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """Apaga o notebook do workspace. Operação irreversível."""
    if not REQUESTS_AVAILABLE:
        return {"error": "requests não instalado"}
    ws = _resolve_workspace_id(workspace_id)
    resp = requests.delete(
        f"{_BASE_URL}/workspaces/{ws}/items/{item_id}",
        headers=_headers(),
        timeout=30,
    )
    if resp.status_code in (200, 204):
        return {"item_id": item_id, "status": "deleted"}
    return {"error": f"HTTP {resp.status_code}", "detail": resp.text[:500]}


@mcp.tool()
def fabric_notebook_run(
    item_id: str,
    parameters: dict[str, Any] | None = None,
    wait: bool = True,
    timeout_s: int = 600,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """
    Executa um notebook on-demand via REST. Endpoint:
      POST /v1/workspaces/{ws}/items/{itemId}/jobs/instances?jobType=RunNotebook

    Args:
        item_id:    ID do notebook a executar.
        parameters: Dict de parâmetros opcionais. Formato:
                    {"param_name": {"value": ..., "type": "string|int|bool|float"}}
        wait:       True = polling até job concluir (ou timeout). False = retorna imediato.
        timeout_s:  Limite do polling (default 10 min).
        workspace_id: Override.

    Returns:
        Sucesso (wait=True):
          {"status": "Completed", "item_id", "job_instance_id", "duration_s", ...}
        Sucesso (wait=False):
          {"status": "Started", "item_id", "job_instance_url"}
        Erro:
          {"error", "detail"}
    """
    if not REQUESTS_AVAILABLE:
        return {"error": "requests não instalado"}
    ws = _resolve_workspace_id(workspace_id)
    url = f"{_BASE_URL}/workspaces/{ws}/items/{item_id}/jobs/instances?jobType=RunNotebook"
    body: dict[str, Any] = {}
    if parameters:
        body["executionData"] = {"parameters": parameters}

    resp = requests.post(url, headers=_headers(), json=body, timeout=30)
    if resp.status_code not in (200, 202):
        return {"error": f"HTTP {resp.status_code}", "detail": resp.text[:500]}

    job_url = resp.headers.get("Location") or resp.headers.get("Operation-Location")
    if not job_url:
        # Algumas variantes retornam body
        return {"status": "Started", "item_id": item_id, "raw": resp.json() if resp.text else {}}

    if not wait:
        return {"status": "Started", "item_id": item_id, "job_instance_url": job_url}

    # Polling
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        job_resp = requests.get(job_url, headers=_headers(), timeout=30)
        if job_resp.status_code != 200:
            return {
                "error": f"polling HTTP {job_resp.status_code}",
                "detail": job_resp.text[:500],
                "item_id": item_id,
            }
        data = job_resp.json()
        status = data.get("status", "")
        if status == "Completed":
            return {
                "status": "Completed",
                "item_id": item_id,
                "job_instance_id": data.get("id"),
                "duration_s": time.monotonic() - start,
                "start_time": data.get("startTimeUtc"),
                "end_time": data.get("endTimeUtc"),
            }
        if status in ("Failed", "Cancelled", "Deduped"):
            return {
                "status": status,
                "error": data.get("failureReason", {}).get("message", "sem detalhes"),
                "item_id": item_id,
                "job_instance_id": data.get("id"),
                "raw": data,
            }
        # Retry-After ou default 10s
        retry_after = int(job_resp.headers.get("Retry-After", 10))
        time.sleep(retry_after)

    return {
        "status": "Timeout",
        "error": f"notebook run não concluiu em {timeout_s}s",
        "item_id": item_id,
        "job_instance_url": job_url,
    }


@mcp.tool()
def fabric_pipeline_run(
    item_id: str,
    parameters: dict[str, Any] | None = None,
    wait: bool = True,
    timeout_s: int = 1800,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """
    Executa um Data Pipeline on-demand via REST. Endpoint:
      POST /v1/workspaces/{ws}/items/{itemId}/jobs/instances?jobType=Pipeline

    Cobre o gap relatado em produção: 'pipeline não pode ser executado via REST'.
    Ele PODE, basta usar o tipo de job correto.

    Args/Returns: mesmo formato que fabric_notebook_run.
    """
    if not REQUESTS_AVAILABLE:
        return {"error": "requests não instalado"}
    ws = _resolve_workspace_id(workspace_id)
    url = f"{_BASE_URL}/workspaces/{ws}/items/{item_id}/jobs/instances?jobType=Pipeline"
    body: dict[str, Any] = {}
    if parameters:
        body["executionData"] = {"parameters": parameters}

    resp = requests.post(url, headers=_headers(), json=body, timeout=30)
    if resp.status_code not in (200, 202):
        return {"error": f"HTTP {resp.status_code}", "detail": resp.text[:500]}

    job_url = resp.headers.get("Location") or resp.headers.get("Operation-Location")
    if not job_url:
        return {"status": "Started", "item_id": item_id, "raw": resp.json() if resp.text else {}}
    if not wait:
        return {"status": "Started", "item_id": item_id, "job_instance_url": job_url}

    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        job_resp = requests.get(job_url, headers=_headers(), timeout=30)
        if job_resp.status_code != 200:
            return {"error": f"polling HTTP {job_resp.status_code}", "detail": job_resp.text[:500]}
        data = job_resp.json()
        status = data.get("status", "")
        if status == "Completed":
            return {
                "status": "Completed",
                "item_id": item_id,
                "job_instance_id": data.get("id"),
                "duration_s": time.monotonic() - start,
            }
        if status in ("Failed", "Cancelled"):
            return {
                "status": status,
                "error": data.get("failureReason", {}).get("message", "sem detalhes"),
                "item_id": item_id,
                "raw": data,
            }
        retry_after = int(job_resp.headers.get("Retry-After", 15))
        time.sleep(retry_after)
    return {"status": "Timeout", "item_id": item_id, "job_instance_url": job_url}


@mcp.tool()
def fabric_notebook_cleanup_test_items(
    pattern: str = r"^test_(notebook|api).*",
    workspace_id: str | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """
    Utilitário pra deletar notebooks de teste que ficaram como lixo no workspace.

    Args:
        pattern: Regex que casa displayName. Default casa "test_notebook*" e "test_api*".
        apply:   False = dry-run (só lista). True = deleta de verdade.

    Returns:
        {"matched": [...], "deleted": [...], "failed": [...], "dry_run": bool}
    """
    listing = fabric_notebook_list(workspace_id=workspace_id)
    if "error" in listing:
        return listing
    pat = re.compile(pattern)
    matched = [nb for nb in listing["notebooks"] if pat.match(nb.get("displayName", ""))]
    if not apply:
        return {"matched": matched, "dry_run": True, "deleted": [], "failed": []}

    deleted, failed = [], []
    for nb in matched:
        r = fabric_notebook_delete(nb["id"], workspace_id=workspace_id)
        if r.get("status") == "deleted":
            deleted.append(nb)
        else:
            failed.append({"notebook": nb, "error": r.get("error")})
    return {"matched": matched, "dry_run": False, "deleted": deleted, "failed": failed}


# ─── Entry point ─────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()
