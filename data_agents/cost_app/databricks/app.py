"""
Databricks Cost Calculator — Streamlit App.

Rodar standalone:
    streamlit run data_agents/cost_app/databricks/app.py --server.port=8514

Layout:
    [Sidebar]
      - Header + mock warning
      - Cloud + Region (filtros globais)
      - Currency converter (USD↔BRL)
      - Saved scenarios

    [Main]
      - Tab 1: Cenário Cluster (Chunk 1.2 — REDESENHADO)
      - Tab 2: Compare PAYG vs DBCU (Chunk 1.3)
      - Tab 3: Workloads múltiplos (Chunk 1.3)
      - Tab 4: Export XLSX (Chunk 1.3)
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from data_agents.cost_app.databricks.comparisons import (
    compute_comparison,
    get_summary_table as get_comparison_table,
)
from data_agents.cost_app.databricks.exporters import (
    build_xlsx_multi_scenarios,
    suggest_filename,
)
from data_agents.cost_app.databricks.instance_prices import (
    get_instance_price_usd_per_hour,
    get_mock_metadata,
    list_instances_for_region,
    list_regions_for_cloud,
)
from data_agents.cost_app.databricks.scenarios import (
    list_saved_scenarios,
    load_scenario,
    save_scenario,
)
from data_agents.cost_app.databricks.workloads import (
    aggregate_workloads,
    get_summary_table as get_workloads_table,
)
from data_agents.cost_engine.databricks import (
    DatabricksScenario,
    calculate_databricks_cost,
    load_databricks_catalog,
)


# ─── Page config ─────────────────────────────────────────────────────────────


st.set_page_config(
    page_title="Databricks Cost Calculator",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS customizado pra refinar visual
st.markdown(
    """
<style>
    /* Remove top padding da main area */
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }

    /* Containers com borda: mais escuro pra ter contraste */
    div[data-testid="stMetric"] {
        background-color: #1A1F2C;
        padding: 12px 16px;
        border-radius: 8px;
        border-left: 4px solid #FF6B6B;
    }

    /* Tabs: mais espaço */
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 16px;
        font-weight: 500;
    }

    /* Sidebar header */
    section[data-testid="stSidebar"] h1 { font-size: 1.4rem; margin-bottom: 0; }
