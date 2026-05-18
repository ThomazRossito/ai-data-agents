# Pattern — Azure OpenAI / Foundry Billing

> Referência crítica pro agent `azure-cost-calculator` entender como os modelos OpenAI deployados via Foundry são cobrados na Azure Retail Prices API.

## 1. Plataforma vs Serviço de Billing

| Conceito | O que é |
|---|---|
| **Azure AI Foundry** | Plataforma — onde você cria agents, deploya modelos, configura knowledge sources |
| **Modelos OpenAI** | gpt-4.1-mini, text-embedding-3-large, gpt-4o, o1-mini, etc. — hospedados dentro do Foundry |
| **Azure OpenAI** (na fatura) | Linha de billing onde aparecem os tokens consumidos pelos modelos OpenAI |
| **Cognitive Services** (na fatura) | Linha de billing para serviços AI não-OpenAI (Speech, Vision, Translator, Form Recognizer) |

**Resumindo:** Foundry é a plataforma; "Azure OpenAI" é como a Microsoft cobra os tokens dos modelos OpenAI deployados via Foundry. Aparece como serviço separado na fatura, mesmo quando todo o uso é via Foundry.

## 2. Mapping de `serviceName` na Retail API

| Modelo deployado via Foundry | serviceName na API |
|---|---|
| gpt-4o, gpt-4o-mini, gpt-4.1-mini, gpt-4.1, gpt-4-turbo, gpt-35-turbo | `Azure OpenAI` |
| text-embedding-3-large, text-embedding-3-small, text-embedding-ada-002 | `Azure OpenAI` |
| o1, o1-mini (reasoning models) | `Azure OpenAI` |
| Whisper (transcrição) | `Azure OpenAI` |
| DALL-E 3 (imagens) | `Azure OpenAI` |
| Foundry Agent Service runtime | NÃO TEM linha — é cobrado embutido nos modelos |
| Content Safety, Prompt Shield | NÃO TEM linha — incluso no Foundry |
| Translator, Speech, Vision, OCR | `Cognitive Services` (separado) |
| Azure AI Search | `Azure Cognitive Search` (legado naming) |

## 3. Cobertura Regional de Azure OpenAI

**Importante:** Azure OpenAI NÃO está em todas as regiões. SKUs e modelos disponíveis variam por região:

| Região | Cobertura OpenAI | Modelos comuns disponíveis |
|---|---|---|
| `eastus`, `eastus2` | ✅ Completa | gpt-4o, gpt-4.1, embeddings, o1 |
| `westeurope`, `northeurope` | ✅ Completa | gpt-4o, gpt-4.1, embeddings |
| `francecentral`, `switzerlandnorth` | ✅ Completa | data residency EU |
| `southcentralus`, `australiaeast` | ✅ Parcial | modelos recentes |
| `japaneast`, `koreacentral` | ✅ Parcial | data residency APAC |
| **`brazilsouth`** | ⚠️ **Parcial / cobertura limitada** | Alguns modelos não registrados na Retail API |
| `centralindia`, `uaenorth` | ⚠️ Parcial | varia por modelo |

**Implicação prática:** quando o cliente está em uma região com cobertura parcial (ex: `brazilsouth`) mas o modelo (ex: `gpt-4.1-mini`) só tem SKU registrado em outra região (ex: `eastus2`), o **billing é feito no preço da deployment region** mesmo o cliente sendo de outra geografia. Microsoft documenta essa pricing-via-deployment-region.

## 4. Estratégia de Fallback Regional (CRÍTICO)

Quando `azure_pricing_get_retail_price(service_name='Azure OpenAI', region='brazilsouth')` retorna **0 SKUs**, o agent DEVE:

1. **Tentar regiões alternativas em ordem:**
   - `eastus2` (cobertura mais ampla de OpenAI)
   - `eastus`
   - `westeurope`
   - `northeurope`

2. **Sinalizar no output que usou cross-region pricing:**
   ```
   ⚠️ Cross-region pricing: gpt-4.1-mini não tem SKU registrado em brazilsouth.
   Preço aplicado é de eastus2 (Microsoft cobra deployment region para modelos OpenAI).
   ```

3. **NÃO usar fallback de pricing hardcoded** — sempre buscar valor real da API em outra região.

## 5. Modelos e meterName Específicos

A Azure Retail API usa `meterName` granular para distinguir input/output e versões. Exemplos:

| Modelo | productName | meterName | Unit |
|---|---|---|---|
| gpt-4o | Azure OpenAI - GPT-4o | Input Tokens, Output Tokens, Cached Input Tokens | 1M Tokens |
| gpt-4o-mini | Azure OpenAI - GPT-4o-mini | Input Tokens, Output Tokens | 1M Tokens |
| gpt-4.1 | Azure OpenAI - GPT-4.1 | Input Tokens, Output Tokens | 1M Tokens |
| gpt-4.1-mini | Azure OpenAI - GPT-4.1-mini | Input Tokens, Output Tokens | 1M Tokens |
| gpt-4.1-nano | Azure OpenAI - GPT-4.1-nano | Input Tokens, Output Tokens | 1M Tokens |
| text-embedding-3-large | Azure OpenAI - text-embedding-3-large | Input Tokens | 1M Tokens |
| text-embedding-3-small | Azure OpenAI - text-embedding-3-small | Input Tokens | 1M Tokens |
| o1 | Azure OpenAI - o1 | Input Tokens, Output Tokens, Cached Input | 1M Tokens |
| o1-mini | Azure OpenAI - o1-mini | Input Tokens, Output Tokens | 1M Tokens |

