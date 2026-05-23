"""
Auto-marker para tests/perf/ — @pytest.mark.perf + @pytest.mark.slow.

Perf tests rodam ONLY when explicitly requested:
    pytest -m perf            # só perf
    pytest -m "not perf"      # default — perf é skipped

Não vão para o pipeline principal de CI ainda (Phase 10 — esqueleto).
Quando a Fase 10.x maturar, adicionar:
    .github/workflows/perf.yml: schedule cron weekly + workflow_dispatch
e wire-up de comparação contra baseline (regressão > 20% falha).

Para já, o critério de aceitação é apenas que os testes EXISTAM e RODEM —
métricas mostradas no terminal servem como baseline informativo.
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    perf_marker = pytest.mark.perf
    slow_marker = pytest.mark.slow
    for item in items:
        item.add_marker(perf_marker)
        item.add_marker(slow_marker)