</style>
""",
    unsafe_allow_html=True,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


@st.cache_data(ttl=300)
def _cached_catalog(cloud: str) -> dict:
    """Carrega catalog YAML uma vez por sessão (TTL 5min)."""
    return load_databricks_catalog(cloud)  # type: ignore[arg-type]


def _format_money(value: float, currency: str = "USD") -> str:
    """Formata número como moeda. Cifrão escapado pra não virar TeX no Streamlit."""
    if currency == "BRL":
        formatted = f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return formatted
    # IMPORTANTE: escape \\$ pra Streamlit não interpretar como LaTeX math
    return f"\\${value:,.2f}"


def _format_money_plain(value: float, currency: str = "USD") -> str:
    """Formata moeda sem escape (uso em st.metric que não interpreta TeX)."""
    if currency == "BRL":
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"$ {value:,.2f}"


def _init_session_state() -> None:
    """Inicializa session_state com defaults."""
    defaults = {
        "cloud": "azure",
        "region": "brazilsouth",
        "currency_label": "USD",
        "currency_rate": 1.0,
        "loaded_scenario_uuid": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ─── Sidebar ─────────────────────────────────────────────────────────────────


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("# 💰 Databricks Cost")
        st.caption("Calculator multi-cloud · Azure + AWS")

        st.divider()

        # Cloud + Region
        st.markdown("### 🌐 Cloud + Region")
        cloud = st.selectbox(
            "Cloud Provider",
            options=["azure", "aws"],
            format_func=lambda c: {"azure": "Azure Databricks", "aws": "AWS Databricks"}[c],
            key="cloud",
            label_visibility="collapsed",
        )
        regions = list_regions_for_cloud(cloud)  # type: ignore[arg-type]
        if st.session_state.region not in regions:
            st.session_state.region = regions[0]
        st.selectbox(
            "Region",
            options=regions,
            key="region",
            help="Brasil = brazilsouth / sa-east-1",
        )

        # Currency
        st.markdown("### 💱 Moeda")
        currency = st.selectbox(
            "Display em:",
            options=["USD", "BRL"],
            key="currency_label",
            label_visibility="collapsed",
        )
        if currency == "BRL":
            st.number_input(
                "USD → BRL",
                min_value=1.0,
                max_value=20.0,
                value=st.session_state.currency_rate
                if st.session_state.currency_rate > 1.0
                else 5.0,
                step=0.01,
                key="currency_rate",
            )
        else:
            st.session_state.currency_rate = 1.0

        # Saved scenarios
        st.markdown("### 📂 Cenários")
        saved = list_saved_scenarios()
        if saved:
            options = ["(novo)"] + [f"{e['name'][:25]} · {e['cloud']}" for e in saved]
            uuids = [None] + [e["uuid"] for e in saved]
            selected_idx = st.selectbox(
                "Carregar",
                options=range(len(options)),
                format_func=lambda i: options[i],
                label_visibility="collapsed",
            )
            if selected_idx > 0 and st.button("📥 Carregar", use_container_width=True):
                st.session_state.loaded_scenario_uuid = uuids[selected_idx]
                st.rerun()
        else:
            st.caption("Nenhum cenário salvo ainda.")
        st.caption(f"📊 {len(saved)} totais")

        st.divider()

        # Mock warning no rodapé (menos chamativo)
        meta = get_mock_metadata()
        if meta["is_mock"]:
            with st.expander("⚠️ Mock pricing (clique pra detalhes)"):
                st.markdown(
                    f"**Última atualização:** {meta['last_updated']}\n\n"
                    f"Instance prices estimados localmente. "
                    f"Fase 2 substitui por API oficial.\n\n"
                    f"- Azure: {meta['azure_regions_count']} regions, "
                    f"{meta['total_skus_azure']} SKUs\n"
                    f"- AWS: {meta['aws_regions_count']} regions, "
                    f"{meta['total_skus_aws']} SKUs"
                )

        st.caption("🔗 [GitHub](https://github.com/ThomazRossito/ai-data-agents) · v1.2")


# ─── Tab 1: Cenário Cluster ─────────────────────────────────────────────────


def render_tab_cenario_cluster() -> None:
    cloud = st.session_state.cloud
    region = st.session_state.region
    catalog = _cached_catalog(cloud)

    # Pre-load do scenario salvo
    loaded: DatabricksScenario | None = None
    if st.session_state.loaded_scenario_uuid:
        try:
            loaded = load_scenario(st.session_state.loaded_scenario_uuid)
            st.success(
                f"📥 Cenário `{loaded.scenario_id[:8] if loaded.scenario_id else 'N/A'}` carregado",
                icon="✅",
            )
        except FileNotFoundError:
            st.session_state.loaded_scenario_uuid = None

    col_form, col_result = st.columns([5, 7], gap="large")

    # ─── COLUNA FORM ────────────────────────────────────────────────────────
    with col_form:
        with st.container(border=True):
            st.markdown("#### ⚙️ Configuração")

            # Compute Type + Tier (lado a lado)
            compute_options = [
                "all_purpose_compute",
                "jobs_compute",
                "delta_live_tables",
                "sql",
                "serverless_compute",
                "model_serving",
                "vector_search",
                "mosaic_agent",
            ]
            compute_type = st.selectbox(
                "Compute Type",
                options=compute_options,
                index=compute_options.index(loaded.compute_type) if loaded else 1,
                format_func=lambda c: {
                    "all_purpose_compute": "All-Purpose (notebooks)",
                    "jobs_compute": "Jobs (scheduled)",
                    "delta_live_tables": "Delta Live Tables",
                    "sql": "SQL Warehouse",
                    "serverless_compute": "Serverless",
                    "model_serving": "Model Serving",
                    "vector_search": "Vector Search",
                    "mosaic_agent": "Mosaic AI Agent",
                }[c],
            )

            tier_options = ["standard", "premium", "enterprise"]
            if compute_type == "delta_live_tables":
                tier_options = ["core", "pro", "advanced"]
            elif compute_type == "sql":
                tier_options = ["classic", "pro", "serverless"]

            col_t, col_p = st.columns([2, 1])
            with col_t:
                tier = st.selectbox(
                    "Tier",
                    options=tier_options,
                    index=min(
                        tier_options.index(loaded.tier)
                        if loaded and loaded.tier in tier_options
                        else 1,
                        len(tier_options) - 1,
                    ),
                )
            with col_p:
                st.markdown("&nbsp;")  # spacer pra alinhar baseline
                photon = st.toggle(
                    "🚀 Photon",
                    value=loaded.photon if loaded else False,
                    help="Photon dobra DBU mas reduz wall-clock. Break-even: 2x speedup.",
                )

        with st.container(border=True):
            st.markdown("#### 🖥️ Instances")

            all_skus = list_instances_for_region(cloud, region)  # type: ignore[arg-type]
            catalog_skus = set(catalog["instance_dbu_map"].keys())
            valid_skus = [sku for sku in all_skus if sku in catalog_skus]

            if not valid_skus:
                st.error(f"Nenhuma instance em {cloud}/{region} tem DBU mapping no catalog.")
                return

            default_driver = (
                loaded.driver_instance
                if loaded and loaded.driver_instance in valid_skus
                else valid_skus[0]
            )
            default_worker = (
                loaded.worker_instance
                if loaded and loaded.worker_instance in valid_skus
                else valid_skus[0]
            )

            driver_instance = st.selectbox(
                "Driver Instance",
                options=valid_skus,
                index=valid_skus.index(default_driver),
            )
            worker_instance = st.selectbox(
                "Worker Instance",
                options=valid_skus,
                index=valid_skus.index(default_worker),
            )
            num_workers = st.number_input(
                "Número de Workers",
                min_value=0,
                max_value=200,
                value=loaded.num_workers if loaded else 4,
                help="0 = single-node. Não inclui o driver.",
            )

        with st.container(border=True):
            st.markdown("#### 📅 Schedule")

            col_h, col_d = st.columns(2)
            with col_h:
                hours_per_day = st.slider(
                    "Horas/dia",
                    min_value=1.0,
                    max_value=24.0,
                    value=loaded.hours_per_day if loaded else 8.0,
                    step=0.5,
                )
            with col_d:
                days_per_month = st.slider(
                    "Dias/mês",
                    min_value=1,
                    max_value=31,
                    value=loaded.days_per_month if loaded else 22,
                )
            autoscale_pct = st.slider(
                "Autoscale médio (%)",
                min_value=0,
                max_value=100,
                value=int(loaded.autoscale_avg_workers_pct) if loaded else 100,
                help="100 = sempre no max. Reduz pra modelar autoscaling.",
            )

        with st.container(border=True):
            st.markdown("#### 💸 Modelo de Pricing")

            pricing_options = ["on_demand", "spot", "reserved_1y", "reserved_3y"]
            pricing_model = st.selectbox(
                "Instance Pricing",
                options=pricing_options,
                index=pricing_options.index(loaded.instance_pricing_model) if loaded else 0,
                format_func=lambda p: {
                    "on_demand": "On-Demand",
                    "spot": "Spot/Low-Priority (~60-80% off)",
                    "reserved_1y": "Reserved 1y (~25-32% off)",
                    "reserved_3y": "Reserved 3y (~45-58% off)",
                }[p],
                label_visibility="collapsed",
            )

            photon_speedup: float | None = None
            if photon:
                # loaded pode ser None (cenário novo, sem carregar saved)
                default_speedup = loaded.photon_speedup_factor or 2.5 if loaded is not None else 2.5
                photon_speedup = st.number_input(
                    "Photon speedup esperado (x)",
                    min_value=1.0,
                    max_value=10.0,
                    value=default_speedup,
                    step=0.1,
                    help="Default 2.5x (típico SQL). <2x = Photon ENCARECE.",
                )

    # ─── COLUNA RESULT ──────────────────────────────────────────────────────
    with col_result:
        # Resolve instance prices
        try:
            driver_price = get_instance_price_usd_per_hour(cloud, region, driver_instance)  # type: ignore[arg-type]
            worker_price = get_instance_price_usd_per_hour(cloud, region, worker_instance)  # type: ignore[arg-type]
        except KeyError as exc:
            st.error(f"Instance price não encontrado: {exc}")
            return

        # Monta + calcula
        try:
            scenario = DatabricksScenario(
                cloud=cloud,  # type: ignore[arg-type]
                compute_type=compute_type,  # type: ignore[arg-type]
                tier=tier,  # type: ignore[arg-type]
                photon=photon,
                driver_instance=driver_instance,
                worker_instance=worker_instance,
                num_workers=num_workers,
                hours_per_day=hours_per_day,
                days_per_month=days_per_month,
                region=region,
                instance_pricing_model=pricing_model,  # type: ignore[arg-type]
                driver_instance_cost_per_hour_usd=driver_price,
                worker_instance_cost_per_hour_usd=worker_price,
                autoscale_avg_workers_pct=autoscale_pct,
                photon_speedup_factor=photon_speedup,
                currency_conversion_rate=st.session_state.currency_rate,
                currency_label=st.session_state.currency_label,
            )
            result = calculate_databricks_cost(scenario, catalog)
        except ValueError as exc:
            st.error(f"Erro no cálculo: {exc}")
            return

        currency = result["currency"]
        breakdown = result["breakdown_hourly_usd"]
        commit = result["commit_savings"]

        # ─── METRICS TOP ────────────────────────────────────────────────────
        st.markdown("### 💵 Custo Estimado")
        col_m, col_a, col_t = st.columns(3)
        with col_m:
            st.metric(
                "Mensal",
                _format_money_plain(result["totals"]["monthly"], currency),
            )
        with col_a:
            st.metric(
                "Anual",
                _format_money_plain(result["totals"]["annual"], currency),
            )
        with col_t:
            st.metric(
                "TCO 36 meses",
                _format_money_plain(result["totals"]["tco_36m"], currency),
            )

        # ─── GRÁFICO BREAKDOWN ─────────────────────────────────────────────
        with st.container(border=True):
            st.markdown("#### 📊 Breakdown do Custo Hourly")

            # Donut chart: DBU vs Instance
            fig = go.Figure(
                data=[
                    go.Pie(
                        labels=["DBU Cost", "Instance Cost"],
                        values=[breakdown["dbu_total"], breakdown["instance_total"]],
                        hole=0.55,
                        marker=dict(colors=["#FF6B6B", "#4ECDC4"]),
                        textinfo="label+percent",
                        textfont=dict(size=14, color="white"),
                        hovertemplate="<b>%{label}</b><br>$%{value:.4f}/h<br>%{percent}<extra></extra>",
                    )
                ]
            )
            fig.update_layout(
                showlegend=False,
                margin=dict(t=20, b=20, l=0, r=0),
                height=240,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                annotations=[
                    dict(
                        text=f"<b>${breakdown['cluster_total']:.2f}/h</b><br><span style='font-size:10px'>cluster total</span>",
                        x=0.5,
                        y=0.5,
                        font=dict(size=18, color="white"),
                        showarrow=False,
                    )
                ],
            )
            st.plotly_chart(fig, use_container_width=True)

            # Tabela compacta abaixo do gráfico
            col_dbu, col_inst = st.columns(2)
            with col_dbu:
                st.markdown(
                    f"""
                    **🔴 DBU Cost**
                    Driver: `${breakdown["dbu_driver"]:.4f}/h`
                    Workers: `${breakdown["dbu_workers"]:.4f}/h`
                    **Total: `${breakdown["dbu_total"]:.4f}/h`**
                    """
                )
            with col_inst:
                st.markdown(
                    f"""
                    **🟢 Instance Cost**
                    Driver: `${breakdown["instance_driver"]:.4f}/h`
                    Workers: `${breakdown["instance_workers"]:.4f}/h`
                    **Total: `${breakdown["instance_total"]:.4f}/h`**
                    """
                )

        # ─── DBCU SAVINGS ────────────────────────────────────────────────────
        with st.container(border=True):
            st.markdown("#### 💎 DBCU Commit Savings")

            if commit["savings_1y_usd"] > 0 or commit["savings_3y_usd"] > 0:
                col_payg, col_1y, col_3y = st.columns(3)
                with col_payg:
                    st.metric(
                        "Pay-as-you-go",
                        _format_money_plain(result["totals"]["monthly"], currency),
                        help="Sem compromisso",
                    )
                with col_1y:
                    saving_1y_monthly = (
                        commit["savings_1y_usd"] / 12 * st.session_state.currency_rate
                    )
                    st.metric(
                        f"Commit 1y · {commit['auto_dbcu_pct_1y']}% off",
                        _format_money_plain(commit["monthly_with_dbcu_1y"], currency),
                        delta=f"-{_format_money_plain(saving_1y_monthly, currency)}/mês",
                        delta_color="inverse",
                    )
                with col_3y:
                    saving_3y_monthly = (
                        commit["savings_3y_usd"] / 12 * st.session_state.currency_rate
                    )
                    st.metric(
                        f"Commit 3y · {commit['auto_dbcu_pct_3y']}% off",
                        _format_money_plain(commit["monthly_with_dbcu_3y"], currency),
                        delta=f"-{_format_money_plain(saving_3y_monthly, currency)}/mês",
                        delta_color="inverse",
                    )
            else:
                annual_dbu_brl = commit["annual_dbu_usd"] * st.session_state.currency_rate
                st.info(
                    f"💡 Gasto anual DBU estimado: "
                    f"**{_format_money_plain(annual_dbu_brl, currency)}**. "
                    f"Abaixo do tier mínimo DBCU commit (USD 10k/ano) — "
                    f"sem desconto disponível."
                )

        # ─── AUDITORIA + SAVE ─────────────────────────────────────────────
        col_audit, col_save = st.columns([3, 2])

        with col_audit:
            with st.expander("🔍 Auditoria · Inputs Resolved"):
                inputs = result["inputs_resolved"]
                st.json(
                    {
                        "DBU rate (USD/DBU·h)": inputs["dbu_rate_per_hour_usd"],
                        "Driver DBU/h": inputs["driver_dbu_per_hour"],
                        "Worker DBU/h": inputs["worker_dbu_per_hour"],
                        "Effective workers": inputs["effective_workers"],
                        "Hours per month": inputs["hours_per_month"],
                        "Instance discount (%)": inputs["instance_discount_pct_applied"],
                        "Driver price (USD/h)": driver_price,
                        "Worker price (USD/h)": worker_price,
                        "Catalog version": result["source"]["catalog_version"],
                        "Catalog last updated": result["source"]["catalog_last_updated"],
                    },
                    expanded=False,
                )

            if result["warnings"]:
                with st.expander(f"⚠️ Warnings ({len(result['warnings'])})"):
                    for warning in result["warnings"]:
                        st.warning(warning)

        with col_save:
            with st.expander("💾 Salvar Cenário"):
                scenario_name = st.text_input(
                    "Nome",
                    placeholder="ETL Bronze prod",
                    key="save_name_input",
                )
                scenario_desc = st.text_area(
                    "Descrição",
                    placeholder="opcional",
                    key="save_desc_input",
                    height=60,
                )
                if st.button("💾 Salvar", use_container_width=True):
                    if not scenario_name.strip():
                        st.error("Nome obrigatório.")
                    else:
                        new_uuid = save_scenario(
                            scenario,
                            name=scenario_name.strip(),
                            description=scenario_desc.strip(),
                            source="manual",
                        )
                        st.success(f"✓ Salvo `{new_uuid[:8]}`")
                        st.balloons()


# ─── Tabs placeholders (Chunk 1.3) ──────────────────────────────────────────


def render_tab_compare_payg_dbcu() -> None:
    """Tab 2: PAYG vs DBCU 1y vs 3y com gráfico breakeven 36m."""
    st.markdown("#### ⚖️ Compare PAYG vs DBCU Commit")
    st.caption(
        "Selecione um cenário salvo (ou volte na Tab 1 pra criar). "
        "Comparação mostra cumulative cost 36 meses com breakeven destacado."
    )

    saved = list_saved_scenarios()
    if not saved:
        st.info(
            "💡 Nenhum cenário salvo ainda. Vá pra **Tab 1: Cenário Cluster**, "
            "configure um cluster e clique em **Salvar Cenário**."
        )
        return

    # Selector
    options = [f"{e['name']} · {e['cloud']} · {e['compute_type']}" for e in saved]
    uuids = [e["uuid"] for e in saved]
    selected_idx = st.selectbox(
        "Cenário pra comparar",
        options=range(len(options)),
        format_func=lambda i: options[i],
    )

    try:
        scenario = load_scenario(uuids[selected_idx])
    except FileNotFoundError:
        st.error(f"Cenário {uuids[selected_idx]} não encontrado.")
        return

    comparison = compute_comparison(scenario)
    currency = comparison.currency

    # ─── Metrics row ────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("##### 💵 Custos Mensais")
        col_payg, col_1y, col_3y = st.columns(3)
        with col_payg:
            st.metric(
                "Pay-as-you-go",
                _format_money_plain(comparison.monthly_payg, currency),
            )
        with col_1y:
            delta_1y = comparison.monthly_payg - comparison.monthly_dbcu_1y
            st.metric(
                f"DBCU 1y · {comparison.savings_1y_pct}% off",
                _format_money_plain(comparison.monthly_dbcu_1y, currency),
                delta=f"-{_format_money_plain(delta_1y, currency)}/mês",
                delta_color="inverse",
            )
        with col_3y:
            delta_3y = comparison.monthly_payg - comparison.monthly_dbcu_3y
            st.metric(
                f"DBCU 3y · {comparison.savings_3y_pct}% off",
                _format_money_plain(comparison.monthly_dbcu_3y, currency),
                delta=f"-{_format_money_plain(delta_3y, currency)}/mês",
                delta_color="inverse",
            )

    # ─── Recomendação ───────────────────────────────────────────────────────
    if "DBCU" in comparison.recommendation:
        st.success(comparison.recommendation)
    elif "Permaneça" in comparison.recommendation:
        st.info(comparison.recommendation)
    else:
        st.warning(comparison.recommendation)

    # ─── Gráfico cumulative 36m ─────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("##### 📈 Custo Cumulativo · 36 meses")

        months = [d["month"] for d in comparison.cumulative_36m]
        payg_cum = [d["payg"] for d in comparison.cumulative_36m]
        cum_1y = [d["dbcu_1y"] for d in comparison.cumulative_36m]
        cum_3y = [d["dbcu_3y"] for d in comparison.cumulative_36m]

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=months,
                y=payg_cum,
                mode="lines+markers",
                name="Pay-as-you-go",
                line=dict(color="#FF6B6B", width=3),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=months,
                y=cum_1y,
                mode="lines+markers",
                name="DBCU 1y",
                line=dict(color="#FFD93D", width=2, dash="dash"),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=months,
                y=cum_3y,
                mode="lines+markers",
                name="DBCU 3y",
                line=dict(color="#4ECDC4", width=2, dash="dot"),
            )
        )

        # Breakeven annotations
        annotations = []
        if comparison.breakeven_month_1y:
            annotations.append(
                dict(
                    x=comparison.breakeven_month_1y,
                    y=payg_cum[comparison.breakeven_month_1y - 1],
                    text=f"Breakeven 1y: mês {comparison.breakeven_month_1y}",
                    showarrow=True,
                    arrowhead=2,
                    ax=20,
                    ay=-30,
                    font=dict(color="#FFD93D"),
                )
            )
        if comparison.breakeven_month_3y:
            annotations.append(
                dict(
                    x=comparison.breakeven_month_3y,
                    y=payg_cum[comparison.breakeven_month_3y - 1],
                    text=f"Breakeven 3y: mês {comparison.breakeven_month_3y}",
                    showarrow=True,
                    arrowhead=2,
                    ax=20,
                    ay=30,
                    font=dict(color="#4ECDC4"),
                )
            )

        fig.update_layout(
            xaxis_title="Mês",
            yaxis_title=f"Custo cumulativo ({currency})",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white"),
            legend=dict(orientation="h", y=-0.2),
            height=400,
            margin=dict(t=20, b=20, l=0, r=0),
            annotations=annotations,
        )
        fig.update_xaxes(gridcolor="#2A2F3C")
        fig.update_yaxes(gridcolor="#2A2F3C", tickformat=",.0f")

        st.plotly_chart(fig, use_container_width=True)

    # ─── Tabela summary ─────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("##### 📋 Comparação Detalhada")
        table = get_comparison_table(comparison)
        # Formata moedas pra display
        for row in table:
            for col in ("Mensal", "Anual", "TCO 36m", "Savings vs PAYG"):
                row[col] = _format_money_plain(row[col], currency)
            row["Savings %"] = f"{row['Savings %']:.1f}%"
        st.dataframe(table, use_container_width=True, hide_index=True)


def render_tab_workloads_multiplos() -> None:
    """Tab 3: combina N cenários salvos e calcula total + breakdowns."""
    st.markdown("#### 🔗 Workloads Múltiplos")
    st.caption(
        "Selecione N cenários salvos e veja o total agregado. "
        "Útil pra estimar projetos inteiros (ex: 3 jobs + 1 cluster + 2 SQL warehouses)."
    )

    saved = list_saved_scenarios()
    if len(saved) < 2:
        st.info(
            f"💡 Pra usar Workloads Múltiplos você precisa de pelo menos 2 cenários "
            f"salvos. Você tem **{len(saved)}** salvo(s) — crie mais na Tab 1."
        )
        return

    # Multi-select
    options = [f"{e['name']} · {e['cloud']} · {e['compute_type']}" for e in saved]
    uuids = [e["uuid"] for e in saved]
    selected_indices = st.multiselect(
        "Cenários pra agregar (selecione 2+)",
        options=range(len(options)),
        format_func=lambda i: options[i],
        default=list(range(min(len(options), 3))),  # default: 3 primeiros
    )

    if len(selected_indices) < 2:
        st.warning("Selecione pelo menos 2 cenários.")
        return

    # Carrega scenarios
    workload_tuples = []
    for idx in selected_indices:
        try:
            scenario = load_scenario(uuids[idx])
            workload_tuples.append((saved[idx]["name"], saved[idx]["description"], scenario))
        except FileNotFoundError:
            continue

    if not workload_tuples:
        st.error("Nenhum cenário carregou com sucesso.")
        return

    # Aggregate
    try:
        agg = aggregate_workloads(workload_tuples)
    except ValueError as exc:
        st.error(f"Erro na agregação: {exc}")
        return

    # Warnings
    if agg.warnings:
        for w in agg.warnings:
            st.warning(w)

    currency = agg.currency

    # ─── Metrics top ────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("##### 💵 Total Agregado")
        col_m, col_a, col_t = st.columns(3)
        with col_m:
            st.metric(
                "Mensal Total",
                _format_money_plain(agg.total_monthly, currency),
                help=f"Soma de {len(agg.workloads)} workloads",
            )
        with col_a:
            st.metric("Anual Total", _format_money_plain(agg.total_annual, currency))
        with col_t:
            st.metric("TCO 36m", _format_money_plain(agg.total_tco_36m, currency))

    # ─── Tabela com contribuição ────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("##### 📋 Workloads Selecionados")
        table = get_workloads_table(agg)
        # Formata moedas
        for row in table:
            for col in ("Mensal", "Anual"):
                if isinstance(row[col], (int, float)):
                    row[col] = _format_money_plain(row[col], currency)
            row["% do Total"] = f"{row['% do Total']:.1f}%"
        st.dataframe(table, use_container_width=True, hide_index=True)

    # ─── Breakdowns visuais ─────────────────────────────────────────────────
    col_ct, col_cl = st.columns(2)
    with col_ct:
        with st.container(border=True):
            st.markdown("##### 🧩 Por Compute Type")
            if agg.by_compute_type:
                fig_ct = go.Figure(
                    data=[
                        go.Pie(
                            labels=list(agg.by_compute_type.keys()),
                            values=list(agg.by_compute_type.values()),
                            hole=0.45,
                            marker=dict(
                                colors=[
                                    "#FF6B6B",
                                    "#4ECDC4",
                                    "#FFD93D",
                                    "#95E1D3",
                                    "#A8DADC",
                                ]
                            ),
                            textinfo="label+percent",
                        )
                    ]
                )
                fig_ct.update_layout(
                    showlegend=False,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="white"),
                    height=300,
                    margin=dict(t=10, b=10, l=0, r=0),
                )
                st.plotly_chart(fig_ct, use_container_width=True)

    with col_cl:
        with st.container(border=True):
            st.markdown("##### ☁️ Por Cloud")
            if agg.by_cloud:
                fig_cl = go.Figure(
                    data=[
                        go.Pie(
                            labels=[c.upper() for c in agg.by_cloud.keys()],
                            values=list(agg.by_cloud.values()),
                            hole=0.45,
                            marker=dict(colors=["#0078D4", "#FF9900"]),
                            textinfo="label+percent",
                        )
                    ]
                )
                fig_cl.update_layout(
                    showlegend=False,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="white"),
                    height=300,
                    margin=dict(t=10, b=10, l=0, r=0),
                )
                st.plotly_chart(fig_cl, use_container_width=True)

    # ─── DBU vs Instance global ─────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("##### 🔴 DBU vs 🟢 Instance Cost (mensal agregado)")
        col_dbu, col_inst, col_pct = st.columns(3)
        with col_dbu:
            st.metric(
                "DBU Cost Total",
                _format_money_plain(agg.dbu_total_monthly, currency),
            )
        with col_inst:
            st.metric(
                "Instance Cost Total",
                _format_money_plain(agg.instance_total_monthly, currency),
            )
        with col_pct:
            total_cost = agg.dbu_total_monthly + agg.instance_total_monthly
            dbu_pct = (agg.dbu_total_monthly / total_cost * 100) if total_cost > 0 else 0
            st.metric("% DBU", f"{dbu_pct:.1f}%")

    # Guarda agg pra Tab 4 (Export) consumir
    st.session_state["last_aggregate"] = agg
    st.session_state["last_aggregate_scenarios"] = [
        (name, scen) for name, _, scen in workload_tuples
    ]


def render_tab_export() -> None:
    """Tab 4: Export XLSX (single scenario ou multi com aggregate)."""
    st.markdown("#### 📤 Export XLSX")
    st.caption(
        "Gera planilha Excel formatada com Resumo Executivo, Detalhes de cada "
        "cenário, comparação DBCU e breakdown hourly. Pronta pra mandar pro cliente."
    )

    saved = list_saved_scenarios()
    if not saved:
        st.info("💡 Nenhum cenário salvo ainda. Crie cenários na **Tab 1** primeiro.")
        return

    # Modo: single vs multi
    mode = st.radio(
        "Modo de export",
        options=["Cenário único", "Múltiplos cenários (com agregação)"],
        horizontal=True,
    )

    options = [f"{e['name']} · {e['cloud']}" for e in saved]
    uuids = [e["uuid"] for e in saved]

    scenarios_to_export: list[tuple[str, DatabricksScenario]] = []
    include_aggregate = None

    if mode == "Cenário único":
        selected_idx = st.selectbox(
            "Cenário",
            options=range(len(options)),
            format_func=lambda i: options[i],
        )
        try:
            scenario = load_scenario(uuids[selected_idx])
            scenarios_to_export = [(saved[selected_idx]["name"], scenario)]
        except FileNotFoundError:
            st.error(f"Cenário {uuids[selected_idx]} não encontrado.")
            return
    else:
        # Multi
        selected_indices = st.multiselect(
            "Cenários (selecione 2+)",
            options=range(len(options)),
            format_func=lambda i: options[i],
            default=list(range(min(len(options), 3))),
        )
        if len(selected_indices) < 2:
            st.warning("Selecione pelo menos 2 cenários.")
            return

        loaded_tuples = []
        loaded_named = []
        for idx in selected_indices:
            try:
                s = load_scenario(uuids[idx])
                loaded_named.append((saved[idx]["name"], s))
                loaded_tuples.append((saved[idx]["name"], saved[idx]["description"], s))
            except FileNotFoundError:
                continue

        scenarios_to_export = loaded_named
        try:
            include_aggregate = aggregate_workloads(loaded_tuples)
        except ValueError as exc:
            st.error(f"Erro na agregação: {exc}")
            return

    if not scenarios_to_export:
        return

    # Filename
    filename = st.text_input(
        "Nome do arquivo",
        value=suggest_filename(),
        help="Default tem timestamp UTC. Edite se preferir nome customizado.",
    )

    # Build XLSX
    try:
        xlsx_bytes = build_xlsx_multi_scenarios(scenarios_to_export, aggregate=include_aggregate)
    except ValueError as exc:
        st.error(f"Erro ao gerar XLSX: {exc}")
        return

    # Preview info
    with st.container(border=True):
        st.markdown("##### 📊 Conteúdo do XLSX")
        sheets_desc = [
            "**Resumo Executivo** — 1-pager pra cliente com totals",
            "**Cenários Detalhados** — 1 row por cenário com 20 colunas",
            "**DBCU Comparison** — PAYG vs 1y vs 3y por cenário com savings/breakeven",
            "**Breakdown Hourly** — DBU vs Instance hourly por cenário",
        ]
        if include_aggregate:
            sheets_desc.append(
                "**Workload Aggregate** — breakdown por compute_type + cloud (agregado)"
            )
        for desc in sheets_desc:
            st.markdown(f"- {desc}")

        st.caption(
            f"Total: {len(scenarios_to_export)} cenário(s), "
            f"~{xlsx_bytes.getbuffer().nbytes // 1024} KB"
        )

    # Download button
    st.download_button(
        label="⬇️ Download XLSX",
        data=xlsx_bytes,
        file_name=filename if filename.endswith(".xlsx") else f"{filename}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


# ─── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    _init_session_state()
    render_sidebar()

    # Header compacto
    col_title, col_info = st.columns([3, 2])
    with col_title:
        st.markdown("## 💰 Databricks Cost Calculator")
    with col_info:
        st.caption(
            f"☁️ **{st.session_state.cloud.upper()}** · "
            f"📍 **{st.session_state.region}** · "
            f"💱 **{st.session_state.currency_label}**"
            + (
                f" · FX `{st.session_state.currency_rate:.2f}`"
                if st.session_state.currency_label == "BRL"
                else ""
            )
        )

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "🖥️ Cenário Cluster",
            "⚖️ Compare PAYG vs DBCU",
            "🔗 Workloads Múltiplos",
            "📤 Export XLSX",
        ]
    )

    with tab1:
        render_tab_cenario_cluster()
    with tab2:
        render_tab_compare_payg_dbcu()
    with tab3:
        render_tab_workloads_multiplos()
    with tab4:
        render_tab_export()


if __name__ == "__main__":
    main()
