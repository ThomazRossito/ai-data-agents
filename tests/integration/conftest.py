"""
Auto-marker para tests/integration/ — todo teste deste subdir recebe
@pytest.mark.integration sem necessidade de decorar manualmente.

Testes integration tocam DB local (SQLite) ou exercitam persistência JSONL/Delta
como contrato. São mais lentos que unit (1-10s típico) mas ainda rodam offline.

Permite seleção:
    pytest -m integration       # só integration
    pytest tests/integration/   # mesma coisa
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    marker = pytest.mark.integration
    for item in items:
        item.add_marker(marker)
