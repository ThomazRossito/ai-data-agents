# Metric Views Databricks — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** O que são Metric Views, integração com Genie, widgets AI/BI, governança

---

## O Que São Metric Views?

Metric Views são a camada semântica **nativa do Databricks** sobre tabelas Gold.

```
┌──────────────────────┐
│  Genie AI (Chat BI)  │
│  AI/BI Dashboards    │
│  Tools Externos      │
└──────────┬───────────┘
           │
    ┌──────▼─────────┐
    │  Metric Views  │  ← Definição de métricas (semântica)
    └──────┬─────────┘
           │
    ┌──────▼────────────┐
    │  Gold Tables      │  ← Dados (fact_, dim_)
    └───────────────────┘
```

---

## Casos de Uso

| Caso | Quem consome | Benefício |
|------|-------------|-----------|
| KPI crítico (fonte única de verdade) | Genie, dashboards, BI | Definição central da métrica |
| Métricas multi-dimensionais | Analistas, ferramentas externas | Filtro por segmento, região, categoria |
| Conversational BI (Genie) | Usuário final (chat) | Consulta em linguagem natural |
| AI/BI Dashboards automáticos | Data consumers | Visualizações sem código |

---

## Integração com Genie (Conversational BI)

Genie é a ferramenta de BI conversacional (chat) do Databricks.

```
Usuário: "Show me revenue by region this month"
          ↓
Genie: Consulta metric_view
       ├─ Filtra data >= CURRENT_DATE() - 30
       ├─ Agrupa por regiao
       └─ Retorna resultado + visualização automática
```

**Requisito:** Metric View com estrutura simples (GROUP BY em dimensões básicas) para Genie funcionar corretamente.

---

## Campos COMMENT: Documentação Obrigatória

| Campo | Exemplo | Uso |
|-------|---------|-----|
| Unit | `Unit: BRL`, `Unit: Count` | Formatação e BI |
| Frequency | `Frequency: Daily` | SLA de atualização |
| Owner | `Owner: Sales Team` | Contato responsável |
| Refresh time | `Refresh: 01:00 UTC` | Hora de atualização |
| Calculation | `Calculation: SUM(...)` | Definição clara |

---

## AI/BI Dashboard: Widget Types

| Widget | Melhor Para | Exemplo |
|--------|-------------|---------|
| **Counter** | Métrica única (KPI) | Total Revenue, User Count |
| **Bar Chart** | Comparação entre categorias | Revenue by Region |
| **Line Chart** | Série temporal | Revenue over time |
| **Scatter** | Correlação 2D | Price vs Margin |
| **Table** | Detalhes granulares | Top 10 customers |

---

## Governança via Unity Catalog

Metric Views herdam o modelo de permissões do Unity Catalog:

- `GRANT SELECT` controla quem pode consultar
- `GRANT MODIFY` controla quem pode alterar definição
- TBLPROPERTIES para classificação e lineage
- Aparecem como tabelas normais em Power BI (via Fabric connection)

---

## Estratégias de Refreshing

| Estratégia | Quando usar | Trade-off |
|-----------|-------------|-----------|
| **Real-time** (query direta na fact_) | Dados críticos, sempre atualizados | Mais lento, sem pré-agregação |
| **Pre-aggregated** (via MATERIALIZED VIEW) | Analytics com latência aceitável | Mais rápido, latência de refresh |
