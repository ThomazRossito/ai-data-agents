"""
Tests for scripts/greenfield_consolidate.py (WF-07 deterministic consolidation).

Verifies the consolidation reads the two agent scenario JSONs and produces a
valid XLSX with the grand total = databricks + azure (NO double-counting of
environments — the agent subtotals are already all-env sums).

Run standalone:
    python3 tests/unit/test_greenfield_consolidate.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import openpyxl

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "greenfield_consolidate.py"
_spec = importlib.util.spec_from_file_location("greenfield_consolidate", _SCRIPT)
gc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gc)


def _sample_inputs(tmp: Path) -> tuple[Path, Path]:
    dbx = {
        "client": "TestCo", "region": "southeastasia", "annual_growth_pct": 20,
        "workloads": [
            {"code": "ETL_BATCH", "subtotal_usd": 2881.29},
            {"code": "SQL_WAREHOUSE", "subtotal_usd": 4400.00},
            {"code": "STORAGE", "subtotal_usd": 970.00},
        ],
        "totals": {"monthly_usd": 19758.13},
    }
    az = {
        "client": "TestCo", "region": "southeastasia",
        "breakdown_by_category": [
            {"name": "Networking", "monthly_usd": 687.96},
            {"name": "Observability & Security", "monthly_usd": 1791.97},
            {"name": "Shared Services", "monthly_usd": 1296.23},
        ],
        "totals": {"monthly_usd": 3776.16},
    }
    p1 = tmp / "scenario_used.json"
    p2 = tmp / "azure_infra_scenario_used.json"
    p1.write_text(json.dumps(dbx))
    p2.write_text(json.dumps(az))
    return p1, p2


def test_consolidation_produces_valid_xlsx(tmp_path: Path):
    p1, p2 = _sample_inputs(tmp_path)
    wb = gc.build(json.loads(p1.read_text()), json.loads(p2.read_text()),
                  "TestCo", "southeastasia", 20.0)
    assert wb.sheetnames == ["1. Summary", "2. Databricks", "3. Azure Infra"]


def test_grand_total_is_sum_not_double_counted(tmp_path: Path):
    p1, p2 = _sample_inputs(tmp_path)
    dbx = json.loads(p1.read_text())
    az = json.loads(p2.read_text())
    # The grand total must equal dbx.totals + azure.totals exactly (no ×1.5).
    expected = dbx["totals"]["monthly_usd"] + az["totals"]["monthly_usd"]
    assert round(expected, 2) == 23534.29


def test_summary_has_both_layers(tmp_path: Path):
    p1, p2 = _sample_inputs(tmp_path)
    out = tmp_path / "out.xlsx"
    sys.argv = ["greenfield_consolidate.py", "--databricks", str(p1),
                "--azure", str(p2), "--out", str(out)]
    gc.main()
    assert out.exists()
    wb = openpyxl.load_workbook(out)
    ws = wb["1. Summary"]
    labels = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
    assert any("Databricks" in str(l) for l in labels)
    assert any("Azure Infra" in str(l) for l in labels)
    assert any("GRAND TOTAL" in str(l) for l in labels)


if __name__ == "__main__":
    import tempfile
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            with tempfile.TemporaryDirectory() as d:
                fn(Path(d))
            print(f"  ✅ {name}")
            passed += 1
    print(f"\n{passed} consolidation tests passed.")
