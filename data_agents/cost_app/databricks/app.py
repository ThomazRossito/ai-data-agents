"""
Databricks Cost Calculator — Streamlit App.

Rodar standalone:
    streamlit run data_agents/cost_app/databricks/app.py --server.port=8514

Ou via start.sh:
    ./start.sh --with-cost

Layout:
    [Sidebar]
      - Header + mock warning
      - Cloud + Region (filtros globais)
      - Load saved scenario (dropdown)
      - Save current scenario button
      - Currency converter (USD↔BRL)

    [Main]
      - Tab 1: Cenário Cluster ........ (Chunk 1.2 — IMPLEMENTADO)
      - Tab 2: Compare PAYG vs DBCU ... (Chunk 1.3)
      - Tab 3: Workloads múltiplos .... (Chunk 1.3)
      - Tab 4: Export XLSX ............ (Chunk 1.3)
"""

from __future__ import annotations

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


# ─── Helpers ─────────────────────────────────────────────────────────────────


@st.cache_data(ttl=300)
def _cached_catalog(cloud: str) -> dict:
    """Carrega catalog YAML uma vez por sessão (TTL 5min)."""
    return load_databricks_catalog(cloud)  # type: ignore[arg-type]


def _format_money(value: float, currency: str = "USD") -> str:
    """Formata número como moeda."""
    if currency == "BRL":
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"${value:,.2f}"


