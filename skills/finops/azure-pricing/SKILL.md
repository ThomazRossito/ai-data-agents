---
name: azure-pricing
description: "Playbook conversational-first para o agent azure-cost-calculator construir cenários Azure (Foundry, AI Search, Fabric, OpenAI, Databricks) a partir de descrições em linguagem natural. Inclui padrões enterprise vs simple, comparação multi-região, TCO 12/24/36 meses."
updated_at: 2026-05-17
source: kb/azure-pricing (index, patterns/openai-foundry-billing, patterns/bundle-skus)
agent: azure-cost-calculator
domain: finops
---

# Skill — Azure Pricing Calculation (FinOps)

> **Uso:** Playbook operacional pro agent `azure-cost-calculator`. Leia este arquivo na primeira chamada da sessão como referência passo-a-passo para cenários comuns.

## Princípio Fundamental: Conversational-First

O usuário descreve a arquitetura em **linguagem natural**. O agent constrói o cenário internamente — **nunca pede JSON ou template ao usuário**.

Exemplos de inputs naturais que o agent precisa processar:

| Input do usuário | O que o agent deve fazer |
|---|---|
| "Quanto custa Foundry + AI Search + Fabric pra 30 users?" | Detectar padrão enterprise, construir cenário com defaults (brazilsouth, 1000 queries/dia), calcular |
| "Custo de uma arquitetura simples com só AI Search S1 e Storage" | Detectar padrão simple, construir cenário mínimo |
| "Compara o cenário X em brazilsouth vs eastus" | Rodar mesmo cenário em 2 regiões, gerar tabela comparativa |
| "TCO 36 meses pra produção do banco XYZ" | Calcular mensal + extrapolar 36 meses + aplicar crescimento orgânico se informado |

## Quando Acionar Esta Skill

- Usuário pede custo de arquitetura Azure (qualquer escala) em linguagem natural
- Comparação RI vs PAYG vs Savings Plans
- Conversão USD↔BRL via rate Microsoft
- TCO 12/24/36 meses
- Comparação de regiões pra um mesmo workload
- Geração de relatório de custos pra comitê de produto / FinOps

## Pré-flight (sempre antes de calcular)

1. Ler `kb/azure-pricing/index.md` (mapping de serviceName, bundles, regiões — único arquivo KB que o loader injeta automaticamente)
2. Chamar `azure_pricing_diagnostics` na primeira pergunta da sessão (valida API responsiva e mostra defaults aplicados)
3. Confirmar regras invioláveis do `agents/registry/azure-cost-calculator.md` (R1-R9) — em especial R6 (FIDELITY) e R7 (sizing: perguntar)

## Cenário 1 — Custo de Arquitetura Nova (Conversational, project-agnostic)

**Input do usuário** (linguagem natural, sem JSON):
> "Quero custo de uma arquitetura completa Foundry + AI Search + Fabric em brazilsouth pra 30 usuários, com 1000 queries/dia."

**Passos do agent (project-agnostic — mesmo fluxo para QUALQUER cliente/arquitetura):**

1. **Confirmation block (Passo 1 do registry)** — primeira resposta ao usuário:
   ```
   📋 Confirmando o pedido:
   - Cliente: <literal do usuário>
   - Região: <literal, ou default brazilsouth>
   - Quantidades: 30 usuários, 1000 queries/dia (literais)
   - Recursos pedidos: Foundry, AI Search, Fabric (literais)
   - Termos compostos: nenhum nesta query

   Foundry = Azure AI Foundry (per R5).
   Sizing não especificado para Fabric/AI Search — preciso perguntar antes de cotar:
   - Fabric: F2 ($409), F4 ($817), F8 ($1.635)? (default sugerido: F4 - medium workload)
   - AI Search: Basic ($75), S1 ($250)? (default sugerido: S1 - 1k queries/dia cabem)
   ```
   Espera resposta do usuário OU usa defaults sugeridos se ele autorizar.

