#!/usr/bin/env python3
"""
[DEPRECATED 2026-08-02] Artefato HARDCODED ao cliente BRF Comercial — NÃO reutilizar.
Substituído por `scripts/ssas_generate.py` (genérico, testado, com gates). Referência histórica.

Gera o plano de migração SSAS → Databricks em Markdown.
"""

import json
from pathlib import Path
from collections import defaultdict

JSON_PATH = Path(
    "/Users/thomaz_rossito/Projects/ai-data-agents/output/migracao_brf_comercial_inventario.json"
)
OUT_MD = Path("/Users/thomaz_rossito/Projects/ai-data-agents/output/migracao_brf_comercial.md")

# Mapeamento manual das tabelas Delta já existentes (extraído de SCHMA_TABLES_v2.md)
DELTA_TABLES = {
    "venda_realizada",
    "meta_x_realizado",
    "venda_realizada_dia_e_carteira",
    "venda_realizada_nrt",
    "cliente_estrutura",
    "cliente_vendedor_material",
    "area_vendas",
    "calendario_generico",
    "rls_comercial",
    "estrutura_venda_rg",
    "estrutura_venda_fvi",
    "estrutura_venda_as",
    "estrutura_venda_fs",
    "estrutura_venda_fir",
    "estrutura_venda_ina",
    "estrutura_venda_inn",
    "material_estrutura",
    "cliente_material_total_itens",
    "filial_vendas",
    "rede_estatico",
    "bandeira_estatico",
    "cliente_segmentacao",
    "cliente_segmentacao_estatico",
}


# Mapeamento aproximado SSAS → Delta (normalização de nomes)
def normalize(name: str) -> str:
    return name.lower().replace("dim", "").replace("fact", "").replace(" ", "_")


SSAS_TO_DELTA = {
    "dimclientesegmentacao": "cliente_segmentacao",
    "dimclientesegmentacaoestatico": "cliente_segmentacao_estatico",
    "dimclientevendedormaterial": "cliente_vendedor_material",
    "dimareavendas": "area_vendas",
    "dimcalendariogenerico": "calendario_generico",
    "dimrlscomercial": "rls_comercial",
    "dimestruturavendarg": "estrutura_venda_rg",
    "dimestruturavendafvi": "estrutura_venda_fvi",
    "dimestruturavendaas": "estrutura_venda_as",
    "dimestruturavendafs": "estrutura_venda_fs",
    "dimestruturavendafir": "estrutura_venda_fir",
    "dimestruturavendaina": "estrutura_venda_ina",
    "dimestruturavendainn": "estrutura_venda_inn",
    "dimmaterialestrutura": "material_estrutura",
    "dimclientematerialtotalitens": "cliente_material_total_itens",
    "dimfilialvendas": "filial_vendas",
    "dimredeestatico": "rede_estatico",
    "dimbandeiraestatico": "bandeira_estatico",
    "dimclienteestrutura": "cliente_estrutura",
    "factvendarealizada": "venda_realizada",
    "factvendarealizadadiaecarteira": "venda_realizada_dia_e_carteira",
    "factmetaxrealizado": "meta_x_realizado",
    "factvendarealizadanrt": "venda_realizada_nrt",
}


def delta_for_ssas(name: str) -> str:
    key = name.lower().replace(" ", "")
    return SSAS_TO_DELTA.get(key, "——")


def fmt_list(items):
    if not items:
        return "Nenhum"
    return "\n".join(f"- {i}" for i in items)


