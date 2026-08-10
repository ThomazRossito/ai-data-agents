#!/usr/bin/env python3
"""
WF-07 Greenfield — deterministic consolidation into a single XLSX.

Reads the two scenario JSONs produced by databricks-cost-calculator and
azure-cost-calculator (already per-environment summed) and writes one
consolidated greenfield workbook. This replaces ad-hoc consolidation by
python-expert (which was non-deterministic and could hang on an ambiguous
Read): the WF-07 step should call THIS script with fixed paths.

Usage
-----
    python3 scripts/greenfield_consolidate.py \
        --databricks output/prj_seatrium/scenario_used.json \
        --azure output/prj_seatrium/azure_infra_scenario_used.json \
        --out output/prj_seatrium/greenfield_cost_consolidated.xlsx \
        [--client Seatrium] [--region southeastasia] [--growth 20]

Contract of the input JSONs (tolerant — falls back gracefully):
  Databricks JSON: { workloads: [{code, subtotal_usd}], totals: {monthly_usd, ...} }
    (one workload code == "STORAGE" is treated as the storage line)
  Azure JSON:      { totals: {monthly_usd, annual_usd, ...},
                     breakdown_by_category: [...] (optional),
                     breakdown_by_environment: [...] (optional) }

The consolidation does NOT re-multiply by environments — the agent subtotals are
already all-environment sums.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

_NAVY = "1B3139"
_FILL_HEADER = PatternFill("solid", fgColor=_NAVY)
_FILL_H2 = PatternFill("solid", fgColor="F1F1EE")
_FILL_GREEN = PatternFill("solid", fgColor="E3F5E1")
_FONT_HEADER = Font(bold=True, color="FFFFFF", size=13, name="Arial")
_FONT_H2 = Font(bold=True, color=_NAVY, size=11, name="Arial")
_FONT_B = Font(size=10, bold=True, name="Arial")
_FONT = Font(size=10, name="Arial")
_FONT_SMALL = Font(size=9, italic=True, color="6B6F76", name="Arial")
_THIN = Side(style="thin", color="D0D0D0")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_MONEY = '"$"#,##0;("$"#,##0);-'


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _hdr(ws, rng, text):
    first = rng.split(":")[0]
    ws[first] = text
    ws[first].font = _FONT_HEADER
    ws[first].fill = _FILL_HEADER
    ws.merge_cells(rng)


def _widths(ws, ws_widths):
    for i, w in enumerate(ws_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def build(databricks: dict, azure: dict, client: str, region: str, growth_pct: float) -> Workbook:
    wb = Workbook()

    dbx_total = float(databricks.get("totals", {}).get("monthly_usd", 0))
    azure_total = float(azure.get("totals", {}).get("monthly_usd", 0))

    # ── Sheet 1: Summary ──────────────────────────────────────────────
    ws = wb.active
    ws.title = "1. Summary"
    _hdr(ws, "A1:C1", f"Greenfield Cost — {client} ({region})")
    ws.row_dimensions[1].height = 24
    ws.cell(row=3, column=1, value="Camada").font = _FONT_B
    ws.cell(row=3, column=1).fill = _FILL_H2
    ws.cell(row=3, column=2, value="$/mês").font = _FONT_B
    ws.cell(row=3, column=2).fill = _FILL_H2
    ws.cell(row=3, column=3, value="$/ano").font = _FONT_B
    ws.cell(row=3, column=3).fill = _FILL_H2
    rows = [
        ("Databricks (compute + storage + AI, 4 envs)", dbx_total),
        ("Azure Infra (vNet, NAT, PEP, Log, KV, FW, Defender, Bastion)", azure_total),
    ]
    r = 4
    first = r
    for label, val in rows:
        ws.cell(row=r, column=1, value=label).font = _FONT
        c = ws.cell(row=r, column=2, value=round(val, 2))
        c.number_format = _MONEY
        a = ws.cell(row=r, column=3, value=f"=B{r}*12")
        a.number_format = _MONEY
        for col in range(1, 4):
            ws.cell(row=r, column=col).border = _BORDER
        r += 1
    ws.cell(row=r, column=1, value="GRAND TOTAL").font = Font(
        bold=True, color="FFFFFF", name="Arial"
    )
    ws.cell(row=r, column=1).fill = _FILL_HEADER
    gt = ws.cell(row=r, column=2, value=f"=SUM(B{first}:B{r - 1})")
    gt.fill = _FILL_HEADER
    gt.font = Font(bold=True, color="FFFFFF", name="Arial")
    gt.number_format = _MONEY
    ga = ws.cell(row=r, column=3, value=f"=B{r}*12")
    ga.fill = _FILL_HEADER
    ga.font = Font(bold=True, color="FFFFFF", name="Arial")
    ga.number_format = _MONEY
    grand_row = r
    r += 2

    # growth projection
    ws.cell(row=r, column=1, value="Projeção (growth aplicado ao total)").font = _FONT_H2
    ws.cell(row=r, column=1).fill = _FILL_H2
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
    r += 1
    g = growth_pct / 100.0
    proj = [
        ("Ano 1", 1.0),
        (f"Ano 2 (+{growth_pct:.0f}%)", 1 + g),
        (f"Ano 3 (+{growth_pct:.0f}%/ano)", (1 + g) ** 2),
    ]
    for label, factor in proj:
        ws.cell(row=r, column=1, value=label).font = _FONT
        c = ws.cell(row=r, column=2, value=f"=B{grand_row}*12*{factor:.3f}")
        c.number_format = _MONEY
        for col in range(1, 3):
            ws.cell(row=r, column=col).border = _BORDER
        r += 1
    r += 1
    ws.cell(
        row=r,
        column=1,
        value=(
            "List price, antes de desconto comercial (DBCU 1y/3y: -33%/-37%). "
            "Region-aware DBU rates (southeastasia) aplicados. Growth aproximado sobre o total."
        ),
    ).font = _FONT_SMALL
    ws.merge_cells(start_row=r, start_column=1, end_row=r + 2, end_column=3)
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True, vertical="top")
    _widths(ws, [52, 16, 16])

    # ── Sheet 2: Databricks breakdown ─────────────────────────────────
    ws2 = wb.create_sheet("2. Databricks")
    _hdr(ws2, "A1:B1", "Databricks — breakdown por workload (4 envs somados)")
    ws2.cell(row=3, column=1, value="Workload").font = _FONT_B
    ws2.cell(row=3, column=1).fill = _FILL_H2
    ws2.cell(row=3, column=2, value="$/mês").font = _FONT_B
    ws2.cell(row=3, column=2).fill = _FILL_H2
    r = 4
    wfirst = r
    for w in databricks.get("workloads", []):
        ws2.cell(row=r, column=1, value=w.get("code", "")).font = _FONT
        c = ws2.cell(row=r, column=2, value=round(float(w.get("subtotal_usd", 0)), 2))
        c.number_format = _MONEY
        for col in range(1, 3):
            ws2.cell(row=r, column=col).border = _BORDER
        r += 1
    ws2.cell(row=r, column=1, value="TOTAL Databricks").font = _FONT_B
    ws2.cell(row=r, column=1).fill = _FILL_GREEN
    t = ws2.cell(row=r, column=2, value=f"=SUM(B{wfirst}:B{r - 1})")
    t.fill = _FILL_GREEN
    t.font = _FONT_B
    t.number_format = _MONEY
    _widths(ws2, [30, 16])

    # ── Sheet 3: Azure Infra breakdown ────────────────────────────────
    ws3 = wb.create_sheet("3. Azure Infra")
    _hdr(ws3, "A1:B1", "Azure Infra — breakdown por categoria")
    ws3.cell(row=3, column=1, value="Categoria / Ambiente").font = _FONT_B
    ws3.cell(row=3, column=1).fill = _FILL_H2
    ws3.cell(row=3, column=2, value="$/mês").font = _FONT_B
    ws3.cell(row=3, column=2).fill = _FILL_H2
    r = 4
    afirst = r
    cats = azure.get("breakdown_by_category") or azure.get("breakdown_by_environment") or []
    if isinstance(cats, dict):
        cats = [{"name": k, "monthly_usd": v} for k, v in cats.items()]
    for c_item in cats:
        name = c_item.get("name") or c_item.get("category") or c_item.get("environment") or "—"
        val = c_item.get("monthly_usd") or c_item.get("monthly") or c_item.get("total_usd") or 0
        ws3.cell(row=r, column=1, value=name).font = _FONT
        cc = ws3.cell(row=r, column=2, value=round(float(val), 2))
        cc.number_format = _MONEY
        for col in range(1, 3):
            ws3.cell(row=r, column=col).border = _BORDER
        r += 1
    if r == afirst:  # no breakdown available — show the total only
        ws3.cell(row=r, column=1, value="Total Azure Infra (sem breakdown no JSON)").font = _FONT
        cc = ws3.cell(row=r, column=2, value=round(azure_total, 2))
        cc.number_format = _MONEY
        r += 1
    ws3.cell(row=r, column=1, value="TOTAL Azure Infra").font = _FONT_B
    ws3.cell(row=r, column=1).fill = _FILL_GREEN
    t = ws3.cell(row=r, column=2, value=round(azure_total, 2))
    t.fill = _FILL_GREEN
    t.font = _FONT_B
    t.number_format = _MONEY
    _widths(ws3, [40, 16])

    return wb


def main() -> int:
    ap = argparse.ArgumentParser(description="WF-07 greenfield XLSX consolidation")
    ap.add_argument("--databricks", required=True, help="path to databricks scenario_used.json")
    ap.add_argument("--azure", required=True, help="path to azure_infra_scenario_used.json")
    ap.add_argument("--out", required=True, help="output .xlsx path")
    ap.add_argument("--client", default=None)
    ap.add_argument("--region", default=None)
    ap.add_argument("--growth", type=float, default=None)
    args = ap.parse_args()

    dbx = _load(args.databricks)
    az = _load(args.azure)
    client = args.client or dbx.get("client") or "Cliente"
    region = args.region or dbx.get("region") or "n/a"
    growth = args.growth if args.growth is not None else float(dbx.get("annual_growth_pct", 20))

    wb = build(dbx, az, client, region, growth)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)

    dbx_total = dbx.get("totals", {}).get("monthly_usd", 0)
    az_total = az.get("totals", {}).get("monthly_usd", 0)
    print(f"✅ wrote {out}")
    print(f"   Databricks: ${dbx_total:,.2f}/mo  +  Azure Infra: ${az_total:,.2f}/mo")
    print(
        f"   GRAND TOTAL: ${dbx_total + az_total:,.2f}/mo  (${(dbx_total + az_total) * 12:,.2f}/yr)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