2. **Construir lista interna** APENAS com os recursos que o usuário pediu + tier confirmado:
   ```python
   resources = [
       # Foundry → Azure OpenAI tokens (per R5)
       {"label": "Foundry gpt-4o-mini Input", "service_name": "Azure OpenAI",
        "meter_name": "gpt-4o-mini Input Tokens", "region": "eastus2", "quantity": 21.0},
       {"label": "Foundry gpt-4o-mini Output", "service_name": "Azure OpenAI",
        "meter_name": "gpt-4o-mini Output Tokens", "region": "eastus2", "quantity": 9.0},
       # AI Search S1 (confirmado pelo usuário)
       {"label": "AI Search S1", "service_name": "Azure Cognitive Search",
        "sku_name": "S1", "region": "brazilsouth", "quantity": 1},
       # Fabric F4 (confirmado pelo usuário)
       {"label": "Fabric F4 Capacity", "service_name": "Microsoft Fabric",
        "sku_name": "F4", "meter_name": "F4 Capacity Unit", "region": "brazilsouth", "quantity": 1},
   ]
   ```
   **NÃO adicione VMs, Storage, Defender, Purview, Site Recovery** — o usuário não pediu.

3. **Discovery (R2)** — para cada resource, antes de filtrar SKU exato, chame `azure_pricing_list_skus(service_name, region)` se houver dúvida sobre naming. Especialmente para Azure OpenAI e Cognitive Search.

4. **Chamar `azure_pricing_estimate_monthly_cost(resources_json)`**.
   - Se retornar `error: fixed_cost_validation_failed`, leia o `violations` e adicione as `missing_line_to_add` à sua lista. Re-chame.
   - Se retornar warnings com `unmatched_count > 0`, use `list_skus` para descobrir SKU correto e re-tente.

5. **Aceitar resultado verbatim**. Não arredonde, não complemente com chutes.

6. **Conversão currency (se solicitado)** — chamar `azure_pricing_currency_convert(total_usd, "USD", "BRL")`. Use a taxa retornada, não estime.

7. **Comparação reservations (se previsível)** — `compare_reservation_terms` para SKUs compute. Para Fabric/AI Search não há RI; só pra VMs (se houver).

8. **Salvar 2 arquivos** no path definido por R9 (cliente nominal → `output/prj_<slug>/`; sem cliente → `output/cost-azure/<YYYYMMDD>_<slug>/`):
   - `cost_report.md` — relatório legível
   - `scenario_used.json` — snapshot do `resources_json` exato

9. **Apresentar links computer://** ao usuário e parar. Supervisor relatará o `cost_report.md` verbatim.

## Cenário 2 — Comparação Regional

**Input:**
> "Compara o mesmo cenário em brazilsouth vs eastus vs westeurope."

**Passos:**

1. Manter a lista de resources idêntica, mudar apenas `region` em cada chamada.
2. Chamar `azure_pricing_estimate_monthly_cost` 3 vezes (uma por região).
3. Apresentar tabela comparativa:

| Componente | brazilsouth | eastus | westeurope |
|---|---|---|---|
| AI Search S1 | $250 | $250 | $265 |
| Fabric F4 | $570 | $525 | $552 |
| Foundry tokens | $80 | $75 | $78 |
| **Total mensal** | $900 | $850 | $895 |

4. Comentar **fatores não-monetários**: data residency, latência, compliance, integração com on-prem.

## Cenário 3 — RI vs PAYG vs Savings Plan

**Input:**
> "Vale a pena RI 3 anos pra esse Standard_D4s_v3 em eastus?"

**Passos:**

1. `compare_reservation_terms("Virtual Machines", "Standard_D4s_v3", region="eastus")`
2. Apresentar saída:

