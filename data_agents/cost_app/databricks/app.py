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
            options = ["(novo)"] + [
                f"{e['name'][:25]} · {e['cloud']}" for e in saved
            ]
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

        st.caption(
            "🔗 [GitHub](https://github.com/ThomazRossito/ai-data-agents) · v1.2"
        )


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
                st.error(
                    f"Nenhuma instance em {cloud}/{region} tem DBU mapping no catalog."
                )
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
                index=pricing_options.index(loaded.instance_pricing_model)
                if loaded
                else 0,
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
                photon_speedup = st.number_input(
                    "Photon speedup esperado (x)",
                    min_value=1.0,
                    max_value=10.0,
                    value=loaded.photon_speedup_factor or 2.5,
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
                    Driver: `${breakdown['dbu_driver']:.4f}/h`
                    Workers: `${breakdown['dbu_workers']:.4f}/h`
                    **Total: `${breakdown['dbu_total']:.4f}/h`**
                    """
                )
            with col_inst:
                st.markdown(
                    f"""
                    **🟢 Instance Cost**
                    Driver: `${breakdown['instance_driver']:.4f}/h`
                    Workers: `${breakdown['instance_workers']:.4f}/h`
                    **Total: `${breakdown['instance_total']:.4f}/h`**
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
                annual_dbu_brl = (
                    commit["annual_dbu_usd"] * st.session_state.currency_rate
                )
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
                        "Instance discount (%)": inputs[
                            "instance_discount_pct_applied"
                        ],
                        "Driver price (USD/h)": driver_price,
                        "Worker price (USD/h)": worker_price,
                        "Catalog version": result["source"]["catalog_version"],
                        "Catalog last updated": result["source"][
                            "catalog_last_updated"
                        ],
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
    st.header("⚖️ Compare PAYG vs DBCU")
    st.info(
        "🚧 **Em construção (Chunk 1.3)** — comparação detalhada entre Pay-as-you-go "
        "e DBCU commit (1y, 3y) com gráfico de breakeven e ROI."
    )


def render_tab_workloads_multiplos() -> None:
    st.header("🔗 Workloads Múltiplos")
    st.info(
        "🚧 **Em construção (Chunk 1.3)** — combine N cenários e veja o "
        "total mensal agregado (ex: 3 jobs + 1 cluster all-purpose + 2 SQL warehouses)."
    )


def render_tab_export() -> None:
    st.header("📤 Export XLSX")
    st.info(
        "🚧 **Em construção (Chunk 1.3)** — exporta cenários e cotações pra XLSX "
        "formatado com fórmulas (openpyxl)."
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
