"""
Persistência de cenários Databricks em JSON.

Estratégia: cenários ficam em `outputs/cost-scenarios/<uuid>.json` com
metadata + payload do DatabricksScenario. Bridge Agent → App: na Fase 2,
o agent `databricks-cost-calculator` grava cenário aqui e retorna link
clicável; o App lista esses arquivos no dropdown e carrega.

Funcionalidade:
  - save_scenario(scenario, name, description) → uuid
  - load_scenario(uuid) → DatabricksScenario
  - list_saved_scenarios() → list[dict] com metadata
  - delete_scenario(uuid)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data_agents.cost_engine.databricks import DatabricksScenario


# Path padrão: outputs/cost-scenarios/ (na raiz do projeto)
# Configurável via env COST_SCENARIOS_DIR
_DEFAULT_SCENARIOS_DIR = Path(__file__).parent.parent.parent.parent / "outputs" / "cost-scenarios"


def _get_scenarios_dir() -> Path:
    """Resolve diretório de cenários, criando se não existir."""
    import os

    dir_env = os.environ.get("COST_SCENARIOS_DIR")
    if dir_env:
        scenarios_dir = Path(dir_env)
    else:
        scenarios_dir = _DEFAULT_SCENARIOS_DIR

    scenarios_dir.mkdir(parents=True, exist_ok=True)
    return scenarios_dir


def save_scenario(
    scenario: DatabricksScenario,
    name: str,
    description: str = "",
    source: str = "manual",
) -> str:
    """
    Persiste um DatabricksScenario em JSON com metadata.

    Args:
        scenario: cenário a persistir.
        name: nome curto display (ex: "ETL Bronze produção").
        description: descrição opcional (texto longo).
        source: origem do scenario ("manual", "agent", "import").

    Returns:
        UUID v4 do scenario salvo (também é o filename: <uuid>.json).
    """
    scenarios_dir = _get_scenarios_dir()
    scenario_uuid = str(uuid.uuid4())

    # Converte dataclass pra dict (asdict é serializável)
    payload = asdict(scenario)

    # Garante que scenario_id no payload casa com o uuid de arquivo
    payload["scenario_id"] = scenario_uuid

    envelope = {
        "uuid": scenario_uuid,
        "name": name,
        "description": description,
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "1.0.0",
        "scenario": payload,
    }

    output_path = scenarios_dir / f"{scenario_uuid}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2, ensure_ascii=False)

    return scenario_uuid


def load_scenario(scenario_uuid: str) -> DatabricksScenario:
    """
    Carrega um scenario por UUID e retorna o DatabricksScenario reconstruído.

    Args:
        scenario_uuid: UUID v4 retornado por save_scenario.

    Returns:
        DatabricksScenario reconstruído (pronto pra calculate_databricks_cost).

    Raises:
        FileNotFoundError: se UUID não existir.
        ValueError: se schema_version incompatível.
    """
    scenarios_dir = _get_scenarios_dir()
    path = scenarios_dir / f"{scenario_uuid}.json"

    if not path.exists():
        raise FileNotFoundError(f"Scenario {scenario_uuid!r} não encontrado em {path}")

    with open(path, encoding="utf-8") as f:
        envelope = json.load(f)

    schema_version = envelope.get("schema_version", "0.0.0")
    if not schema_version.startswith("1."):
        raise ValueError(f"Schema incompatível: {schema_version}. Esperado 1.x")

    return DatabricksScenario(**envelope["scenario"])


def list_saved_scenarios() -> list[dict[str, Any]]:
    """
    Lista todos os cenários salvos com metadata (sem carregar o scenario inteiro).

    Returns:
        Lista de dicts ordenada por created_at DESC. Cada dict tem:
            - uuid, name, description, source, created_at, cloud, compute_type
    """
    scenarios_dir = _get_scenarios_dir()
    entries: list[dict[str, Any]] = []

    for path in scenarios_dir.glob("*.json"):
        try:
            with open(path, encoding="utf-8") as f:
                envelope = json.load(f)
            entries.append(
                {
                    "uuid": envelope.get("uuid", path.stem),
                    "name": envelope.get("name", "(sem nome)"),
                    "description": envelope.get("description", ""),
                    "source": envelope.get("source", "unknown"),
                    "created_at": envelope.get("created_at", ""),
                    "cloud": envelope.get("scenario", {}).get("cloud", "?"),
                    "compute_type": envelope.get("scenario", {}).get("compute_type", "?"),
                    "filepath": str(path),
                }
            )
        except (json.JSONDecodeError, KeyError):
            # Arquivo corrompido — pula silenciosamente
            continue

    # Ordena DESC por created_at
    entries.sort(key=lambda e: e["created_at"], reverse=True)
    return entries


def delete_scenario(scenario_uuid: str) -> bool:
    """
    Deleta um scenario. Retorna True se removeu, False se não existia.
    """
    scenarios_dir = _get_scenarios_dir()
    path = scenarios_dir / f"{scenario_uuid}.json"

    if not path.exists():
        return False

    path.unlink()
    return True
