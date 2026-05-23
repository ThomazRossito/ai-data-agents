"""
Auto-marker para tests/unit/ — todo teste deste subdir recebe @pytest.mark.unit
sem necessidade de decorar manualmente.

Permite seleção rápida:
    pytest -m unit              # só unit
    pytest -m "not integration" # tudo menos integration
    pytest tests/unit/          # mesma coisa, via path

Não substitui fixtures globais de tests/conftest.py — apenas adiciona o marker.
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    marker = pytest.mark.unit
    for item in items:
        item.add_marker(marker)
