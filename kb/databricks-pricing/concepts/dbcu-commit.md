---
concept: dbcu-commit
domain: databricks-pricing
updated_at: 2026-05-27
---

# DBCU Commit — Pre-purchase 1y / 3y

## O que é DBCU Commit?

**DBCU (Databricks Commit Units)** é o modelo de pre-purchase da Databricks. O cliente compromete consumo de DBU pra 1 ou 3 anos em troca de desconto.

- **DBCU 1y:** 10-25% de desconto sobre PAYG (Pay-as-you-go)
- **DBCU 3y:** 25-40% de desconto sobre PAYG

Os percentuais reais dependem de:
- Volume comprometido ($USD/ano)
- Negociação com a Account Team Databricks
- Cloud (Azure vs AWS — pode variar)
- Region

> No catalog atual o agente usa percentuais **mock** (definidos em `azure.yaml` e `aws.yaml` na seção `dbcu_discounts`). Para valores reais, pedir cotação à Databricks.

## Quando DBCU compensa?

Regra prática: **se o workload roda > X horas/mês de forma previsível**, DBCU compensa. O breakeven depende do desconto:

- Desconto 15% → breakeven em ~85% de utilização vs PAYG
- Desconto 30% → breakeven em ~70%

A tool `databricks_pricing_compare_payg_vs_dbcu` retorna o `breakeven_hours_per_month` exato pro cenário.

## Quando DBCU NÃO compensa?

- Workload **bursty** (3h/dia 5 dias por semana, dorme nos finais de semana)
- Workload **temporário** (PoC de 3 meses)
- Workload com **alta variabilidade** (uns meses pesados, outros leves) — risco de não consumir o compromisso
- Cliente **sem previsibilidade de consumo** — comprometer antes de medir é arriscado

## Casos de uso ideais

✅ Production 24/7 (sempre on)
✅ ETL diário consistente há > 6 meses (histórico estável)
✅ DLT pipelines em produção
✅ SQL Warehouse com auto-stop curto mas uso diário

## Casos onde PAYG é melhor

❌ PoC / exploração
❌ Workloads experimentais
❌ Workspaces de dev/test
❌ Workloads que vão migrar / mudar arquitetura nos próximos 12 meses

## Como o agente apresenta a comparação

Tool: `databricks_pricing_compare_payg_vs_dbcu(...)`

Retorno tem 3 cenários:
- `payg_annual_usd` — custo PAYG por ano
- `dbcu_1y_annual_usd` — custo DBCU 1y por ano (com desconto aplicado)
- `dbcu_3y_annual_usd` — custo DBCU 3y por ano

E métricas auxiliares:
- `savings_1y_annual` / `savings_1y_pct`
- `savings_3y_annual` / `savings_3y_pct`
- `breakeven_hours_per_month` — abaixo disso, DBCU não compensa
- `recommendation` — texto: "Permaneça em Pay-as-you-go" | "DBCU 1y compensa" | "DBCU 3y compensa"

## Formato esperado no `cost_report.md`

```markdown
## Comparação PAYG vs DBCU

| Modelo | Custo Anual | Savings vs PAYG | Recomendação |
|---|---|---|---|
| Pay-as-you-go | $X | — | baseline |
| DBCU 1y | $Y | $Z (Q%) | <se savings > 0> |
| DBCU 3y | $W | $V (P%) | <se savings > savings_1y> |

Breakeven: <hours>/mês de uso. Abaixo disso, PAYG continua mais barato.

**Recomendação:** <texto da tool>
```

## O que evitar

❌ **Citar percentuais sem rodar a tool** — Não diga "DBCU dá 30% desconto" como fato; rode `compare_payg_vs_dbcu` e use o retorno.

❌ **Recomendar DBCU 3y sem checar breakeven** — DBCU 3y é só pra workload muito estável. Se o usuário menciona "PoC", "experimento", "novo cliente" → DBCU 3y NÃO.

❌ **Inventar histórico** — Não diga "se o workload rodar 24/7 nos próximos 3 anos" sem o usuário confirmar essa premissa. Pergunte primeiro.

## Onde isso é codificado

- Catalog: `dbcu_discounts:` em `data/databricks_pricing/{azure,aws}.yaml`
- Engine: `data_agents.cost_app.databricks.comparisons.compare_payg_vs_dbcu(...)`
- MCP tool: `databricks_pricing_compare_payg_vs_dbcu(...)`
