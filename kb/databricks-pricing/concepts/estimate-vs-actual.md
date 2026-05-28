---
concept: estimate-vs-actual
domain: databricks-pricing
updated_at: 2026-05-28
---

# Estimate vs Actual — Bridge Fase 2 ↔ Fase 3

## Problema

A Fase 2 (cotação determinística) e a Fase 3 (consumo real via `system.billing`) operam em **modos distintos**:

- **Estimate** (Fase 2): "se eu rodar X workers Y horas, quanto custaria?" — números do catalog YAML.
- **Actual** (Fase 3): "quanto **estou** gastando?" — números reais do consumo da conta.

A questão **FinOps mais valiosa** é: **estimate bate com actual?**

- Se sim → cotação validada, pode usar o cenário pra projetar TCO.
- Se não → ou o cenário está errado (sizing, sku, region) ou o workload mudou de comportamento.

## Tool: `databricks_billing_compare_estimate_vs_actual`

Bridge entre as duas fases. Recebe:

```python
databricks_billing_compare_estimate_vs_actual(
    scenario_uuid: str,         # UUID do cenário salvo (Fase 2)
    start_date: str,            # 'YYYY-MM-DD'
    end_date: str,              # 'YYYY-MM-DD'
    cluster_name_filter: str | None = None,   # filtra system.billing por cluster
    workspace_id: int | None = None,
)
```

Retorna JSON com:

```json
{
  "scenario_uuid": "...",
  "scenario_name": "ETL Bronze produção",
  "estimated_monthly_usd": 726.88,
  "actual_monthly_usd": 819.50,
  "actual_period_days": 7,
  "variance_pct": 12.74,
  "verdict": "over_budget",
  "cluster_name_filter": "etl-bronze-prod",
  "period": { ... }
}
```

## Algoritmo do engine (`compare_estimate_vs_actual`)

1. **Calcular estimated_monthly_usd** via `cost_engine.databricks.calculate_databricks_cost(scenario)` (Fase 0)
2. **Buscar actual_total_usd_in_period** via `cost_by_compute_type` ou `top_cost_clusters` no `system.billing.usage` filtrado pela janela + cluster
3. **Extrapolar actual pro mensal:** `actual_monthly_usd = actual_total × (30 / days_in_period)`
   - Premissa: distribuição uniforme do consumo nos dias
   - Não vale pra workloads bursty (1 semana de pico + 3 semanas idle) — caveat
4. **Calcular variance:** `(actual_monthly - estimated_monthly) / estimated_monthly × 100`
5. **Verdict:**
   - `on_budget` se `|variance| ≤ 10%`
   - `over_budget` se `variance > +10%`
   - `under_budget` se `variance < -10%`

## Interpretação dos verdicts

### `on_budget` (|variance| ≤ 10%)

✅ Cenário **validado** pelo realizado. Você pode usar pra:
- Projeção de TCO 12/24/36 meses
- Comparação PAYG vs DBCU com confiança
- Apresentação pra comitê FinOps com lastro real

**Ação:** continuar monitorando trimestralmente.

### `over_budget` (variance > +10%)

⚠️ Workload consumindo **mais** que o cenário previu. Causas comuns:

1. **Sizing subestimado:** o cenário assumiu `num_workers=4`, mas autoscale subiu pra 8. **Investigar:** rodar `get_top_cost_clusters` filtrado pelo cluster e ver pico real.
2. **Hours/day maior que o cenário:** `hours_per_day=8` no cenário, mas job começou a rodar 10h/dia. **Investigar:** rodar `get_dbu_usage_daily` e ver distribuição diária.
3. **Photon ativado depois do cenário:** dobra o DBU rate. **Investigar:** checar `system.compute.clusters.dbr_version` ou job config.
4. **Mudança de SKU:** workload migrou de Standard pra Premium ou de Jobs pra All-Purpose. **Investigar:** `get_cost_by_compute_type` pra ver share de SKUs.

**Ação:** **NÃO ajuste o cenário cegamente.** Investigue a causa primeiro. Depois atualize o cenário (carregando + editando no Tab Histórico do App) e re-rode o compare.