def _init_session_state() -> None:
    """Inicializa session_state com defaults."""
    defaults = {
        "cloud": "azure",
        "region": "brazilsouth",
        "currency_label": "USD",
        "currency_rate": 1.0,
        "loaded_scenario_uuid": None,
        "save_scenario_open": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ─── Sidebar ─────────────────────────────────────────────────────────────────


def render_sidebar() -> None:
    """Sidebar com filtros globais + scenarios + currency."""
    with st.sidebar:
        st.title("💰 Databricks Cost")
        st.caption("Calculator multi-cloud — Azure + AWS")

        # Mock warning
        meta = get_mock_metadata()
        if meta["is_mock"]:
            st.warning(
                f"⚠️ **Mock pricing** (atualizado {meta['last_updated']})\n\n"
                "Instance prices estimados localmente. Pra produção, "
                "Fase 2 substitui por API oficial (Azure Retail Prices + "
                "AWS Pricing API).",
                icon="⚠️",
            )

        st.divider()

        # Cloud + Region (filtros globais)
        st.subheader("🌐 Cloud + Region")
        cloud = st.selectbox(
            "Cloud Provider",
            options=["azure", "aws"],
            format_func=lambda c: {"azure": "Azure Databricks", "aws": "AWS Databricks"}[c],
            key="cloud",
        )
        regions = list_regions_for_cloud(cloud)  # type: ignore[arg-type]
        if st.session_state.region not in regions:
            st.session_state.region = regions[0]
        st.selectbox(
            "Region",
            options=regions,
            key="region",
            help="Region pra cálculo de instance prices. Brasil = brazilsouth/sa-east-1.",
        )

        st.divider()

        # Currency converter
        st.subheader("💱 Moeda")
        currency = st.selectbox(
            "Display em:",
            options=["USD", "BRL"],
            key="currency_label",
        )
        if currency == "BRL":
            st.number_input(
                "USD → BRL rate",
                min_value=1.0,
                max_value=20.0,
                value=st.session_state.currency_rate if st.session_state.currency_rate > 1.0 else 5.0,
                step=0.01,
                key="currency_rate",
                help="Cotação USD/BRL pra conversão. Default: 5.0",
            )
        else:
            st.session_state.currency_rate = 1.0

        st.divider()

        # Saved scenarios
        st.subheader("📂 Cenários Salvos")
        saved = list_saved_scenarios()
        if saved:
            options = ["(novo)"] + [f"{e['name']} — {e['source']}" for e in saved]
            uuids = [None] + [e["uuid"] for e in saved]
            selected_idx = st.selectbox(
                "Carregar cenário",
                options=range(len(options)),
                format_func=lambda i: options[i],
            )
            if selected_idx > 0 and st.button("📥 Carregar"):
                st.session_state.loaded_scenario_uuid = uuids[selected_idx]
                st.rerun()
        else:
            st.info("Nenhum cenário salvo ainda. Salve abaixo após calcular.")

        st.caption(f"📊 {len(saved)} cenários totais")

        st.divider()
        st.caption(
            "🔗 [GitHub](https://github.com/ThomazRossito/ai-data-agents) · "
            "Versão Fase 1 (Chunk 1.2)"
        )


# ─── Tab 1: Cenário Cluster ─────────────────────────────────────────────────


def render_tab_cenario_cluster() -> None:
    """Tab 1: formulário completo de cluster + breakdown de custo."""
    st.header("🖥️ Cenário Cluster")
    st.caption(
        "Configure um cluster Databricks e veja o custo mensal estimado. "
        "Use 'Salvar Cenário' depois pra reaproveitar."
    )

    cloud = st.session_state.cloud
    region = st.session_state.region
    catalog = _cached_catalog(cloud)

    # Pre-load do scenario salvo se selecionado
    loaded: DatabricksScenario | None = None
    if st.session_state.loaded_scenario_uuid:
        try:
            loaded = load_scenario(st.session_state.loaded_scenario_uuid)
            st.success(f"📥 Cenário carregado: `{loaded.scenario_id}`", icon="✅")
        except FileNotFoundError:
            st.session_state.loaded_scenario_uuid = None

    col_form, col_result = st.columns([1, 1])

    # ─── COLUNA FORM ────────────────────────────────────────────────────────
    with col_form:
        st.subheader("⚙️ Configuração do Cluster")

        # Compute type
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
                "all_purpose_compute": "All-Purpose Compute (interativo)",
                "jobs_compute": "Jobs Compute (scheduled)",
                "delta_live_tables": "Delta Live Tables (DLT)",
                "sql": "SQL Warehouse",
                "serverless_compute": "Serverless Compute",
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

        tier = st.selectbox(
            "Tier",
            options=tier_options,
            index=min(tier_options.index(loaded.tier) if loaded and loaded.tier in tier_options else 1, len(tier_options) - 1),
        )

        photon = st.checkbox(
            "🚀 Photon Engine",
            value=loaded.photon if loaded else False,
            help="Photon aumenta DBU consumption mas reduz wall-clock time. "
                 "Em queries SQL típicas: ~2.5x speedup → custo final menor.",
        )

        st.divider()

        # Driver + Workers
        st.markdown("**Driver + Workers**")
        all_skus = list_instances_for_region(cloud, region)  # type: ignore[arg-type]
        if not all_skus:
            st.error(f"Nenhuma instance disponível em {cloud}/{region}.")
            return

        # Filtra apenas SKUs que estão no catalog DBU map
        catalog_skus = set(catalog["instance_dbu_map"].keys())
        valid_skus = [sku for sku in all_skus if sku in catalog_skus]
        if not valid_skus:
            st.error(
                f"Nenhuma instance em {cloud}/{region} tem DBU mapping no catalog. "
                "Verifique data/databricks_pricing/{cloud}.yaml."
            )
            return

        # Default driver = primeira instance, mas se loaded usa o salvo
        default_driver = valid_skus[0]
        if loaded and loaded.driver_instance in valid_skus:
            default_driver = loaded.driver_instance

        default_worker = valid_skus[0]
        if loaded and loaded.worker_instance in valid_skus:
            default_worker = loaded.worker_instance

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
            help="0 = single-node (só driver). Não inclui o driver.",
        )

        st.divider()

        # Schedule
        st.markdown("**Schedule de Execução**")
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
                help="22 = working days padrão. 30 = 24/7.",
            )

        autoscale_pct = st.slider(
            "Autoscale médio (%)",
            min_value=0,
            max_value=100,
            value=int(loaded.autoscale_avg_workers_pct) if loaded else 100,
            help="Se cluster faz autoscaling, % médio do max. "
                 "100 = sempre no max (sem autoscaling efetivo).",
        )

        st.divider()

        # Pricing model
        st.markdown("**Modelo de Pricing**")
        pricing_options = ["on_demand", "spot", "reserved_1y", "reserved_3y"]
        pricing_model = st.selectbox(
            "Instance Pricing Model",
            options=pricing_options,
            index=pricing_options.index(loaded.instance_pricing_model) if loaded else 0,
            format_func=lambda p: {
                "on_demand": "On-Demand (sem compromisso)",
                "spot": "Spot/Low-Priority (~60-80% off, interrupção possível)",
                "reserved_1y": "Reserved 1 year (~25-32% off)",
                "reserved_3y": "Reserved 3 years (~45-58% off)",
            }[p],
        )

        # Photon speedup (só se Photon ON)
        photon_speedup: float | None = None
        if photon:
            photon_speedup = st.number_input(
                "Photon speedup esperado (x)",
                min_value=1.0,
                max_value=10.0,
                value=loaded.photon_speedup_factor or 2.5,
                step=0.1,
                help="Default: 2.5x (típico em SQL queries). "
                     "Break-even = 2.0x. Abaixo disso, Photon ENCARECE.",
            )

    # ─── COLUNA RESULT ──────────────────────────────────────────────────────
    with col_result:
        st.subheader("💵 Custo Estimado")

        # Resolve instance prices via mock
        try:
            driver_price = get_instance_price_usd_per_hour(cloud, region, driver_instance)  # type: ignore[arg-type]
            worker_price = get_instance_price_usd_per_hour(cloud, region, worker_instance)  # type: ignore[arg-type]
        except KeyError as exc:
            st.error(f"Instance price não encontrado: {exc}")
            return

        # Monta scenario + calcula
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

        # Totals em destaque
        currency = result["currency"]
        col_m, col_a, col_t = st.columns(3)
        with col_m:
            st.metric(
                "Mensal",
                _format_money(result["totals"]["monthly"], currency),
            )
        with col_a:
            st.metric(
                "Anual",
                _format_money(result["totals"]["annual"], currency),
            )
        with col_t:
            st.metric(
                "TCO 36m",
                _format_money(result["totals"]["tco_36m"], currency),
            )

        st.divider()

        # DBCU savings
        commit = result["commit_savings"]
        if commit["savings_1y_usd"] > 0 or commit["savings_3y_usd"] > 0:
            st.markdown("**💎 DBCU Commit Savings (sobre DBU cost)**")
            col_1y, col_3y = st.columns(2)
            with col_1y:
                st.metric(
                    f"1y commit ({commit['auto_dbcu_pct_1y']}%)",
                    _format_money(commit["monthly_with_dbcu_1y"], currency),
                    delta=_format_money(
                        -(commit["savings_1y_usd"] / 12) * st.session_state.currency_rate,
                        currency,
                    ),
                )
            with col_3y:
                st.metric(
                    f"3y commit ({commit['auto_dbcu_pct_3y']}%)",
                    _format_money(commit["monthly_with_dbcu_3y"], currency),
                    delta=_format_money(
                        -(commit["savings_3y_usd"] / 12) * st.session_state.currency_rate,
                        currency,
                    ),
                )
        else:
            st.info(
                f"💡 Gasto anual DBU: {_format_money(commit['annual_dbu_usd'], 'USD')} "
                f"— abaixo do tier mínimo de DBCU commit ($10k). Sem desconto."
            )

        st.divider()

        # Breakdown hourly
        st.markdown("**📊 Breakdown Hourly (USD)**")
        breakdown = result["breakdown_hourly_usd"]
        col_dbu, col_inst = st.columns(2)
        with col_dbu:
            st.write("**DBU Cost**")
            st.write(f"Driver: ${breakdown['dbu_driver']:.4f}/h")
            st.write(f"Workers: ${breakdown['dbu_workers']:.4f}/h")
            st.write(f"**Total: ${breakdown['dbu_total']:.4f}/h**")
        with col_inst:
            st.write("**Instance Cost**")
            st.write(f"Driver: ${breakdown['instance_driver']:.4f}/h")
            st.write(f"Workers: ${breakdown['instance_workers']:.4f}/h")
            st.write(f"**Total: ${breakdown['instance_total']:.4f}/h**")

        st.markdown(
            f"### 🔢 Cluster Total: **${breakdown['cluster_total']:.4f}/h** USD"
        )

        # Inputs resolved (transparência)
        with st.expander("🔍 Inputs Resolved (auditoria)"):
            inputs = result["inputs_resolved"]
            st.json(
                {
                    "DBU rate (USD/DBU·h)": inputs["dbu_rate_per_hour_usd"],
                    "Driver DBU/h": inputs["driver_dbu_per_hour"],
                    "Worker DBU/h": inputs["worker_dbu_per_hour"],
                    "Effective workers": inputs["effective_workers"],
                    "Hours per month": inputs["hours_per_month"],
                    "Instance discount applied (%)": inputs["instance_discount_pct_applied"],
                    "Catalog version": result["source"]["catalog_version"],
                    "Catalog last updated": result["source"]["catalog_last_updated"],
                }
            )

        # Warnings (Photon ROI, etc)
        if result["warnings"]:
            with st.expander(f"⚠️ Warnings ({len(result['warnings'])})"):
                for warning in result["warnings"]:
                    st.warning(warning)

        st.divider()

        # Save scenario button
        with st.expander("💾 Salvar Cenário"):
            scenario_name = st.text_input(
                "Nome",
                placeholder="ex: ETL Bronze produção",
                key="save_name_input",
            )
            scenario_desc = st.text_area(
                "Descrição (opcional)",
                placeholder="ex: Pipeline diário ingerindo Kafka → Delta Bronze",
                key="save_desc_input",
                height=80,
            )
            if st.button("💾 Salvar"):
                if not scenario_name.strip():
                    st.error("Nome obrigatório.")
                else:
                    new_uuid = save_scenario(
                        scenario,
                        name=scenario_name.strip(),
                        description=scenario_desc.strip(),
                        source="manual",
                    )
                    st.success(f"✓ Salvo como `{new_uuid}`")
                    st.balloons()