def main():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        inv = json.load(f)

    lines = []
    lines.append("# Plano de Migração: Modelo Tabular SSAS → Databricks")
    lines.append("")
    lines.append("**Projeto:** BRF Comercial")
    lines.append(
        f"**Modelo SSAS:** {inv['model_name']} (compatibilityLevel {inv['compatibilityLevel']})"
    )
    lines.append(
        f"**Cultura:** {inv['culture']} | discourageImplicitMeasures: {inv['discourageImplicitMeasures']}"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # ============================================================
    # 1. INVENTÁRIO DO MODELO SSAS
    # ============================================================
    lines.append("## 1. Inventário do Modelo SSAS")
    lines.append("")

    # 1.1 Data Sources
    lines.append("### 1.1 Data Sources")
    lines.append("")
    for ds in inv["dataSources"]:
        lines.append(f"- **{ds['name']}**")
        lines.append(f"  - Tipo: {ds['type']} | Protocolo: {ds['protocol']}")
        lines.append(f"  - Servidor: `{ds['server']}`")
        lines.append(f"  - Database: `{ds['database']}`")
        lines.append(f"  - Autenticação: {ds['authentication_kind']} (usuário: `{ds['username']}`)")
        lines.append(
            f"  - EncryptConnection: {ds['encrypt_connection']} | CommandTimeout: {ds['command_timeout']}"
        )
        lines.append("")

    # 1.2 Tabelas (dimensões e fatos)
    lines.append("### 1.2 Tabelas")
    lines.append("")
    lines.append(f"Total: **{len(inv['tables'])}** tabelas")
    lines.append("")

    dims = [t for t in inv["tables"] if t["name"].lower().startswith("dim")]
    facts = [t for t in inv["tables"] if t["name"].lower().startswith("fat")]
    others = [t for t in inv["tables"] if t not in dims and t not in facts]

    lines.append(f"- Dimensões: {len(dims)}")
    lines.append(f"- Fatos: {len(facts)}")
    lines.append(f"- Outras: {len(others)}")
    lines.append("")

    # Tabela resumo
    lines.append("| Tabela SSAS | Tipo | Colunas | Medidas | Partições | Mapeamento Delta |")
    lines.append("|-------------|------|---------|---------|-----------|------------------|")
    for t in inv["tables"]:
        tipo = (
            "Fato"
            if t["name"].lower().startswith("fat")
            else ("Dimensão" if t["name"].lower().startswith("dim") else "Outra")
        )
        delta = delta_for_ssas(t["name"])
        lines.append(
            f"| {t['name']} | {tipo} | {len(t['columns'])} | {len(t['measures'])} | {len(t['partitions'])} | {delta} |"
        )
    lines.append("")

    # Detalhes de colunas (abreviado: apenas dims e fatos principais)
    lines.append("#### Colunas por Tabela (visão das principais)")
    lines.append("")
    for t in inv["tables"]:
        if len(t["columns"]) == 0:
            continue
        hidden_cols = [c["name"] for c in t["columns"] if c.get("isHidden")]
        visible_cols = [c["name"] for c in t["columns"] if not c.get("isHidden")]
        lines.append(f"**{t['name']}** — {len(t['columns'])} colunas ({len(hidden_cols)} ocultas)")
        if visible_cols:
            lines.append(
                f"  - Visíveis: {', '.join(visible_cols[:10])}{'...' if len(visible_cols) > 10 else ''}"
            )
        if hidden_cols:
            lines.append(
                f"  - Ocultas (SKs): {', '.join(hidden_cols[:8])}{'...' if len(hidden_cols) > 8 else ''}"
            )
        lines.append("")

    # 1.3 Partições
    lines.append("### 1.3 Partições e Queries Fonte")
    lines.append("")
    for t in inv["tables"]:
        if not t["partitions"]:
            continue
        lines.append(f"#### {t['name']}")
        for p in t["partitions"]:
            lines.append(f"- **Partição:** `{p['name']}` | Tipo: `{p['type']}`")
            expr = p["expression"]
            if "Value.NativeQuery" in expr:
                lines.append("  - Fonte: `Value.NativeQuery` (SQL direto no Synapse)")
                # extrair query SQL
                sql_start = expr.find('"\\n')
                sql_end = expr.rfind('\\n"')
                if sql_start != -1 and sql_end != -1:
                    sql = expr[sql_start + 3 : sql_end].replace("\\n", "\n").replace("\\t", "\t")
                    lines.append("  - Query SQL (resumo):")
                    lines.append("    ```sql")
                    # mostrar até 15 linhas
                    sql_lines = sql.strip().splitlines()
                    for sl in sql_lines[:15]:
                        lines.append(f"    {sl}")
                    if len(sql_lines) > 15:
                        lines.append("    -- ... (truncado)")
                    lines.append("    ```")
            else:
                lines.append("  - Fonte: Expressão M (não-SQL)")
                lines.append("    ```")
                lines.append(f"    {expr[:300]}")
                lines.append("    ```")
        lines.append("")

    # 1.4 Relacionamentos
    lines.append("### 1.4 Relacionamentos")
    lines.append("")
    lines.append(f"Total: **{len(inv['relationships'])}** relacionamentos")
    lines.append("")
    lines.append("| Nome | De (Tabela.Coluna) | Para (Tabela.Coluna) | Ativo | Cross-Filtering |")
    lines.append("|------|---------------------|----------------------|-------|-----------------|")
    for rel in inv["relationships"]:
        active = "Sim" if rel["isActive"] else "Não"
        lines.append(
            f"| {rel['name']} | {rel['fromTable']}.{rel['fromColumn']} → {rel['toTable']}.{rel['toColumn']} | {active} | {rel['crossFilteringBehavior']} |"
        )
    lines.append("")

    # 1.5 Medidas DAX
    lines.append("### 1.5 Medidas DAX")
    lines.append("")
    lines.append(f"Total: **{sum(len(t['measures']) for t in inv['tables'])}** medidas")
    lines.append("")

    # Agrupar por displayFolder / tabela
    measures_by_table = defaultdict(list)
    for t in inv["tables"]:
        for m in t["measures"]:
            measures_by_table[t["name"]].append(m)

    for tbl_name, measures in measures_by_table.items():
        if not measures:
            continue
        lines.append(f"#### {tbl_name} ({len(measures)} medidas)")
        lines.append("")
        for m in measures:
            folder = f" / pasta: `{m['displayFolder']}`" if m.get("displayFolder") else ""
            lines.append(f"- **{m['name']}**{folder}")
            expr = (
                " ".join(m["expression"])
                if isinstance(m["expression"], list)
                else m["expression"].replace("\n", " ")
            )
            lines.append(f"  - Expressão: `{expr[:250]}{'...' if len(expr) > 250 else ''}`")
            if m.get("formatString"):
                lines.append(f"  - Formato: `{m['formatString']}`")
            if m.get("description"):
                lines.append(f"  - Descrição: {m['description']}")
        lines.append("")

    # 1.6 Hierarquias
    lines.append("### 1.6 Hierarquias")
    lines.append("")
    total_hier = sum(len(t["hierarchies"]) for t in inv["tables"])
    lines.append(f"Total: **{total_hier}** hierarquias definidas no modelo.")
    if total_hier == 0:
        lines.append(
            "> **Nota:** O modelo não contém hierarquias explícitas no TOM. No Power BI, os usuários provavelmente montam drill-downs a partir das colunas individuais (ex: Ano → Mês → Dia)."
        )
    lines.append("")

    # 1.7 Roles e RLS
    lines.append("### 1.7 Roles e RLS (Row-Level Security)")
    lines.append("")
    lines.append(f"Total: **{len(inv['roles'])}** roles")
    lines.append("")
    for role in inv["roles"]:
        lines.append(f"#### Role: `{role['name']}`")
        if role.get("description"):
            lines.append(f"- Descrição: {role['description']}")
        lines.append(f"- Membros: {', '.join(role['members']) if role['members'] else 'Nenhum'}")
        lines.append("- Filtros de tabela (RLS DAX):")
        if role["tablePermissions"]:
            for tp in role["tablePermissions"]:
                lines.append(f"  - **{tp['table']}**: `{tp['filter']}`")
        else:
            lines.append("  - Nenhum filtro definido.")
        lines.append("")

    # 1.8 Perspectives
    lines.append("### 1.8 Perspectives")
    lines.append("")
    lines.append(f"Total: **{len(inv['perspectives'])}** perspectives")
    lines.append("")
    for p in inv["perspectives"]:
        lines.append(f"- **{p['name']}**: {len(p['tables'])} tabelas")
    lines.append("")

    # 1.9 Cultures
    lines.append("### 1.9 Cultures / Traduções")
    lines.append("")
    lines.append(f"Cultures: {', '.join(c['name'] for c in inv['cultures'])}")
    lines.append("")

    # ============================================================
    # 2. MAPEAMENTO PARA DATABRICKS
    # ============================================================
    lines.append("---")
    lines.append("")
    lines.append("## 2. Mapeamento para Databricks")
    lines.append("")

    lines.append("### 2.1 Tabelas SSAS → Tabelas Unity Catalog (Delta)")
    lines.append("")
    lines.append(
        "O schema `lakehouse.debug_poc` já possui as tabelas correspondentes. O mapeamento é direto para a maioria das entidades:"
    )
    lines.append("")
    lines.append("| Tabela SSAS | Tabela Delta (UC) | Status | Observações |")
    lines.append("|-------------|-------------------|--------|-------------|")
    for t in inv["tables"]:
        delta = delta_for_ssas(t["name"])
        status = "✅ Existe" if delta != "——" else "⚠️ Não mapeada"
        obs = ""
        if t["name"].lower().startswith("dim") and delta == "——":
            obs = "Verificar se existe no schema ou se será descontinuada"
        elif t["name"].lower().startswith("fat") and delta == "——":
            obs = "Possível tabela fato nova — verificar com negócio"
        lines.append(f"| {t['name']} | `{delta}` | {status} | {obs} |")
    lines.append("")

    lines.append("### 2.2 Medidas DAX → Databricks")
    lines.append("")
    lines.append("No Databricks, as medidas DAX podem ser materializadas de três formas:")
    lines.append("")
    lines.append(
        "1. **Metric Views (Unity Catalog)** — métricas governadas reutilizáveis por SQL. Ideal para KPIs simples (SUM, COUNT, DIVIDE)."
    )
    lines.append(
        "2. **AI/BI Dashboards** — medidas definidas em DAX-like no layer semântico do dashboard. Bom para visualizações ad-hoc."
    )
    lines.append(
        "3. **Materialized Views Delta** — pré-computar agregações no pipeline. Ideal para medidas de alta cardinalidade ou complexas."
    )
    lines.append("")
    lines.append(
        "Recomendação: usar **Metric Views** para medidas de negócio reutilizáveis e **Materialized Views** para agregações pesadas."
    )
    lines.append("")
    lines.append("Exemplos de mapeamento:")
    lines.append("")
    lines.append("| Medida SSAS (exemplo) | Tipo | Implementação no Databricks |")
    lines.append("|-----------------------|------|-----------------------------|")
    lines.append(
        "| SUM de volume/faturamento | Agregação simples | Metric View (`SUM(volume_real)`) ou coluna na MV Gold |"
    )
    lines.append("| DIVIDE (taxa, %) | Razão | Metric View com expressão SQL |")
    lines.append(
        "| Medidas com FILTER/ALL | Contexto modificado | Materialized View pré-filtrada ou view parametrizada |"
    )
    lines.append(
        "| Medidas com CALCULATE+TIMEINTEL | Inteligência temporal | `dim_data` + joins temporais em MV Gold |"
    )
    lines.append("")

    lines.append("### 2.3 RLS → Databricks")
    lines.append("")
    lines.append(
        "O modelo SSAS usa roles com filtros DAX por e-mail e organização de vendas. No Databricks, existem três camadas de RLS:"
    )
    lines.append("")
    lines.append("| Mecanismo | Escopo | Quando usar |")
    lines.append("|-----------|--------|-------------|")
    lines.append(
        "| **Dynamic View Filters** | Schema/View | Filtros baseados em `current_user()` ou lookup de e-mail. Bom para RLS simples por usuário. |"
    )
    lines.append(
        "| **Unity Catalog Row Filters** | Tabela Delta | Política de acesso nativa no UC (REDACT/MASK/FILTER). Requer Databricks 15.4+ com tabelas do tipo `MANAGED`. |"
    )
    lines.append(
        "| **AI/BI Dashboard RLS** | Dashboard | Filtros aplicados no contexto do dashboard. Limitado ao escopo do AI/BI. |"
    )
    lines.append("")
    lines.append(
        "**Recomendação:** Implementar RLS via **Dynamic Views** no schema `gold` (ou `analytics`), fazendo JOIN com a dimensão `rls_comercial` filtrando por `current_user()`. Isso replica o comportamento DAX do SSAS sem duplicar dados."
    )
    lines.append("")
    lines.append("```sql")
    lines.append("-- Exemplo de view com RLS dinâmico")
    lines.append("CREATE OR REPLACE VIEW lakehouse.gold.venda_realizada_rls AS")
    lines.append("SELECT f.*")
    lines.append("FROM lakehouse.debug_poc.venda_realizada f")
    lines.append("JOIN lakehouse.debug_poc.rls_comercial r")
    lines.append("  ON f.rls_comercial_sid = r.rls_comercial_sid")
    lines.append("WHERE r.email = current_user()  -- ou lookup em grupo do Entra ID")
    lines.append("```")
    lines.append("")

    lines.append("### 2.4 Hierarquias")
    lines.append("")
    lines.append(
        "Como o modelo SSAS não define hierarquias explícitas, o mapeamento consiste em garantir que as colunas de nível existam nas dimensões Delta e que estejam ordenadas corretamente (via `sortByColumn` ou `ORDER BY`)."
    )
    lines.append("")
    lines.append("Exemplos de hierarquias implícitas a expor:")
    lines.append("- **Tempo:** Ano → Mês → Dia (usar `calendario_generico`)")
    lines.append(
        "- **Produto:** Negócio GM → Categoria GM → Sub-Categoria → Material (usar `material_estrutura`)"
    )
    lines.append("- **Cliente:** Rede → Bandeira → Cliente (usar `cliente_estrutura`)")
    lines.append(
        "- **Venda:** Diretoria → Regional → Filial → Supervisor → Vendedor (usar `estrutura_venda_*`)"
    )
    lines.append("")
    lines.append("No Databricks, hierarquias podem ser expostas via:")
    lines.append("- **Genie Space** — o assistente entende colunas e sugere drill-down.")
    lines.append("- **AI/BI Dashboard** — definir hierarquias no layer semântico do dashboard.")
    lines.append("- **SQL + dbt** — documentar relações no dbt docs para discovery.")
    lines.append("")

    lines.append("### 2.5 Proposta de Arquitetura Semântica")
    lines.append("")
    lines.append(
        "Para substituir o modelo tabular SSAS no Databricks, recomenda-se uma arquitetura em camadas:"
    )
    lines.append("")
    lines.append("```")
    lines.append("┌─────────────────────────────────────────────────────────────┐")
    lines.append("│  Camada de Consumo (Semantic Layer)                         │")
    lines.append("│  ├── Genie Space (NLQ + SQL gerado)                         │")
    lines.append("│  ├── AI/BI Dashboards (visualizações + DAX-like measures)   │")
    lines.append("│  └── Metric Views (UC) — KPIs governados via SQL            │")
    lines.append("├─────────────────────────────────────────────────────────────┤")
    lines.append("│  Camada Gold (Star Schema materializado)                    │")
    lines.append("│  ├── dim_cliente, dim_material, dim_tempo, dim_venda...     │")
    lines.append("│  ├── fact_venda_realizada, fact_meta_x_realizado...         │")
    lines.append("│  └── Views RLS (dynamic filters por usuário)                │")
    lines.append("├─────────────────────────────────────────────────────────────┤")
    lines.append("│  Camada Silver (limpa + SCD2 via AUTO CDC)                  │")
    lines.append("│  └── Tabelas conformadas com tipos canônicos                │")
    lines.append("├─────────────────────────────────────────────────────────────┤")
    lines.append("│  Camada Bronze (ingestão bruta do Synapse/SQL DW)           │")
    lines.append("│  └── Valor.NativeQuery → Delta via Lakeflow Connect / JDBC  │")
    lines.append("└─────────────────────────────────────────────────────────────┘")
    lines.append("```")
    lines.append("")
    lines.append("**Decisão entre Genie Space vs AI/BI Dashboard:**")
    lines.append("")
    lines.append("| Critério | Genie Space | AI/BI Dashboard |")
    lines.append("|----------|-------------|-----------------|")
    lines.append(
        "| Público | Analistas de negócio (self-service) | Consumidores de relatório fixo |"
    )
    lines.append("| Interação | Linguagem natural | Visualizações pré-construídas |")
    lines.append("| Medidas complexas | Limitado (depende do Genie entender) | Suporta DAX-like |")
    lines.append("| RLS | Herda da view/tabela subjacente | RLS próprio do dashboard |")
    lines.append("| Performance | Depende do SQL Warehouse | Otimizado com caching |")
    lines.append("")
    lines.append(
        "> **Recomendação:** Iniciar com **AI/BI Dashboard** para os relatórios fixos (substituindo os consumers do SSAS) e disponibilizar **Genie Space** para exploração ad-hoc. Ambos devem apontar para as mesmas views RLS no schema `gold`."
    )
    lines.append("")

    # ============================================================
    # 3. GAPS E DECISÕES PENDENTES
    # ============================================================
    lines.append("---")
    lines.append("")
    lines.append("## 3. Gaps e Decisões Pendentes")
    lines.append("")

    # Identificar tabelas SSAS sem mapeamento Delta
    unmapped = [t["name"] for t in inv["tables"] if delta_for_ssas(t["name"]) == "——"]
    lines.append("### 3.1 Tabelas sem Mapeamento Delta Identificado")
    lines.append("")
    if unmapped:
        lines.append(
            f"**{len(unmapped)}** tabelas do SSAS não possuem equivalente direto no schema `lakehouse.debug_poc`:"
        )
        lines.append("")
        for u in unmapped:
            lines.append(f"- `{u}`")
        lines.append("")
        lines.append("**Decisão:** Confirmar com o time de dados se essas tabelas serão:")
        lines.append("- (a) Criadas no pipeline de carga; ou")
        lines.append(
            "- (b) Descontinuadas (algumas podem ser tabelas de suporte não utilizadas nos consumers atuais)."
        )
    else:
        lines.append("Todas as tabelas principais possuem mapeamento.")
    lines.append("")

    lines.append("### 3.2 Features sem Equivalente Direto no Databricks")
    lines.append("")
    lines.append("| Feature SSAS | Equivalente Databricks | Gap | Mitigação |")
    lines.append("|--------------|------------------------|-----|-----------|")
    lines.append(
        "| Perspectives | Não há no UC / Delta | Views diferentes por persona | Criar views `gold.venda_analista`, `gold.venda_gerente` com subsets de colunas |"
    )
    lines.append(
        "| Implicit Measures | Desabilitado no SSAS; no Databricks, métricas devem ser explícitas | Usuários podem criar agregações ad-hoc no Genie | Documentar métricas oficiais em Metric Views |"
    )
    lines.append(
        "| KPIs (status/trend) | Não nativo | Sem semáforo nativo no SQL | Implementar em AI/BI Dashboard ou com CASE/WHEN em views |"
    )
    lines.append(
        "| Calculated Columns (DAX) | Não existe em Delta | Lógica de coluna calculada | Mover para pipeline Silver (PySpark) ou views SQL |"
    )
    lines.append(
        "| Variáveis DAX (SUMMARIZE, ADDCOLUMNS) | SQL CTEs / subqueries | Reescrita necessária | Mapear para CTEs em views materializadas |"
    )
    lines.append(
        "| Time Intelligence (SAMEPERIODLASTYEAR, etc.) | Funções de janela SQL + dim_data | Reescrita manual | Criar colunas offset na `dim_data` (ex: `data_ano_anterior`) |"
    )
    lines.append("")

    lines.append("### 3.3 Decisões de Arquitetura")
    lines.append("")
    lines.append(
        "1. **Granularidade do RLS:** O SSAS filtra por `email` na dimensão `rls_comercial`. No Databricks, o `current_user()` retorna o UPN do Entra ID. É necessário validar se os e-mails do SSAS batem com os UPNs do Databricks."
    )
    lines.append(
        "2. **Performance das partições:** Algumas tabelas (ex: `DimClienteVendedorMaterial`) têm múltiplas partições com lógica de data/hora (`@hora < 19`). No Databricks, isso deve virar uma tabela Delta com `ORDER BY` + `ZORDER BY` ou `CLUSTER BY` na chave de join, e a lógica de hora deve ser tratada no pipeline (Bronze/Silver) ou no filtro da query."
    )
    lines.append(
        "3. **Multi-tenancy de estrutura de venda:** Existem múltiplas dimensões `EstruturaVenda` (RG, FVI, AS, FS, FIR, INA, INN). Confirmar se todas são necessárias no Gold ou se podem ser unificadas."
    )
    lines.append(
        "4. **Materializado vs Virtual:** As agregações do SSAS são pré-computadas (VertiPaq). No Databricks, decidir entre `MATERIALIZED VIEW` (custo de recomputação) ou views virtuais (custo de query). Recomendação: MV para fatos > 100M linhas; views para dimensões."
    )
    lines.append(
        "5. **Frequência de carga:** O SSAS processa partições diárias/horárias. Definir se o pipeline Databricks será incremental (`MERGE`) ou full-refresh."
    )
    lines.append("")

    # ============================================================
    # 4. PROPOSTA DE IMPLEMENTAÇÃO
    # ============================================================
    lines.append("---")
    lines.append("")
    lines.append("## 4. Proposta de Implementação")
    lines.append("")

    lines.append("### 4.1 Ordem de Migração (Fases)")
    lines.append("")
    lines.append("```")
    lines.append("Fase 1 — Foundation (semanas 1-2)")
    lines.append("  ├── Mapear todas as tabelas SSAS → Delta (validar schema, tipos, nulos)")
    lines.append("  ├── Criar pipeline Bronze (ingestão do Synapse via Lakeflow Connect / JDBC)")
    lines.append("  ├── Implementar Silver (limpeza, deduplicação, SCD2 para dims se necessário)")
    lines.append("  └── Validar counts origem × destino")
    lines.append("")
    lines.append("Fase 2 — Star Schema Gold (semanas 3-4)")
    lines.append("  ├── Criar views/tabelas `dim_*` no schema gold (ou materializar se for MV)")
    lines.append("  ├── Criar views/tabelas `fact_*` no schema gold")
    lines.append("  ├── Implementar joins entre fatos e dimensões (validar com EXPLAIN)")
    lines.append("  └── Criar views RLS dinâmicas")
    lines.append("")
    lines.append("Fase 3 — Semantic Layer (semanas 5-6)")
    lines.append("  ├── Migrar medidas DAX → Metric Views (UC) e/ou Materialized Views")
    lines.append("  ├── Criar Genie Space com tabelas gold + descrições de negócio")
    lines.append("  ├── Criar AI/BI Dashboards para os principais consumers")
    lines.append("  └── Replicar Perspectives como views ou páginas de dashboard separadas")
    lines.append("")
    lines.append("Fase 4 — RLS e Governança (semanas 7-8)")
    lines.append("  ├── Mapear roles SSAS → GRANTs UC + row filters")
    lines.append("  ├── Testar RLS com usuários reais (validar performance)")
    lines.append("  ├── Documentar lineage e Data Contract (ODCS)")
    lines.append("  └── Treinamento de usuários (Genie + Dashboard)")
    lines.append("")
    lines.append("Fase 5 — Decomissionamento (semana 9+)")
    lines.append("  ├── Paralel run: SSAS e Databricks lado a lado por 2 semanas")
    lines.append("  ├── Reconciliação final (counts, somas, amostras)")
    lines.append("  └── Desligar modelo SSAS após aceite")
    lines.append("```")
    lines.append("")

    lines.append("### 4.2 Scripts SQL/PySpark Necessários")
    lines.append("")
    lines.append("#### 4.2.1 Criação do Schema Gold e Views Dimensão")
    lines.append("")
    lines.append("```sql")
    lines.append("-- Exemplo: dimensão cliente")
    lines.append("CREATE SCHEMA IF NOT EXISTS lakehouse.gold;")
    lines.append("")
    lines.append("CREATE OR REPLACE VIEW lakehouse.gold.dim_cliente AS")
    lines.append("SELECT")
    lines.append("  cliente_estrutura_sid,")
    lines.append("  cliente,")
    lines.append("  cliente_descricao,")
    lines.append("  rede,")
    lines.append("  rede_descricao,")
    lines.append("  bandeira,")
    lines.append("  bandeira_descricao,")
    lines.append("  municipio,")
    lines.append("  uf,")
    lines.append("  pais,")
    lines.append("  cnpj")
    lines.append("FROM lakehouse.debug_poc.cliente_estrutura;")
    lines.append("")
    lines.append("CREATE OR REPLACE VIEW lakehouse.gold.dim_tempo AS")
    lines.append("SELECT")
    lines.append("  data,")
    lines.append("  ano,")
    lines.append("  mes,")
    lines.append("  descricao_mes,")
    lines.append("  dia,")
    lines.append("  dia_da_semana_iniciando_domingo,")
    lines.append("  ano_mes,")
    lines.append("  data_semana_nielsen,")
    lines.append("  feriado,")
    lines.append("  dia_util,")
    lines.append("  num_quinzena,")
    lines.append("  num_trimestre,")
    lines.append("  num_semestre,")
    lines.append("  flag_dia,")
    lines.append("  dif_mes,")
    lines.append("  flag_mes,")
    lines.append("  flag_mes_ordem,")
    lines.append("  semana_faseamento")
    lines.append("FROM lakehouse.debug_poc.calendario_generico;")
    lines.append("")
    lines.append("CREATE OR REPLACE VIEW lakehouse.gold.dim_material AS")
    lines.append("SELECT")
    lines.append("  material_estrutura_sid,")
    lines.append("  negocio_gm,")
    lines.append("  atividade_gm,")
    lines.append("  categoria_gm,")
    lines.append("  sub_categoria_gm,")
    lines.append("  apresentacao_gm,")
    lines.append("  material,")
    lines.append("  material_descricao,")
    lines.append("  marca_mae,")
    lines.append("  marca,")
    lines.append("  divisao_gestao,")
    lines.append("  familia_foco,")
    lines.append("  zera_volume")
    lines.append("FROM lakehouse.debug_poc.material_estrutura;")
    lines.append("```")
    lines.append("")

    lines.append("#### 4.2.2 View Fato com Joins (para validação)")
    lines.append("")
    lines.append("```sql")
    lines.append("CREATE OR REPLACE VIEW lakehouse.gold.fact_venda_realizada AS")
    lines.append("SELECT")
    lines.append("  f.data,")
    lines.append("  f.volume_real,")
    lines.append("  f.faturamento_real,")
    lines.append("  f.volume_real_bruto,")
    lines.append("  f.faturamento_real_bruto,")
    lines.append("  f.volume_devolucao,")
    lines.append("  f.faturamento_devolucao,")
    lines.append("  f.receita_operacional_dre,")
    lines.append("  c.cliente,")
    lines.append("  c.rede,")
    lines.append("  c.bandeira,")
    lines.append("  m.material,")
    lines.append("  m.categoria_gm,")
    lines.append("  t.ano_mes,")
    lines.append("  t.descricao_mes,")
    lines.append("  r.organizacao_venda")
    lines.append("FROM lakehouse.debug_poc.venda_realizada f")
    lines.append("LEFT JOIN lakehouse.debug_poc.cliente_estrutura c")
    lines.append("  ON f.cliente_estrutura_sid = c.cliente_estrutura_sid")
    lines.append("LEFT JOIN lakehouse.debug_poc.material_estrutura m")
    lines.append("  ON f.material_estrutura_sid = m.material_estrutura_sid")
    lines.append("LEFT JOIN lakehouse.debug_poc.calendario_generico t")
    lines.append("  ON f.data = t.data")
    lines.append("LEFT JOIN lakehouse.debug_poc.rls_comercial r")
    lines.append("  ON f.rls_comercial_sid = r.rls_comercial_sid;")
    lines.append("```")
    lines.append("")

    lines.append("#### 4.2.3 View RLS Dinâmico")
    lines.append("")
    lines.append("```sql")
    lines.append("CREATE OR REPLACE VIEW lakehouse.gold.venda_realizada_rls AS")
    lines.append("SELECT f.*")
    lines.append("FROM lakehouse.gold.fact_venda_realizada f")
    lines.append("WHERE EXISTS (")
    lines.append("  SELECT 1 FROM lakehouse.debug_poc.rls_comercial r")
    lines.append("  WHERE f.rls_comercial_sid = r.rls_comercial_sid")
    lines.append("    AND r.email = current_user()  -- ajustar para UPN se necessário")
    lines.append(");")
    lines.append("```")
    lines.append("")

    lines.append("#### 4.2.4 Metric View (exemplo)")
    lines.append("")
    lines.append("```yaml")
    lines.append("# Salvar como: resources/metric_views.yml no DAB")
    lines.append("metric_views:")
    lines.append("  - name: mv_faturamento_total")
    lines.append("    schema: lakehouse.gold")
    lines.append("    sql: |")
    lines.append("      SELECT")
    lines.append("        t.ano_mes,")
    lines.append("        SUM(f.faturamento_real) AS faturamento_total")
    lines.append("      FROM lakehouse.gold.fact_venda_realizada f")
    lines.append("      JOIN lakehouse.gold.dim_tempo t ON f.data = t.data")
    lines.append("      GROUP BY t.ano_mes")
    lines.append("    grains: [ano_mes]")
    lines.append("    dimensions:")
    lines.append("      - name: ano_mes")
    lines.append("        expr: ano_mes")
    lines.append("    measures:")
    lines.append("      - name: faturamento_total")
    lines.append("        expr: SUM(faturamento_total)")
    lines.append("        format: '#,##0.00'")
    lines.append("```")
    lines.append("")

    lines.append("### 4.3 Configuração de Genie Space")
    lines.append("")
    lines.append("```python")
    lines.append("# Exemplo de criação via API/SDK")
    lines.append("from databricks.sdk import WorkspaceClient")
    lines.append("wc = WorkspaceClient()")
    lines.append("")
    lines.append("space = wc.genie.create_space(")
    lines.append("    display_name='BRF Comercial - Genie',")
    lines.append("    description='Análise comercial de vendas, metas e carteira.',")
    lines.append("    table_identifiers=[")
    lines.append("        'lakehouse.gold.dim_cliente',")
    lines.append("        'lakehouse.gold.dim_material',")
    lines.append("        'lakehouse.gold.dim_tempo',")
    lines.append("        'lakehouse.gold.fact_venda_realizada',")
    lines.append("        'lakehouse.gold.fact_meta_x_realizado',")
    lines.append("    ],")
    lines.append("    warehouse_id='<sql-warehouse-id>',")
    lines.append("    sample_questions=[")
    lines.append("        'Qual o faturamento real por rede no último mês?',")
    lines.append("        'Compare volume real vs meta móvel por categoria GM.',")
    lines.append("        'Qual o desempenho de carteira por vendedor?'")
    lines.append("    ]")
    lines.append(")")
    lines.append("```")
    lines.append("")

    lines.append("### 4.4 Testes de Reconciliação (SSAS vs Databricks)")
    lines.append("")
    lines.append("| Teste | Query SSAS (DAX) | Query Databricks (SQL) | Critério de Aceite |")
    lines.append("|-------|------------------|------------------------|--------------------|")
    lines.append(
        '| Count por tabela | `EVALUATE ROW("Count", COUNTROWS(Tabela))` | `SELECT COUNT(*) FROM tabela` | Diferença = 0 |'
    )
    lines.append(
        "| Soma de faturamento | `SUM(FactVendaRealizada[Faturamento Real])` | `SELECT SUM(faturamento_real) FROM venda_realizada` | Diferença <= 0.01% |"
    )
    lines.append(
        "| Soma de volume | `SUM(FactVendaRealizada[Volume Real])` | `SELECT SUM(volume_real) FROM venda_realizada` | Diferença <= 0.01% |"
    )
    lines.append(
        "| Cardinalidade de dimensão | `DISTINCTCOUNT(DimCliente[Cliente])` | `SELECT COUNT(DISTINCT cliente) FROM cliente_estrutura` | Diferença = 0 |"
    )
    lines.append(
        "| Range de datas | `MIN(DimCalendario[Data])` / `MAX(...)` | `SELECT MIN(data), MAX(data) FROM calendario_generico` | Igual |"
    )
    lines.append(
        "| RLS (por usuário) | Processar com role ativa | `SELECT COUNT(*) FROM venda_realizada_rls WHERE email = 'user@brf.com'` | Count compatível |"
    )
    lines.append(
        "| Medida calculada | Comparar 5 medidas principais | Executar mesma lógica em SQL | Diferença <= 0.1% |"
    )
    lines.append("")
    lines.append("**Scripts de reconciliação:**")
    lines.append("")
    lines.append("```sql")
    lines.append("-- Reconciliação: counts e somas por tabela fato")
    lines.append("SELECT")
    lines.append("  'venda_realizada' AS tabela,")
    lines.append("  COUNT(*) AS row_count,")
    lines.append("  ROUND(SUM(volume_real), 2) AS sum_volume,")
    lines.append("  ROUND(SUM(faturamento_real), 2) AS sum_faturamento,")
    lines.append("  ROUND(SUM(receita_operacional_dre), 2) AS sum_dre")
    lines.append("FROM lakehouse.debug_poc.venda_realizada")
    lines.append("")
    lines.append("UNION ALL")
    lines.append("")
    lines.append("SELECT")
    lines.append("  'meta_x_realizado',")
    lines.append("  COUNT(*),")
    lines.append("  ROUND(SUM(volume_meta_movel), 2),")
    lines.append("  ROUND(SUM(faturamento_meta_movel), 2),")
    lines.append("  ROUND(SUM(receita_operacional_dre), 2)")
    lines.append("FROM lakehouse.debug_poc.meta_x_realizado")
    lines.append("")
    lines.append("UNION ALL")
    lines.append("")
    lines.append("SELECT")
    lines.append("  'venda_realizada_dia_e_carteira',")
    lines.append("  COUNT(*),")
    lines.append("  ROUND(SUM(volume_real), 2),")
    lines.append("  ROUND(SUM(faturamento_real), 2),")
    lines.append("  NULL")
    lines.append("FROM lakehouse.debug_poc.venda_realizada_dia_e_carteira;")
    lines.append("```")
    lines.append("")

    # ============================================================
    # 5. APÊNDICE — TABELAS NÃO MAPEADAS
    # ============================================================
    lines.append("---")
    lines.append("")
    lines.append("## Apêndice A — Tabelas SSAS Não Mapeadas ao Delta")
    lines.append("")
    if unmapped:
        for u in unmapped:
            # procurar partições dessa tabela para dar contexto
            tbl_obj = next((t for t in inv["tables"] if t["name"] == u), None)
            if tbl_obj and tbl_obj["partitions"]:
                expr = tbl_obj["partitions"][0]["expression"]
                # extrair nome da tabela SQL fonte
                import re

                m = re.search(r"FROM\s+(\S+)", expr, re.IGNORECASE)
                src = m.group(1) if m else "N/A"
                lines.append(f"- `{u}` → Fonte SQL: `{src}`")
            else:
                lines.append(f"- `{u}`")
    else:
        lines.append("Nenhuma.")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Gerado automaticamente a partir do parser do modelo `Comercial.bim`.*")
    lines.append(
        f"*Tabelas: {len(inv['tables'])} | Relacionamentos: {len(inv['relationships'])} | Medidas: {sum(len(t['measures']) for t in inv['tables'])} | Roles: {len(inv['roles'])}*"
    )

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Relatório salvo em {OUT_MD}")


if __name__ == "__main__":
    main()
