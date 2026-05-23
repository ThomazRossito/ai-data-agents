"""
Auto-marker para tests/e2e/ — todo teste deste subdir recebe
@pytest.mark.e2e + @pytest.mark.requires_network sem decorar manualmente.

Testes e2e atingem serviços externos reais (Moonshot/Anthropic, Databricks,
Fabric, OneLake). Exigem credenciais via .env e NÃO devem rodar em air-gapped CI.

Padrão de skip se credenciais ausentes:
    @pytest.fixture
    def databricks_token():
        token = os.environ.get("DATABRICKS_TOKEN", "").strip()
        if not token:
            pytest.skip("requires DATABRICKS_TOKEN")
        return token

Permite seleção:
    pytest -m e2e               # só e2e (nightly cron)
    pytest -m "not e2e"         # tudo menos e2e (default local + CI)
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    e2e_marker = pytest.mark.e2e
    network_marker = pytest.mark.requires_network
    for item in items:
        item.add_marker(e2e_marker)
        item.add_marker(network_marker)
