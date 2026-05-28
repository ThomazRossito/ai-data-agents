---
name: databricks-pricing
description: "Playbook conversational-first para o agent databricks-cost-calculator construir cenários Databricks (Azure + AWS) a partir de descrições em linguagem natural. Inclui workflow canonical, comparação PAYG vs DBCU, comparação Photon on/off, e TCO 12/24/36 meses."
updated_at: 2026-05-27
source: kb/databricks-pricing (index + concepts/dbu-model + concepts/dbcu-commit + concepts/photon-roi + concepts/multi-cloud + concepts/instance-pricing)
agent: databricks-cost-calculator
domain: databricks
---

# Skill — Databricks Pricing Calculation

> **Uso:** Playbook operacional pro agent `databricks-cost-calculator`. Leia este arquivo na primeira chamada da sessão como referência passo-a-passo para cenários comuns.

## Princípio Fundamental: Conversational-First

O usuário descreve o workload em **linguagem natural**. O agent constrói o cenário internamente — **nunca pede JSON ou template ao usuário**.

Exemplos de inputs naturais que o agent processa:

| Input do usuário | O que o agent deve fazer |
|---|---|
| "Quanto custa ETL Bronze com 4 workers DS4_v2 8h/dia 22d/mês?" | Cenário canonical → `calc_cluster_cost(...)` → $726.88/mês |
| "Vale a pena comprar DBCU pra rodar 24/7 com 10 workers?" | Calcular PAYG + comparar com DBCU 1y/3y → `compare_payg_vs_dbcu(...)` |
| "Estimar AWS Jobs Standard 5 workers m5.xlarge us-east-1 sem Photon" | Cenário AWS → `calc_cluster_cost(cloud=aws, ...)` |
| "Compara Photon on/off pro mesmo cenário" | 2 cálculos separados (`photon=true` e `photon=false`) → tabela comparativa + caveat de não assumir aceleração |
| "TCO 36 meses pro workload ETL nightly do banco XYZ" | Mensal × 36 + cite premissa de crescimento se mencionado |
| "Custo em BRL desse cenário" | Após calcular, chamar `currency_convert(amount, 'BRL', fx_rate=5.0)` |
| "Salva esse cenário no app pra eu ver depois" | (R5 condicional) chamar `save_scenario(...)` e retornar UUID + URL |

## Quando Acionar Esta Skill

- Usuário pede custo de workload Databricks (qualquer escala) em linguagem natural
- Comparação Pay-as-you-go vs DBCU 1y vs DBCU 3y
- Comparação Photon on vs off
- Conversão USD↔BRL
- TCO 12/24/36 meses
- Comparação cross-cloud Azure vs AWS (mesmo workload em 2 catalogs)
- Geração de relatório auditável pra comitê de FinOps / pré-venda

## Pré-flight (sempre antes de calcular)

1. **Ler `kb/databricks-pricing/index.md`** — único arquivo KB que o loader injeta automaticamente
2. **Chamar `databricks_pricing_diagnostics`** na primeira pergunta da sessão — valida engine + smoke test ($726.88 canonical)
3. **Confirmar R1-R9** do `agents/registry/databricks-cost-calculator.md` — em especial R5 (save_scenario condicional), R6 (FIDELITY), R7 (sizing: perguntar)

## Workflow Canonical — 9 passos

### Passo 1: Confirmation Block (echo fidelidade)

Sua PRIMEIRA resposta SEMPRE começa com bloco que confirma o input literal. Veja R6/R7 do registry md.

### Passo 2: Diagnostics

```
databricks_pricing_diagnostics() →
  {
    "data": {
      "status": "ok",
      "catalogs_loaded": ["azure", "aws"],
      "smoke_test_canonical": {
        "expected_monthly_usd": 726.88,
        "actual_monthly_usd": 726.88,
        "match": true
      }
    }
  }
```

Se `match: false` → STOP e reporte erro.

### Passo 3: Discovery (se SKU/region desconhecido)

```
databricks_pricing_list_instances(cloud="azure", region="brazilsouth") →
  {"data": {"count": 7, "instances": ["Standard_DS3_v2", "Standard_DS4_v2", ...]}}

databricks_pricing_list_regions(cloud="azure") →
  {"data": {"regions": ["brazilsouth", "eastus", "westeurope"]}}
```

