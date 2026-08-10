"""
Regression tests for region-aware DBU rate overrides (2026-07-22).

Verifies:
  1. The canonical brazilsouth rate is UNCHANGED (no override → base rate).
  2. southeastasia uses the Azure-Retail-API-derived override rates.
  3. A region with no override block falls back to base cleanly.

These tests call the engine directly (no conftest / .env dependency) so they run
in any environment. Run:
    python3 tests/unit/test_region_dbu_overrides.py
or via pytest once the project .env is configured.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from data_agents.cost_engine.databricks import (  # noqa: E402
    DatabricksScenario,
    load_databricks_catalog,
    _resolve_dbu_rate,
    _resolve_base_dbu_rate,
)

_CAT = load_databricks_catalog("azure")


def _mk(region: str, compute_type: str = "jobs_compute", tier: str = "premium",
        photon: bool = False) -> DatabricksScenario:
    return DatabricksScenario(
        cloud="azure", compute_type=compute_type, tier=tier, photon=photon,
        driver_instance="Standard_DS4_v2", worker_instance="Standard_DS4_v2",
        num_workers=4, hours_per_day=8, days_per_month=22, region=region,
        instance_pricing_model="on_demand",
        driver_instance_cost_per_hour_usd=0.526,
        worker_instance_cost_per_hour_usd=0.526,
    )


def test_brazilsouth_unchanged_jobs():
    assert _resolve_dbu_rate(_CAT, _mk("brazilsouth")) == 0.20


def test_brazilsouth_unchanged_sql_pro():
    assert _resolve_dbu_rate(_CAT, _mk("brazilsouth", "sql", "pro")) == 0.55


def test_southeastasia_jobs_override():
    assert _resolve_dbu_rate(_CAT, _mk("southeastasia")) == 0.30


def test_southeastasia_sql_pro_override():
    assert _resolve_dbu_rate(_CAT, _mk("southeastasia", "sql", "pro")) == 0.69


def test_southeastasia_sql_serverless_override():
    assert _resolve_dbu_rate(_CAT, _mk("southeastasia", "sql", "serverless")) == 0.88


def test_southeastasia_jobs_serverless_override():
    assert _resolve_dbu_rate(_CAT, _mk("southeastasia", "jobs_serverless")) == 0.50


def test_southeastasia_all_purpose_serverless_override():
    assert _resolve_dbu_rate(_CAT, _mk("southeastasia", "all_purpose_serverless")) == 1.00


def test_unlisted_region_falls_back_to_base():
    # 'northeurope' has no override block → must equal base rate.
    base = _resolve_base_dbu_rate(_CAT, _mk("northeurope"))
    assert _resolve_dbu_rate(_CAT, _mk("northeurope")) == base


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✅ {name}")
            passed += 1
    print(f"\n{passed} region-override tests passed.")
