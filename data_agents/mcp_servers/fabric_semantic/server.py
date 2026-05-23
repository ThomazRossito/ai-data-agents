"""
Fabric Semantic Model MCP — Introspecção profunda de Semantic Models no Microsoft Fabric.

Resolve o gap crítico do fabric_community MCP: a REST API padrão não expõe a estrutura
interna de um Semantic Model (tabelas, colunas, medidas DAX, relacionamentos, RLS).

Este servidor combina duas abordagens:

  A) REST API — getDefinition: baixa o TMDL (Tabular Model Definition Language) codificado
     em base64, faz o parse e expõe tabelas, colunas, medidas e relacionamentos.

  C) DAX INFO Functions via executeQueries: executa queries DAX usando as funções INFO.*
     que retornam metadados do modelo em runtime (sem XMLA, sem Premium obrigatório).

Ambas usam as mesmas credenciais Azure já configuradas no .env:
  AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, FABRIC_WORKSPACE_ID

Scope OAuth necessário: https://analysis.windows.net/powerbi/api/.default
(Power BI REST API — inclui datasets/executeQueries e items/getDefinition)

Pré-requisitos:
  pip install -e .  (azure-identity + requests já incluídos)

Como obter o model_id:
  Use fabric_semantic_list_models() OU
  mcp__fabric_community__list_items → filtre type="SemanticModel" → campo "id"
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
import traceback
import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("fabric_semantic_mcp")

try:
    from azure.identity import ClientSecretCredential

    AZURE_IDENTITY_AVAILABLE = True
except ImportError:
    AZURE_IDENTITY_AVAILABLE = False

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# ─── FastMCP Server ───────────────────────────────────────────────────────────

mcp = FastMCP("fabric-semantic")

# ─── Scopes OAuth ─────────────────────────────────────────────────────────────

_POWERBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
_FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"

# ─── Helpers de autenticação ─────────────────────────────────────────────────


def _get_token(scope: str) -> str:
    if not AZURE_IDENTITY_AVAILABLE:
        raise RuntimeError("azure-identity não instalado. Execute: pip install azure-identity")
    cred = ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
    )
    return cred.get_token(scope).token


def _powerbi_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_token(_POWERBI_SCOPE)}",
        "Content-Type": "application/json",
    }


def _fabric_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_token(_FABRIC_SCOPE)}",
        "Content-Type": "application/json",
    }


def _workspace_id() -> str:
    ws = os.environ.get("FABRIC_WORKSPACE_ID", "").strip()
    if not ws:
        raise RuntimeError("FABRIC_WORKSPACE_ID não configurado. Adicione ao .env.")
    return ws


def _error_response(e: Exception) -> str:
    return json.dumps(
        {"error": str(e), "type": type(e).__name__, "traceback": traceback.format_exc()},
        ensure_ascii=False,
    )


def _check_deps() -> str | None:
    if not AZURE_IDENTITY_AVAILABLE:
        return "azure-identity não instalado. Execute: pip install azure-identity"
    if not REQUESTS_AVAILABLE:
        return "requests não instalado. Execute: pip install requests"
    return None


# ─── Helpers de parse TMDL ────────────────────────────────────────────────────


def _decode_tmdl_parts(parts: list[dict]) -> dict[str, Any]:
    """Decodifica partes base64 do TMDL retornado por getDefinition."""
    decoded: dict[str, Any] = {}
    for part in parts:
        path = part.get("path", "")
        payload_b64 = part.get("payload", "")
        if not payload_b64:
            continue
        try:
            content = base64.b64decode(payload_b64).decode("utf-8", errors="replace")
            try:
                decoded[path] = json.loads(content)
            except json.JSONDecodeError:
                decoded[path] = content  # TMDL texto puro
        except Exception:
            decoded[path] = f"[erro ao decodificar: {path}]"
    return decoded


def _parse_tmdl_text_table(content: str) -> dict[str, Any]:
    """
    Parseia um arquivo TMDL texto de tabela (definition/tables/<name>.tmdl).
    Extrai nome, colunas, medidas e partições via indentação por tabs.
    """

    def tabs(line: str) -> int:
        return len(line) - len(line.lstrip("\t"))

    result: dict[str, Any] = {
        "name": "",
        "is_hidden": False,
        "description": "",
        "columns": [],
        "measures": [],
        "partitions": [],
    }
    section: str | None = None
    obj: dict | None = None
    measure_expr_buf: list[str] = []

    def _flush_measure() -> None:
        if obj is not None and measure_expr_buf:
            obj["expression"] = "\n".join(measure_expr_buf).strip()
            measure_expr_buf.clear()

    for line in content.splitlines():
        if not line.strip():
            continue
        t = tabs(line)
        s = line.strip()

        # Ignorar anotações e tags de linhagem (ruído)
        if s.startswith(
            (
                "annotation ",
                "lineageTag:",
                "sourceLineageTag:",
                "sourceProviderType:",
                "sourceColumn:",
            )
        ):
            continue

        if t == 0:
            if s.startswith("table "):
                result["name"] = s[6:].strip()

        elif t == 1:
            _flush_measure()
            if s.startswith("column "):
                section = "column"
                obj = {
                    "name": s[7:].strip(),
                    "data_type": "",
                    "is_hidden": False,
                    "description": "",
                    "format_string": "",
                    "data_category": "",
                    "summarize_by": "",
                }
                result["columns"].append(obj)
            elif s.startswith("measure "):
                section = "measure"
                rest = s[8:]
                name, _, expr = rest.partition("=")
                obj = {
                    "name": name.strip().strip("'\""),
                    "expression": expr.strip(),
                    "description": "",
                    "format_string": "",
                    "is_hidden": False,
                    "display_folder": "",
                }
                if not expr.strip():
                    measure_expr_buf.clear()  # expressão multi-linha
                result["measures"].append(obj)
            elif s.startswith("partition "):
                section = "partition"
                obj = {
                    "name": s[10:].strip(),
                    "mode": "",
                    "source_type": "",
                    "expression": "",
                    "entity_name": "",
                    "schema_name": "",
                }
                result["partitions"].append(obj)
            elif ":" in s:
                k, _, v = s.partition(":")
                k, v = k.strip(), v.strip().strip('"')
                if k == "isHidden":
                    result["is_hidden"] = v.lower() == "true"
                elif k == "description":
                    result["description"] = v

        elif t >= 2 and obj is not None:
            # Captura expressão DAX multi-linha de medida
            if section == "measure" and obj.get("expression") == "" and ":" not in s:
                measure_expr_buf.append(s)
                continue
            elif section == "measure" and measure_expr_buf and ":" not in s:
                measure_expr_buf.append(s)
                continue

            if ":" in s:
                _flush_measure()
                k, _, v = s.partition(":")
                k, v = k.strip(), v.strip().strip('"')
                if section == "column":
                    if k == "dataType":
                        obj["data_type"] = v
                    elif k == "isHidden":
                        obj["is_hidden"] = v.lower() == "true"
                    elif k == "description":
                        obj["description"] = v
                    elif k == "formatString":
                        obj["format_string"] = v
                    elif k == "dataCategory":
                        obj["data_category"] = v
                    elif k == "summarizeBy":
                        obj["summarize_by"] = v
                elif section == "measure":
                    if k == "isHidden":
                        obj["is_hidden"] = v.lower() == "true"
                    elif k == "description":
                        obj["description"] = v
                    elif k == "formatString":
                        obj["format_string"] = v
                    elif k == "displayFolder":
                        obj["display_folder"] = v
                elif section == "partition":
                    if k == "mode":
                        obj["mode"] = v
                    elif k == "type":
                        obj["source_type"] = v
                    elif k == "expression":
                        obj["expression"] = v.strip("`'")
                    elif k == "entityName":
                        obj["entity_name"] = v.strip("'")
                    elif k == "schemaName":
                        obj["schema_name"] = v.strip("'")

    _flush_measure()
    return result


def _parse_tmdl_text_relationships(content: str) -> list[dict[str, Any]]:
    """Parseia arquivo TMDL texto de relacionamentos."""

    def tabs(line: str) -> int:
        return len(line) - len(line.lstrip("\t"))

    rels: list[dict[str, Any]] = []
    cur: dict | None = None

    for line in content.splitlines():
        if not line.strip():
            continue
        t = tabs(line)
        s = line.strip()

        if t == 0 and s.startswith("relationship "):
            cur = {
                "from_table": "",
                "from_column": "",
                "to_table": "",
                "to_column": "",
                "cardinality": "many_to_one",
                "cross_filter": "singleDirection",
                "is_active": True,
            }
            rels.append(cur)
        elif t == 1 and cur is not None and ":" in s:
            k, _, v = s.partition(":")
            k, v = k.strip(), v.strip().strip("'\"")
            if k == "fromTable":
                cur["from_table"] = v
            elif k == "fromColumn":
                cur["from_column"] = v
            elif k == "toTable":
                cur["to_table"] = v
            elif k == "toColumn":
                cur["to_column"] = v
            elif k == "fromCardinality":
                cur["cardinality"] = v + "_to_" + cur["cardinality"].split("_to_", 1)[-1]
            elif k == "toCardinality":
                cur["cardinality"] = cur["cardinality"].split("_to_", 1)[0] + "_to_" + v
            elif k == "crossFilteringBehavior":
                cur["cross_filter"] = v
            elif k == "isActive":
                cur["is_active"] = v.lower() != "false"

    return rels


def _extract_model_from_tmdl(tmdl_parts: dict[str, Any]) -> dict[str, Any]:
    """
    Extrai tabelas, medidas, relacionamentos e roles do TMDL decodificado.
    Suporta:
      - TMDL texto por arquivo (Fabric REST API v1 async — formato padrão atual)
      - TMDL JSON unificado (Fabric REST API v1 sync)
      - .bim legado (Power BI Desktop)
    """
    model_data: dict[str, Any] = {
        "tables": [],
        "relationships": [],
        "roles": [],
        "expressions": [],
        "format": "unknown",
    }

    # ── Formato TMDL texto por arquivo (Fabric async, formato "TMDL") ──────────
    tmdl_text_parts = {
        p: c for p, c in tmdl_parts.items() if isinstance(c, str) and p.endswith(".tmdl")
    }
    if tmdl_text_parts:
        model_data["format"] = "tmdl_text"
        for path, content in tmdl_text_parts.items():
            if "/tables/" in path:
                model_data["tables"].append(_parse_tmdl_text_table(content))
            elif "relationship" in path.lower():
                model_data["relationships"].extend(_parse_tmdl_text_relationships(content))
            elif path.endswith("model.tmdl"):
                # Extrai nome do modelo e roles se presentes
                for line in content.splitlines():
                    s = line.strip()
                    if s.startswith("model "):
                        model_data["name"] = s[6:].strip()
        return model_data

    # ── Formato JSON (fallback) ──────────────────────────────────────────────────
    for path, content in tmdl_parts.items():
        if not isinstance(content, dict):
            continue

        # Formato TMDL unificado (Fabric REST API v1 sync)
        if "model" in content:
            model_obj = content["model"]
            model_data["format"] = "tmdl_v1"
            model_data["name"] = content.get("name", "")
            model_data["compatibility_level"] = content.get("compatibilityLevel", "")

            for tbl in model_obj.get("tables", []):
                partitions = tbl.get("partitions", [])
                table_info: dict[str, Any] = {
                    "name": tbl.get("name", ""),
                    "description": tbl.get("description", ""),
                    "is_hidden": tbl.get("isHidden", False),
                    "columns": [],
                    "measures": [],
                    "partitions": [],
                }
                for col in tbl.get("columns", []):
                    table_info["columns"].append(
                        {
                            "name": col.get("name", ""),
                            "data_type": col.get("dataType", ""),
                            "expression": col.get("expression", ""),
                            "is_hidden": col.get("isHidden", False),
                            "description": col.get("description", ""),
                            "format_string": col.get("formatString", ""),
                            "data_category": col.get("dataCategory", ""),
                            "summarize_by": col.get("summarizeBy", ""),
                        }
                    )
                for msr in tbl.get("measures", []):
                    table_info["measures"].append(
                        {
                            "name": msr.get("name", ""),
                            "expression": msr.get("expression", ""),
                            "description": msr.get("description", ""),
                            "format_string": msr.get("formatString", ""),
                            "is_hidden": msr.get("isHidden", False),
                            "display_folder": msr.get("displayFolder", ""),
                        }
                    )
                for part in partitions:
                    source = part.get("source", {})
                    table_info["partitions"].append(
                        {
                            "name": part.get("name", ""),
                            "mode": part.get("mode", ""),
                            "source_type": source.get("type", ""),
                            "expression": source.get("expression", ""),
                            "entity_name": source.get("entityName", ""),
                            "schema_name": source.get("schemaName", ""),
                        }
                    )
                model_data["tables"].append(table_info)

            for rel in model_obj.get("relationships", []):
                model_data["relationships"].append(
                    {
                        "from_table": rel.get("fromTable", ""),
                        "from_column": rel.get("fromColumn", ""),
                        "to_table": rel.get("toTable", ""),
                        "to_column": rel.get("toColumn", ""),
                        "cardinality": rel.get("fromCardinality", "many")
                        + "_to_"
                        + rel.get("toCardinality", "one"),
                        "cross_filter": rel.get("crossFilteringBehavior", "singleDirection"),
                        "is_active": rel.get("isActive", True),
                    }
                )

            for role in model_obj.get("roles", []):
                model_data["roles"].append(
                    {
                        "name": role.get("name", ""),
                        "description": role.get("description", ""),
                        "model_permission": role.get("modelPermission", ""),
                        "table_permissions": [
                            {
                                "table": tp.get("name", ""),
                                "filter_expression": tp.get("filterExpression", ""),
                            }
                            for tp in role.get("tablePermissions", [])
                        ],
                    }
                )

            for expr in model_obj.get("expressions", []):
                model_data["expressions"].append(
                    {
                        "name": expr.get("name", ""),
                        "kind": expr.get("kind", ""),
                        "expression": expr.get("expression", ""),
                        "description": expr.get("description", ""),
                    }
                )
            break

        # Formato .bim legado (Power BI Desktop)
        if "database" in content or "Model" in content:
            db = content.get("database", content)
            model_obj = db.get("model", db.get("Model", {}))
            model_data["format"] = "bim_legacy"
            for tbl in model_obj.get("tables", model_obj.get("Tables", [])):
                model_data["tables"].append(
                    {
                        "name": tbl.get("name", tbl.get("Name", "")),
                        "is_hidden": tbl.get("isHidden", False),
                        "description": tbl.get("description", ""),
                        "columns": [
                            {
                                "name": c.get("name", c.get("Name", "")),
                                "data_type": c.get("dataType", c.get("DataType", "")),
                            }
                            for c in tbl.get("columns", tbl.get("Columns", []))
                        ],
                        "measures": [
                            {
                                "name": m.get("name", m.get("Name", "")),
                                "expression": m.get("expression", m.get("Expression", "")),
                            }
                            for m in tbl.get("measures", tbl.get("Measures", []))
                        ],
                        "partitions": [],
                    }
                )
            break

    return model_data


# ─── Helpers de geração e injeção TMDL ───────────────────────────────────────


def _build_measure_tmdl_block(m: dict) -> str:
    """Gera bloco TMDL de uma medida com indentação de 1 tab.

    Formato TMDL correto para medidas:
      \\tmeasure 'Nome' = <expr_inline>          ← expressão curta inline
      \\t\\tformatString: "0.00%"                 ← propriedades em \\t\\t
      \\t\\tlineageTag: <uuid>                    ← obrigatório pelo Fabric

    Para expressão multi-linha:
      \\tmeasure 'Nome' =
      \\t\\t\\t<linha1>                            ← corpo em \\t\\t\\t (3 tabs)
      \\t\\t\\t<linha2>
      \\t\\tformatString: "0.00%"
      \\t\\tlineageTag: <uuid>
    """
    name = m.get("name", "").strip()
    expr = m.get("expression", "").strip()
    fmt = m.get("format_string", "").strip()
    desc = m.get("description", "").strip()
    folder = m.get("display_folder", "").strip()
    # lineageTag é obrigatório no TMDL do Fabric — sem ele o parser rejeita a medida
    ltag = m.get("lineage_tag") or str(uuid.uuid4())

    if "\n" in expr or len(expr) > 80:
        lines = [f"\tmeasure '{name}' ="]
        for eline in expr.splitlines():
            lines.append(f"\t\t\t{eline.strip()}")
    else:
        lines = [f"\tmeasure '{name}' = {expr}"]

    if fmt:
        lines.append(f'\t\tformatString: "{fmt}"')
    if desc:
        lines.append(f'\t\tdescription: "{desc}"')
    if folder:
        lines.append(f'\t\tdisplayFolder: "{folder}"')
    lines.append(f"\t\tlineageTag: {ltag}")

    return "\n".join(lines)


def _inject_measures_into_tmdl(
    tmdl_content: str, measures: list[dict]
) -> tuple[str, list[str], list[str]]:
    """Injeta ou atualiza medidas em um bloco TMDL de tabela.

    Para cada medida:
    - Se já existe no TMDL, substitui o bloco inteiro (update).
    - Se não existe, insere antes da primeira `partition` ou no final (insert).

    Retorna:
        (novo_tmdl, nomes_atualizados, nomes_inseridos)
    """
    updated_names: list[str] = []
    inserted_names: list[str] = []
    new_tmdl = tmdl_content

    for m in measures:
        mname = m.get("name", "").strip()
        block = _build_measure_tmdl_block(m)

        escaped = re.escape(mname)
        # Casa `measure 'Nome'`, `measure "Nome"` e `measure Nome` (sem aspas).
        # Evitar ['\"]? opcional: com zero-length match, o padrão ignora as aspas
        # e casa substrings dentro de nomes diferentes (ex: "A" dentro de "'AB'").
        existing_pattern = re.compile(
            rf"\tmeasure\s+(?:'{escaped}'|\"{escaped}\"|{escaped})\s*=(?:[^\n]|\n(?!\t(?:measure|partition|column|annotation|\w)))*",
            re.MULTILINE,
        )
        if existing_pattern.search(new_tmdl):
            new_tmdl = existing_pattern.sub(block, new_tmdl, count=1)
            updated_names.append(mname)
        else:
            partition_match = re.search(r"\n\tpartition ", new_tmdl)
            if partition_match:
                insert_pos = partition_match.start()
                new_tmdl = new_tmdl[:insert_pos] + "\n" + block + new_tmdl[insert_pos:]
            else:
                new_tmdl = new_tmdl.rstrip() + "\n" + block + "\n"
            inserted_names.append(mname)

    return new_tmdl, updated_names, inserted_names


# ─── MCP Tools ───────────────────────────────────────────────────────────────


@mcp.tool()
def fabric_semantic_diagnostics(model_id: str | None = None) -> str:
    """
    Diagnóstico de conectividade do MCP fabric_semantic.
    Verifica credenciais, scopes OAuth e conexão com as APIs.

    Args:
        model_id: ID opcional de um Semantic Model para testar a API executeQueries.
    """
    report: dict[str, Any] = {"status": "ok", "checks": []}

    def check(name: str, ok: bool, detail: str) -> None:
        report["checks"].append(
            {"check": name, "status": "ok" if ok else "error", "detail": detail}
        )
        if not ok:
            report["status"] = "error"

    check(
        "azure-identity",
        AZURE_IDENTITY_AVAILABLE,
        "ok" if AZURE_IDENTITY_AVAILABLE else "pip install azure-identity",
    )
    check("requests", REQUESTS_AVAILABLE, "ok" if REQUESTS_AVAILABLE else "pip install requests")

    for var in ["AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "FABRIC_WORKSPACE_ID"]:
        val = os.environ.get(var, "")
        check(f"ENV:{var}", bool(val), "configurado" if val else "NÃO CONFIGURADO")

    if AZURE_IDENTITY_AVAILABLE and all(
        os.environ.get(v) for v in ["AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"]
    ):
        for scope_name, scope in [("powerbi", _POWERBI_SCOPE), ("fabric", _FABRIC_SCOPE)]:
            try:
                token = _get_token(scope)
                check(f"oauth_{scope_name}", True, f"token obtido ({len(token)} chars)")
            except Exception as e:
                check(f"oauth_{scope_name}", False, str(e))

        ws = os.environ.get("FABRIC_WORKSPACE_ID", "")
        if model_id and ws and REQUESTS_AVAILABLE:
            try:
                resp = requests.post(
                    f"https://api.powerbi.com/v1.0/myorg/groups/{ws}/datasets/{model_id}/executeQueries",
                    headers=_powerbi_headers(),
                    json={
                        "queries": [{"query": "EVALUATE {1}"}],
                        "serializerSettings": {"includeNulls": True},
                    },
                    timeout=15,
                )
                check("api_executeQueries", resp.status_code == 200, f"HTTP {resp.status_code}")
            except Exception as e:
                check("api_executeQueries", False, str(e))

    return json.dumps(report, ensure_ascii=False, indent=2)


@mcp.tool()
def fabric_semantic_list_models(workspace_id: str | None = None) -> str:
    """
    Lista todos os Semantic Models de um workspace via Power BI REST API.

    Retorna metadados adicionais vs mcp__fabric_community__list_items:
    targetStorageMode (DirectLake vs Import), isRefreshable, configuredBy.

    Args:
        workspace_id: ID do workspace. Se None, usa FABRIC_WORKSPACE_ID do .env.
    """
    dep_err = _check_deps()
    if dep_err:
        return json.dumps({"error": dep_err}, ensure_ascii=False)

    ws = workspace_id or _workspace_id()

    try:
        resp = requests.get(
            f"https://api.powerbi.com/v1.0/myorg/groups/{ws}/datasets",
            headers=_powerbi_headers(),
            timeout=30,
        )
        if resp.status_code != 200:
            return json.dumps(
                {"error": f"HTTP {resp.status_code}", "detail": resp.text[:500]}, ensure_ascii=False
            )

        models = resp.json().get("value", [])
        return json.dumps(
            {
                "workspace_id": ws,
                "model_count": len(models),
                "models": [
                    {
                        "id": m.get("id", ""),
                        "name": m.get("name", ""),
                        "target_storage_mode": m.get("targetStorageMode", ""),
                        "is_refreshable": m.get("isRefreshable", False),
                        "configured_by": m.get("configuredBy", ""),
                        "created_date": m.get("createdDate", ""),
                        "description": m.get("description", ""),
                    }
                    for m in models
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return _error_response(e)


@mcp.tool()
def fabric_semantic_get_definition(model_id: str, workspace_id: str | None = None) -> str:
    """
    Baixa e parseia a definição completa de um Semantic Model (TMDL).

    Retorna tabelas, colunas, medidas DAX, relacionamentos, roles (RLS) e
    parâmetros M/Direct Lake. Use como ponto de entrada para análise profunda.

    Tenta o endpoint Fabric REST API v1 primeiro; faz fallback para Power BI REST API.

    Args:
        model_id: ID do Semantic Model (use fabric_semantic_list_models para obtê-lo).
        workspace_id: ID do workspace. Se None, usa FABRIC_WORKSPACE_ID do .env.
    """
    dep_err = _check_deps()
    if dep_err:
        return json.dumps({"error": dep_err}, ensure_ascii=False)

    ws = workspace_id or _workspace_id()

    def _parse_and_return(resp: "requests.Response", source: str) -> str:
        data = resp.json()
        # Fabric LRO async: {"status": "Succeeded", "result": {"definition": {"parts": [...]}}}
        # Fabric sync:      {"definition": {"parts": [...]}}
        definition = data.get("definition") or data.get("result", {}).get("definition") or {}
        parts = definition.get("parts", [])
        tmdl_parts = _decode_tmdl_parts(parts)
        model_structure = _extract_model_from_tmdl(tmdl_parts)
        return json.dumps(
            {
                "source": source,
                "model_id": model_id,
                "workspace_id": ws,
                "tmdl_files": list(tmdl_parts.keys()),
                "model": model_structure,
            },
            ensure_ascii=False,
            indent=2,
        )

    def _poll_fabric_operation(location: str, max_wait: int = 60) -> "requests.Response | None":
        """
        Faz polling de uma operação assíncrona da Fabric API.
        Retorna a resposta do endpoint /result após Succeeded, ou None em timeout.
        Padrão Fabric LRO:
          1. GET location → {status: "Succeeded"} (sem dados)
          2. GET location/result → definição completa
        """
        deadline = time.time() + max_wait
        delay = 2
        while time.time() < deadline:
            time.sleep(delay)
            status_resp = requests.get(location, headers=_fabric_headers(), timeout=30)
            if status_resp.status_code not in (200, 202, 429):
                return status_resp  # erro inesperado
            if status_resp.status_code in (202, 429):
                delay = min(delay * 2, 10)
                continue
            # 200 — verificar se a operação completou
            try:
                status_data = status_resp.json()
            except Exception:
                return status_resp
            op_status = status_data.get("status", "")
            if op_status == "Succeeded":
                # Busca o resultado no endpoint /result
                result_resp = requests.get(
                    location.rstrip("/") + "/result",
                    headers=_fabric_headers(),
                    timeout=30,
                )
                return result_resp
            if op_status in ("Failed", "Cancelled"):
                return status_resp
            delay = min(delay * 2, 10)
        return None

    try:
        # Tenta Fabric REST API v1 (melhor para Direct Lake)
        resp = requests.post(
            f"https://api.fabric.microsoft.com/v1/workspaces/{ws}/semanticModels/{model_id}/getDefinition",
            headers=_fabric_headers(),
            timeout=30,
        )
        if resp.status_code == 200:
            return _parse_and_return(resp, "fabric_rest_v1")

        # 202 = operação assíncrona — faz polling via Location header
        if resp.status_code == 202:
            location = resp.headers.get("Location") or resp.headers.get("Operation-Location")
            if location:
                polled = _poll_fabric_operation(location)
                if polled is not None and polled.status_code == 200:
                    return _parse_and_return(polled, "fabric_rest_v1_async")
                fabric_err = f"polling timeout ou HTTP {polled.status_code if polled else 'N/A'}: {polled.text[:300] if polled else ''}"
            else:
                fabric_err = "202 sem Location header"
        else:
            fabric_err = f"HTTP {resp.status_code}: {resp.text[:400]}"

        # Fallback Power BI REST API
        resp2 = requests.post(
            f"https://api.powerbi.com/v1.0/myorg/groups/{ws}/datasets/{model_id}/getDefinition",
            headers=_powerbi_headers(),
            timeout=30,
        )
        if resp2.status_code == 200:
            return _parse_and_return(resp2, "powerbi_rest")

        return json.dumps(
            {
                "error": f"Fabric API: {fabric_err} | Power BI API: HTTP {resp2.status_code}",
                "powerbi_detail": resp2.text[:400],
                "hint": (
                    "Verifique se o Service Principal tem 'Dataset.ReadWrite.All' no Power BI Admin Portal "
                    "e é membro/contribuidor do workspace."
                ),
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return _error_response(e)


@mcp.tool()
def fabric_semantic_list_tables(model_id: str, workspace_id: str | None = None) -> str:
    """
    Lista todas as tabelas de um Semantic Model com colunas e modo de armazenamento.

    Mostra exatamente o que está no modelo: tabelas calculadas, tabelas de datas,
    modo Direct Lake (entityName = tabela Delta no Lakehouse).

    Args:
        model_id: ID do Semantic Model.
        workspace_id: ID do workspace. Se None, usa FABRIC_WORKSPACE_ID do .env.
    """
    dep_err = _check_deps()
    if dep_err:
        return json.dumps({"error": dep_err}, ensure_ascii=False)

    raw = fabric_semantic_get_definition(model_id, workspace_id)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if "error" in data:
        return raw

    tables = data.get("model", {}).get("tables", [])
    summary = []
    for tbl in tables:
        partitions = tbl.get("partitions", [])
        first_part = partitions[0] if partitions else {}
        summary.append(
            {
                "name": tbl["name"],
                "is_hidden": tbl.get("is_hidden", False),
                "description": tbl.get("description", ""),
                "storage_mode": first_part.get("mode", "unknown"),
                "source_type": first_part.get("source_type", ""),
                "direct_lake_entity": first_part.get("entity_name", ""),
                "column_count": len(tbl.get("columns", [])),
                "measure_count": len(tbl.get("measures", [])),
                "columns": [
                    {
                        "name": c["name"],
                        "data_type": c["data_type"],
                        "is_hidden": c.get("is_hidden", False),
                        "data_category": c.get("data_category", ""),
                    }
                    for c in tbl.get("columns", [])
                ],
            }
        )

    return json.dumps(
        {"model_id": model_id, "table_count": len(summary), "tables": summary},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def fabric_semantic_list_measures(
    model_id: str,
    workspace_id: str | None = None,
    table_filter: str | None = None,
) -> str:
    """
    Lista todas as medidas DAX de um Semantic Model com fórmulas completas.

    Principal tool para auditar a lógica de negócio do modelo: fórmulas DAX,
    formatos de exibição, pastas e visibilidade.

    Args:
        model_id: ID do Semantic Model.
        workspace_id: ID do workspace. Se None, usa FABRIC_WORKSPACE_ID do .env.
        table_filter: Filtra medidas de uma tabela específica. Ex: "fato_vendas".
    """
    dep_err = _check_deps()
    if dep_err:
        return json.dumps({"error": dep_err}, ensure_ascii=False)

    raw = fabric_semantic_get_definition(model_id, workspace_id)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if "error" in data:
        return raw

    tables = data.get("model", {}).get("tables", [])
    result: list[dict] = []
    total = 0

    for tbl in tables:
        if table_filter and tbl["name"] != table_filter:
            continue
        measures = tbl.get("measures", [])
        if not measures:
            continue
        total += len(measures)
        result.append({"table": tbl["name"], "measure_count": len(measures), "measures": measures})

    return json.dumps(
        {
            "model_id": model_id,
            "total_measures": total,
            "table_filter": table_filter,
            "tables_with_measures": len(result),
            "measures_by_table": result,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def fabric_semantic_list_relationships(model_id: str, workspace_id: str | None = None) -> str:
    """
    Lista todos os relacionamentos de um Semantic Model.

    Valida o Star Schema: cardinalidade, direção de cross-filter,
    relacionamentos ativos vs inativos (role-playing dimensions).

    Args:
        model_id: ID do Semantic Model.
        workspace_id: ID do workspace. Se None, usa FABRIC_WORKSPACE_ID do .env.
    """
    dep_err = _check_deps()
    if dep_err:
        return json.dumps({"error": dep_err}, ensure_ascii=False)

    raw = fabric_semantic_get_definition(model_id, workspace_id)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if "error" in data:
        return raw

    relationships = data.get("model", {}).get("relationships", [])
    return json.dumps(
        {
            "model_id": model_id,
            "relationship_count": len(relationships),
            "relationships": relationships,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def fabric_semantic_execute_dax(
    model_id: str,
    dax_query: str,
    workspace_id: str | None = None,
    max_rows: int = 100,
) -> str:
    """
    Executa uma query DAX em um Semantic Model.

    Tenta a Fabric REST API v1 primeiro (usa token Fabric, sem restrição Power BI).
    Faz fallback para Power BI REST API se necessário.

    Use para inspecionar metadados em runtime (sem XMLA, sem Premium obrigatório):
      EVALUATE INFO.TABLES()          — tabelas do modelo
      EVALUATE INFO.COLUMNS()         — colunas com tipos e propriedades
      EVALUATE INFO.MEASURES()        — medidas com fórmulas DAX
      EVALUATE INFO.RELATIONSHIPS()   — relacionamentos
      EVALUATE INFO.ROLES()           — roles e permissões RLS
      EVALUATE SUMMARIZECOLUMNS(...)  — dados reais para validação

    Args:
        model_id: ID do Semantic Model.
        dax_query: Query DAX começando com EVALUATE.
        workspace_id: ID do workspace. Se None, usa FABRIC_WORKSPACE_ID do .env.
        max_rows: Máximo de linhas (padrão: 100, limite: 1000).
    """
    dep_err = _check_deps()
    if dep_err:
        return json.dumps({"error": dep_err}, ensure_ascii=False)

    ws = workspace_id or _workspace_id()
    max_rows = min(max(1, max_rows), 1000)

    if not dax_query.strip().upper().startswith("EVALUATE"):
        return json.dumps(
            {
                "error": "A query DAX deve começar com EVALUATE.",
                "examples": [
                    "EVALUATE INFO.TABLES()",
                    "EVALUATE INFO.MEASURES()",
                    "EVALUATE INFO.COLUMNS()",
                    "EVALUATE INFO.RELATIONSHIPS()",
                ],
            },
            ensure_ascii=False,
        )

    payload = {"queries": [{"query": dax_query}], "serializerSettings": {"includeNulls": True}}

    def _parse_execute_response(resp: "requests.Response") -> str | None:
        """Parseia resposta de executeQueries. Retorna JSON string ou None se vazio."""
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return json.dumps({"rows": [], "row_count": 0}, ensure_ascii=False)
        tables = results[0].get("tables", [])
        if not tables:
            return json.dumps({"rows": [], "row_count": 0}, ensure_ascii=False)
        rows = tables[0].get("rows", [])
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        return json.dumps(
            {
                "model_id": model_id,
                "dax_query": dax_query,
                "columns": list(rows[0].keys()) if rows else [],
                "rows": rows,
                "row_count": len(rows),
                "truncated": truncated,
            },
            ensure_ascii=False,
            indent=2,
        )

    try:
        # Tenta Fabric REST API v1 (usa token Fabric — sem restrição Power BI executeQueries)
        fabric_resp = requests.post(
            f"https://api.fabric.microsoft.com/v1/workspaces/{ws}/semanticModels/{model_id}/executeQueries",
            headers=_fabric_headers(),
            json=payload,
            timeout=60,
        )
        if fabric_resp.status_code == 200:
            parsed = _parse_execute_response(fabric_resp)
            if parsed:
                return parsed

        # Fallback Power BI REST API
        resp = requests.post(
            f"https://api.powerbi.com/v1.0/myorg/groups/{ws}/datasets/{model_id}/executeQueries",
            headers=_powerbi_headers(),
            json=payload,
            timeout=60,
        )

        if resp.status_code != 200:
            return json.dumps(
                {
                    "error": f"Fabric API: HTTP {fabric_resp.status_code} | Power BI API: HTTP {resp.status_code}",
                    "fabric_detail": fabric_resp.text[:400],
                    "powerbi_detail": resp.text[:400],
                    "hint": (
                        "O executeQueries via Power BI API requer 'Allow service principals to use Power BI APIs' "
                        "no Power BI Admin Portal. A Fabric API requer role ≥ Member no workspace."
                    ),
                },
                ensure_ascii=False,
            )

        return _parse_execute_response(resp) or json.dumps(
            {"rows": [], "row_count": 0}, ensure_ascii=False
        )
    except Exception as e:
        return _error_response(e)


@mcp.tool()
def fabric_semantic_get_refresh_history(
    model_id: str, workspace_id: str | None = None, top: int = 10
) -> str:
    """
    Retorna o histórico de refreshes de um Semantic Model.

    Útil para diagnosticar falhas, verificar frequência de atualização e monitorar SLA.

    Args:
        model_id: ID do Semantic Model.
        workspace_id: ID do workspace. Se None, usa FABRIC_WORKSPACE_ID do .env.
        top: Número de refreshes a retornar (padrão: 10, máximo: 60).
    """
    dep_err = _check_deps()
    if dep_err:
        return json.dumps({"error": dep_err}, ensure_ascii=False)

    ws = workspace_id or _workspace_id()
    top = min(max(1, top), 60)

    try:
        resp = requests.get(
            f"https://api.powerbi.com/v1.0/myorg/groups/{ws}/datasets/{model_id}/refreshes?$top={top}",
            headers=_powerbi_headers(),
            timeout=30,
        )

        if resp.status_code != 200:
            return json.dumps(
                {"error": f"HTTP {resp.status_code}", "detail": resp.text[:500]}, ensure_ascii=False
            )

        refreshes = resp.json().get("value", [])
        summary = [
            {
                "request_id": r.get("requestId", ""),
                "refresh_type": r.get("refreshType", ""),
                "start_time": r.get("startTime", ""),
                "end_time": r.get("endTime", ""),
                "status": r.get("status", ""),
                "error": (r.get("serviceExceptionJson") or {}).get("errorCode", ""),
                "error_description": (r.get("serviceExceptionJson") or {}).get(
                    "errorDescription", ""
                ),
            }
            for r in refreshes
        ]

        return json.dumps(
            {
                "model_id": model_id,
                "workspace_id": ws,
                "total_returned": len(summary),
                "failed_count": sum(1 for r in summary if r["status"] == "Failed"),
                "last_status": summary[0]["status"] if summary else "unknown",
                "last_refresh": summary[0]["end_time"] if summary else None,
                "refreshes": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return _error_response(e)


@mcp.tool()
def fabric_semantic_update_definition(
    model_id: str,
    table_name: str,
    measures: list[dict],
    workspace_id: str | None = None,
) -> str:
    """
    Adiciona ou atualiza medidas DAX em um Semantic Model do Fabric.

    Faz get da definição atual (TMDL), injeta as medidas novas/atualizadas no
    arquivo TMDL da tabela alvo e publica via updateDefinition (Fabric REST API v1).

    Args:
        model_id: ID do Semantic Model.
        table_name: Nome da tabela onde as medidas serão criadas. Ex: "vw_monitoramento_powerbi".
        measures: Lista de medidas a criar/atualizar. Cada item deve ter:
                  - name (str): nome da medida
                  - expression (str): fórmula DAX
                  - format_string (str, opcional): ex: "0.00%", "#,0", "0"
                  - description (str, opcional)
                  - display_folder (str, opcional)
        workspace_id: ID do workspace. Se None, usa FABRIC_WORKSPACE_ID do .env.

    Exemplo:
        fabric_semantic_update_definition(
            model_id="89e2a130-...",
            table_name="vw_monitoramento_powerbi",
            measures=[
                {"name": "Taxa de Sucesso", "expression": "DIVIDE(COUNTROWS(FILTER(...)), COUNTROWS(...))", "format_string": "0.00%"},
                {"name": "Total Falhas", "expression": "COUNTROWS(FILTER(...))", "format_string": "#,0"},
            ]
        )
    """
    dep_err = _check_deps()
    if dep_err:
        return json.dumps({"error": dep_err}, ensure_ascii=False)

    ws = workspace_id or _workspace_id()

    # ── Passo 1: Baixar definição atual via getDefinition ─────────────────────
    try:
        resp_get = requests.post(
            f"https://api.fabric.microsoft.com/v1/workspaces/{ws}/semanticModels/{model_id}/getDefinition",
            headers=_fabric_headers(),
            timeout=30,
        )

        tmdl_parts_raw: list[dict] = []

        def _get_parts_from_response(r: "requests.Response") -> list[dict]:
            data = r.json()
            definition = data.get("definition") or data.get("result", {}).get("definition") or {}
            return definition.get("parts", [])

        def _poll_get(location: str, max_wait: int = 60) -> "requests.Response | None":
            deadline = time.time() + max_wait
            delay = 2
            while time.time() < deadline:
                time.sleep(delay)
                sr = requests.get(location, headers=_fabric_headers(), timeout=30)
                if sr.status_code not in (200, 202, 429):
                    return sr
                if sr.status_code in (202, 429):
                    delay = min(delay * 2, 10)
                    continue
                try:
                    sd = sr.json()
                except Exception:
                    return sr
                if sd.get("status") == "Succeeded":
                    rr = requests.get(
                        location.rstrip("/") + "/result",
                        headers=_fabric_headers(),
                        timeout=30,
                    )
                    return rr
                if sd.get("status") in ("Failed", "Cancelled"):
                    return sr
                delay = min(delay * 2, 10)
            return None

        if resp_get.status_code == 200:
            tmdl_parts_raw = _get_parts_from_response(resp_get)
        elif resp_get.status_code == 202:
            location = resp_get.headers.get("Location") or resp_get.headers.get(
                "Operation-Location"
            )
            if not location:
                return json.dumps(
                    {"error": "getDefinition retornou 202 sem Location header"}, ensure_ascii=False
                )
            polled = _poll_get(location)
            if polled is None or polled.status_code != 200:
                return json.dumps(
                    {
                        "error": f"polling getDefinition falhou: HTTP {polled.status_code if polled else 'timeout'}",
                        "detail": polled.text[:400] if polled else "",
                    },
                    ensure_ascii=False,
                )
            tmdl_parts_raw = _get_parts_from_response(polled)
        else:
            return json.dumps(
                {
                    "error": f"getDefinition HTTP {resp_get.status_code}",
                    "detail": resp_get.text[:400],
                },
                ensure_ascii=False,
            )
    except Exception as e:
        return _error_response(e)

    if not tmdl_parts_raw:
        return json.dumps({"error": "getDefinition não retornou parts TMDL"}, ensure_ascii=False)

    # ── Passo 2: Decodificar, modificar e re-encodar as parts ─────────────────
    try:
        # Encontrar o arquivo TMDL da tabela alvo
        table_path_key: str | None = None
        table_content: str | None = None

        for part in tmdl_parts_raw:
            path = part.get("path", "")
            payload_b64 = part.get("payload", "")
            if not payload_b64:
                continue
            decoded = base64.b64decode(payload_b64).decode("utf-8", errors="replace")
            # Verifica se este arquivo é da tabela alvo (nome no path ou no conteúdo)
            if f"/tables/{table_name}.tmdl" in path or (
                path.endswith(".tmdl") and "/tables/" in path and f"table {table_name}" in decoded
            ):
                table_path_key = path
                table_content = decoded
                break

        if table_path_key is None or table_content is None:
            # Tenta match mais flexível (case-insensitive, espaços → underscore)
            norm_target = table_name.lower().replace(" ", "_")
            for part in tmdl_parts_raw:
                path = part.get("path", "")
                payload_b64 = part.get("payload", "")
                if not payload_b64:
                    continue
                decoded = base64.b64decode(payload_b64).decode("utf-8", errors="replace")
                if "/tables/" in path and path.endswith(".tmdl"):
                    path_norm = path.lower().replace(" ", "_")
                    if norm_target in path_norm or norm_target in decoded.lower():
                        table_path_key = path
                        table_content = decoded
                        break

        if table_path_key is None or table_content is None:
            available = [
                p.get("path", "") for p in tmdl_parts_raw if "/tables/" in p.get("path", "")
            ]
            return json.dumps(
                {
                    "error": f"Tabela '{table_name}' não encontrada no TMDL.",
                    "available_table_paths": available,
                },
                ensure_ascii=False,
            )

        # Injetar medidas novas/atualizadas no TMDL da tabela
        new_tmdl, updated_names, inserted_names = _inject_measures_into_tmdl(
            table_content, measures
        )

        # Re-encodar o conteúdo modificado em base64
        new_payload_b64 = base64.b64encode(new_tmdl.encode("utf-8")).decode("ascii")

        # Reconstruir lista de parts com o arquivo da tabela atualizado
        updated_parts = []
        for part in tmdl_parts_raw:
            if part.get("path") == table_path_key:
                updated_parts.append(
                    {
                        "path": table_path_key,
                        "payload": new_payload_b64,
                        "payloadType": part.get("payloadType", "InlineBase64"),
                    }
                )
            else:
                updated_parts.append(part)

    except Exception as e:
        return _error_response(e)

    # ── Passo 2.5: Validar sintaxe DAX de cada medida antes de publicar ─────────
    # Usa executeQueries com WITH DEFINE MEASURE + EVALUATE {1} — se a expressão
    # tiver erro de sintaxe a API retorna 400/200+error antes de qualquer escrita.
    try:
        syntax_errors: list[dict] = []
        for m in measures:
            mname = m.get("name", "").strip()
            expr = m.get("expression", "").strip()
            if not expr:
                syntax_errors.append({"measure": mname, "error": "expressão DAX vazia"})
                continue

            # Sanitiza nome da tabela para uso na query DAX
            safe_table = table_name.replace("'", "''")
            safe_name = mname.replace("'", "''")
            validation_query = (
                f"DEFINE\n  MEASURE '{safe_table}'[{safe_name}] = {expr}\nEVALUATE {{1}}"
            )
            val_payload = {
                "queries": [{"query": validation_query}],
                "serializerSettings": {"includeNulls": True},
            }
            # Tenta Fabric API primeiro, depois Power BI
            val_resp = requests.post(
                f"https://api.fabric.microsoft.com/v1/workspaces/{ws}/semanticModels/{model_id}/executeQueries",
                headers=_fabric_headers(),
                json=val_payload,
                timeout=30,
            )
            if val_resp.status_code != 200:
                val_resp = requests.post(
                    f"https://api.powerbi.com/v1.0/myorg/groups/{ws}/datasets/{model_id}/executeQueries",
                    headers=_powerbi_headers(),
                    json=val_payload,
                    timeout=30,
                )
            if val_resp.status_code == 200:
                val_data = val_resp.json()
                # A API retorna 200 mesmo com erro DAX — o erro fica em results[0].tables ou error field
                val_results = val_data.get("results", [{}])
                val_error = val_results[0].get("error") if val_results else None
                if val_error:
                    syntax_errors.append(
                        {
                            "measure": mname,
                            "error": val_error.get("message", str(val_error)),
                            "code": val_error.get("code", ""),
                        }
                    )
            elif val_resp.status_code in (400, 422):
                # Erro HTTP direto = sintaxe DAX inválida com certeza
                try:
                    err_detail = val_resp.json()
                except Exception:
                    err_detail = val_resp.text[:300]
                syntax_errors.append({"measure": mname, "error": str(err_detail)})
            # 403/401 = sem permissão para executeQueries — pula validação silenciosamente

        if syntax_errors:
            return json.dumps(
                {
                    "status": "validation_error",
                    "error": "Erros de sintaxe DAX encontrados. Nenhuma alteração foi publicada.",
                    "syntax_errors": syntax_errors,
                    "hint": "Corrija as expressões DAX acima e tente novamente.",
                },
                ensure_ascii=False,
                indent=2,
            )
    except Exception as e:
        # Falha na validação não bloqueia a publicação — loga e segue
        logger.warning("Validação DAX falhou (não-bloqueante): %s", e)

    # ── Passo 3: Publicar via updateDefinition ────────────────────────────────
    try:
        update_payload = {"definition": {"parts": updated_parts}}

        resp_upd = requests.post(
            f"https://api.fabric.microsoft.com/v1/workspaces/{ws}/semanticModels/{model_id}/updateDefinition",
            headers=_fabric_headers(),
            json=update_payload,
            timeout=60,
        )

        # 200 = sucesso imediato
        if resp_upd.status_code == 200:
            return json.dumps(
                {
                    "status": "success",
                    "model_id": model_id,
                    "table": table_name,
                    "measures_inserted": inserted_names,
                    "measures_updated": updated_names,
                    "total_processed": len(measures),
                    "source": "fabric_rest_v1_sync",
                },
                ensure_ascii=False,
                indent=2,
            )

        # 202 = operação assíncrona
        if resp_upd.status_code == 202:
            location = resp_upd.headers.get("Location") or resp_upd.headers.get(
                "Operation-Location"
            )
            if location:
                # Polling do status
                deadline = time.time() + 60
                delay = 2
                while time.time() < deadline:
                    time.sleep(delay)
                    sr = requests.get(location, headers=_fabric_headers(), timeout=30)
                    if sr.status_code == 200:
                        try:
                            sd = sr.json()
                            op_status = sd.get("status", "")
                            if op_status == "Succeeded":
                                return json.dumps(
                                    {
                                        "status": "success",
                                        "model_id": model_id,
                                        "table": table_name,
                                        "measures_inserted": inserted_names,
                                        "measures_updated": updated_names,
                                        "total_processed": len(measures),
                                        "source": "fabric_rest_v1_async",
                                    },
                                    ensure_ascii=False,
                                    indent=2,
                                )
                            if op_status in ("Failed", "Cancelled"):
                                return json.dumps(
                                    {"error": f"updateDefinition {op_status}", "detail": sd},
                                    ensure_ascii=False,
                                )
                        except Exception:
                            pass
                    delay = min(delay * 2, 10)
                return json.dumps(
                    {"error": "updateDefinition polling timeout (60s)"}, ensure_ascii=False
                )

        return json.dumps(
            {
                "error": f"updateDefinition HTTP {resp_upd.status_code}",
                "detail": resp_upd.text[:500],
                "hint": (
                    "Verifique se o Service Principal tem permissão 'Dataset.ReadWrite.All' "
                    "e role >= Contributor no workspace."
                ),
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return _error_response(e)


# ─── Entry Point ─────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    mcp.run()


if __name__ == "__main__":
    main()