### Passo 4: Cluster Cost (tool principal)

```
databricks_pricing_calc_cluster_cost(
  cloud="azure",
  compute_type="jobs_compute",
  tier="premium",
  photon=false,
  driver_instance="Standard_DS4_v2",
  worker_instance="Standard_DS4_v2",
  num_workers=4,
  hours_per_day=8.0,
  days_per_month=22,
  region="brazilsouth",
) →
  {
    "data": {
      "totals": {
        "monthly": 726.88,
        "daily": 33.04,
        "hourly": 4.13
      },
      "breakdown": {
        "dbu_cost_monthly": 264.00,
        "instance_cost_monthly": 462.88,
        "dbu_pct": 36.3,
        "instance_pct": 63.7
      }
    }
  }
```

### Passo 5: PAYG vs DBCU (se solicitado)

Trigger keywords: "DBCU", "comprar", "comprometimento", "RI", "savings", "vale a pena".

```
databricks_pricing_compare_payg_vs_dbcu(<mesmos params do Passo 4>) →
  {
    "data": {
      "payg_annual_usd": 8722.56,
      "dbcu_1y_annual_usd": 7414.18,
      "dbcu_3y_annual_usd": 6105.79,
      "savings_1y_annual": 1308.38,
      "savings_1y_pct": 15.0,
      "savings_3y_annual": 2616.77,
      "savings_3y_pct": 30.0,
      "breakeven_hours_per_month": 149.6,
      "recommendation": "DBCU 1y compensa (savings > 0)..."
    }
  }
```

### Passo 6: Photon comparison (se solicitado)

Trigger keywords: "Photon", "comparar Photon", "vetorizado", "engine".

Rodar 2× `calc_cluster_cost` — uma com `photon=true`, outra `photon=false`. **NUNCA afirmar aceleração sem benchmark** — veja `kb/databricks-pricing/concepts/photon-roi.md`.

### Passo 7: Currency conversion (se solicitado)

Trigger keywords: "BRL", "real", "reais", "BRL", currency name diferente de USD.

```
databricks_pricing_currency_convert(
  amount_usd=726.88,
  target_currency="BRL",
  fx_rate=5.0,
) →
  {
    "data": {
      "amount_converted": 3634.40,
      "fx_rate": 5.0
    }
  }
```

### Passo 8: Salvar arquivos (R4 + R8 do registry)

Path:
- Cliente nominal → `output/prj_<slug>/cost_report.md` + `scenario_used.json`
- Sem cliente → `output/cost-databricks/<YYYYMMDD>_<slug>/`

### Passo 9: Save scenario para App (CONDICIONAL — R5)

**Só se o usuário pediu explicitamente** ("salva no app", "manda pro Streamlit", "quero editar depois"):

```
databricks_pricing_save_scenario(
  cloud="azure",
  compute_type="jobs_compute",
  tier="premium",
  photon=false,
  driver_instance="Standard_DS4_v2",
  worker_instance="Standard_DS4_v2",
  num_workers=4,
  hours_per_day=8.0,
  days_per_month=22,
  region="brazilsouth",
  name="ETL Bronze produção",
  description="Pipeline noturno",
) →
  {
    "data": {
      "uuid": "<uuid v4>",
      "app_url": "http://localhost:8514",
      "next_step": "Abra http://localhost:8514 → Histórico → procure por 'ETL Bronze produção'"
    }
  }
```

## Padrões comuns — playbook

### Padrão 1: PoC simples (1 cenário, sem comparação)

```
1. Diagnostics
2. Confirmation Block + AskUserQuestion (sizing se omitido per R7)
3. calc_cluster_cost
4. Salvar cost_report.md + scenario_used.json
5. (R5) NÃO chamar save_scenario sem pedido explícito
```

### Padrão 2: Comparação PAYG vs DBCU (cenário 24/7)

```
1. Diagnostics
2. Confirmation Block
3. calc_cluster_cost (workload 24/7)
4. compare_payg_vs_dbcu (mesmo cenário)
5. Apresentar tabela 3 linhas (PAYG, 1y, 3y) + recommendation
6. Salvar arquivos
```

### Padrão 3: Cross-cloud Azure vs AWS

