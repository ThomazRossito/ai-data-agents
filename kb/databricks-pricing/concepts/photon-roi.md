---
concept: photon-roi
domain: databricks-pricing
updated_at: 2026-05-27
---

# Photon ROI — Quando Vale a Pena Pagar 2× pelo DBU?

## O que Photon faz

**Photon** é uma engine de execução vetorizada (C++ + SIMD) que substitui o motor JVM do Spark em workloads SQL/agregação. Foi GA na Databricks em 2022 (Azure) / 2021 (AWS).

**Custo:** dobra o DBU rate (~2×).

**Benefício:** acelera workloads 2-5× em padrões adequados. Em workloads inadequados, **não acelera ou pode até desacelerar** (raríssimo, mas existe).

## Regra de bolso — Photon provavelmente compensa quando:

✅ Workload é **SQL agregação pesada** (GROUP BY com COUNT/SUM/AVG sobre tabelas grandes)
✅ Workload tem **joins multi-tabela com filtros seletivos**
✅ Workload usa **windowing functions** (ROW_NUMBER, RANK, LAG/LEAD)
✅ Workload usa **funções built-in vetorizáveis** (regex, string ops, date arithmetic)
✅ Workload tem **alto throughput de leitura Delta** (Photon otimiza scan de Parquet)

## Regra de bolso — Photon provavelmente NÃO compensa quando:

❌ Workload é **PySpark com UDFs custom (Python)** — Photon não acelera UDFs Python
❌ Workload é **streaming de baixa volumetria** (Photon brilha em batch grande)
❌ Workload tem **predominância de operações I/O bound** (rede/disco saturando antes do compute)
❌ Workload usa **MLlib pesado** (training) — Photon não acelera ML training
❌ Workload é **small data** (< 100 GB) — overhead vs benefit não compensa

## O que dizer ao usuário (NUNCA afirme economia sem benchmark)

> **NUNCA escreva no `cost_report.md`:** "Photon vai acelerar 3× e custar 2× — payback positivo".
>
> **SEMPRE escreva:** "Photon dobra o DBU rate. Rule of thumb: pode acelerar 2-5× em workloads SQL pesados, mas isso varia. Recomendamos rodar 1 semana side-by-side (mesmo cenário com e sem Photon) e comparar custo total + latência antes de decidir."

## Como o agente apresenta no relatório

Se o usuário pediu "comparar Photon on/off":

1. Calcular cenário com `photon=false` → `cost_off`
2. Calcular cenário com `photon=true` → `cost_on`
3. Apresentar comparação **DE CUSTO PURO** (sem assumir aceleração):

```markdown
## Comparação Photon On/Off

| Cenário | DBU rate | Custo Mensal |
|---|---|---|
| Photon OFF | $0.20/DBU·h | $726.88 |
| Photon ON | $0.40/DBU·h | $990.88 |

⚠️ **Photon dobra o DBU rate.** O custo acima assume mesmo `hours_per_day` em ambos os cenários.
Se o seu workload realmente acelerar 2× com Photon (regra de bolso pra SQL pesado), o `hours_per_day`
cairia pela metade, e o custo real ficaria comparável ou menor. **Mas isso varia muito por workload —
recomendamos rodar 1 semana side-by-side antes de decidir.**
```

## Quando perguntar ao usuário sobre Photon (R9 do agente)

Se o usuário descreveu um workload **pesado** (> 4 workers, > 8h/dia) e **não mencionou Photon**:

> **AskUserQuestion:** "Esse workload parece pesado o suficiente pra Photon fazer diferença. Quer que eu calcule com Photon on, off, ou ambos pra comparar? (Photon dobra o DBU rate mas pode acelerar 2-5× em workloads SQL pesados — não recomendamos sem benchmark)."

Se o workload é leve (< 4 workers, < 8h/dia) ou claramente não-SQL (PySpark custom, streaming, ML): **assuma Photon off** (R6) e cite no output.

## Onde isso é codificado

- Parâmetro: `photon: bool` no `DatabricksScenario`
- Engine: lookup do `dbu_rate` no catalog YAML multiplica por 2× quando `photon=true`
- MCP tool: `databricks_pricing_calc_cluster_cost(photon=...)` aceita o flag

## Referências externas

- Databricks docs: https://docs.databricks.com/en/runtime/photon.html
- AnyScale benchmark (terceiro): https://docs.databricks.com/en/photon/performance.html