# ─── Tabs placeholders (Chunk 1.3) ──────────────────────────────────────────


def render_tab_compare_payg_dbcu() -> None:
    st.header("⚖️ Compare PAYG vs DBCU")
    st.info(
        "🚧 **Em construção (Chunk 1.3)** — comparação detalhada entre Pay-as-you-go "
        "e DBCU commit (1y, 3y) com gráfico de breakeven."
    )


def render_tab_workloads_multiplos() -> None:
    st.header("🔗 Workloads Múltiplos")
    st.info(
        "🚧 **Em construção (Chunk 1.3)** — combine múltiplos cenários e veja o "
        "total mensal agregado (ex: 3 jobs + 1 cluster all-purpose + 2 SQL warehouses)."
    )


def render_tab_export() -> None:
    st.header("📤 Export XLSX")
    st.info(
        "🚧 **Em construção (Chunk 1.3)** — exporta cenários e cotações pra XLSX "
        "formatado com fórmulas (openpyxl) — pronto pra mandar pro cliente."
    )


# ─── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    _init_session_state()
    render_sidebar()

    st.title("💰 Databricks Cost Calculator")
    st.caption(
        f"Cloud: **{st.session_state.cloud.upper()}** · "
        f"Region: **{st.session_state.region}** · "
        f"Moeda: **{st.session_state.currency_label}**"
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
