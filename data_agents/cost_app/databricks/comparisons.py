"""
Comparações Pay-as-you-go vs DBCU Commit (1y, 3y).

Funções puras que computam:
  - Custo cumulativo mês a mês ao longo de 36m
  - Break-even point (mês em que commit fica mais barato que PAYG)
  - ROI absoluto (savings totais em 1y/3y)
  - Recomendação textual baseada em utilização esperada

Consumido por:
  - app.py Tab 2 (gráfico breakeven + tabela ROI)
  - exporters.py (sheet "DBCU Comparison")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from data_agents.cost_engine.databricks import (
    DatabricksScenario,
    calculate_databricks_cost,
)


@dataclass
class ComparisonResult:
    """Resultado da comparação PAYG vs DBCU pra um scenario."""

    scenario_id: str | None
    currency: str
    monthly_payg: float
    monthly_dbcu_1y: float
    monthly_dbcu_3y: float
    annual_payg: float
    annual_dbcu_1y: float
    annual_dbcu_3y: float
    savings_1y_annual: float
    savings_3y_annual: float
    savings_1y_pct: float
    savings_3y_pct: float
    cumulative_36m: list[dict[str, float]]
    """Lista de 36 dicts: {month: 1, payg: X, dbcu_1y: Y, dbcu_3y: Z}"""

    breakeven_month_1y: int | None
    """Mês em que 1y commit fica mais barato que PAYG (None se nunca)."""

    breakeven_month_3y: int | None
    """Mês em que 3y commit fica mais barato que PAYG (None se nunca)."""

    recommendation: str
    """Texto curto com recomendação contextual."""


def compute_comparison(scenario: DatabricksScenario) -> ComparisonResult:
    """
    Computa comparação completa PAYG vs DBCU pro scenario.

    Args:
        scenario: cenário a comparar (qualquer DatabricksScenario válido).

    Returns:
        ComparisonResult com totals, cumulativo 36m, breakeven e recomendação.
    """
    result = calculate_databricks_cost(scenario)
    currency = result["currency"]

    monthly_payg = result["totals"]["monthly"]
    monthly_dbcu_1y = result["commit_savings"]["monthly_with_dbcu_1y"]
    monthly_dbcu_3y = result["commit_savings"]["monthly_with_dbcu_3y"]

    annual_payg = monthly_payg * 12
    annual_dbcu_1y = monthly_dbcu_1y * 12
    annual_dbcu_3y = monthly_dbcu_3y * 12

    savings_1y_annual = annual_payg - annual_dbcu_1y
    savings_3y_annual = annual_payg - annual_dbcu_3y

    savings_1y_pct = (savings_1y_annual / annual_payg * 100) if annual_payg > 0 else 0.0
    savings_3y_pct = (savings_3y_annual / annual_payg * 100) if annual_payg > 0 else 0.0

    # Cumulative cost month-by-month over 36 months
    cumulative: list[dict[str, float]] = []
    cum_payg = 0.0
    cum_1y = 0.0
    cum_3y = 0.0
    breakeven_1y: int | None = None
    breakeven_3y: int | None = None

    for month in range(1, 37):
        cum_payg += monthly_payg
        cum_1y += monthly_dbcu_1y
        cum_3y += monthly_dbcu_3y

        cumulative.append(
            {
                "month": month,
                "payg": round(cum_payg, 2),
                "dbcu_1y": round(cum_1y, 2),
                "dbcu_3y": round(cum_3y, 2),
            }
        )

        # Breakeven: primeiro mês em que cumulative dbcu fica menor que payg
        if breakeven_1y is None and cum_1y < cum_payg and monthly_dbcu_1y < monthly_payg:
            breakeven_1y = month
        if breakeven_3y is None and cum_3y < cum_payg and monthly_dbcu_3y < monthly_payg:
            breakeven_3y = month

    # Recomendação contextual
    recommendation = _build_recommendation(
        savings_1y_pct, savings_3y_pct, savings_1y_annual, savings_3y_annual, currency
    )

    return ComparisonResult(
        scenario_id=scenario.scenario_id,
        currency=currency,
        monthly_payg=round(monthly_payg, 2),
        monthly_dbcu_1y=round(monthly_dbcu_1y, 2),
        monthly_dbcu_3y=round(monthly_dbcu_3y, 2),
        annual_payg=round(annual_payg, 2),
        annual_dbcu_1y=round(annual_dbcu_1y, 2),
        annual_dbcu_3y=round(annual_dbcu_3y, 2),
        savings_1y_annual=round(savings_1y_annual, 2),
        savings_3y_annual=round(savings_3y_annual, 2),
        savings_1y_pct=round(savings_1y_pct, 1),
        savings_3y_pct=round(savings_3y_pct, 1),
        cumulative_36m=cumulative,
        breakeven_month_1y=breakeven_1y,
        breakeven_month_3y=breakeven_3y,
        recommendation=recommendation,
    )


def _build_recommendation(
    savings_1y_pct: float,
    savings_3y_pct: float,
    savings_1y_abs: float,
    savings_3y_abs: float,
    currency: str,
) -> str:
    """Constrói texto de recomendação baseado em savings + utilização."""
    if savings_3y_pct == 0 and savings_1y_pct == 0:
        return (
            "💡 **Sem desconto disponível.** O gasto anual está abaixo do tier "
            "mínimo de DBCU commit (USD 10k/ano). Permaneça em Pay-as-you-go."
        )

    if savings_3y_pct < 5:
        return (
            "💡 **Permaneça em Pay-as-you-go.** Savings de DBCU 3y são pequenos "
            f"({savings_3y_pct:.1f}%) e não justificam compromisso de 3 anos. "
            "Workload provavelmente irá evoluir."
        )

    if savings_3y_pct > 30:
        return (
            f"✅ **Forte recomendação: DBCU 3y commit.** Savings de {savings_3y_pct:.1f}% "
            f"(~{currency} {savings_3y_abs:,.0f}/ano) compensam o lock-in de 3 anos. "
            "Workload estabilizado, alto volume."
        )

    if savings_1y_pct > 15:
        return (
            f"✅ **Recomendação: DBCU 1y commit.** Savings de {savings_1y_pct:.1f}% "
            f"(~{currency} {savings_1y_abs:,.0f}/ano) com baixo compromisso. "
            "Boa escolha se workload pode evoluir em 12-24 meses."
        )

    return (
        f"⚖️ **Avaliação caso-a-caso.** Savings moderados (1y: {savings_1y_pct:.1f}%, "
        f"3y: {savings_3y_pct:.1f}%). Considere DBCU 1y se workload estabilizou; "
        "PAYG se ainda está em fase de descoberta."
    )


def get_summary_table(comparison: ComparisonResult) -> list[dict[str, Any]]:
    """
    Retorna lista de dicts pronta pra renderizar como tabela no Streamlit.

    Format compatível com st.dataframe ou pandas.DataFrame.
    """
    return [
        {
            "Opção": "Pay-as-you-go",
            "Mensal": comparison.monthly_payg,
            "Anual": comparison.annual_payg,
            "TCO 36m": round(comparison.annual_payg * 3, 2),
            "Savings vs PAYG": 0.0,
            "Savings %": 0.0,
            "Breakeven": "—",
        },
        {
            "Opção": "DBCU Commit 1 ano",
            "Mensal": comparison.monthly_dbcu_1y,
            "Anual": comparison.annual_dbcu_1y,
            "TCO 36m": round(comparison.annual_dbcu_1y * 3, 2),
            "Savings vs PAYG": comparison.savings_1y_annual,
            "Savings %": comparison.savings_1y_pct,
            "Breakeven": (
                f"mês {comparison.breakeven_month_1y}"
                if comparison.breakeven_month_1y
                else "—"
            ),
        },
        {
            "Opção": "DBCU Commit 3 anos",
            "Mensal": comparison.monthly_dbcu_3y,
            "Anual": comparison.annual_dbcu_3y,
            "TCO 36m": round(comparison.annual_dbcu_3y * 3, 2),
            "Savings vs PAYG": comparison.savings_3y_annual,
            "Savings %": comparison.savings_3y_pct,
            "Breakeven": (
                f"mês {comparison.breakeven_month_3y}"
                if comparison.breakeven_month_3y
                else "—"
            ),
        },
    ]