```
1. Diagnostics
2. Confirmation Block + pedir SKU equivalente AWS (NÃO mapear automaticamente)
3. calc_cluster_cost(cloud="azure", ...)
4. calc_cluster_cost(cloud="aws", ...) com SKU AWS confirmado
5. Apresentar tabela 2 colunas no cost_report.md
6. Cite caveat: "Custos de mudança (S3 vs ADLS, networking, training) não inclusos"
```

### Padrão 4: TCO multi-período

```
1. Diagnostics + cenário base
2. calc_cluster_cost → monthly
3. TCO 12m = monthly × 12; 24m = monthly × 24; 36m = monthly × 36
4. Se usuário mencionou crescimento ("vamos crescer 30% ao ano"): aplicar growth_rate ao mensal e somar progressivamente. Cite no output.
5. Salvar
```

### Padrão 5: Salvar pro App (uso CONDICIONAL — só com pedido)

```
1-8: cenário normal
9. save_scenario(name=<descritivo>, description=<contexto>)
10. Apresentar UUID + app_url + next_step ao usuário
```

### Padrão 6: Editar cenário existente (Chunk 2.3 — bridge App → Agent)

Trigger keywords: "carrega o cenário XYZ", "abre o que salvei", "recalcula meu ETL Bronze com 8 workers", "compara o cenário X com Y mas com Photon".

```
1. Diagnostics (se 1ª pergunta da sessão)
2. Resolução do UUID:
   - Se user falou UUID direto → vai pro Passo 3
   - Se user falou nome ("ETL Bronze") → search_scenarios("ETL Bronze")
     - 0 matches → reportar, pedir clarificação
     - 1 match → confirmar com user e prosseguir
     - 2+ matches → listar os top 3 e perguntar qual
3. load_scenario(uuid) → envelope completo (uuid, name, source, parent_uuid, scenario)
4. Apresentar premissas do cenário carregado + diff pedido:
   "Carreguei 'ETL Bronze' (4 workers, 8h/dia, brazilsouth, Premium sem Photon = $726.88/mês).
    Vou recalcular com num_workers=8 mantendo o resto."
5. calc_cluster_cost(...) com os campos do envelope + a alteração
6. Apresentar novo custo + delta vs original
7. (CONDICIONAL R5) Se user pediu salvar a variante:
   save_scenario(
     scenario_modificado,
     name="ETL Bronze — 8 workers",   # nome descritivo da variante
     description=f"Variant de {original_uuid[:8]} com num_workers=8",
     # NÃO passe source aqui — o agent sempre grava como "agent"
   )
8. Salvar arquivos (cost_report.md + scenario_used.json)
```

### Padrão 7: Listar/Limpar cenários (housekeeping)

Trigger keywords: "quais cenários eu tenho salvos?", "limpa os cenários de teste".

```
1. list_scenarios(filter_source="agent")  # ou filter_cloud, ou ambos
2. Apresentar tabela com uuid[:8], name, source, created_at, cloud
3. (DELETE — destrutivo, só com pedido explícito):
   - Confirmar com user: "Vou deletar uuid=X (name='Y'). Confirma?"
   - delete_scenario(uuid)
   - Confirmar retorno deleted=true
4. NUNCA deletar sem pedido + confirmação explícita
```

## Anti-patterns

❌ **Não rode `save_scenario` sem pedido explícito.** A bridge `outputs/cost-scenarios/` existe pra uso humano deliberado. Lixo aí polui o Tab Histórico do App.

❌ **Não chute SKU equivalente cross-cloud.** "DS4_v2 ≈ m5.2xlarge" é aproximação. Pergunte ao usuário.

❌ **Não afirme aceleração Photon.** "Photon vai economizar 30%" só com benchmark real do workload.

❌ **Não pule diagnostics.** Smoke test garante engine OK; se falhar, todo o resto está suspeito.

❌ **Não invente preço quando SKU/region não está no mock.** Cite "não disponível na Fase 1 — pedir cotação real" e pare.

## Referências cruzadas (KB)

- DBU model: `kb/databricks-pricing/concepts/dbu-model.md`
- DBCU 1y/3y: `kb/databricks-pricing/concepts/dbcu-commit.md`
- Photon ROI: `kb/databricks-pricing/concepts/photon-roi.md`
- Multi-cloud: `kb/databricks-pricing/concepts/multi-cloud.md`
- Mock instance pricing limits: `kb/databricks-pricing/concepts/instance-pricing.md`