**⚠️ CRÍTICO: Discovery-first para modelos OpenAI**

Os `productName` exatos na Retail API mudam frequentemente (Microsoft re-padroniza naming). Em vez de tentar adivinhar o nome correto, **sempre faça discovery primeiro**:

### Passo 1 — Descobrir o productName exato

```python
# Lista todos os SKUs de Azure OpenAI em uma região com cobertura ampla
azure_pricing_list_skus(service_name="Azure OpenAI", region="eastus2")
```

A resposta vai mostrar produtos no formato real, ex:
- `Azure OpenAI - GPT-4.1-mini`  ← às vezes
- `Azure OpenAI - GPT-4.1 Mini`  ← outras vezes (com espaço)
- `Azure OpenAI GPT-4.1-mini`  ← variação

### Passo 2 — Usar o productName EXATO descoberto

```python
azure_pricing_get_retail_price(
    service_name="Azure OpenAI",
    product_name="Azure OpenAI - GPT-4.1-mini",   # EXATAMENTE como retornou no list_skus
    meter_name="Input Tokens",
    region="eastus2"
)
```

### Alternativa: buscar por meter_name apenas (sem productName)

Se o usuário sabe o modelo mas não o productName exato, filtrar só por meter pode funcionar:

```python
# Busca tudo que tem "gpt-4.1-mini" no meter, sem amarrar productName
azure_pricing_get_retail_price(
    service_name="Azure OpenAI",
    meter_name="gpt-4.1-mini Input Tokens",   # mais granular, mais previsível
    region="eastus2"
)
```

**Anti-pattern:** chutar `product_name="Azure OpenAI - GPT-4.1-mini"` sem fazer discovery — quando Microsoft muda o naming, o filter falha silenciosamente retornando 0 itens.

## 6. PTU (Provisioned Throughput Units) vs Standard

| Modalidade | priceType | Cobrança |
|---|---|---|
| **Standard** (Pay-as-you-go) | `Consumption` | $/1M tokens, sem SLA throughput |
| **Provisioned (PTU)** | `Consumption` (mas com `productName` específico) | $/PTU/hora (ex: 50 PTUs × $50/PTU/hora) |
| **Global Standard** | `Consumption` | Mais barato que regional Standard, sem data residency |
| **Provisioned Global** | `Consumption` | PTUs globais |

Como heurística: até ~50k queries/dia, **Standard** é suficiente. PTU só compensa em workloads pesados (>50k queries/dia ou throughput previsível alto sustained).

## 7. Exemplos de Pricing Real (referência maio/2026)

| Modelo | Modalidade | Preço | Região |
|---|---|---|---|
| gpt-4.1-mini Input | Standard | $0.40 / 1M tokens | eastus, eastus2, westeurope |
| gpt-4.1-mini Output | Standard | $1.60 / 1M tokens | eastus, eastus2, westeurope |
| gpt-4o Input | Standard | $2.50 / 1M tokens | eastus, etc. |
| gpt-4o Output | Standard | $10.00 / 1M tokens | eastus, etc. |
| text-embedding-3-large | Standard | $0.13 / 1M tokens | eastus, etc. |
| text-embedding-3-small | Standard | $0.02 / 1M tokens | eastus, etc. |

> **Atenção:** preços brazilsouth tipicamente são **5-10% mais caros** que eastus (quando disponíveis). Mas como muitos modelos OpenAI são cobrados via deployment region (não tenant region), o preço efetivo costuma ser o de eastus2 mesmo o cliente sendo brazilsouth.

## 8. Exemplo de Cálculo de Custo Mensal (referência)

Cenário: workload corporativo médio com ~1000 queries/dia × ~3500 tokens/query = ~3.5M tokens/dia = **~105M tokens/mês**
Split típico de chat com RAG: ~75M input + ~30M output + ~1.5M embedding (query embedding em runtime)

```
gpt-4.1-mini Input:    75M × $0.40 / 1M  = $30.00
gpt-4.1-mini Output:   30M × $1.60 / 1M  = $48.00
text-embedding-3-large: 1.5M × $0.13 / 1M = $0.20
─────────────────────────────────────────────────
Total Foundry tokens/mês:                  ~$78
```

Use este formato como **template de cálculo** ajustando para o volume do projeto que você está estimando.

## 9. Anti-pattern: Não Confundir Foundry e OpenAI no Custo

❌ **Errado:** "Foundry custa X, e além disso OpenAI custa Y" — soma duplicada
❌ **Errado:** "Foundry tem custo fixo" — só tem tokens, sem fixed cost
❌ **Errado:** Listar Foundry e Azure OpenAI como dois recursos separados no JSON de input

✅ **Correto:** "Modelos deployados via Foundry consomem tokens cobrados como Azure OpenAI"
✅ **Correto:** Listar apenas `service_name: "Azure OpenAI"` no JSON, especificando o modelo via `product_name` ou `meter_name`
✅ **Correto:** Foundry resource em si tem custo zero base (pay-per-token apenas)

## 10. Referências

- [Azure OpenAI pricing](https://azure.microsoft.com/pricing/details/cognitive-services/openai-service/)
- [Foundry Agent Service overview](https://learn.microsoft.com/azure/foundry/agents/overview)
- [Azure OpenAI regions and quotas](https://learn.microsoft.com/azure/ai-foundry/openai/quotas-limits)
- [Standard vs PTU pricing](https://learn.microsoft.com/azure/ai-foundry/openai/concepts/provisioned-throughput)
