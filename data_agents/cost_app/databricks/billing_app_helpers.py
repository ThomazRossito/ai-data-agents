"""
Helpers do Streamlit App pra Tab 'FinOps Realizado' (Chunk 3.3).

Wrappa o engine `cost_engine.billing` + mock generator `billing_mock` numa
interface conveniente pra UI Streamlit. Mantém o app.py limpo de lógica
de carregamento de DataFrames.

Padrão:
  - `load_billing_data(period, cloud, mock=True)` → (usage_df, prices_df)
  - `format_compare_dataframe(scenarios, ...)` → DataFrame para st.dataframe

Quando real mode (mock=False) for implementado num chunk posterior, o
helper ganha branch pra usar databricks-sdk + warehouse_id. Por enquanto,
real mode levanta RuntimeError igual ao MCP server.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from data_agents.cost_engine.billing import BillingPeriod

if TYPE_CHECKING:
    import pandas as pd


def load_billing_data(
    period: BillingPeriod,
    cloud: str = "AZURE",
    mock: bool = True,
    seed: int = 42,
) -> tuple:
    """
    Carrega usage_df + prices_df para o App.

    Args:
        period: BillingPeriod com janela.
        cloud: "AZURE" ou "AWS".
        mock: True usa generator sintético. False usa SQL real via
            databricks-sdk (Chunk 3.4).
        seed: seed do mock pra reprodutibilidade nos testes (ignorado em real).

    Returns:
        (usage_df, prices_df) — DataFrames já no schema do engine.

    Raises:
        RuntimeError: se mock=False e config do real mode está inválida
            (DATABRICKS_HOST/TOKEN/BILLING_WAREHOUSE_ID ausentes) ou se a
            execução SQL falhar (permissão, warehouse pausado, UC desabilitado).
    """
    if not mock:
        # Real mode (Chunk 3.4) — usa o mesmo loader do MCP pra consistência
        from data_agents.cost_app.databricks.billing_real import load_real_dataframes

        days_back = max(period.days + 10, 60)
        return load_real_dataframes(cloud=cloud, days_back=days_back, use_cache=True)

    from data_agents.cost_app.databricks.billing_mock import (
        generate_mock_list_prices_df,
        generate_mock_usage_df,
    )

    # Gera dias suficientes pra cobrir a janela + buffer
    days_to_generate = max(period.days + 10, 60)
    usage_df = generate_mock_usage_df(days=days_to_generate, cloud=cloud, seed=seed)
    prices_df = generate_mock_list_prices_df(cloud=cloud)
    return usage_df, prices_df


def format_compare_dataframe(
    scenario_name: str,
    estimated_monthly_usd: float,
    actual_monthly_usd: float,
    variance_pct: float,
    verdict: str,
    actual_period_days: int,
) -> pd.DataFrame:
    """
    Monta DataFrame de 1 linha pra exibir no st.dataframe da seção compare.

    Args:
        scenario_name: nome display do cenário.
        estimated_monthly_usd: custo estimado mensal (Fase 2).
        actual_monthly_usd: custo real extrapolado pro mensal.
        variance_pct: (actual - estimate) / estimate × 100.
        verdict: "on_budget" | "over_budget" | "under_budget".
        actual_period_days: dias da janela analisada (caveat de extrapolação).

    Returns:
        DataFrame com colunas amigáveis pra UI.
    """
    import pandas as pd

    verdict_labels = {
        "on_budget": "✅ On Budget (±10%)",
        "over_budget": "⚠️ Over Budget (>+10%)",
        "under_budget": "🔍 Under Budget (<-10%)",
    }
    return pd.DataFrame(
        [
            {
                "Cenário": scenario_name,
                "Estimado/mês": f"${estimated_monthly_usd:,.2f}",
                "Real/mês (extrapolado)": f"${actual_monthly_usd:,.2f}",
                "Variance": f"{variance_pct:+.2f}%",
                "Verdict": verdict_labels.get(verdict, verdict),
                "Janela actual": f"{actual_period_days} dias",
            }
        ]
    )


def interpret_verdict(verdict: str, variance_pct: float) -> str:
    """
    Mensagem interpretativa pro user, alinhada com kb/estimate-vs-actual.md.

    Args:
        verdict: "on_budget" | "over_budget" | "under_budget".
        variance_pct: usado pra detalhar magnitude.

    Returns:
        Texto markdown pronto pra st.info / st.warning / st.success.
    """
    if verdict == "on_budget":
        return (
            f"✅ **Cenário validado pelo realizado** (variance {variance_pct:+.1f}%). "
            "Pode usar pra projeção de TCO e comparação PAYG vs DBCU com confiança. "
            "Recomendação: monitorar trimestralmente."
        )
    if verdict == "over_budget":
        return (
            f"⚠️ **Workload consumindo +{variance_pct:.1f}% acima do estimado.** "
            "Causas comuns: sizing subestimado (autoscale), hours/day maior, "
            "Photon ativado depois, mudança de SKU. **Investigue antes de ajustar** — "
            "rode `get_top_cost_clusters` filtrado pelo cluster pra ver pico real."
        )
    if verdict == "under_budget":
        return (
            f"🔍 **Workload consumindo {variance_pct:+.1f}% abaixo do estimado.** "
            "Possíveis causas: cenário superdimensionado, autoscale eficiente, "
            "redução de volume, idle não contabilizado. **Oportunidade**: ajustar "
            "cenário pra refletir realidade e liberar budget pra outros workloads."
        )
    return f"Verdict desconhecido: {verdict}"
