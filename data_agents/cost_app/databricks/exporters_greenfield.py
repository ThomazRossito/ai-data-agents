"""
Greenfield XLSX exporter — Databricks compute + Azure infra + storage.

Produces a financial-model-style workbook (formulas, colour legend, toggles,
audit sheet) for a greenfield Databricks deployment across N environments. This
is the output format that turns a flat markdown estimate into a commercial-grade
artefact the customer can edit and re-cost.

It is intentionally engine-agnostic on INPUT: callers pass already-computed line
items (from databricks-cost-calculator and azure-cost-calculator / WF-07). The
exporter's job is layout + formulas + provenance, not pricing.

Sheets:
  1. Cover        — client, region, tier, colour legend, sheet map
  2. Databricks   — per-workload compute + storage (PROD), formulas
  3. Azure Infra  — per-env stack + shared services with ON/OFF toggles
  4. Rollup       — PROD + non-prod (20%×2) + Sandbox (10%) + infra + storage
  5. Summary      — monthly + annual + Y2/Y3 growth
  6. Sources      — official pricing URLs + caveats

Colour legend (matches project financial-model convention):
  blue   = hardcoded input from official source (Azure Retail Prices API)
  yellow = CI&T assumption / editable toggle — review before commit
  green  = output total
  black  = formula
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


# ── palette ──────────────────────────────────────────────────────────────────
_NAVY = "1B3139"
_RED = "FF3621"
_GREEN = "00A972"
_BORDER = "D0D0D0"
_FILL_HEADER = PatternFill("solid", fgColor=_NAVY)
_FILL_H2 = PatternFill("solid", fgColor="F1F1EE")
_FILL_BLUE = PatternFill("solid", fgColor="E3F0FF")     # official hardcoded input
_FILL_YELLOW = PatternFill("solid", fgColor="FFF3B0")   # assumption / toggle
_FILL_GREEN = PatternFill("solid", fgColor="E3F5E1")    # output total
_FONT_HEADER = Font(bold=True, color="FFFFFF", size=13, name="Arial")
_FONT_H2 = Font(bold=True, color=_NAVY, size=11, name="Arial")
_FONT_BODY = Font(size=10, name="Arial")
_FONT_BODY_B = Font(size=10, bold=True, name="Arial")
_FONT_BLUE = Font(size=10, color="0000FF", name="Arial")   # hardcoded input
_FONT_GREEN = Font(size=10, color="008000", name="Arial")  # cross-sheet link
_FONT_SMALL = Font(size=9, italic=True, color="6B6F76", name="Arial")
_THIN = Side(style="thin", color=_BORDER)
_BORDER_ALL = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_MONEY = '"$"#,##0;("$"#,##0);-'
_MONEY2 = '"$"#,##0.00;("$"#,##0.00);-'
_NUM = "#,##0"
_PCT = "0.0%"


def _hdr(ws, cell_range: str, text: str) -> None:
    first = cell_range.split(":")[0]
    ws[first] = text
    ws[first].font = _FONT_HEADER
    ws[first].fill = _FILL_HEADER
    ws.merge_cells(cell_range)


def _h2(ws, row: int, ncols: int, text: str) -> None:
    c = ws.cell(row=row, column=1, value=text)
    c.font = _FONT_H2
    c.fill = _FILL_H2
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)


def _widths(ws, widths: list[int]) -> None:
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


# ── main entry point ─────────────────────────────────────────────────────────
def build_greenfield_xlsx(
    *,
    client: str,
    region: str,
    tier: str,
    currency: str,
    databricks_lines: list[dict[str, Any]],
    azure_infra_per_env: list[dict[str, Any]],
    azure_infra_shared: list[dict[str, Any]],
    storage_line: dict[str, Any],
    num_envs: int = 4,
    nonprod_factor: float = 0.20,
    nonprod_count: int = 2,
    sandbox_factor: float = 0.10,
    annual_growth_pct: float = 20.0,
    sources: list[dict[str, str]] | None = None,
    generated_at: str | None = None,
) -> BytesIO:
    """Build the greenfield workbook and return it as an in-memory BytesIO.

    Parameters
    ----------
    databricks_lines
        list of {code, name, monthly_usd, note} — PROD Databricks compute/AI lines.
    azure_infra_per_env
        list of {ref, resource, qty, unit_measure, unit_price, monthly_per_env, note}.
    azure_infra_shared
        list of {ref, resource, enabled(0/1), qty, unit_measure, unit_price, note}.
    storage_line
        {name, gb, price_per_gb, monthly_usd, note}.
    """
    wb = Workbook()
    generated_at = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    _build_cover(wb.active, client, region, tier, currency, generated_at)
    dbx_compute_cell, storage_cell = _build_databricks(
        wb.create_sheet("2. Databricks"), databricks_lines, storage_line
    )
    infra_total_cell = _build_azure_infra(
        wb.create_sheet("3. Azure Infra"), azure_infra_per_env, azure_infra_shared, num_envs
    )
    storage_line = {**storage_line, "_cell": storage_cell}
    _build_rollup(
        wb.create_sheet("4. Rollup"),
        dbx_compute_cell, infra_total_cell, storage_line,
        nonprod_factor, nonprod_count, sandbox_factor,
    )
    _build_summary(wb.create_sheet("5. Summary"), annual_growth_pct)
    _build_sources(wb.create_sheet("6. Sources"), sources or _DEFAULT_SOURCES)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _build_cover(ws, client, region, tier, currency, generated_at) -> None:
    ws.title = "1. Cover"
    _hdr(ws, "A1:F1", f"Greenfield Cost Estimate — {client}")
    ws.row_dimensions[1].height = 26
    meta = [
        ("Cliente", client),
        ("Cloud / Região", f"Azure Databricks — {region}"),
        ("Tier", tier),
        ("Moeda", f"{currency} (list price, antes de desconto comercial)"),
        ("Gerado em", generated_at),
        ("Fonte de pricing", "Azure Retail Prices API (DBU region-aware + VM + infra)"),
    ]
    r = 3
    for k, v in meta:
        ws.cell(row=r, column=1, value=k).font = _FONT_BODY_B
        ws.cell(row=r, column=2, value=v).font = _FONT_BODY
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
        r += 1

    r += 1
    _h2(ws, r, 6, "Legenda de cores")
    r += 1
    legend = [
        ("Azul", "Input hardcoded de fonte OFICIAL (Azure Retail Prices API)", _FILL_BLUE),
        ("Amarelo", "Premissa CI&T / toggle editável — revisar antes do commit", _FILL_YELLOW),
        ("Verde", "Total / output consolidado", _FILL_GREEN),
    ]
    for label, desc, fill in legend:
        ws.cell(row=r, column=1, value=label).fill = fill
        ws.cell(row=r, column=1).font = _FONT_BODY_B
        ws.cell(row=r, column=2, value=desc).font = _FONT_BODY
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
        r += 1

    r += 1
    _h2(ws, r, 6, "Estrutura do workbook")
    r += 1
    smap = [
        ("2. Databricks", "Compute por workload (PROD) + storage. Region-aware DBU rates."),
        ("3. Azure Infra", "Stack de rede/segurança por ambiente + shared services com toggles ON/OFF."),
        ("4. Rollup", "PROD + 2 non-prod (20%) + Sandbox (10%) + infra + storage."),
        ("5. Summary", "Mensal + anual + projeção Y2/Y3 com growth."),
        ("6. Sources", "URLs oficiais Microsoft/Databricks + caveats."),
    ]
    for name, desc in smap:
        ws.cell(row=r, column=1, value=name).font = _FONT_BODY_B
        ws.cell(row=r, column=2, value=desc).font = _FONT_BODY
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
        r += 1
    _widths(ws, [22, 30, 18, 18, 18, 18])


def _build_databricks(ws, lines, storage_line) -> str:
    _hdr(ws, "A1:D1", "Databricks — Compute + Storage (PROD, list price)")
    hdr = ["Ref", "Workload", "$ / mês (PROD)", "Nota"]
    for i, h in enumerate(hdr, 1):
        c = ws.cell(row=3, column=i, value=h)
        c.font = _FONT_BODY_B
        c.fill = _FILL_H2
        c.border = _BORDER_ALL
    r = 4
    first = r
    for ln in lines:
        ws.cell(row=r, column=1, value=ln.get("code", "")).font = _FONT_BODY_B
        ws.cell(row=r, column=2, value=ln.get("name", "")).font = _FONT_BODY
        cost = ws.cell(row=r, column=3, value=round(float(ln.get("monthly_usd", 0)), 2))
        cost.number_format = _MONEY
        cost.font = _FONT_BODY
        if ln.get("note"):
            ws.cell(row=r, column=2).comment = Comment(ln["note"], "WF-07")
        for col in range(1, 5):
            ws.cell(row=r, column=col).border = _BORDER_ALL
        r += 1
    # storage
    ws.cell(row=r, column=1, value="STORAGE").font = _FONT_BODY_B
    ws.cell(row=r, column=2, value=storage_line.get("name", "ADLS Gen2 Hot")).font = _FONT_BODY
    sc = ws.cell(row=r, column=3, value=round(float(storage_line.get("monthly_usd", 0)), 2))
    sc.number_format = _MONEY
    for col in range(1, 5):
        ws.cell(row=r, column=col).border = _BORDER_ALL
    storage_row = r
    r += 1
    # PROD total (compute + storage)
    ws.cell(row=r, column=2, value="TOTAL PROD (compute + storage)").font = _FONT_BODY_B
    tot = ws.cell(row=r, column=3, value=f"=SUM(C{first}:C{r-1})")
    tot.font = Font(bold=True, color="FFFFFF", name="Arial")
    tot.fill = _FILL_HEADER
    tot.number_format = _MONEY
    # compute-only total (excludes storage) — used by rollup
    r += 1
    ws.cell(row=r, column=2, value="  → compute-only (exclui storage)").font = _FONT_SMALL
    comp = ws.cell(row=r, column=3, value=f"=SUM(C{first}:C{storage_row-1})")
    comp.number_format = _MONEY
    comp.font = _FONT_BODY
    _widths(ws, [12, 50, 16, 50])
    compute_only_cell = f"'2. Databricks'!$C${r}"
    storage_cell = f"'2. Databricks'!$C${storage_row}"
    return compute_only_cell, storage_cell


def _build_azure_infra(ws, per_env, shared, num_envs) -> str:
    _hdr(ws, "A1:H1", f"Azure Infra — {num_envs} ambientes (greenfield, Southeast Asia)")

    # per-env section
    _h2(ws, 3, 8, "3.1  Stack por ambiente (× N envs)")
    hdr = ["Ref", "Recurso", "Qty", "Horas/GB", "$ unit", "$/env/mês", "Envs", "$/mês total"]
    for i, h in enumerate(hdr, 1):
        c = ws.cell(row=4, column=i, value=h)
        c.font = _FONT_BODY_B
        c.fill = _FILL_H2
        c.border = _BORDER_ALL
    r = 5
    first = r
    for it in per_env:
        ws.cell(row=r, column=1, value=it.get("ref", "")).font = _FONT_BODY_B
        ws.cell(row=r, column=2, value=it.get("resource", "")).font = _FONT_BODY
        q = ws.cell(row=r, column=3, value=it.get("qty", 1))
        q.font = _FONT_BLUE
        q.fill = _FILL_BLUE
        h = ws.cell(row=r, column=4, value=it.get("hours_or_gb", 0))
        h.font = _FONT_BLUE
        h.fill = _FILL_BLUE
        p = ws.cell(row=r, column=5, value=it.get("unit_price", 0))
        p.font = _FONT_BLUE
        p.fill = _FILL_BLUE
        p.number_format = '"$"#,##0.000'
        env_cost = ws.cell(row=r, column=6, value=f"=C{r}*D{r}*E{r}")
        env_cost.number_format = _MONEY2
        envs = ws.cell(row=r, column=7, value=num_envs)
        envs.font = _FONT_BLUE
        envs.fill = _FILL_BLUE
        tot = ws.cell(row=r, column=8, value=f"=F{r}*G{r}")
        tot.number_format = _MONEY2
        tot.font = _FONT_BODY_B
        if it.get("note"):
            ws.cell(row=r, column=2).comment = Comment(it["note"], "WF-07")
        for col in range(1, 9):
            ws.cell(row=r, column=col).border = _BORDER_ALL
        r += 1
    ws.cell(row=r, column=2, value="Subtotal per-env × envs").font = _FONT_BODY_B
    per_env_total = ws.cell(row=r, column=8, value=f"=SUM(H{first}:H{r-1})")
    per_env_total.fill = _FILL_GREEN
    per_env_total.font = _FONT_BODY_B
    per_env_total.number_format = _MONEY
    per_env_total_row = r
    r += 2

    # shared section
    _h2(ws, r, 8, "3.2  Shared services (toggle ON=1 / OFF=0 na coluna 'On?')")
    r += 1
    hdr = ["Ref", "Recurso", "On?", "Qty", "Horas/GB", "$ unit", "$/mês (se ON)", ""]
    for i, h in enumerate(hdr, 1):
        c = ws.cell(row=r, column=i, value=h)
        c.font = _FONT_BODY_B
        c.fill = _FILL_H2
        c.border = _BORDER_ALL
    r += 1
    sfirst = r
    for it in shared:
        ws.cell(row=r, column=1, value=it.get("ref", "")).font = _FONT_BODY_B
        ws.cell(row=r, column=2, value=it.get("resource", "")).font = _FONT_BODY
        en = ws.cell(row=r, column=3, value=it.get("enabled", 1))
        en.font = _FONT_BODY_B
        en.fill = _FILL_YELLOW
        en.comment = Comment("Toggle: 1=ON, 0=OFF. Amarelo = editável.", "WF-07")
        q = ws.cell(row=r, column=4, value=it.get("qty", 1))
        q.font = _FONT_BLUE
        q.fill = _FILL_BLUE
        h = ws.cell(row=r, column=5, value=it.get("hours_or_gb", 0))
        h.font = _FONT_BLUE
        h.fill = _FILL_BLUE
        p = ws.cell(row=r, column=6, value=it.get("unit_price", 0))
        p.font = _FONT_BLUE
        p.fill = _FILL_BLUE
        p.number_format = '"$"#,##0.000'
        cost = ws.cell(row=r, column=7, value=f"=C{r}*D{r}*E{r}*F{r}")
        cost.number_format = _MONEY2
        cost.font = _FONT_BODY_B
        if it.get("note"):
            ws.cell(row=r, column=2).comment = Comment(it["note"], "WF-07")
        for col in range(1, 8):
            ws.cell(row=r, column=col).border = _BORDER_ALL
        r += 1
    ws.cell(row=r, column=2, value="Subtotal shared (toggles atuais)").font = _FONT_BODY_B
    shared_total = ws.cell(row=r, column=7, value=f"=SUM(G{sfirst}:G{r-1})")
    shared_total.fill = _FILL_GREEN
    shared_total.font = _FONT_BODY_B
    shared_total.number_format = _MONEY
    shared_total_row = r
    r += 2

    # infra total
    ws.cell(row=r, column=2, value="TOTAL AZURE INFRA / mês").font = Font(bold=True, color="FFFFFF", name="Arial")
    ws.cell(row=r, column=2).fill = _FILL_HEADER
    infra_total = ws.cell(row=r, column=8, value=f"=H{per_env_total_row}+G{shared_total_row}")
    infra_total.font = Font(bold=True, color="FFFFFF", name="Arial")
    infra_total.fill = _FILL_HEADER
    infra_total.number_format = _MONEY
    _widths(ws, [7, 44, 8, 12, 12, 12, 16, 14])
    return f"'3. Azure Infra'!$H${r}"


def _build_rollup(ws, dbx_compute_cell, infra_total_cell, storage_line,
                  nonprod_factor, nonprod_count, sandbox_factor) -> None:
    _hdr(ws, "A1:C1", "Environments Rollup")
    # dbx_compute_cell references the compute-only line on the Databricks sheet.
    ws.cell(row=3, column=1, value="Bloco").font = _FONT_BODY_B
    ws.cell(row=3, column=1).fill = _FILL_H2
    ws.cell(row=3, column=2, value="Fator").font = _FONT_BODY_B
    ws.cell(row=3, column=2).fill = _FILL_H2
    ws.cell(row=3, column=3, value="$ / mês").font = _FONT_BODY_B
    ws.cell(row=3, column=3).fill = _FILL_H2

    total_factor = 1.0 + nonprod_factor * nonprod_count + sandbox_factor
    rows = [
        ("Databricks compute — PROD", 1.0, f"={dbx_compute_cell}*1.0"),
        (f"Databricks compute — {nonprod_count} non-prod ({int(nonprod_factor*100)}% cada)",
         nonprod_factor * nonprod_count, f"={dbx_compute_cell}*{nonprod_factor*nonprod_count}"),
        (f"Databricks compute — Sandbox ({int(sandbox_factor*100)}%)",
         sandbox_factor, f"={dbx_compute_cell}*{sandbox_factor}"),
        ("Storage (1× — não replica)", None, f"={storage_line['_cell']}" if storage_line.get("_cell") else None),
        ("Azure Infra (já inclui N envs)", None, f"={infra_total_cell}"),
    ]
    r = 4
    first = r
    for label, factor, formula in rows:
        ws.cell(row=r, column=1, value=label).font = _FONT_BODY
        if factor is not None:
            fc = ws.cell(row=r, column=2, value=factor)
            fc.number_format = _PCT
        if formula:
            cc = ws.cell(row=r, column=3, value=formula)
            cc.number_format = _MONEY
            cc.font = _FONT_GREEN
        for col in range(1, 4):
            ws.cell(row=r, column=col).border = _BORDER_ALL
        r += 1
    ws.cell(row=r, column=1, value="GRAND TOTAL MENSAL").font = Font(bold=True, color="FFFFFF", name="Arial")
    ws.cell(row=r, column=1).fill = _FILL_HEADER
    gt = ws.cell(row=r, column=3, value=f"=SUM(C{first}:C{r-1})")
    gt.fill = _FILL_HEADER
    gt.font = Font(bold=True, color="FFFFFF", name="Arial")
    gt.number_format = _MONEY
    ws._gf_grand_monthly = f"'4. Rollup'!$C${r}"
    r += 1
    ws.cell(row=r, column=1, value="GRAND TOTAL ANUAL").font = Font(bold=True, color="FFFFFF", name="Arial")
    ws.cell(row=r, column=1).fill = _FILL_HEADER
    ga = ws.cell(row=r, column=3, value=f"=C{r-1}*12")
    ga.fill = _FILL_HEADER
    ga.font = Font(bold=True, color="FFFFFF", name="Arial")
    ga.number_format = _MONEY
    _widths(ws, [46, 12, 18])


def _build_summary(ws, growth_pct) -> None:
    _hdr(ws, "A1:C1", "Summary — Mensal, Anual, Projeção Y2/Y3")
    ws.cell(row=3, column=1, value="Período").font = _FONT_BODY_B
    ws.cell(row=3, column=1).fill = _FILL_H2
    ws.cell(row=3, column=2, value="Fator growth").font = _FONT_BODY_B
    ws.cell(row=3, column=2).fill = _FILL_H2
    ws.cell(row=3, column=3, value="$ (aprox)").font = _FONT_BODY_B
    ws.cell(row=3, column=3).fill = _FILL_H2
    g = growth_pct / 100.0
    rows = [
        ("Mensal (Y1)", 1.0, f"='4. Rollup'!$C${_ROLLUP_MONTHLY_ROW}"),
        ("Anual (Y1)", 1.0, f"='4. Rollup'!$C${_ROLLUP_MONTHLY_ROW}*12"),
        (f"Anual (Y2, +{growth_pct:.0f}% growth aprox)", 1 + g, f"='4. Rollup'!$C${_ROLLUP_MONTHLY_ROW}*12*{1+g:.3f}"),
        (f"Anual (Y3, +{growth_pct:.0f}%/ano aprox)", (1 + g) ** 2, f"='4. Rollup'!$C${_ROLLUP_MONTHLY_ROW}*12*{(1+g)**2:.3f}"),
    ]
    r = 4
    for label, factor, formula in rows:
        ws.cell(row=r, column=1, value=label).font = _FONT_BODY
        fc = ws.cell(row=r, column=2, value=round(factor, 3))
        fc.number_format = "0.000"
        cc = ws.cell(row=r, column=3, value=formula)
        cc.number_format = _MONEY
        cc.font = _FONT_GREEN
        for col in range(1, 4):
            ws.cell(row=r, column=col).border = _BORDER_ALL
        r += 1
    r += 1
    note = ("Growth aplicado como aproximação sobre o total (compute + infra). "
            "Storage cresce mais que compute na prática — refinar por camada se necessário. "
            "Descontos comerciais (DBCU 1y/3y: -33%/-37%) NÃO aplicados — list price.")
    ws.cell(row=r, column=1, value=note).font = _FONT_SMALL
    ws.merge_cells(start_row=r, start_column=1, end_row=r + 2, end_column=3)
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True, vertical="top")
    _widths(ws, [40, 14, 18])


def _build_sources(ws, sources) -> None:
    _hdr(ws, "A1:C1", "Sources & Caveats")
    ws.cell(row=3, column=1, value="Item").font = _FONT_BODY_B
    ws.cell(row=3, column=1).fill = _FILL_H2
    ws.cell(row=3, column=2, value="URL").font = _FONT_BODY_B
    ws.cell(row=3, column=2).fill = _FILL_H2
    r = 4
    for s in sources:
        ws.cell(row=r, column=1, value=s.get("name", "")).font = _FONT_BODY
        u = ws.cell(row=r, column=2, value=s.get("url", ""))
        u.font = Font(size=9, color="0563C1", underline="single", name="Arial")
        if s.get("url"):
            u.hyperlink = s["url"]
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
        r += 1
    _widths(ws, [40, 60, 10])


# Rollup monthly row is deterministic given the fixed rollup layout (5 blocks →
# grand total on row 9). Kept as a module constant to keep _build_summary simple.
_ROLLUP_MONTHLY_ROW = 9

_DEFAULT_SOURCES = [
    {"name": "Azure Retail Prices API", "url": "https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices"},
    {"name": "Azure Databricks pricing", "url": "https://azure.microsoft.com/pricing/details/databricks/"},
    {"name": "Azure NAT Gateway", "url": "https://azure.microsoft.com/pricing/details/azure-nat-gateway/"},
    {"name": "Azure Private Link", "url": "https://azure.microsoft.com/pricing/details/private-link/"},
    {"name": "Azure Monitor / Log Analytics", "url": "https://azure.microsoft.com/pricing/details/monitor/"},
    {"name": "Azure Firewall", "url": "https://azure.microsoft.com/pricing/details/azure-firewall/"},
    {"name": "Microsoft Defender for Cloud", "url": "https://azure.microsoft.com/pricing/details/defender-for-cloud/"},
    {"name": "KB azure-infra-for-databricks", "url": "kb/azure-infra-for-databricks/index.md"},
]