### `under_budget` (variance < -10%)

🔍 Workload consumindo **menos** que previsto. Possíveis causas:

1. **Cenário superdimensionado:** `num_workers=10` no cenário mas workload roda confortavelmente com 6. **Oportunidade:** ajustar cenário pra refletir realidade + economizar custo se for replicar.
2. **Autoscale eficiente:** scale-down funcionou melhor que o assumido (autoscale_avg_workers_pct).
3. **Workload reduziu volume:** menos eventos/transações que o assumido.
4. **Idle não contabilizado no estimate:** cenário previu cluster ligado 24/7, mas auto-termination está agressivo.

**Ação:** revisar cenário pra refletir o real. Pode liberar budget pra outros workloads.

## Caveats e edge cases

### Período muito curto (< 7 dias)

Extrapolação `× (30 / days)` amplifica ruído. **Mínimo recomendado:** 14 dias.

Se o user pediu 3 dias, avise:
> "3 dias é período curto pra extrapolação confiável. Variance pode estar inflada por dias atípicos. Recomendo 14+ dias pra confiança estatística."

### Workload bursty (não-uniforme)

Premissa de distribuição uniforme nos dias **falha** quando:
- ETL diário com pico semanal (segunda)
- Workload sazonal (fim de mês fecha 5×)
- PoC com bursts de teste

**Mitigação:** use cluster_name_filter pra isolar o workload + janela longa (30+ dias). Se ainda assim variance for alta, é sinal real (não artefato).

### `cluster_name_filter` aumenta especificidade mas reduz amostra

- Sem filter: actual = total da conta no período (inclui workloads não cobertos pelo cenário) → over_budget falso-positivo
- Com filter: actual = só do cluster nominal → mais preciso, mas exige que `cluster_name` no system.billing case com o que o usuário descreveu no cenário

**Regra:** sempre que possível, **pergunte** ao user qual cluster_name corresponde ao cenário antes de chamar compare.

### Multi-workspace (workspace_id=None)

Sem filtro de workspace, `actual` agrega TODOS os workspaces da conta. Pode inflar artificialmente quando o cenário descreve workload de 1 workspace específico.

**Regra:** se workspace_id não foi especificado e há multi-workspace, perguntar ao user qual workspace o cenário se refere.

### Cluster que não consta no system.billing

Se o cluster do cenário **nunca rodou** (foi só estimado, nunca executado), `actual` será $0 e variance = -100% → `under_budget` falso.

**Mitigação:** o agent deve perguntar "Esse cenário já está em produção, ou é hipotético?" antes do compare. Se hipotético → não rodar compare, apenas estimate.

## Workflow do agente — o que apresentar ao user

```markdown
## Estimate vs Actual: <scenario_name>

| Dimensão | Estimate (Fase 2) | Actual (Fase 3) | Δ |
|---|---|---|---|
| Custo mensal | $X | $Y | <variance pct>% |
| Janela actual | — | <N> dias |
| Cluster filtrado | — | <name ou "todos"> |

**Verdict:** <on_budget | over_budget | under_budget>

**Interpretação:** [explicar conforme verdict — ver §Interpretação acima]

**Caveats:**
- Mock mode: [se aplicável]
- Período curto: [se < 14d]
- Workload bursty: [se variance > 30% e período < 30d]
- Cluster filter aplicado: <name ou "nenhum">

**Sugestão:** [ação concreta baseada no verdict + caveats]
```

## Onde está codificado

- Engine: `data_agents.cost_engine.billing.compare_estimate_vs_actual()` retorna `EstimateVsActual` dataclass
- Tool MCP: `databricks_billing_compare_estimate_vs_actual` em `data_agents/mcp_servers/databricks_billing/server.py`
- Testes: `tests/unit/test_billing_engine.py::TestCompareEstimateVsActual` (5 testes — verdicts, extrapolação, edge cases) + `tests/unit/test_databricks_billing_server.py::TestCompareEstimateVsActual` (bridge integration)