```
| Termo | Mensal | Savings | Total 3 anos |
|---|---|---|---|
| PAYG | $140 | — | $5.040 |
| RI 1 ano | $98 | -30% | $3.528 |
| RI 3 anos | $70 | -50% | $2.520 |
```

3. **Sempre alertar tradeoffs:**
   - RI exige commit de termo completo
   - Cancelamento parcial possível mas com penalidade
   - SKU específico — não vale pra outra VM
   - Considerar Savings Plan se workload é variável

## Cenário 4 — TCO 36 Meses

**Input:**
> "TCO 36 meses do cenário X, incluindo crescimento orgânico de Y% YoY"

**Passos:**

1. Calcular custo base mensal via `estimate_monthly_cost`.
2. Aplicar curva de crescimento (input do usuário ou default conservador 20% YoY).
3. Projetar tabela:

| Período | Queries/dia (estimado) | Custo mensal | Custo acumulado |
|---|---|---|---|
| Mês 1 | 100 | R$ 2.085 | R$ 2.085 |
| Mês 6 | 500 | R$ 2.300 | R$ 13.500 |
| Mês 12 | 1.000 | R$ 2.500 | R$ 27.000 |
| Mês 24 | 3.000 | R$ 3.800 | R$ 64.000 |
| Mês 36 | 5.000 | R$ 5.500 | R$ 120.000 |

4. Salvar em `output/cost-azure/tco_36m_<scenario>.md`.

## Cenário 5 — Validação Cruzada com Calculadora UI

**Quando útil:** usuário desconfia do número, ou compliance exige auditoria.

**Passos:**

1. Após calcular, chamar `azure_pricing_generate_calculator_url` pra gerar links.
2. Instruir usuário:
   - Abrir o link de cada serviço
   - Selecionar a mesma região e SKU exato retornados
   - Comparar valor mensal
3. **Esperar delta ≤ 1%** por timing de currency. Se delta > 5%, investigar bundle pricing.

## Output Sempre Inclui

```
**Fonte:** Azure Retail Prices API (https://prices.azure.com)
**Consultado em:** <ISO 8601 UTC timestamp>
**Hours/month:** 730 (padrão da calculadora oficial)
**Link calculadora oficial:** <URL gerada>
**Caveats:**
  - Preços retail públicos; descontos EA/MCA NÃO inclusos
  - Currency rate: Microsoft FX
  - Bundles aplicados: <lista>
```

## Anti-patterns

❌ Retornar número sem citar fonte
❌ Estimar "de cabeça" valores que a tool consegue buscar
❌ Esquecer de mencionar caveat EA/MCA pra clientes corporativos grandes
❌ Adicionar Storage à parte quando o tier principal já inclui
❌ Comparar tiers diferentes lado a lado sem alertar diferenças (AI Search Basic NÃO tem semantic ranker; S1 tem)
❌ Aplicar discount % sem o usuário ter mencionado contrato EA

## Recovery em Caso de Falha

| Problema | Ação |
|---|---|
| MCP retorna 0 items | Tentar `list_skus` pra descobrir nome correto |
| API timeout / 5xx | Tentar novamente após 30s; se persistir, comunicar usuário e oferecer cached data |
| Currency conversion falha | Usar USD e mencionar "BRL conversion unavailable — apply at billing time" |
| SKU não existe na região | Chamar `list_regions` e sugerir região alternativa |

## Performance Tips

- Cache em memória do MCP guarda preços por 1 hora — múltiplas chamadas seguidas são rápidas
- Pra cenários >20 resources, dividir em chamadas batch
- `diagnostics` é leve (~200ms) — usar como heartbeat no início

## Quando Acionar Outro Agent

- Decisões arquiteturais (qual SKU usar) → `fabric-engineer` ou `databricks-engineer`
- Análise de FinOps em larga escala (tags, chargeback, budgets) → `governance-auditor` ou `data-mesh-architect`
- Negociação contratual com Microsoft → fora do escopo dos agents
