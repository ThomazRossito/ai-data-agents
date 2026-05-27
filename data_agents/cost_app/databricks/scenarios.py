"""
Persistência de cenários Databricks em JSON.

Estratégia: cenários ficam em `outputs/cost-scenarios/<uuid>.json` com
metadata + payload do DatabricksScenario. Bridge Agent → App e vice-versa:

  - Agent salva via MCP tool `databricks_pricing_save_scenario(source='agent')`
  - App lista no Tab Histórico via `list_saved_scenarios()`
  - User edita cenário no App e salva → source='app-edited' + parent_uuid
  - Agent carrega cenário existente via MCP `databricks_pricing_load_scenario(uuid)`
    pra calcular variantes ("carrega XYZ e troca pra 8 workers")

Source vocabulary (consistente em todo o sistema):
  - 'manual'      → user criou novo no App
  - 'agent'       → databricks-cost-calculator gravou via save_scenario tool
  - 'app-edited'  → user carregou um cenário (de qualquer source) e re-salvou
                    com modificações. Inclui parent_uuid pra rastrear linhagem.
  - 'import'      → reservado pra futura tool de import (CSV, scenarios_used.json)

Schema version 1.1.0 (Chunk 2.3): adiciona campo opcional parent_uuid.
Load aceita 1.0.0 e 1.1.0 (parent_uuid default None se ausente).

Funcionalidade:
  - save_scenario(scenario, name, description, source, parent_uuid) → uuid
  - load_scenario(uuid) → DatabricksScenario
  - load_envelope(uuid) → dict completo (uuid, name, source, parent_uuid, scenario)
  - list_saved_scenarios(filter_source?, filter_cloud?) → list[dict]
  - search_scenarios(query, limit=10) → list[dict] (fuzzy match name+description)
  - delete_scenario(uuid) → bool
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


_VALID_SOURCES = frozenset({"manual", "agent", "app-edited", "import"})


def save_scenario(
    scenario: DatabricksScenario,
    name: str,
    description: str = "",
    source: str = "manual",
    parent_uuid: str | None = None,
) -> str:
    """
    Persiste um DatabricksScenario em JSON com metadata.

    Args:
        scenario: cenário a persistir.
        name: nome curto display (ex: "ETL Bronze produção").
        description: descrição opcional (texto longo).
        source: origem do scenario. Valores permitidos:
            - "manual"     → user criou novo no App
            - "agent"      → databricks-cost-calculator via MCP tool
            - "app-edited" → user editou cenário existente no App (informar parent_uuid)
            - "import"     → reservado pra import bulk
        parent_uuid: UUID do cenário pai (obrigatório para source='app-edited',
            opcional para os outros). Permite rastrear linhagem de edições.

    Returns:
        UUID v4 do scenario salvo (também é o filename: <uuid>.json).

    Raises:
        ValueError: se source não está em _VALID_SOURCES.
    """
    if source not in _VALID_SOURCES:
        raise ValueError(f"source={source!r} inválido. Permitidos: {sorted(_VALID_SOURCES)}")

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
        "parent_uuid": parent_uuid,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "1.1.0",
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


def load_envelope(scenario_uuid: str) -> dict[str, Any]:
    """
    Carrega o envelope completo (metadata + scenario) por UUID.

    Útil quando o caller precisa de `name`, `description`, `source`, `parent_uuid`
    além do DatabricksScenario reconstruído. Para uso direto pelo App e por
    tools MCP (`databricks_pricing_load_scenario`).

    Args:
        scenario_uuid: UUID v4 retornado por save_scenario.

    Returns:
        Dict com chaves: uuid, name, description, source, parent_uuid, created_at,
        schema_version, scenario (dict serializado do DatabricksScenario).

    Raises:
        FileNotFoundError: se UUID não existir.
    """
    scenarios_dir = _get_scenarios_dir()
    path = scenarios_dir / f"{scenario_uuid}.json"

    if not path.exists():
        raise FileNotFoundError(f"Scenario {scenario_uuid!r} não encontrado em {path}")

    with open(path, encoding="utf-8") as f:
        envelope: dict[str, Any] = json.load(f)

    # Backward-compat: schema 1.0.0 não tinha parent_uuid
    envelope.setdefault("parent_uuid", None)
    return envelope


def list_saved_scenarios(
    filter_source: str | None = None,
    filter_cloud: str | None = None,
) -> list[dict[str, Any]]:
    """
    Lista todos os cenários salvos com metadata (sem carregar o scenario inteiro).

    Args:
        filter_source: se informado, retorna só cenários com esse source
            (ex: "agent" pra ver só os do agent). None = todos.
        filter_cloud: se informado, retorna só cenários com esse cloud
            (ex: "azure"). None = todos.

    Returns:
        Lista de dicts ordenada por created_at DESC. Cada dict tem:
            uuid, name, description, source, parent_uuid, created_at,
            cloud, compute_type, filepath
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
                    "parent_uuid": envelope.get("parent_uuid"),  # default None
                    "created_at": envelope.get("created_at", ""),
                    "cloud": envelope.get("scenario", {}).get("cloud", "?"),
                    "compute_type": envelope.get("scenario", {}).get("compute_type", "?"),
                    "filepath": str(path),
                }
            )
        except (json.JSONDecodeError, KeyError):
            # Arquivo corrompido — pula silenciosamente
            continue

    # Aplica filtros
    if filter_source is not None:
        entries = [e for e in entries if e["source"] == filter_source]
    if filter_cloud is not None:
        entries = [e for e in entries if e["cloud"] == filter_cloud]

    # Ordena DESC por created_at
    entries.sort(key=lambda e: e["created_at"], reverse=True)
    return entries


def search_scenarios(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """
    Busca fuzzy por nome ou descrição (case-insensitive substring match).

    Útil pro agent encontrar "o cenário do ETL banco z" sem decorar UUIDs.

    Args:
        query: termo de busca. Case-insensitive. Vazio retorna [].
        limit: máximo de resultados retornados (default 10).

    Returns:
        Lista ordenada por relevância (matches no name primeiro, depois
        description), tie-break por created_at DESC.
    """
    query_lower = query.strip().lower()
    if not query_lower:
        return []

    all_entries = list_saved_scenarios()
    matched: list[tuple[int, dict[str, Any]]] = []

    for entry in all_entries:
        name_lower = entry["name"].lower()
        desc_lower = entry["description"].lower()

        # Score: match no nome conta 2× match na descrição
        if query_lower in name_lower:
            score = 2
        elif query_lower in desc_lower:
            score = 1
        else:
            continue

        matched.append((score, entry))

    # Ordena por score DESC, depois por created_at DESC (já vem ordenado de list_saved_scenarios)
    matched.sort(key=lambda t: t[0], reverse=True)
    return [entry for _score, entry in matched[:limit]]


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
