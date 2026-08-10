"""
Parse a T-shirt sizing spreadsheet (Seatrium-style) into a structured cost scenario.

Recognises the "# / Assumption / Value used in estimate / Basis / Notes" column
layout (and common aliases) and extracts the fields the Databricks + Azure cost
engines need to build a greenfield estimate.

Design principle (matches project constitution S3/S7): NEVER invent values. When a
keyword is not found, the field is left absent and surfaced under
``scenario["_unmapped_rows"]`` so the agent can ask the user to map it.

Usage
-----
    from skills.finops.read_sizing_spreadsheet.parse_sizing import (
        parse_sizing, sizing_to_scenario,
    )
    parsed = parse_sizing("/path/Seatrium sizing.xlsx")
    scenario = sizing_to_scenario(parsed)

The two steps are separate on purpose: ``parse_sizing`` is a pure extraction
(auditable — keeps every raw row), ``sizing_to_scenario`` is the interpretation
layer (region normalisation, numeric coercion, workload inference).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import openpyxl


# ── Keyword mappings ─────────────────────────────────────────────────────────
# canonical field name → list of regex patterns matched against the "assumption"
# column. First match wins. Patterns are intentionally broad but anchored to
# domain vocabulary so unrelated rows do not match.
KEYWORD_MAP: dict[str, list[re.Pattern]] = {
    "num_envs": [re.compile(r"\benvironments?\b", re.I)],
    "cloud_scope": [re.compile(r"cloud scope|\bclouds?\b", re.I)],
    "cloud_region": [
        re.compile(r"\bregion\b|\bresidency\b|singapore|singapura|southeast", re.I)
    ],
    "storage_gb": [
        re.compile(r"data at rest|storage.*sized|total data|estimated.*storage", re.I)
    ],
    "annual_growth_rate": [re.compile(r"annual.*growth|growth.*(year|ano)", re.I)],
    "batch_etl_volume": [
        re.compile(r"batch ETL|batch.*volume|GB/day|GB/dia", re.I)
    ],
    "streaming": [re.compile(r"streaming|real-time|real time|\bCDC\b", re.I)],
    "num_source_systems": [re.compile(r"source systems?|sistemas? de origem", re.I)],
    "pipeline_split": [re.compile(r"pipeline split|managed connectors?", re.I)],
    "sap_path": [re.compile(r"\bSAP\b", re.I)],
    "num_sql_users": [
        re.compile(
            r"SQL.*users?|BI.*users?|interactive users?|usu[aá]rios? interativ"
            r"|SQL\s*/\s*BI|SQL.*workload|BI workload",
            re.I,
        )
    ],
    "num_dashboards": [re.compile(r"dashboards?|pain[eé]is", re.I)],
    "sql_duty_cycle": [re.compile(r"duty cycle|peak.*non-peak|hor[aá]rio comercial", re.I)],
    "bi_tool": [re.compile(r"BI tool|Power BI|identity|SSO", re.I)],
    "num_notebook_users": [
        re.compile(r"notebook users?|DS/DE|data scientist|cientista", re.I)
    ],
    "genie_questions_per_month": [
        re.compile(r"Genie.*(volume|Q&A|question)|questions?/mo|perguntas?/m[eê]s", re.I)
    ],
    "num_genie_users": [re.compile(r"Genie.*user base|Genie.*users?", re.I)],
    "genie_query_mix": [re.compile(r"query mix|space queries|agent queries", re.I)],
    "genie_consumption": [re.compile(r"Genie consumption|DBU free|free allowance", re.I)],
    "monitoring_coverage": [
        re.compile(r"monitoring coverage|tables profiled|lakehouse monitoring", re.I)
    ],
    "ml_training": [re.compile(r"ML training|model training", re.I)],
    "model_serving": [re.compile(r"model serving|real-time model", re.I)],
    "agent_pattern": [re.compile(r"agent pattern|multi-agent|supervisor", re.I)],
    "genai_llm": [
        re.compile(r"\bLLM\b|Claude|GPT|Llama|Gemini|frontier model|foundation model", re.I)
    ],
    "genai_questions_per_month": [
        re.compile(r"GenAI.*question|question volume", re.I)
    ],
    "genai_token_profile": [re.compile(r"token profile|tokens? per question", re.I)],
    "rag": [re.compile(r"\bRAG\b|retrieval|vector", re.I)],
    "lakebase": [re.compile(r"lakebase|OLTP", re.I)],
    "dr_ha": [re.compile(r"\bDR\b|\bHA\b|RTO|RPO|disaster recovery", re.I)],
    "historical_migration": [re.compile(r"historical.*migration|migra[cç][aã]o hist", re.I)],
}


# ── Extraction (pure, auditable) ─────────────────────────────────────────────
def parse_sizing(xlsx_path: str | Path) -> dict[str, Any]:
    """Read the sizing spreadsheet and return the extracted fields + raw rows.

    Returns a dict with:
      - one key per matched canonical field (value = raw string from the sheet)
      - ``raw_rows``: every data row (ref/assumption/value/basis/notes)
      - ``_unmapped_rows``: rows whose assumption matched no keyword
      - ``_source_file`` / ``_sheet``: provenance
    """
    xlsx_path = Path(xlsx_path)
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)

    # Prefer a sheet named "Sizing" / "Assumptions"; else first sheet.
    ws = None
    for name in wb.sheetnames:
        if re.search(r"sizing|assumption", name, re.I):
            ws = wb[name]
            break
    if ws is None:
        ws = wb.active

    result: dict[str, Any] = {
        "_source_file": str(xlsx_path),
        "_sheet": ws.title,
        "raw_rows": [],
        "_unmapped_rows": [],
    }

    # Locate the header row. A real header has SEVERAL distinct column labels,
    # not just the word "assumption" buried in a prose note. Score each candidate
    # row by how many separate cells look like column headers, and require the
    # winner to contain a "value" column (the field we must have).
    header_signals = [
        re.compile(r"assumption|driver|\bitem\b|requirement", re.I),
        re.compile(r"value used|^\s*value\s*$|target|sized value", re.I),
        re.compile(r"basis|source|origin", re.I),
        re.compile(r"notes|comment", re.I),
    ]
    best_row, best_score = None, 0
    for r in range(1, min(15, ws.max_row + 1)):
        cells = [
            str(ws.cell(row=r, column=c).value or "").strip()
            for c in range(1, ws.max_column + 1)
        ]
        # Count how many DISTINCT cells match a header signal.
        score = 0
        has_value = False
        for cell in cells:
            if not cell or len(cell) > 40:  # skip empty + long prose cells
                continue
            for i, sig in enumerate(header_signals):
                if sig.search(cell):
                    score += 1
                    if i == 1:
                        has_value = True
                    break
        if has_value and score > best_score:
            best_row, best_score = r, score
    header_row = best_row
    if header_row is None or best_score < 2:
        raise ValueError(
            "Could not find a header row (expected columns like 'Assumption', "
            f"'Value used', 'Basis') in sheet '{ws.title}' of {xlsx_path.name}"
        )

    # Map columns by header text.
    col: dict[str, int] = {}
    for c in range(1, ws.max_column + 1):
        h = str(ws.cell(row=header_row, column=c).value or "").strip()
        if re.search(r"^\s*(#|ref|code|id)\s*$", h, re.I):
            col["ref"] = c
        elif re.search(r"assumption|driver|item|requirement", h, re.I):
            col["assumption"] = c
        elif re.search(r"value used|^value|target|sized", h, re.I):
            col["value"] = c
        elif re.search(r"basis|source|origin", h, re.I):
            col["basis"] = c
        elif re.search(r"notes|comment", h, re.I):
            col["notes"] = c

    if "assumption" not in col or "value" not in col:
        raise ValueError(
            f"Required columns not found (need Assumption + Value). Detected: {col}"
        )

    # Walk data rows.
    for r in range(header_row + 1, ws.max_row + 1):
        assumption = ws.cell(row=r, column=col["assumption"]).value
        value = ws.cell(row=r, column=col["value"]).value
        if not assumption:
            continue
        assumption_str = str(assumption).strip()
        value_str = "" if value is None else str(value).strip()

        row_record = {
            "ref": str(ws.cell(row=r, column=col.get("ref", 0)).value or "").strip()
            if "ref" in col
            else "",
            "assumption": assumption_str,
            "value": value_str,
            "basis": str(ws.cell(row=r, column=col.get("basis", 0)).value or "").strip()
            if "basis" in col
            else "",
            "notes": str(ws.cell(row=r, column=col.get("notes", 0)).value or "").strip()
            if "notes" in col
            else "",
        }
        result["raw_rows"].append(row_record)

        # Section headers (no value) are skipped for keyword matching.
        if not value_str:
            continue

        matched = False
        for canonical, patterns in KEYWORD_MAP.items():
            if canonical in result:  # first match wins
                continue
            if any(p.search(assumption_str) for p in patterns):
                result[canonical] = value_str
                matched = True
                break
        if not matched:
            result["_unmapped_rows"].append(row_record)

    return result


# ── Interpretation layer ─────────────────────────────────────────────────────
_REGION_MAP = {
    "singapore": "southeastasia",
    "singapura": "southeastasia",
    "southeast asia": "southeastasia",
    "brazil": "brazilsouth",
    "brasil": "brazilsouth",
    "são paulo": "brazilsouth",
    "us east": "eastus",
    "east us": "eastus",
    "west europe": "westeurope",
    "europe": "westeurope",
}


def _extract_region(text: str) -> str | None:
    t = text.lower()
    for keyword, region in _REGION_MAP.items():
        if keyword in t:
            return region
    return None


def _extract_number(text: str, multiplier_units: dict[str, int] | None = None) -> float | None:
    """Pull the first numeric token; optionally apply a unit multiplier (TB→1000)."""
    if not text:
        return None
    m = re.search(r"([\d][\d,\.]*)", str(text))
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    try:
        num = float(raw)
    except ValueError:
        return None
    if multiplier_units:
        low = str(text).lower()
        for unit, mult in multiplier_units.items():
            if unit.lower() in low:
                return num * mult
    return num


def _extract_storage_gb(text: str) -> float | None:
    """Storage-specific extraction.

    Sizing cells often carry both a band ("10-100 TB") and the explicit modelled
    figure ("50,000 GB modelled"). Prefer an explicit GB figure; fall back to an
    explicit TB figure × 1000; only then to a bare number.
    """
    if not text:
        return None
    # 1. Explicit "<number> GB" (largest, in case of ranges)
    gb_matches = re.findall(r"([\d][\d,\.]*)\s*GB", text, re.I)
    if gb_matches:
        vals = [float(x.replace(",", "")) for x in gb_matches]
        return max(vals)
    # 2. Explicit "<number> TB"
    tb_matches = re.findall(r"([\d][\d,\.]*)\s*TB", text, re.I)
    if tb_matches:
        vals = [float(x.replace(",", "")) for x in tb_matches]
        return max(vals) * 1000
    # 3. Bare number
    return _extract_number(text)


def _extract_pct(text: str, default: float | None = None) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", str(text))
    return float(m.group(1)) if m else default


def sizing_to_scenario(parsed: dict[str, Any]) -> dict[str, Any]:
    """Interpret the parsed fields into a cost-engine-ready scenario spec.

    Anything that cannot be confidently derived is left as None and reported in
    ``needs_confirmation`` so the calling agent can ask (never guess).
    """
    needs_confirmation: list[str] = []

    region = _extract_region(parsed.get("cloud_region", "")) or _extract_region(
        parsed.get("cloud_scope", "")
    )
    if region is None:
        needs_confirmation.append("cloud_region (could not map to an Azure region code)")

    num_envs = _extract_number(parsed.get("num_envs", ""))
    if num_envs is None:
        needs_confirmation.append("num_envs")

    storage_gb = _extract_storage_gb(parsed.get("storage_gb", ""))
    if storage_gb is None:
        needs_confirmation.append("storage_gb")

    growth = _extract_pct(parsed.get("annual_growth_rate", ""))

    scenario: dict[str, Any] = {
        "cloud": "azure",
        "region": region,
        "num_envs": int(num_envs) if num_envs is not None else None,
        "storage_gb": int(storage_gb) if storage_gb is not None else None,
        "annual_growth_pct": growth,
        "streaming_required": _is_present(parsed.get("streaming", "")),
        "num_source_systems": _extract_number(parsed.get("num_source_systems", "")),
        "num_sql_users": _extract_number(parsed.get("num_sql_users", "")),
        "num_dashboards": _extract_number(parsed.get("num_dashboards", "")),
        "num_notebook_users": _extract_number(parsed.get("num_notebook_users", "")),
        "genie_questions_per_month": _extract_number(
            parsed.get("genie_questions_per_month", "")
        ),
        "num_genie_users": _extract_number(parsed.get("num_genie_users", "")),
        "genai_questions_per_month": _extract_number(
            parsed.get("genai_questions_per_month", "")
        ),
        "genai_llm": parsed.get("genai_llm"),
        "workloads": _infer_workloads(parsed),
        "excluded": _infer_exclusions(parsed),
        "needs_confirmation": needs_confirmation,
        "_source_file": parsed.get("_source_file"),
        "_unmapped_count": len(parsed.get("_unmapped_rows", [])),
    }
    return scenario


def _is_present(value: str) -> bool | None:
    """Interpret a yes/no-ish cell. Returns None when ambiguous."""
    if not value:
        return None
    v = value.lower()
    if re.search(r"\bnone\b|\bno\b|nenhum|não|nao|batch only", v):
        return False
    if re.search(r"\byes\b|\bsim\b|required|necess", v):
        return True
    return None


def _infer_workloads(parsed: dict[str, Any]) -> list[dict[str, str]]:
    """Map detected drivers to the compute types the cost engine understands."""
    workloads: list[dict[str, str]] = []

    def add(code: str, compute_type: str, driver_field: str) -> None:
        if parsed.get(driver_field):
            workloads.append({"code": code, "compute_type": compute_type})

    add("ETL_BATCH", "jobs_compute", "batch_etl_volume")
    add("LFC_CONNECT", "jobs_serverless", "num_source_systems")
    add("SQL_WAREHOUSE", "sql_serverless", "num_sql_users")
    add("NOTEBOOK", "all_purpose_compute", "num_notebook_users")
    add("MONITORING", "jobs_compute", "monitoring_coverage")
    add("GENIE", "genie", "genie_questions_per_month")
    add("AI_SEARCH", "vector_search", "rag")
    add("FM_LLM", "proprietary_foundation_model_serving", "genai_questions_per_month")
    return workloads


def _infer_exclusions(parsed: dict[str, Any]) -> list[str]:
    excluded = []
    if _is_present(parsed.get("streaming", "")) is False:
        excluded.append("streaming")
    if parsed.get("ml_training") and re.search(
        r"none|não|nao", parsed["ml_training"], re.I
    ):
        excluded.append("ml_training")
    if parsed.get("model_serving") and re.search(
        r"none|não|nao", parsed["model_serving"], re.I
    ):
        excluded.append("model_serving")
    if parsed.get("lakebase") and re.search(r"not sized|não|nao", parsed["lakebase"], re.I):
        excluded.append("lakebase")
    if parsed.get("dr_ha") and re.search(r"none|não|nao", parsed["dr_ha"], re.I):
        excluded.append("dr_ha")
    if parsed.get("historical_migration") and re.search(
        r"none|não|nao|in scope", parsed["historical_migration"], re.I
    ):
        excluded.append("historical_migration")
    return excluded


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    import json
    import sys

    if len(sys.argv) < 2:
        print("usage: python parse_sizing.py <sizing.xlsx>")
        raise SystemExit(1)
    parsed = parse_sizing(sys.argv[1])
    scenario = sizing_to_scenario(parsed)
    print(json.dumps({"parsed_fields": {k: v for k, v in parsed.items()
                                        if not k.startswith("_") and k != "raw_rows"},
                      "scenario": scenario}, indent=2, ensure_ascii=False))
