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

from data_agents.cost_app.databricks.billing_app_helpers import (
    format_compare_dataframe,
    interpret_verdict,
    load_billing_data,
)
from data_agents.cost_app.databricks.billing_mock import get_mock_metadata as get_billing_mock_meta
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
    delete_scenario,
    list_saved_scenarios,
    load_scenario,
    save_scenario,
)

# PR 7 (2026-05-28): AI/ML scenarios do PR 5 expostos no UI.
from data_agents.cost_engine import (
    AgentBricksScenario,
    LakebaseScenario,
    LLMScenario,
    VectorSearchScenario,
    calculate_agent_bricks_cost,
    calculate_lakebase_cost,
    calculate_llm_cost,
    calculate_vector_search_cost,
)
from data_agents.cost_app.databricks.workloads import (
    aggregate_workloads,
    get_summary_table as get_workloads_table,
)
from data_agents.cost_engine.billing import (
    BillingPeriod,
    aggregate_dbu_daily,
    compare_estimate_vs_actual,
    cost_by_compute_type,
    top_cost_clusters,
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
        # PR 2 (2026-05-28): + GCP (gcp.yaml scaffold). Cobertura beta — preços
        # GCP derivados via paridade AWS per /product/sku-groups.
        st.markdown("### 🌐 Cloud + Region")
        cloud = st.selectbox(
            "Cloud Provider",
            options=["azure", "aws", "gcp"],
            format_func=lambda c: {
                "azure": "Azure Databricks",
                "aws": "AWS Databricks",
                "gcp": "GCP Databricks (beta)",
            }[c],
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
            # PR 2 (2026-05-28): + 3 serverless sub-types oficiais.
            # serverless_compute mantido como alias DEPRECATED pra back-compat com
            # cenários salvos. Engine resolve igual ao jobs_serverless ($0.35/DBU).
            compute_options = [
                "all_purpose_compute",
                "jobs_compute",
                "delta_live_tables",
                "sql",
                "jobs_serverless",
                "dlt_serverless",
                "all_purpose_serverless",
                "serverless_compute",  # legacy alias (deprecated)
                "model_serving",
                "vector_search",
                "mosaic_agent",
            ]
            compute_type = st.selectbox(
                "Compute Type",
                options=compute_options,
                index=compute_options.index(loaded.compute_type)
                if loaded and loaded.compute_type in compute_options
                else 1,
                format_func=lambda c: {
                    "all_purpose_compute": "All-Purpose (notebooks)",
                    "jobs_compute": "Jobs (scheduled)",
                    "delta_live_tables": "Delta Live Tables",
                    "sql": "SQL Warehouse",
                    "jobs_serverless": "Jobs Serverless ($0.35/DBU)",
                    "dlt_serverless": "DLT Serverless ($0.35/DBU)",
                    "all_purpose_serverless": "All-Purpose Serverless ($0.75/DBU)",
                    "serverless_compute": "Serverless (DEPRECATED — use sub-type acima)",
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

        # Serverless: Databricks-managed (sem instances declaradas pelo user)
        # PR 2 (2026-05-28): expandido pra todos os 4 sub-types oficiais.
        # Mantém sincronizado com _SERVERLESS_COMPUTE_TYPES no cost_engine.databricks.
        is_serverless = compute_type in (
            "serverless_compute",  # legacy alias
            "sql_serverless",
            "jobs_serverless",  # PR 2
            "dlt_serverless",  # PR 2
            "all_purpose_serverless",  # PR 2
        ) or (compute_type == "sql" and tier == "serverless")

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

            if is_serverless:
                st.info(
                    "ℹ️ **Serverless é Databricks-managed.** "
                    "O user paga apenas DBU consumido — sem instance cost separado. "
                    "Driver/Workers/Num Workers são ignorados no cálculo. "
                    "Selecione apenas pra metadados de auditoria do cenário."
                )
                # Mantém os selectboxes pra preservar metadados do scenario,
                # mas avisa visualmente que não afetam custo.
                driver_instance = st.selectbox(
                    "Driver Instance (metadados, não usado no custo)",
                    options=valid_skus,
                    index=valid_skus.index(default_driver),
                    disabled=False,  # mantém habilitado pra audit trail
                )
                worker_instance = st.selectbox(
                    "Worker Instance (metadados, não usado no custo)",
                    options=valid_skus,
                    index=valid_skus.index(default_worker),
                )
                num_workers = st.number_input(
                    "Workers paralelos (referência — não afeta custo serverless)",
                    min_value=0,
                    max_value=200,
                    value=loaded.num_workers if loaded else 4,
                    help=(
                        "Em Serverless, o custo escala com DBU consumido — "
                        "Databricks gerencia o número de workers automaticamente. "
                        "Este campo serve apenas pra documentar o perfil esperado."
                    ),
                )
            else:
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
                        # Source tracking: se carregou um cenário existente e está re-salvando,
                        # vira "app-edited" com parent_uuid rastreando linhagem. Caso contrário,
                        # cenário novo → "manual".
                        parent = st.session_state.get("loaded_scenario_uuid")
                        is_edit = parent is not None
                        new_uuid = save_scenario(
                            scenario,
                            name=scenario_name.strip(),
                            description=scenario_desc.strip(),
                            source="app-edited" if is_edit else "manual",
                            parent_uuid=parent,
                        )
                        msg = f"✓ Salvo `{new_uuid[:8]}`"
                        if is_edit:
                            msg += f" (editado de `{parent[:8]}`)"
                        st.success(msg)
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


# ─── Tab 5: Histórico (Chunk 2.3 — bridge bidirecional Agent↔App) ───────────


_SOURCE_LABELS = {
    "agent": "🤖 Agent",
    "manual": "✋ Manual",
    "app-edited": "✏️ Editado",
    "import": "📥 Import",
    "unknown": "❓ Desconhecido",
}


def _format_created_at(iso: str) -> str:
    """Formata ISO timestamp pra display compacto (YYYY-MM-DD HH:MM)."""
    if not iso:
        return "—"
    try:
        from datetime import datetime as _dt

        dt = _dt.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return iso[:16] if len(iso) > 16 else iso


def render_tab_historico() -> None:
    """Tab 5: Histórico de cenários salvos (bridge bidirecional).

    Mostra todos os cenários em outputs/cost-scenarios/ com filtros, badge
    no header (contagem por source), e botões Load/Delete por linha.
    """
    st.markdown("#### 📋 Histórico de Cenários")
    st.caption(
        "Bridge bidirecional: cenários salvos pelo Agent (via MCP `save_scenario`) "
        "e pelo App. Use Load pra reabrir num cenário existente, Delete pra remover."
    )

    all_entries = list_saved_scenarios()

    if not all_entries:
        st.info(
            "📭 Nenhum cenário salvo ainda. "
            "Crie um na Tab 'Cenário Cluster' ou peça ao agent: `/cost-databricks ... salva no app`."
        )
        return

    # Badges por source (counts)
    counts: dict[str, int] = {}
    for e in all_entries:
        counts[e["source"]] = counts.get(e["source"], 0) + 1

    badge_cols = st.columns(len(_SOURCE_LABELS))
    for col, (src, label) in zip(badge_cols, _SOURCE_LABELS.items()):
        with col:
            count = counts.get(src, 0)
            if count > 0:
                st.metric(label, count)
            else:
                st.metric(label, count, label_visibility="visible")

    st.divider()

    # Filtros
    col_f1, col_f2, col_f3 = st.columns([2, 2, 3])
    with col_f1:
        source_options = ["(todos)"] + sorted({e["source"] for e in all_entries})
        filter_source = st.selectbox(
            "Filtrar por Source",
            options=source_options,
            key="hist_filter_source",
        )
    with col_f2:
        cloud_options = ["(todos)"] + sorted({e["cloud"] for e in all_entries if e["cloud"] != "?"})
        filter_cloud = st.selectbox(
            "Filtrar por Cloud",
            options=cloud_options,
            key="hist_filter_cloud",
        )
    with col_f3:
        search_query = st.text_input(
            "🔍 Buscar (nome/descrição)",
            placeholder="ex: ETL bronze",
            key="hist_search",
        )

    # Aplica filtros
    filtered = all_entries
    if filter_source != "(todos)":
        filtered = [e for e in filtered if e["source"] == filter_source]
    if filter_cloud != "(todos)":
        filtered = [e for e in filtered if e["cloud"] == filter_cloud]
    if search_query.strip():
        q = search_query.strip().lower()
        filtered = [e for e in filtered if q in e["name"].lower() or q in e["description"].lower()]

    st.caption(f"**{len(filtered)} de {len(all_entries)} cenários** após filtros")

    if not filtered:
        st.warning("Nenhum cenário casa com os filtros aplicados.")
        return

    # Tabela com ações
    for entry in filtered:
        with st.container(border=True):
            col_info, col_actions = st.columns([5, 2])

            with col_info:
                source_label = _SOURCE_LABELS.get(entry["source"], entry["source"])
                created = _format_created_at(entry["created_at"])
                parent_info = ""
                if entry.get("parent_uuid"):
                    parent_info = f" · derivado de `{entry['parent_uuid'][:8]}`"

                st.markdown(
                    f"**{entry['name']}** · `{entry['uuid'][:8]}`  \n"
                    f"{source_label} · {entry['cloud']} · {entry['compute_type']} · {created}"
                    f"{parent_info}"
                )
                if entry["description"]:
                    st.caption(entry["description"])

            with col_actions:
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("📥 Load", key=f"load_{entry['uuid']}", use_container_width=True):
                        st.session_state.loaded_scenario_uuid = entry["uuid"]
                        st.success(f"Carregado `{entry['uuid'][:8]}`. Vá na Tab 'Cenário Cluster'.")
                        st.rerun()
                with col_btn2:
                    # Delete com confirmação inline via st.session_state flag
                    confirm_key = f"confirm_delete_{entry['uuid']}"
                    if st.session_state.get(confirm_key):
                        if st.button(
                            "✓ Confirma",
                            key=f"confirm_{entry['uuid']}",
                            type="primary",
                            use_container_width=True,
                        ):
                            delete_scenario(entry["uuid"])
                            st.session_state[confirm_key] = False
                            # Limpa loaded_scenario_uuid se era esse
                            if st.session_state.get("loaded_scenario_uuid") == entry["uuid"]:
                                st.session_state.loaded_scenario_uuid = None
                            st.rerun()
                    else:
                        if st.button(
                            "🗑️ Delete", key=f"del_{entry['uuid']}", use_container_width=True
                        ):
                            st.session_state[confirm_key] = True
                            st.rerun()


# ─── Tab 6: FinOps Realizado (Chunk 3.3 — análise actual via system.billing) ──


def render_tab_finops_realizado() -> None:
    """Tab 6: análise FinOps de consumo real via system.billing.usage.

    No Chunk 3.1 só mock mode está implementado — toggle 'Real data' fica
    desabilitado com aviso. Quando integração SDK ficar pronta, habilita.
    """
    st.markdown("#### 📊 FinOps Realizado — Análise de Consumo")
    st.caption(
        "Análise de workloads Databricks em produção via `system.billing.usage` "
        "(Fase 3). Distinto da Tab 'Cenário Cluster' (estimate determinístico)."
    )

    cloud = st.session_state.cloud.upper()

    # ─── Inputs ─────────────────────────────────────────────────────────────
    col_form1, col_form2, col_form3 = st.columns([2, 2, 1])

    with col_form1:
        period_days = st.selectbox(
            "Janela",
            options=[7, 14, 30, 60],
            index=2,  # default 30 dias
            format_func=lambda d: f"Últimos {d} dias",
            help="Janelas curtas amplificam ruído na extrapolação. Recomendado: ≥14 dias.",
        )
    with col_form2:
        workspace_id_str = st.text_input(
            "Workspace ID (opcional)",
            placeholder="vazio = todos os workspaces",
            help="Filtra por workspace específico em contas multi-workspace.",
        )
    with col_form3:
        mode = st.radio(
            "Modo dos dados",
            options=["Mock", "Real (system.billing)"],
            index=0,
            help=(
                "Mock = dados sintéticos pra dev/test. "
                "Real = SQL contra system.billing (requer DATABRICKS_HOST + "
                "DATABRICKS_TOKEN + DATABRICKS_BILLING_WAREHOUSE_ID no .env "
                "+ Unity Catalog habilitado + permissão SELECT em system.billing)."
            ),
        )

    workspace_id: int | None = None
    if workspace_id_str.strip():
        try:
            workspace_id = int(workspace_id_str.strip())
        except ValueError:
            st.error("workspace_id deve ser numérico.")
            return

    use_mock = mode.startswith("Mock")

    # ─── Carrega dados ──────────────────────────────────────────────────────
    from datetime import datetime, timedelta, timezone

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=period_days - 1)
    period = BillingPeriod(start_date=start_date, end_date=end_date, workspace_id=workspace_id)

    try:
        usage_df, prices_df = load_billing_data(period=period, cloud=cloud, mock=use_mock)
    except RuntimeError as exc:
        st.error(f"❌ Erro ao carregar dados: {exc}")
        if not use_mock:
            st.caption(
                "💡 Verifique no .env: DATABRICKS_HOST, DATABRICKS_TOKEN, "
                "DATABRICKS_BILLING_WAREHOUSE_ID. O warehouse deve estar startado "
                "e ter SELECT em system.billing."
            )
        return

    if usage_df.empty:
        st.info("📭 Sem registros de consumo na janela selecionada.")
        return

    # Banner do mode usado
    if use_mock:
        mock_meta = get_billing_mock_meta()
        st.caption(
            f"📦 **Mock mode** · {mock_meta['num_clusters']} clusters fictícios "
            f"({', '.join(mock_meta['cluster_names'])}) · {mock_meta['num_skus_per_cloud']} SKUs · "
            f"seed={mock_meta['seed_default']}"
        )
    else:
        from data_agents.cost_app.databricks.billing_real import get_last_load_timestamp

        ts = get_last_load_timestamp()
        ts_str = ts.strftime("%Y-%m-%d %H:%M UTC") if ts else "agora"
        st.caption(
            f"🔗 **Real mode** · dados de system.billing.usage · "
            f"última carga: {ts_str} · cache TTL 5min"
        )

    # ─── Métricas top ───────────────────────────────────────────────────────
    daily = aggregate_dbu_daily(usage_df, period)
    breakdown = cost_by_compute_type(usage_df, prices_df, period)
    top_clusters = top_cost_clusters(usage_df, prices_df, period, limit=10)

    total_dbus = float(daily["total_dbus"].sum())
    total_cost_usd = float(breakdown["estimated_cost_usd"].sum()) if not breakdown.empty else 0.0

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.metric("Total DBU", f"{total_dbus:,.1f}")
    with col_m2:
        st.metric("Custo estimado", _format_money_plain(total_cost_usd, "USD"))
    with col_m3:
        if st.session_state.currency_label == "BRL":
            total_brl = total_cost_usd * st.session_state.currency_rate
            st.metric("Em BRL", _format_money_plain(total_brl, "BRL"))
        else:
            st.metric("Período", f"{period.days} dias")
    with col_m4:
        clusters_ativos = top_clusters["cluster_name"].nunique() if not top_clusters.empty else 0
        st.metric("Clusters ativos", clusters_ativos)

    st.divider()

    # ─── Chart 1: Daily DBU trend ───────────────────────────────────────────
    st.markdown("##### 📈 Consumo diário (DBU)")

    # Agrega total por dia (sem quebrar por SKU pra trend simples)
    daily_total = daily.groupby("usage_date", as_index=False)["total_dbus"].sum()
    daily_total["usage_date"] = daily_total["usage_date"].astype(str)

    # Moving average 7d (só se janela >= 7d)
    if len(daily_total) >= 7:
        daily_total["ma_7d"] = daily_total["total_dbus"].rolling(window=7, min_periods=1).mean()

    fig_trend = go.Figure()
    fig_trend.add_trace(
        go.Scatter(
            x=daily_total["usage_date"],
            y=daily_total["total_dbus"],
            mode="lines+markers",
            name="DBU diário",
            line={"color": "#FF6B6B", "width": 2},
            marker={"size": 6},
        )
    )
    if "ma_7d" in daily_total.columns:
        fig_trend.add_trace(
            go.Scatter(
                x=daily_total["usage_date"],
                y=daily_total["ma_7d"],
                mode="lines",
                name="Média móvel 7d",
                line={"color": "#4ECDC4", "width": 2, "dash": "dash"},
            )
        )
    fig_trend.update_layout(
        height=320,
        margin={"l": 20, "r": 20, "t": 30, "b": 40},
        xaxis_title="Data",
        yaxis_title="DBU",
        showlegend=True,
        legend={"orientation": "h", "y": -0.2},
    )
    st.plotly_chart(fig_trend, use_container_width=True)

    st.divider()

    # ─── Chart 2 + 3 lado a lado: Donut + Top Clusters ──────────────────────
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.markdown("##### 🍩 Breakdown por Compute Type")
        if breakdown.empty:
            st.caption("Sem dados na janela.")
        else:
            fig_donut = go.Figure(
                go.Pie(
                    labels=breakdown["compute_type"],
                    values=breakdown["estimated_cost_usd"],
                    hole=0.5,
                    marker={"colors": ["#FF6B6B", "#4ECDC4", "#FFE66D", "#A0E7E5", "#B4F8C8"]},
                    textinfo="label+percent",
                    hovertemplate="<b>%{label}</b><br>$%{value:.2f}<br>%{percent}<extra></extra>",
                )
            )
            fig_donut.update_layout(
                height=320,
                margin={"l": 20, "r": 20, "t": 20, "b": 20},
                showlegend=False,
            )
            st.plotly_chart(fig_donut, use_container_width=True)

    with col_chart2:
        st.markdown("##### 🏆 Top 10 Clusters por Custo")
        if top_clusters.empty:
            st.caption("Sem clusters identificados na janela.")
        else:
            fig_bar = go.Figure(
                go.Bar(
                    x=top_clusters["estimated_cost_usd"],
                    y=top_clusters["cluster_name"],
                    orientation="h",
                    marker={"color": "#FF6B6B"},
                    text=top_clusters["estimated_cost_usd"].apply(lambda v: f"${v:.2f}"),
                    textposition="outside",
                )
            )
            fig_bar.update_layout(
                height=320,
                margin={"l": 20, "r": 60, "t": 20, "b": 20},
                xaxis_title="Custo (USD)",
                yaxis={"autorange": "reversed"},  # maior em cima
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    st.divider()

    # ─── Bridge: Compare estimate vs actual ────────────────────────────────
    st.markdown("##### 🔗 Comparar com Cenário Estimado (Bridge Fase 2 ↔ Fase 3)")
    st.caption(
        "Selecione um cenário salvo (Fase 2) pra calcular variance vs consumo real. "
        "Veja `kb/databricks-pricing/concepts/estimate-vs-actual.md` para semantics."
    )

    saved_scenarios = list_saved_scenarios()
    if not saved_scenarios:
        st.info(
            "📋 Nenhum cenário salvo. Crie um na Tab 'Cenário Cluster' ou peça ao agent: "
            "`/cost-databricks ... salva no app`."
        )
        return

    col_compare1, col_compare2 = st.columns([3, 2])

    with col_compare1:
        scenario_options = [
            f"{e['name'][:40]} · {e['cloud']} · {e['source']}" for e in saved_scenarios
        ]
        scenario_idx = st.selectbox(
            "Cenário",
            options=range(len(scenario_options)),
            format_func=lambda i: scenario_options[i],
            key="finops_compare_scenario_idx",
        )

    with col_compare2:
        # Cluster_name filter (opcional) — populado com os clusters do mock
        cluster_options = ["(todos os clusters)"] + sorted(
            usage_df["cluster_name"].dropna().unique().tolist()
        )
        cluster_filter = st.selectbox(
            "Filtrar cluster",
            options=cluster_options,
            index=0,
            help="Filtra system.billing pelo cluster_name específico do cenário (recomendado).",
        )

    if st.button("📊 Comparar estimate vs actual", use_container_width=True):
        scenario_meta = saved_scenarios[scenario_idx]
        try:
            envelope_dict = {
                "uuid": scenario_meta["uuid"],
                "name": scenario_meta["name"],
            }

            # Carrega scenario completo via load_scenario (Fase 2)
            scenario = load_scenario(scenario_meta["uuid"])
            catalog = _cached_catalog(scenario.cloud)
            result = calculate_databricks_cost(scenario, catalog)
            estimated_monthly = float(result["totals"]["monthly"])

            # Filtra usage por cluster se aplicável
            usage_filtered = usage_df
            if cluster_filter != "(todos os clusters)":
                usage_filtered = usage_df[usage_df["cluster_name"] == cluster_filter].copy()

            # Calcula actual_total via cost_by_compute_type filtrado
            actual_breakdown = cost_by_compute_type(usage_filtered, prices_df, period)
            actual_total = (
                float(actual_breakdown["estimated_cost_usd"].sum())
                if not actual_breakdown.empty
                else 0.0
            )

            # Bridge engine
            comparison = compare_estimate_vs_actual(
                scenario_envelope=envelope_dict,
                estimated_monthly_usd=estimated_monthly,
                actual_total_usd_in_period=actual_total,
                period=period,
            )

            # Display
            compare_df = format_compare_dataframe(
                scenario_name=comparison.scenario_name,
                estimated_monthly_usd=comparison.estimated_monthly_usd,
                actual_monthly_usd=comparison.actual_monthly_usd,
                variance_pct=comparison.variance_pct,
                verdict=comparison.verdict,
                actual_period_days=comparison.actual_period_days,
            )
            st.dataframe(compare_df, use_container_width=True, hide_index=True)

            # Interpretação textual
            msg = interpret_verdict(comparison.verdict, comparison.variance_pct)
            if comparison.verdict == "on_budget":
                st.success(msg)
            elif comparison.verdict == "over_budget":
                st.warning(msg)
            else:
                st.info(msg)

            # Caveats automáticos
            if period.days < 14:
                st.caption(
                    f"⚠️ Período de {period.days} dias é curto — extrapolação pode amplificar ruído. "
                    "Recomendado ≥14 dias."
                )
            if cluster_filter == "(todos os clusters)":
                st.caption(
                    "ℹ️ Sem filtro de cluster — actual inclui workloads não cobertos pelo cenário. "
                    "Pode inflar variance falsamente. Recomenda-se selecionar o cluster específico."
                )
        except (FileNotFoundError, ValueError) as exc:
            st.error(f"Erro no compare: {exc}")


# ─── Tab 7: Otimização Proativa (Fase 4) ────────────────────────────────────


# ─── Tab 8: Catálogo de Preços (transparência) ────────────────────────────────


def render_tab_catalogo() -> None:
    """Tab 8: lista todos os preços usados pelo App (DBU rates + Instance prices).

    Transparência total pra audit: source URLs, last_updated, modo (mock vs real).
    User valida cada número antes de tomar decisão de negócio.
    """
    from data_agents.cost_app.databricks.instance_prices_real import (
        fetch_aws_ec2_price,
        fetch_azure_vm_price,
        get_pricing_metadata,
        is_real_mode_enabled,
    )

    st.markdown("#### 📋 Catálogo de Preços — Transparência")
    st.caption(
        "Todos os preços usados pelo App neste momento. Compare com fontes oficiais "
        "antes de decisão de negócio."
    )

    pricing_meta = get_pricing_metadata()
    real_active = is_real_mode_enabled()

    if real_active:
        st.success(
            f"🔗 **Modo REAL ativo** — Azure Retail API + AWS Pricing API. "
            f"Fallback transparente pro mock se API falhar. "
            f"Cache TTL: {pricing_meta['cache_ttl_seconds']}s · "
            f"Entries cacheados: {pricing_meta['cache_entries']}"
        )
    else:
        st.warning(
            "📦 **Modo MOCK ativo** — valores estáticos hardcoded no projeto. "
            "Para usar APIs reais (Azure Retail + AWS Pricing), set "
            "`DATABRICKS_INSTANCE_PRICES_MODE=real` no `.env`."
        )
        if not pricing_meta["boto3_available"]:
            st.caption(
                "ℹ️ `boto3` não instalado — AWS Pricing API requer "
                "`pip install boto3` + AWS credentials."
            )

    sub1, sub2, sub3 = st.tabs(
        ["💰 DBU Rates (Databricks)", "☁️ Azure VM Prices", "☁️ AWS EC2 Prices"]
    )

    # ─── Sub-tab 1: DBU rates do YAML ────────────────────────────────────────
    with sub1:
        st.markdown("##### Databricks DBU Rates")
        st.caption(
            "Preço cobrado pela Databricks por **DBU·h** consumido. "
            "Multiplicado por DBU/h da instance pra cobrar consumo Databricks."
        )

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            dbu_cloud = st.selectbox(
                "Cloud",
                options=["azure", "aws"],
                key="catalogo_dbu_cloud",
                format_func=lambda c: c.upper(),
            )
        with col_d2:
            st.caption(
                f"🔗 Source: `data/databricks_pricing/{dbu_cloud}.yaml`  \n"
                "Origem oficial: https://www.databricks.com/product/pricing"
            )

        catalog_dbu = _cached_catalog(dbu_cloud)
        st.caption(
            f"**Catalog version:** {catalog_dbu.get('version', '?')} · "
            f"**Last updated:** {catalog_dbu.get('last_updated', '?')} · "
            f"⚠️ Hardcoded manual no projeto"
        )

        # Tabela DBU rates: compute_type × tier × photon
        import pandas as pd

        dbu_rows = []
        compute_types = catalog_dbu.get("compute_types", {})
        for ct_name, ct_data in compute_types.items():
            if isinstance(ct_data, dict) and "base_per_dbu" in ct_data:
                dbu_rows.append(
                    {
                        "compute_type": ct_name,
                        "tier": "—",
                        "photon": "—",
                        "USD/DBU·h": ct_data["base_per_dbu"],
                    }
                )
            elif isinstance(ct_data, dict):
                for tier_name, tier_data in ct_data.items():
                    if isinstance(tier_data, dict):
                        for photon_key, rate in tier_data.items():
                            dbu_rows.append(
                                {
                                    "compute_type": ct_name,
                                    "tier": tier_name,
                                    "photon": "ON" if photon_key == "photon" else "OFF",
                                    "USD/DBU·h": rate,
                                }
                            )
                    elif isinstance(tier_data, (int, float)):
                        dbu_rows.append(
                            {
                                "compute_type": ct_name,
                                "tier": tier_name,
                                "photon": "—",
                                "USD/DBU·h": tier_data,
                            }
                        )

        if dbu_rows:
            dbu_df = pd.DataFrame(dbu_rows)
            st.dataframe(
                dbu_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "USD/DBU·h": st.column_config.NumberColumn("USD/DBU·h", format="$%.4f"),
                },
            )
        else:
            st.warning("Catalog YAML sem entries DBU — verifique estrutura.")

        # ─── PR 2 (2026-05-28): Lakebase + Lakeflow Connect ─────────────────
        # SKUs novos não-DBU (ou parcialmente DBU). Renderizados aqui pra
        # transparência. Engine não modela ainda — PR 3 vai adicionar
        # scenario types específicos (LakebaseScenario, etc.).
        lakebase_data = catalog_dbu.get("lakebase")
        if lakebase_data:
            st.markdown("---")
            st.markdown("##### 🗄️ Lakebase — Database Serverless")
            st.caption(
                f"Postgres managed pra serving de data/features. "
                f"Disponível em: **{', '.join(lakebase_data.get('available_clouds', []))}**. "
                f"Fonte: {lakebase_data.get('source_url', 'databricks.com')}"
            )
            promo_until = lakebase_data.get("promo_until")
            if promo_until:
                st.info(
                    f"🎁 **Promoção 50% off** ativa até **{promo_until}** — preços abaixo já refletem o desconto."
                )
            lakebase_rows = [
                {
                    "Item": "Autoscaling Compute",
                    "Preço (promo)": f"${lakebase_data.get('autoscaling_per_cu_h_promo', 0):.3f}/CU·h",
                    "Preço list": f"${lakebase_data.get('autoscaling_per_cu_h_list', 0):.3f}/CU·h",
                },
                {
                    "Item": "Always-On Compute (min)",
                    "Preço (promo)": f"${lakebase_data.get('always_on_min_per_cu_h_promo', 0):.3f}/CU·h",
                    "Preço list": f"${lakebase_data.get('always_on_min_per_cu_h_list', 0):.3f}/CU·h",
                },
                {
                    "Item": "Database Storage",
                    "Preço (promo)": f"${lakebase_data.get('storage_per_gb_month', 0):.3f}/GB·month",
                    "Preço list": "—",
                },
            ]
            st.dataframe(pd.DataFrame(lakebase_rows), use_container_width=True, hide_index=True)
            st.caption(
                "📐 CU = Capacity Unit (unidade Postgres-equivalent). "
                "Não disponível em GCP. Engine ainda não modela Lakebase — usar como referência apenas."
            )

        lfc_data = catalog_dbu.get("lakeflow_connect")
        if lfc_data:
            st.markdown("---")
            st.markdown("##### 🔌 Lakeflow Connect — Ingestão Managed")
            st.caption(
                f"Connectors enterprise + Zerobus Ingest (push API). "
                f"Fonte: {lfc_data.get('source_url', 'databricks.com')}"
            )
            mc = lfc_data.get("managed_connectors", {})
            zb = lfc_data.get("zerobus_ingest", {})
            lfc_rows = [
                {
                    "Item": "Managed Connectors",
                    "Preço": f"${mc.get('base_per_dbu', 0):.2f}/DBU",
                    "Free tier": f"{mc.get('free_tier_dbu_per_workspace_per_day', 0)} DBU/workspace/dia",
                    "Promo": "—",
                },
                {
                    "Item": "Zerobus Ingest",
                    "Preço": f"${zb.get('per_gb_promo', 0):.3f}/GB (promo) / ${zb.get('per_gb_list', 0):.3f}/GB (list)",
                    "Free tier": "—",
                    "Promo": f"50% off até {zb.get('promo_until', '—')}",
                },
            ]
            st.dataframe(pd.DataFrame(lfc_rows), use_container_width=True, hide_index=True)
            st.caption(
                "💡 Bills aparecem como **Jobs Serverless** ou **Automated Serverless** SKU. "
                "Engine ainda não modela ingest jobs — usar como referência."
            )

        # ─── PR 3 (2026-05-28): AI/ML SKUs completo ────────────────────────
        # 10 novos blocos: Model Serving (CPU+GPU), Foundation Model Serving,
        # Proprietary FM (OpenAI/Anthropic/Gemini), Vector Search v2, AI Functions,
        # AI Gateway, Agent Bricks, Agent Evaluation, Model Training, AI Runtime.
        # Display-only — engine ainda não modela. PR 4 vai adicionar scenario types.

        # Model Serving
        ms = catalog_dbu.get("model_serving")
        if ms and isinstance(ms.get("gpu_instances"), dict):
            st.markdown("---")
            st.markdown("##### 🤖 Model Serving (CPU + GPU)")
            st.caption(
                f"Real-time inference. Bills: Serverless Real-time Inference SKU. "
                f"Fonte: {ms.get('source_url', 'databricks.com')}"
            )
            st.markdown(
                f"**CPU Serving**: `${ms.get('cpu_per_dbu', 0):.3f}/DBU` · "
                f"**GPU Serving**: `${ms.get('gpu_per_dbu', 0):.3f}/DBU` (rates iguais; "
                f"diferenciação por DBU/h da instance)"
            )
            ms_rows = [
                {"Size": k, "GPU config": v.get("gpu", "—"), "DBU/h": v.get("dbu_per_hour", 0)}
                for k, v in ms["gpu_instances"].items()
            ]
            st.dataframe(pd.DataFrame(ms_rows), use_container_width=True, hide_index=True)

        # Foundation Model Serving
        fms = catalog_dbu.get("foundation_model_serving")
        if fms:
            st.markdown("---")
            st.markdown("##### 🧠 Foundation Model Serving")
            st.caption(
                f"3 modos: Pay-Per-Token (${fms['pay_per_token']['input_per_m_tokens_usd']}/M in + "
                f"${fms['pay_per_token']['output_per_m_tokens_usd']}/M out), "
                f"Provisioned Throughput (${fms['provisioned_throughput']['per_hour_per_pt_unit_usd']}/h/unit), "
                f"Batch Inference (${fms['batch_inference']['per_hour_per_throughput_band_usd']}/h/band). "
                f"Fonte: {fms.get('source_url', 'databricks.com')}"
            )
            models = fms.get("per_model_dbu_rates", {})
            if models:
                fms_rows = [
                    {
                        "Model": k.replace("_", " ").title(),
                        "DBU/M Input": v.get("input_dbu_per_m") or "—",
                        "DBU/M Output": v.get("output_dbu_per_m") or "—",
                        "DBU/h (Entry PT)": v.get("entry_pt_dbu_h") or "—",
                        "DBU/h (Scaling PT)": v.get("scaling_pt_dbu_h") or "—",
                    }
                    for k, v in models.items()
                ]
                st.dataframe(pd.DataFrame(fms_rows), use_container_width=True, hide_index=True)

        # Proprietary Foundation Model Serving
        pfms = catalog_dbu.get("proprietary_foundation_model_serving")
        if pfms:
            st.markdown("---")
            st.markdown(
                "##### 🔒 Proprietary Foundation Model Serving (OpenAI / Anthropic / Gemini)"
            )
            st.caption(
                f"Pay-Per-Token + Batch: `${pfms.get('base_per_dbu_pay_per_token', 0):.3f}/DBU`. "
                f"Bills: AWS/GCP → '<Vendor> Model Serving' SKU. Azure → ADI Service. "
                f"Fonte: {pfms.get('source_url', 'databricks.com')}"
            )
            openai_models = pfms.get("vendors", {}).get("openai", {}).get("models", {})
            if openai_models:
                st.markdown(
                    "**OpenAI — Global Short context (in-geo +~10% uplift, long context ~2x):**"
                )
                pfms_rows = [
                    {
                        "Model": k.replace("_", " ").upper(),
                        "DBU/M In": v.get("input_dbu_per_m") or "—",
                        "DBU/M Out": v.get("output_dbu_per_m") or "—",
                        "DBU/M Cache W": v.get("cache_write_dbu_per_m") or "—",
                        "DBU/M Cache R": v.get("cache_read_dbu_per_m") or "—",
                        "Batch DBU/h": v.get("batch_dbu_per_h") or "—",
                    }
                    for k, v in openai_models.items()
                ]
                st.dataframe(pd.DataFrame(pfms_rows), use_container_width=True, hide_index=True)
            st.caption(
                "⚠️ Anthropic e Gemini têm mesma estrutura ($0.07/DBU base) com tabelas DBU "
                "per-model próprias. Captura completa via Chrome MCP — TODO PR 4."
            )

        # Vector Search v2
        vsv2 = catalog_dbu.get("vector_search_v2")
        if vsv2:
            st.markdown("---")
            st.markdown("##### 🔍 Vector Search (Standard 2M + Storage Optimized 64M)")
            st.caption(
                f"Effective $/DBU US East = `${vsv2.get('effective_dollar_per_dbu_us_east', 0):.3f}`. "
                f"Bills: Serverless Real-time Inference. "
                f"Fonte: {vsv2.get('source_url', 'databricks.com')}"
            )
            tiers = vsv2.get("tiers", {})
            vs_rows = [
                {
                    "Tier": tier_name.replace("_", " ").title(),
                    "Compute $/h": tier_data.get("compute_per_hour_usd", 0),
                    "Storage $/GB·mo": tier_data.get("storage_per_gb_month_usd", 0),
                    "Free GB": tier_data.get("storage_free_gb", 0),
                    "Vector cap/unit": f"{tier_data.get('vector_capacity_per_unit', 0):,}",
                    "DBU/h": tier_data.get("dbu_per_hour", 0),
                }
                for tier_name, tier_data in tiers.items()
            ]
            st.dataframe(pd.DataFrame(vs_rows), use_container_width=True, hide_index=True)

        # AI Functions
        aif = catalog_dbu.get("ai_functions")
        if aif:
            st.markdown("---")
            st.markdown("##### 📄 AI Functions (Parse / Extract / Classify)")
            promo = aif.get("promo_until")
            if promo:
                st.info(
                    f"🎁 **Promoção 50% off** até **{promo}** — preços promo abaixo refletem desconto."
                )
            aif_rows = [
                {
                    "Function": fn.replace("_", " ").title(),
                    "$/DBU (promo)": data.get("per_dbu_promo", 0),
                    "$/DBU (list)": data.get("per_dbu_list", 0),
                    "Notes": data.get("note", ""),
                }
                for fn, data in aif.items()
                if isinstance(data, dict) and "per_dbu_promo" in data
            ]
            st.dataframe(pd.DataFrame(aif_rows), use_container_width=True, hide_index=True)
            st.caption(
                f"Fonte: {aif.get('source_url', 'databricks.com')}. Bills: Serverless Real-time Inference SKU."
            )

        # AI Gateway
        aig = catalog_dbu.get("ai_gateway")
        if aig:
            st.markdown("---")
            st.markdown("##### 🚪 AI Gateway (Guardrails / Inference Tables / Usage Tracking)")
            aig_rows = []
            if "ai_guardrails" in aig:
                aig_rows.append(
                    {
                        "Feature": "AI Guardrails",
                        "Preço": f"${aig['ai_guardrails']['per_m_tokens_usd']:.2f}/M tok",
                        "Unit": "M tokens",
                    }
                )
            if "inference_tables" in aig:
                aig_rows.append(
                    {
                        "Feature": "Inference Tables",
                        "Preço": f"${aig['inference_tables']['per_gb_usd']:.3f}/GB",
                        "Unit": f"GB (incr {aig['inference_tables'].get('increment', '1KB')})",
                    }
                )
            if "usage_tracking" in aig:
                aig_rows.append(
                    {
                        "Feature": "Usage Tracking",
                        "Preço": f"${aig['usage_tracking']['per_gb_usd']:.3f}/GB",
                        "Unit": f"GB (incr {aig['usage_tracking'].get('increment', '1KB')})",
                    }
                )
            st.dataframe(pd.DataFrame(aig_rows), use_container_width=True, hide_index=True)
            st.caption(f"Fonte: {aig.get('source_url', 'databricks.com')}")

        # Agent Bricks
        ab = catalog_dbu.get("agent_bricks")
        if ab:
            st.markdown("---")
            st.markdown("##### 🧱 Agent Bricks (Knowledge Assistant / Supervisor Agent)")
            promo = ab.get("promo_until")
            if promo:
                st.info(
                    f"🎁 **Promoção 50% off** até **{promo}** — preços promo abaixo refletem desconto."
                )
            ka = ab.get("knowledge_assistant", {})
            sa = ab.get("supervisor_agent", {})
            ab_rows = [
                {
                    "Feature": "Knowledge Assistant",
                    "Promo": f"${ka.get('per_answer_promo_usd', 0):.3f}/answer",
                    "List": f"${ka.get('per_answer_list_usd', 0):.3f}/answer",
                    "Unit": "answer",
                },
                {
                    "Feature": "Supervisor Agent",
                    "Promo": f"${sa.get('per_dbu_promo', 0):.3f}/DBU",
                    "List": f"${sa.get('per_dbu_list', 0):.3f}/DBU",
                    "Unit": "DBU·h",
                },
            ]
            st.dataframe(pd.DataFrame(ab_rows), use_container_width=True, hide_index=True)
            st.caption(
                f"Fonte: {ab.get('source_url', 'databricks.com')}. Setup/storage cobrado em SKUs subjacentes (Vector Search, FM Serving)."
            )

        # Agent Evaluation
        ae = catalog_dbu.get("agent_evaluation")
        if ae:
            st.markdown("---")
            st.markdown("##### ✅ Agent Evaluation (MLflow)")
            ae_rows = [
                {
                    "Item": "Input tokens",
                    "Preço": f"${ae.get('input_per_m_tokens_usd', 0):.2f}/M tok",
                },
                {
                    "Item": "Output tokens",
                    "Preço": f"${ae.get('output_per_m_tokens_usd', 0):.2f}/M tok",
                },
                {
                    "Item": "Synthetic Data",
                    "Preço": f"${ae.get('synthetic_data', {}).get('per_question_usd', 0):.2f}/question",
                },
            ]
            st.dataframe(pd.DataFrame(ae_rows), use_container_width=True, hide_index=True)
            st.caption(f"Fonte: {ae.get('source_url', 'databricks.com')}")

        # Model Training (Foundation Model Training)
        mt = catalog_dbu.get("model_training")
        if mt:
            st.markdown("---")
            st.markdown(
                f"##### 🎓 Foundation Model Training {'(' + mt.get('status', '') + ')' if mt.get('status') else ''}"
            )
            st.markdown(
                f"**Fine-tuning**: `${mt.get('fine_tuning_per_dbu_usd', 0):.2f}/DBU` · "
                f"**Forecasting**: `${mt.get('forecasting_per_dbu_usd', 0):.2f}/DBU`"
            )
            estimates = mt.get("fine_tuning_dbu_estimates", {})
            if estimates:
                est_rows = [
                    {
                        "Model": k.replace("_", " ").title(),
                        "DBU (10M words)": v.get("dbu_10m_words", 0),
                        "DBU (500M words)": v.get("dbu_500m_words", 0),
                        "Cost (10M words)": f"${v.get('dbu_10m_words', 0) * mt.get('fine_tuning_per_dbu_usd', 0):.2f}",
                        "Cost (500M words)": f"${v.get('dbu_500m_words', 0) * mt.get('fine_tuning_per_dbu_usd', 0):.2f}",
                    }
                    for k, v in estimates.items()
                ]
                st.markdown("**DBU estimates por modelo (fine-tuning):**")
                st.dataframe(pd.DataFrame(est_rows), use_container_width=True, hide_index=True)
            st.caption(f"Fonte: {mt.get('source_url', 'databricks.com')}")

        # AI Runtime
        ait = catalog_dbu.get("ai_runtime")
        if ait:
            available = ait.get("available_clouds", [])
            st.markdown("---")
            st.markdown(
                f"##### ⚡ AI Runtime {'(' + ait.get('status', '') + ')' if ait.get('status') else ''}"
            )
            if catalog_dbu.get("cloud") not in available:
                st.warning(
                    f"⚠️ AI Runtime **não disponível em {catalog_dbu.get('cloud', '?').upper()}** "
                    f"oficialmente. Disponível em: {', '.join(available)}."
                )
            ait_rows = [
                {
                    "GPU": "A10 On Demand",
                    "Preço": f"${ait.get('a10_on_demand_per_dbu_usd', 0):.2f}/DBU",
                    "Use case": "Train/fine-tune smaller models",
                },
                {
                    "GPU": "H100 On Demand",
                    "Preço": f"${ait.get('h100_on_demand_per_dbu_usd', 0):.2f}/DBU",
                    "Use case": "Train/fine-tune large models",
                },
            ]
            st.dataframe(pd.DataFrame(ait_rows), use_container_width=True, hide_index=True)
            st.caption(
                f"Fonte: {ait.get('source_url', 'databricks.com')}. Bills: Model Training SKU."
            )

        # ─── PR 4 (2026-05-28): Platform SKUs ──────────────────────────────
        # 7 novos blocos plataforma: Default Storage, Data Transfer, Managed Services,
        # Platform Add-ons, Clean Rooms, View Sharing, Delta Share SAP BDC.

        # Default Storage
        ds = catalog_dbu.get("default_storage")
        if ds:
            st.markdown("---")
            st.markdown("##### 💾 Default Storage (Databricks-managed)")
            st.caption(
                f"DSU = Databricks Storage Unit. 1 GB·month = 1 DSU = `${ds.get('per_dsu_usd', 0):.3f}`. "
                f"Fonte: {ds.get('source_url', 'databricks.com')}"
            )
            current_cloud = catalog_dbu.get("cloud", "azure")
            ops = ds.get("operations_per_1000", {}).get(current_cloud, {})
            ds_rows = [
                {
                    "Item": "Stored Data",
                    "Unit": "GB·month",
                    "DSU rate": f"{ops.get('stored_data_per_gb_month_dsu', 1.0)} DSU/GB·mo",
                    "USD cost": f"${ds.get('per_dsu_usd', 0) * ops.get('stored_data_per_gb_month_dsu', 1.0):.4f}/GB·mo",
                },
                {
                    "Item": "Tier 1 (Writes/PUT/COPY)",
                    "Unit": "1000 ops",
                    "DSU rate": f"{ops.get('tier1_writes_dsu', 0)} DSU/1k ops",
                    "USD cost": f"${ds.get('per_dsu_usd', 0) * ops.get('tier1_writes_dsu', 0):.6f}/1k ops",
                },
                {
                    "Item": "Tier 2 (Reads/GET)",
                    "Unit": "1000 ops",
                    "DSU rate": f"{ops.get('tier2_reads_dsu', 0)} DSU/1k ops",
                    "USD cost": f"${ds.get('per_dsu_usd', 0) * ops.get('tier2_reads_dsu', 0):.6f}/1k ops",
                },
            ]
            st.dataframe(pd.DataFrame(ds_rows), use_container_width=True, hide_index=True)
            st.caption(
                f"Rates específicos para **{current_cloud.upper()}**. DSU operations diferem por cloud — Azure usa Tier 1/2, AWS usa PUT/GET, GCP usa Class A/B."
            )

        # Data Transfer
        dt = catalog_dbu.get("data_transfer")
        if dt:
            st.markdown("---")
            st.markdown("##### 🌐 Data Transfer & Connectivity")
            st.caption(
                f"Charges quando data move entre regions/AZs ou sai do Databricks. "
                f"Preços específicos vêm de docs por cloud (não cobertos no catalog). "
                f"Fonte: {dt.get('source_url', 'databricks.com')}"
            )
            current_cloud = catalog_dbu.get("cloud", "azure")
            conn_types = dt.get("connection_types", {})
            dt_rows = []
            for name, data in conn_types.items():
                if isinstance(data, dict):
                    billed_key = f"billed_{current_cloud}"
                    billed_status = (
                        "Yes" if data.get(billed_key, data.get("billed", False)) else "WAIVED"
                    )
                    dt_rows.append(
                        {
                            "Type": name.replace("_", " ").title(),
                            "Unit": data.get("cost_unit", "—"),
                            f"Billed in {current_cloud.upper()}": billed_status,
                            "Note": data.get("note", "")[:80],
                        }
                    )
            st.dataframe(pd.DataFrame(dt_rows), use_container_width=True, hide_index=True)

        # Managed Services
        msv = catalog_dbu.get("managed_services")
        if msv:
            st.markdown("---")
            st.markdown(
                "##### 🛠️ Managed Services (DQ Monitoring / Predictive Optimization / FGAC / Data Classification)"
            )
            dq = msv.get("data_quality_monitoring", {})
            if dq.get("promo_until"):
                st.info(
                    f"🎁 **DQ Monitoring 50% off** até **{dq['promo_until']}** "
                    f"(`${dq.get('per_dbu_promo', 0):.3f}/DBU` vs list `${dq.get('per_dbu_list', 0):.3f}/DBU`). "
                    f"⚠️ DBU multiplicador: **{dq.get('dbu_multiplier', 1)}x** — cada DBU consumido conta como {dq.get('dbu_multiplier', 1)} pra cobrança."
                )
            msv_rows = []
            for sku_name, sku_data in msv.items():
                if isinstance(sku_data, dict) and "cost_unit" in sku_data:
                    promo = sku_data.get("per_dbu_promo")
                    list_p = sku_data.get("per_dbu_list", sku_data.get("per_dbu_usd"))
                    msv_rows.append(
                        {
                            "SKU": sku_name.replace("_", " ").title(),
                            "Preço (current)": f"${promo:.3f}/DBU"
                            if promo
                            else f"${list_p:.3f}/DBU",
                            "Preço (list)": f"${list_p:.3f}/DBU" if list_p else "—",
                            "Promo until": sku_data.get("promo_until", "—"),
                            "DBU mult": sku_data.get("dbu_multiplier", 1.0),
                        }
                    )
            st.dataframe(pd.DataFrame(msv_rows), use_container_width=True, hide_index=True)
            st.caption(f"Fonte: {msv.get('source_url', 'databricks.com')}")

        # Platform Add-ons
        pa = catalog_dbu.get("platform_addons")
        if pa:
            st.markdown("---")
            st.markdown("##### 🔐 Platform Tiers & Add-ons")
            esc = pa.get("enhanced_security_and_compliance", {})
            if esc:
                st.markdown(
                    f"**Enhanced Security and Compliance**: `{esc.get('pct_of_product_spend', 0)}% of Product Spend` "
                    f"(antes de descontos/credits/uplifts). Aplicável em tiers: "
                    f"{', '.join(esc.get('available_tiers', []))}."
                )
                st.caption(esc.get("note", ""))
            st.caption(f"Fonte: {pa.get('source_url', 'databricks.com')}")

        # View Sharing
        vs = catalog_dbu.get("view_sharing")
        if vs:
            st.markdown("---")
            st.markdown("##### 🪟 View Sharing (cross-account + Open Sharing)")
            st.caption(
                f"Sharing de Views, MVs e Streaming Tables. "
                f"Fonte: {vs.get('source_url', 'databricks.com')}"
            )
            scenarios = vs.get("scenarios", {})
            vs_rows = [
                {
                    "Cenário": k.replace("_", " ").title(),
                    "$/DBU": f"${v.get('per_dbu_usd', 0):.2f}",
                    "Note": v.get("note", "")[:80],
                }
                for k, v in scenarios.items()
            ]
            st.dataframe(pd.DataFrame(vs_rows), use_container_width=True, hide_index=True)

        # Clean Rooms
        cr = catalog_dbu.get("clean_rooms")
        if cr:
            st.markdown("---")
            st.markdown("##### 🧹 Clean Rooms")
            st.caption(
                f"**Sem SKU própria** — cobrança via SKUs subjacentes. {cr.get('note', '')} "
                f"Fonte: {cr.get('source_url', 'databricks.com')}"
            )
            billing = cr.get("billing_skus", {})
            current_cloud = catalog_dbu.get("cloud", "azure")
            cr_rows = [
                {"Item": "Compute", "Billed as": billing.get(current_cloud, "—")},
                {"Item": "Storage", "Billed as": cr.get("storage_billed_via", "—")},
            ]
            st.dataframe(pd.DataFrame(cr_rows), use_container_width=True, hide_index=True)

        # Delta Share SAP BDC
        dsap = catalog_dbu.get("delta_share_sap_bdc")
        if dsap:
            st.markdown("---")
            st.markdown("##### 🆓 Delta Share from SAP Business Data Cloud")
            st.success(
                f"**100% FREE** — Data Sharing: {dsap.get('data_sharing_cost', 'FREE')} · "
                f"Compute: {dsap.get('compute_cost', 'FREE')}"
            )
            st.caption(f"{dsap.get('note', '')} Fonte: {dsap.get('source_url', 'databricks.com')}")

    # ─── Sub-tab 2: Azure VM prices ─────────────────────────────────────────
    with sub2:
        st.markdown("##### Azure VM Prices (Linux on-demand)")

        col_a1, col_a2 = st.columns(2)
        with col_a1:
            azure_region = st.selectbox(
                "Region",
                options=list_regions_for_cloud("azure"),
                key="catalogo_azure_region",
            )
        with col_a2:
            if real_active:
                st.caption(
                    "🔗 Source: Azure Retail Prices API  \n"
                    "https://prices.azure.com/api/retail/prices  \n"
                    "_Cache TTL 1h. Fallback pro mock se API falhar._"
                )
            else:
                st.caption(
                    "📦 Source: `data_agents/cost_app/databricks/instance_prices.py` (mock)  \n"
                    "_Última atualização manual. Ative real mode pra valores ao vivo._"
                )

        skus = list_instances_for_region("azure", azure_region)
        if not skus:
            st.info("Nenhum SKU mapeado nesta region.")
        else:
            rows = []
            for sku in skus:
                mock_price = _get_mock_price_safe("azure", azure_region, sku)
                row = {"SKU": sku, "Mock USD/h": mock_price}

                if real_active:
                    try:
                        real = fetch_azure_vm_price(azure_region, sku)
                        row["Real API USD/h"] = real if real is not None else "—"
                        if real is not None and mock_price is not None:
                            delta_pct = (real - mock_price) / mock_price * 100
                            row["Δ% (real-mock)"] = round(delta_pct, 1)
                        else:
                            row["Δ% (real-mock)"] = "—"
                    except Exception as exc:
                        row["Real API USD/h"] = f"err: {str(exc)[:30]}"
                        row["Δ% (real-mock)"] = "—"

                rows.append(row)

            df = pd.DataFrame(rows)
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
            )

            if real_active:
                st.caption(
                    "💡 **Δ% (real-mock)**: positivo = mock está SUBESTIMANDO custo real. "
                    "Negativo = mock está SUPERESTIMANDO. Se Δ% > 20%, considere atualizar mock."
                )

    # ─── Sub-tab 3: AWS EC2 prices ──────────────────────────────────────────
    with sub3:
        st.markdown("##### AWS EC2 Prices (Linux on-demand, Shared tenancy)")

        col_w1, col_w2 = st.columns(2)
        with col_w1:
            aws_region = st.selectbox(
                "Region",
                options=list_regions_for_cloud("aws"),
                key="catalogo_aws_region",
            )
        with col_w2:
            if real_active and pricing_meta["boto3_available"]:
                st.caption(
                    "🔗 Source: AWS Pricing API (boto3)  \n"
                    "Requer AWS credentials no .env  \n"
                    "_Cache TTL 1h. Fallback pro mock se sem credenciais._"
                )
            elif real_active and not pricing_meta["boto3_available"]:
                st.warning(
                    "⚠️ `boto3` não instalado — AWS Pricing API indisponível. "
                    "Instale com: `pip install boto3`"
                )
            else:
                st.caption(
                    "📦 Source: `instance_prices.py` (mock)  \n"
                    "_Ative real mode pra valores ao vivo (requer AWS creds)._"
                )

        skus_aws = list_instances_for_region("aws", aws_region)
        if not skus_aws:
            st.info("Nenhum SKU mapeado nesta region.")
        else:
            rows_aws = []
            for sku in skus_aws:
                mock_price = _get_mock_price_safe("aws", aws_region, sku)
                row = {"SKU": sku, "Mock USD/h": mock_price}

                if real_active and pricing_meta["boto3_available"]:
                    try:
                        real = fetch_aws_ec2_price(aws_region, sku)
                        row["Real API USD/h"] = real if real is not None else "—"
                        if real is not None and mock_price is not None:
                            delta_pct = (real - mock_price) / mock_price * 100
                            row["Δ% (real-mock)"] = round(delta_pct, 1)
                        else:
                            row["Δ% (real-mock)"] = "—"
                    except Exception as exc:
                        row["Real API USD/h"] = f"err: {str(exc)[:30]}"
                        row["Δ% (real-mock)"] = "—"

                rows_aws.append(row)

            df_aws = pd.DataFrame(rows_aws)
            st.dataframe(
                df_aws,
                use_container_width=True,
                hide_index=True,
            )


def _get_mock_price_safe(cloud: str, region: str, sku: str) -> float | None:
    """Wrapper que retorna None em vez de KeyError pra não quebrar Tab Catálogo."""
    try:
        from data_agents.cost_app.databricks.instance_prices import _get_mock_price

        return _get_mock_price(cloud, region, sku)
    except (KeyError, ValueError):
        return None


def render_tab_otimizacao() -> None:
    """Tab 7: análises proativas de otimização (rightsizing + idle + Photon ROI)."""
    from data_agents.cost_engine.billing import BillingPeriod
    from data_agents.cost_engine.optimization import (
        IdleThresholds,
        RightsizingThresholds,
        detect_idle_clusters,
        detect_rightsizing_opportunities,
        evaluate_photon_roi,
    )

    st.markdown("#### 🔧 Otimização Proativa")
    st.caption(
        "Análises sobre workloads em produção pra detectar oportunidades de redução de custo. "
        "Engine: `cost_engine/optimization.py` (Fase 4). Distinto da Tab 'FinOps Realizado' "
        "(que mostra consumo bruto)."
    )

    cloud = st.session_state.cloud.upper()

    # ─── Inputs globais ──────────────────────────────────────────────────────
    col_f1, col_f2, col_f3 = st.columns([1, 1, 2])
    with col_f1:
        period_days = st.selectbox(
            "Janela",
            options=[14, 30, 60],
            index=1,
            format_func=lambda d: f"Últimos {d} dias",
            key="opt_period",
            help="Janelas < 14 dias amplificam ruído. Recomendado: ≥30 dias.",
        )
    with col_f2:
        opt_mode = st.radio(
            "Modo",
            options=["Mock", "Real"],
            index=0,
            horizontal=True,
            key="opt_mode",
            help="Mock = dados sintéticos. Real = system.billing via warehouse.",
        )
    with col_f3:
        st.caption(
            "Análises disponíveis: rightsizing (subutilização), idle hunting "
            "(sempre on sem uso), Photon ROI (custo 2× vs aceleração)."
        )

    use_mock = opt_mode == "Mock"

    # ─── Carrega dados (compartilhado entre todas as análises) ───────────────
    from datetime import datetime, timedelta, timezone

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=period_days - 1)
    period = BillingPeriod(start_date=start_date, end_date=end_date)

    try:
        usage_df, _prices_df = load_billing_data(period=period, cloud=cloud, mock=use_mock)
    except RuntimeError as exc:
        st.error(f"❌ Erro ao carregar dados: {exc}")
        return

    if usage_df.empty:
        st.info("📭 Sem registros de consumo na janela selecionada.")
        return

    if use_mock:
        st.caption("📦 Mock mode — dados sintéticos pra demonstração")
    else:
        st.caption("🔗 Real mode — dados de system.billing.usage")

    st.divider()

    # ─── Sub-tabs internos (3 análises) ──────────────────────────────────────
    sub1, sub2, sub3 = st.tabs(["📉 Rightsizing", "💤 Idle Hunting", "⚡ Photon ROI"])

    # ── Rightsizing ──────────────────────────────────────────────────────────
    with sub1:
        st.markdown("##### 📉 Rightsizing — Clusters Subutilizados")
        st.caption(
            "Detecta clusters cuja média de DBU/h consumido está muito abaixo do esperado "
            "pelo seu compute_type — candidatos a downsize."
        )

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            underuse_pct = (
                st.slider(
                    "Limiar de subutilização (%)",
                    min_value=10,
                    max_value=80,
                    value=50,
                    step=5,
                    key="rightsize_underuse",
                    help="Cluster com utilização abaixo desse % é flagged como downsize.",
                )
                / 100.0
            )
        with col_t2:
            min_days = st.slider(
                "Dias mínimos observados",
                min_value=3,
                max_value=30,
                value=7,
                key="rightsize_min_days",
            )

        rightsize_df = detect_rightsizing_opportunities(
            usage_df,
            period,
            thresholds=RightsizingThresholds(
                underuse_pct=underuse_pct,
                min_days_observed=min_days,
            ),
        )

        if rightsize_df.empty:
            st.info("Nenhum cluster com dados suficientes pra análise.")
        else:
            downsize_count = int((rightsize_df["suggestion"] == "downsize").sum())
            st.metric("Candidatos a downsize", f"{downsize_count} / {len(rightsize_df)}")

            display_cols = [
                "cluster_name",
                "compute_type",
                "days_observed",
                "avg_dbu_per_hour",
                "expected_dbu_per_hour",
                "utilization_pct",
                "suggestion",
                "potential_savings_pct",
            ]
            st.dataframe(
                rightsize_df[display_cols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "utilization_pct": st.column_config.NumberColumn(
                        "Utilização %", format="%.2f%%"
                    ),
                    "potential_savings_pct": st.column_config.NumberColumn(
                        "Savings potencial", format="%.2f%%"
                    ),
                    "avg_dbu_per_hour": st.column_config.NumberColumn("Avg DBU/h", format="%.2f"),
                    "expected_dbu_per_hour": st.column_config.NumberColumn(
                        "Expected DBU/h", format="%.2f"
                    ),
                },
            )

            if downsize_count > 0:
                st.caption(
                    "💡 **Próximo passo:** investigar cada candidato — pode ser autoscale "
                    "configurado mas nunca usado, ou cluster manual oversized. NÃO ajuste "
                    "automaticamente: pode haver picos pontuais que justificam o sizing."
                )

    # ── Idle Hunting ─────────────────────────────────────────────────────────
    with sub2:
        st.markdown("##### 💤 Idle Hunting — Clusters Sempre On Sem Uso")
        st.caption(
            "Detecta clusters ativos em quase todos os dias da janela MAS com DBU/h "
            "muito baixo (auto-termination desativado ou agressivo demais)."
        )

        col_i1, col_i2 = st.columns(2)
        with col_i1:
            max_dbu_h = st.slider(
                "Threshold DBU/h (idle)",
                min_value=0.1,
                max_value=2.0,
                value=0.5,
                step=0.1,
                key="idle_max_dbu",
                help="Cluster com avg DBU/h abaixo desse valor é candidato a idle.",
            )
        with col_i2:
            min_active_pct = (
                st.slider(
                    "% dias ativos (sempre on)",
                    min_value=50,
                    max_value=100,
                    value=70,
                    step=5,
                    key="idle_active_pct",
                )
                / 100.0
            )

        idle_df = detect_idle_clusters(
            usage_df,
            period,
            thresholds=IdleThresholds(
                max_dbu_per_hour=max_dbu_h,
                min_active_days_pct=min_active_pct,
            ),
        )

        if idle_df.empty:
            st.info("Nenhum cluster analisável na janela.")
        else:
            idle_count = int((idle_df["verdict"] == "idle").sum())
            low_use_count = int((idle_df["verdict"] == "low_use").sum())

            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.metric("Idle (sempre on, sem uso)", idle_count)
            with col_m2:
                st.metric("Low use (uso bursty)", low_use_count)

            display_cols = [
                "cluster_name",
                "active_days",
                "active_days_pct",
                "total_dbus",
                "avg_dbu_per_hour",
                "verdict",
                "savings_hint",
            ]
            st.dataframe(
                idle_df[display_cols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "active_days_pct": st.column_config.NumberColumn("Active %", format="%.2f%%"),
                    "avg_dbu_per_hour": st.column_config.NumberColumn("Avg DBU/h", format="%.2f"),
                    "total_dbus": st.column_config.NumberColumn("Total DBUs", format="%.2f"),
                },
            )

            if idle_count > 0:
                st.caption(
                    "💡 **Próximo passo (idle):** habilitar auto-termination com timeout "
                    "agressivo (10-15min idle), ou migrar pra Serverless SQL que tem "
                    "auto-pause built-in."
                )

    # ── Photon ROI ───────────────────────────────────────────────────────────
    with sub3:
        st.markdown("##### ⚡ Photon ROI — Vale a Pena Pagar 2× DBU?")
        st.warning(
            "⚠️ **Caveat forte:** comparação válida apenas se os 2 clusters rodam workload "
            "SIMILAR (mesma natureza de query). Sem `system.query.history`, usamos DBU total "
            "como proxy de tempo — resultado é estimativa, não definitivo."
        )

        cluster_options = sorted(usage_df["cluster_name"].dropna().unique().tolist())
        if len(cluster_options) < 2:
            st.info(
                "Pelo menos 2 clusters distintos são necessários pra comparação. "
                "Janela atual tem apenas " + str(len(cluster_options)) + "."
            )
            return

        col_p1, col_p2 = st.columns(2)
        with col_p1:
            cluster_with = st.selectbox(
                "Cluster COM Photon",
                options=cluster_options,
                index=0,
                key="photon_with",
            )
        with col_p2:
            other_options = [c for c in cluster_options if c != cluster_with]
            cluster_without = st.selectbox(
                "Cluster SEM Photon",
                options=other_options,
                index=0,
                key="photon_without",
            )

        if st.button("📊 Comparar Photon vs sem Photon", use_container_width=True):
            try:
                # Mapeia name → cluster_id
                with_id_series = usage_df[usage_df["cluster_name"] == cluster_with]["cluster_id"]
                without_id_series = usage_df[usage_df["cluster_name"] == cluster_without][
                    "cluster_id"
                ]

                if with_id_series.empty or without_id_series.empty:
                    st.error("Cluster sem cluster_id válido na janela.")
                    return

                cluster_id_with = str(with_id_series.iloc[0])
                cluster_id_without = str(without_id_series.iloc[0])

                result = evaluate_photon_roi(usage_df, period, cluster_id_with, cluster_id_without)

                # Verdict display
                verdict_labels = {
                    "photon_worth_it": "✅ Photon compensa",
                    "photon_marginal": "⚠️ Marginal — depende do workload",
                    "photon_not_worth": "❌ Photon não compensa (custo 2× sem aceleração suficiente)",
                }

                col_v1, col_v2, col_v3 = st.columns(3)
                with col_v1:
                    st.metric("DBU com Photon", f"{result.total_dbus_with:.2f}")
                with col_v2:
                    st.metric("DBU sem Photon", f"{result.total_dbus_without:.2f}")
                with col_v3:
                    st.metric("Relative consumption", f"{result.relative_consumption:.2f}")

                st.markdown(f"**Verdict:** {verdict_labels.get(result.verdict, result.verdict)}")
                st.markdown(
                    f"**Speedup proxy estimado:** {result.actual_speedup_proxy:.2f}× "
                    f"(precisa ≥ {result.breakeven_speedup:.1f}× pra empatar custo)"
                )
                st.caption(f"⚠️ Caveat: {result.caveat}")
            except ValueError as exc:
                st.error(f"Erro no compare: {exc}")


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


# ─── Tab 9: AI/ML Cost Calculator (PR 7, 2026-05-28) ─────────────────────────


def render_tab_ai_ml_calculator() -> None:
    """Calculadora interativa pra scenarios AI/ML (LLM, Vector Search, Lakebase, Agent Bricks).

    Usa os scenarios do PR 5 (databricks_ai_ml). 4 sub-tabs:
        - 🧠 LLM Tokens (Foundation + Proprietary)
        - 🔍 Vector Search Sizing
        - 🗄️ Lakebase CU·h
        - 🧱 Agent Bricks Q&A
    """
    st.markdown("#### 🧠 AI/ML Cost Calculator")
    st.caption(
        "Cenários para SKUs AI/ML (PR 5 engine). Promoção aplicada automaticamente "
        "se hoje < `promo_until` no catalog. Engine determinístico — mesma entrada = mesma saída."
    )

    cloud = st.session_state.get("cloud", "azure")
    try:
        catalog = load_databricks_catalog(cloud)  # type: ignore[arg-type]
    except Exception as exc:
        st.error(f"Falha ao carregar catalog: {exc}")
        return

    sub_llm, sub_vs, sub_lb, sub_ab = st.tabs(
        ["🧠 LLM Tokens", "🔍 Vector Search", "🗄️ Lakebase", "🧱 Agent Bricks"]
    )

    # ─── Sub-tab 1: LLM Tokens ──────────────────────────────────────────────
    with sub_llm:
        st.markdown("##### 🧠 LLM Token Cost Calculator")

        col_v, col_m = st.columns(2)
        with col_v:
            vendor = st.selectbox(
                "Vendor",
                options=["foundation_open", "openai", "anthropic", "gemini"],
                format_func=lambda v: {
                    "foundation_open": "Foundation (open LLMs)",
                    "openai": "OpenAI (proprietary)",
                    "anthropic": "Anthropic (stub — PR 6)",
                    "gemini": "Gemini (stub — PR 6)",
                }[v],
                key="aiml_llm_vendor",
            )
        with col_m:
            mode = st.selectbox(
                "Modo",
                options=["pay_per_token", "provisioned_throughput", "batch_inference"],
                format_func=lambda m: {
                    "pay_per_token": "Pay-Per-Token",
                    "provisioned_throughput": "Provisioned Throughput",
                    "batch_inference": "Batch Inference",
                }[m],
                key="aiml_llm_mode",
            )

        # Model dropdown depende do vendor
        model: str | None = None
        if vendor == "foundation_open":
            fms = catalog.get("foundation_model_serving", {})
            models = list((fms.get("per_model_dbu_rates") or {}).keys())
            if models:
                model = st.selectbox(
                    "Modelo (opcional — usado se quiser ver DBU rates do modelo no breakdown)",
                    options=["(use rate base PPT)"] + models,
                    key="aiml_llm_model_foundation",
                )
                if model == "(use rate base PPT)":
                    model = None
        elif vendor == "openai":
            pfms = catalog.get("proprietary_foundation_model_serving", {})
            openai_models = list(
                (pfms.get("vendors", {}).get("openai", {}).get("models") or {}).keys()
            )
            if openai_models:
                model = st.selectbox(
                    "Modelo OpenAI", options=openai_models, key="aiml_llm_model_openai"
                )
        else:
            st.warning(
                f"⚠️ {vendor.title()} ainda é stub no catalog (PR 6 vai capturar Chrome MCP). "
                f"Cálculo retorna $0 + warning."
            )
            model = "any_model"

        st.markdown("---")

        # Inputs dependem do mode
        scenario_kwargs: dict = {
            "cloud": cloud,
            "mode": mode,
            "vendor": vendor,
            "model": model,
        }
        if mode == "pay_per_token":
            col_i, col_o = st.columns(2)
            with col_i:
                scenario_kwargs["m_input_tokens"] = st.number_input(
                    "M tokens input (milhões)", min_value=0.0, value=1.0, step=0.5, key="aiml_m_in"
                )
            with col_o:
                scenario_kwargs["m_output_tokens"] = st.number_input(
                    "M tokens output (milhões)",
                    min_value=0.0,
                    value=0.5,
                    step=0.5,
                    key="aiml_m_out",
                )
            if vendor == "openai":
                col_cw, col_cr = st.columns(2)
                with col_cw:
                    scenario_kwargs["m_cache_write_tokens"] = st.number_input(
                        "M cache write tokens", min_value=0.0, value=0.0, step=0.1, key="aiml_m_cw"
                    )
                with col_cr:
                    scenario_kwargs["m_cache_read_tokens"] = st.number_input(
                        "M cache read tokens", min_value=0.0, value=0.0, step=0.1, key="aiml_m_cr"
                    )
                col_g, col_l = st.columns(2)
                with col_g:
                    scenario_kwargs["in_geo"] = st.toggle(
                        "📍 In-geo (+10%)",
                        help="Regional in-geo endpoint, ~10% uplift sobre Global Short",
                        key="aiml_in_geo",
                    )
                with col_l:
                    scenario_kwargs["long_context"] = st.toggle(
                        "📏 Long context (×2)",
                        help="GPT 5.4/5.5 Pro / 5.4 long context: ~2x uplift",
                        key="aiml_long_ctx",
                    )
        elif mode == "provisioned_throughput":
            col_u, col_h = st.columns(2)
            with col_u:
                scenario_kwargs["pt_units"] = st.number_input(
                    "PT Units", min_value=1, value=1, step=1, key="aiml_pt_units"
                )
            with col_h:
                scenario_kwargs["pt_hours"] = st.number_input(
                    "PT Hours (mensal)",
                    min_value=0.0,
                    value=720.0,
                    step=24.0,
                    key="aiml_pt_hours",
                )
        elif mode == "batch_inference":
            col_b, col_bh = st.columns(2)
            with col_b:
                scenario_kwargs["batch_throughput_bands"] = st.number_input(
                    "Batch throughput bands",
                    min_value=1,
                    value=1,
                    step=1,
                    key="aiml_batch_bands",
                )
            with col_bh:
                scenario_kwargs["batch_hours"] = st.number_input(
                    "Batch hours", min_value=0.0, value=10.0, step=1.0, key="aiml_batch_hours"
                )

        scenario = LLMScenario(**scenario_kwargs)
        try:
            result = calculate_llm_cost(scenario, catalog)
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                st.metric("💵 Custo Mensal", f"${result['totals']['monthly']:.4f}")
            with col_t2:
                st.metric("📅 Custo Anual", f"${result['totals']['annual']:.2f}")

            with st.expander("📊 Breakdown completo", expanded=False):
                st.json(result["breakdown"])
            with st.expander("🔧 Inputs resolved (auditoria)", expanded=False):
                st.json(result["inputs_resolved"])
            for w in result["warnings"]:
                st.warning(w)
        except (KeyError, ValueError) as exc:
            st.error(f"Erro no cálculo: {exc}")

    # ─── Sub-tab 2: Vector Search ───────────────────────────────────────────
    with sub_vs:
        st.markdown("##### 🔍 Vector Search Sizing Calculator")
        col_t, col_u = st.columns(2)
        with col_t:
            tier = st.selectbox(
                "Tier",
                options=["standard", "storage_optimized"],
                format_func=lambda t: {
                    "standard": "Standard (2M vectors/unit, 30 GB free storage)",
                    "storage_optimized": "Storage Optimized (64M vectors/unit, sem free)",
                }[t],
                key="aiml_vs_tier",
            )
        with col_u:
            num_units = st.number_input(
                "Number of units", min_value=1, value=1, step=1, key="aiml_vs_units"
            )
        col_h, col_s, col_ap = st.columns(3)
        with col_h:
            hours = st.number_input(
                "Hours/month", min_value=1.0, value=720.0, step=24.0, key="aiml_vs_hours"
            )
        with col_s:
            storage_gb = st.number_input(
                "Storage (GB)", min_value=0.0, value=50.0, step=10.0, key="aiml_vs_storage"
            )
        with col_ap:
            is_ap = st.toggle("🌏 AP region (+25%)", key="aiml_vs_ap")

        scenario = VectorSearchScenario(
            cloud=cloud,  # type: ignore[arg-type]
            tier=tier,
            num_units=num_units,
            hours_per_month=hours,
            storage_gb=storage_gb,
            is_ap_region=is_ap,
        )
        try:
            result = calculate_vector_search_cost(scenario, catalog)
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                st.metric("💵 Custo Mensal", f"${result['totals']['monthly']:.2f}")
            with col_t2:
                st.metric("📅 Custo Anual", f"${result['totals']['annual']:.2f}")

            # Capacity estimation
            tiers_data = catalog.get("vector_search_v2", {}).get("tiers", {}).get(tier, {})
            capacity = tiers_data.get("vector_capacity_per_unit", 0) * num_units
            st.caption(f"📐 Capacidade estimada: **{capacity:,} vectors** com {num_units} unit(s)")

            with st.expander("📊 Breakdown completo", expanded=True):
                st.json(result["breakdown"])
            with st.expander("🔧 Inputs resolved", expanded=False):
                st.json(result["inputs_resolved"])
        except (KeyError, ValueError) as exc:
            st.error(f"Erro: {exc}")

    # ─── Sub-tab 3: Lakebase ────────────────────────────────────────────────
    with sub_lb:
        st.markdown("##### 🗄️ Lakebase Cost Calculator")

        lakebase_data = catalog.get("lakebase")
        if lakebase_data is None:
            st.warning(
                f"⚠️ Lakebase não disponível em **{cloud.upper()}** oficialmente. "
                "Disponível em: AWS + Azure. Cálculo retornará $0."
            )

        col_m, col_cu = st.columns(2)
        with col_m:
            mode = st.selectbox(
                "Mode",
                options=["autoscaling", "always_on"],
                format_func=lambda m: {
                    "autoscaling": "Autoscaling (escala com tráfego, scale-to-zero)",
                    "always_on": "Always-On (minimum, no scale-to-zero)",
                }[m],
                key="aiml_lb_mode",
            )
        with col_cu:
            cu_hours = st.number_input(
                "CU·hours / month",
                min_value=0.0,
                value=720.0,
                step=24.0,
                key="aiml_lb_cu_hours",
                help="Capacity Unit Hours. 720 = 1 CU sempre ligado por 1 mês.",
            )
        storage_gb_months = st.number_input(
            "Storage GB·months",
            min_value=0.0,
            value=100.0,
            step=10.0,
            key="aiml_lb_storage",
            help="GB armazenado × meses (ex: 100 GB durante 1 mês = 100)",
        )

        col_p1, col_p2 = st.columns(2)
        with col_p1:
            use_promo = st.toggle("🎁 Aplicar promo se ativa", value=True, key="aiml_lb_promo")
        with col_p2:
            today_override = st.text_input(
                "Date override (YYYY-MM-DD, opcional)",
                value="",
                placeholder="ex: 2027-02-01 (pós-promo)",
                key="aiml_lb_today",
                help="Vazio = data atual. Use pra simular cenário pós-promo.",
            )

        scenario = LakebaseScenario(
            cloud=cloud,  # type: ignore[arg-type]
            mode=mode,
            cu_hours=cu_hours,
            storage_gb_months=storage_gb_months,
            use_promo_if_active=use_promo,
            today_override=today_override or None,
        )
        try:
            result = calculate_lakebase_cost(scenario, catalog)
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                st.metric("💵 Custo Mensal", f"${result['totals']['monthly']:.2f}")
            with col_t2:
                promo_active = result["inputs_resolved"].get("promo_active", False)
                st.metric("🎁 Promo ativa?", "Sim" if promo_active else "Não")

            with st.expander("📊 Breakdown", expanded=True):
                st.json(result["breakdown"])
            with st.expander("🔧 Inputs resolved", expanded=False):
                st.json(result["inputs_resolved"])
            for w in result["warnings"]:
                st.warning(w)
        except (KeyError, ValueError) as exc:
            st.error(f"Erro: {exc}")

    # ─── Sub-tab 4: Agent Bricks ────────────────────────────────────────────
    with sub_ab:
        st.markdown("##### 🧱 Agent Bricks Cost Calculator")
        st.caption(
            "Knowledge Assistant cobra por **answer** (apenas answers que acessam KB). "
            "Supervisor Agent cobra por **DBU·h** (sub-agents passa-through ao preço nativo)."
        )

        col_ka, col_sa, col_sub = st.columns(3)
        with col_ka:
            ka_answers = st.number_input(
                "Knowledge Assistant: # answers/mês",
                min_value=0,
                value=1000,
                step=100,
                key="aiml_ab_ka",
            )
        with col_sa:
            sa_dbu = st.number_input(
                "Supervisor Agent: DBU·h/mês",
                min_value=0.0,
                value=50.0,
                step=5.0,
                key="aiml_ab_sa",
            )
        with col_sub:
            sub_agent_usd = st.number_input(
                "Sub-agents cost ($/mês)",
                min_value=0.0,
                value=0.0,
                step=10.0,
                key="aiml_ab_sub",
                help="Soma do custo de sub-agents (cada um cobrado ao preço nativo)",
            )

        col_p1, col_p2 = st.columns(2)
        with col_p1:
            use_promo = st.toggle("🎁 Aplicar promo se ativa", value=True, key="aiml_ab_promo")
        with col_p2:
            today_override = st.text_input(
                "Date override (YYYY-MM-DD, opcional)",
                value="",
                placeholder="ex: 2026-07-01 (pós-promo)",
                key="aiml_ab_today",
            )

        scenario = AgentBricksScenario(
            cloud=cloud,  # type: ignore[arg-type]
            knowledge_assistant_answers=ka_answers,
            supervisor_dbu_hours=sa_dbu,
            sub_agent_costs_usd=sub_agent_usd,
            use_promo_if_active=use_promo,
            today_override=today_override or None,
        )
        try:
            result = calculate_agent_bricks_cost(scenario, catalog)
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                st.metric("💵 Custo Mensal", f"${result['totals']['monthly']:.2f}")
            with col_t2:
                promo_active = result["inputs_resolved"].get("promo_active", False)
                st.metric("🎁 Promo ativa?", "Sim" if promo_active else "Não")

            with st.expander("📊 Breakdown", expanded=True):
                st.json(result["breakdown"])
            with st.expander("🔧 Inputs resolved", expanded=False):
                st.json(result["inputs_resolved"])
            for w in result["warnings"]:
                st.warning(w)
        except (KeyError, ValueError) as exc:
            st.error(f"Erro: {exc}")


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

    # Tab Histórico inclui contador de cenários do agent (badge)
    saved_for_badge = list_saved_scenarios()
    agent_count = sum(1 for e in saved_for_badge if e["source"] == "agent")
    historico_label = "📋 Histórico"
    if agent_count > 0:
        historico_label = f"📋 Histórico 🤖×{agent_count}"

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs(
        [
            "🖥️ Cenário Cluster",
            "⚖️ Compare PAYG vs DBCU",
            "🔗 Workloads Múltiplos",
            "📤 Export XLSX",
            historico_label,
            "📊 FinOps Realizado",
            "🔧 Otimização",
            "📋 Catálogo",
            "🧠 AI/ML Calc",
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
    with tab5:
        render_tab_historico()
    with tab6:
        render_tab_finops_realizado()
    with tab7:
        render_tab_otimizacao()
    with tab8:
        render_tab_catalogo()
    with tab9:
        render_tab_ai_ml_calculator()


if __name__ == "__main__":
    main()
