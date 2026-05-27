"""
Agregação de múltiplos cenários (Tab 3: Workloads Múltiplos).

Permite combinar N DatabricksScenarios e calcular total mensal + breakdown
por contribuição. Útil pra projetos inteiros que têm múltiplos clusters/jobs:

    Workload 1: ETL Bronze (Jobs Premium 4w 24/7)        → $1,200/mês
    Workload 2: All-Purpose dev (sandbox 4w 8x22d)        → $400/mês
    Workload 3: SQL Pro warehouse (SMALL 4h x 22d)        → $200/mês
    ─────────────────────────────────────────────────────────────
    PROJETO TOTAL                                          → $1,800/mês

Funções puras que computam:
  - aggregate_workloads(scenarios): soma + breakdown por nome
  - get_contribution_by_compute_type(scenarios): % por tipo
  - get_contribution_by_cloud(scenarios): % por cloud
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from data_agents.cost_engine.databricks import (
    DatabricksScenario,
    calculate_databricks_cost,
)


@dataclass
class WorkloadEntry:
    """Um workload dentro do agregado."""

    name: str
    description: str
    scenario: DatabricksScenario
    monthly_cost: float
    annual_cost: float
    breakdown_dbu_hourly: float
    breakdown_instance_hourly: float


@dataclass
class WorkloadAggregate:
    """Resultado da agregação de N workloads."""

    workloads: list[WorkloadEntry]
    total_monthly: float
    total_annual: float
    total_tco_36m: float
    currency: str

    # Breakdowns
    dbu_total_monthly: float
    """Quanto da total_monthly veio de DBU cost."""

    instance_total_monthly: float
    """Quanto da total_monthly veio de Instance cost."""

    by_compute_type: dict[str, float]
    """{compute_type: total_monthly_contribution}"""

    by_cloud: dict[str, float]
    """{'azure': total_monthly, 'aws': total_monthly}"""

    warnings: list[str]


def aggregate_workloads(
    workloads: list[tuple[str, str, DatabricksScenario]],
) -> WorkloadAggregate:
    """
    Agrega N workloads e retorna total + breakdown.

    Args:
        workloads: lista de tuplas (name, description, scenario).
            Ex: [("ETL Bronze", "Jobs noturno", scenario1),
                 ("Dev sandbox", "All-purpose 8h", scenario2)]

    Returns:
        WorkloadAggregate com totals e breakdowns.

    Raises:
        ValueError: se workloads estiver vazio ou misturar currencies diferentes.
    """
    if not workloads:
        raise ValueError("Lista de workloads vazia.")

    # Valida que todos os scenarios usam a mesma currency (não tem sentido somar USD + BRL)
    currencies = {s.currency_label for _, _, s in workloads}
    if len(currencies) > 1:
        raise ValueError(
            f"Workloads usam currencies diferentes ({currencies}). Use a mesma currency em todos."
        )

    currency = workloads[0][2].currency_label
    fx_rate = workloads[0][2].currency_conversion_rate

    entries: list[WorkloadEntry] = []
    total_monthly = 0.0
    total_annual = 0.0
    dbu_total_hourly = 0.0
    instance_total_hourly = 0.0
    by_compute_type: dict[str, float] = {}
    by_cloud: dict[str, float] = {}
    warnings: list[str] = []

    for name, description, scenario in workloads:
        try:
            result = calculate_databricks_cost(scenario)
        except ValueError as exc:
            warnings.append(f"⚠️ Workload '{name}' falhou: {exc}")
            continue

        monthly = result["totals"]["monthly"]
        annual = result["totals"]["annual"]
        dbu_h = result["breakdown_hourly_usd"]["dbu_total"]
        inst_h = result["breakdown_hourly_usd"]["instance_total"]
        hours = result["inputs_resolved"]["hours_per_month"]

        entry = WorkloadEntry(
            name=name,
            description=description,
            scenario=scenario,
            monthly_cost=round(monthly, 2),
            annual_cost=round(annual, 2),
            breakdown_dbu_hourly=round(dbu_h, 4),
            breakdown_instance_hourly=round(inst_h, 4),
        )
        entries.append(entry)

        total_monthly += monthly
        total_annual += annual
        # DBU + Instance hourly precisam ser multiplicados pelas horas reais do mês
        # e pelo fx_rate pra ficar no mesmo eixo da total_monthly
        dbu_total_hourly += dbu_h * hours * fx_rate
        instance_total_hourly += inst_h * hours * fx_rate

        # By compute_type
        ct = scenario.compute_type
        by_compute_type[ct] = by_compute_type.get(ct, 0.0) + monthly

        # By cloud
        cl = scenario.cloud
        by_cloud[cl] = by_cloud.get(cl, 0.0) + monthly

    return WorkloadAggregate(
        workloads=entries,
        total_monthly=round(total_monthly, 2),
        total_annual=round(total_annual, 2),
        total_tco_36m=round(total_annual * 3, 2),
        currency=currency,
        dbu_total_monthly=round(dbu_total_hourly, 2),
        instance_total_monthly=round(instance_total_hourly, 2),
        by_compute_type={k: round(v, 2) for k, v in by_compute_type.items()},
        by_cloud={k: round(v, 2) for k, v in by_cloud.items()},
        warnings=warnings,
    )


def get_summary_table(aggregate: WorkloadAggregate) -> list[dict[str, Any]]:
    """
    Retorna lista pronta pra renderizar como tabela no Streamlit.
    Última linha = TOTAL.
    """
    rows: list[dict[str, Any]] = []
    for entry in aggregate.workloads:
        rows.append(
            {
                "Workload": entry.name,
                "Cloud": entry.scenario.cloud,
                "Compute Type": entry.scenario.compute_type,
                "Driver": entry.scenario.driver_instance,
                "Workers": entry.scenario.num_workers,
                "Mensal": entry.monthly_cost,
                "Anual": entry.annual_cost,
                "% do Total": round(entry.monthly_cost / aggregate.total_monthly * 100, 1)
                if aggregate.total_monthly > 0
                else 0.0,
            }
        )
    # Linha TOTAL
    rows.append(
        {
            "Workload": "**TOTAL**",
            "Cloud": "—",
            "Compute Type": f"{len(aggregate.workloads)} workloads",
            "Driver": "—",
            "Workers": "—",
            "Mensal": aggregate.total_monthly,
            "Anual": aggregate.total_annual,
            "% do Total": 100.0,
        }
    )
    return rows
