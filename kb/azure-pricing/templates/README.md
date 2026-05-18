# Templates de Arquitetura Azure — Referência Interna do Agent

> ⚠️ **Esta pasta contém referências INTERNAS para o agent `azure-cost-calculator`.**
> O usuário final NÃO precisa conhecer ou editar esses arquivos.
> O agent lê estes templates para entender padrões de arquitetura comuns
> e construir cenários a partir de descrição em linguagem natural.

## Como o agent usa estes templates

Quando o usuário pede algo como:

> "Quanto custa uma arquitetura completa Foundry + AI Search + Fabric pra 30 usuários em brazilsouth?"

O agent:

1. **Identifica** o padrão de arquitetura sendo descrito ("enterprise full" vs "simple PoC" vs custom)
2. **Lê** o template correspondente desta pasta como base mental
3. **Adapta** quantidades, região, currency conforme premissas do usuário
4. **Pergunta** ao usuário apenas o estritamente necessário (1-2 perguntas no máximo)
5. **Aplica defaults inteligentes** para o resto, citando-os no output
6. **Calcula** via Azure Retail Prices API
7. **Salva** o cenário usado (JSON) junto com o relatório para auditoria

## Padrões disponíveis

| Template | Cenário típico | Recursos | Custo típico (brazilsouth) |
|---|---|---|---|
| `simple-poc.json` | PoC, validação técnica, 1 use case isolado | 3-5 recursos | $300-500/mês |
| `enterprise-full.json` | **Cliente enterprise** com Foundry + AI Search + Fabric + Network Hub + Security + DR | ~15 recursos | $2.500-3.500/mês |

## Heurísticas de detecção de padrão

O agent usa estas heurísticas para escolher o template-base:

### → `enterprise-full.json` quando o usuário menciona:
- "produção", "enterprise", "corporativo", "completo"
- "compliance", "LGPD", "SOX", "auditoria"
- "Network Hub", "Firewall", "Bastion", "WAF"
- "Defender", "Sentinel", "Purview"
- "DR", "disaster recovery", "multi-region"
- Combinação Foundry + AI Search + Fabric + Network + Security

### → `simple-poc.json` quando o usuário menciona:
- "PoC", "prova de conceito", "MVP", "validação"
- "simples", "básico", "teste"
- Lista curta de recursos (1-3 serviços)

### → Construção custom (sem template-base) quando:
- Usuário lista recursos específicos que não casam com padrão
- Arquitetura inclui workloads que não estão nos templates (ex: Databricks, IoT Hub, SAP)
- Usuário pede comparação entre cenários

## Heurísticas de escala (defaults inteligentes)

A partir do volume informado pelo usuário, o agent escala os recursos:

| Premissa do usuário | Foundry tokens/mês | AI Search tier | Fabric tier |
|---|---|---|---|
| "PoC pra 1-5 usuários" | 5M | Basic | F2 com pause |
| "30 usuários, ~1000 queries/dia" | ~105M (75 in + 30 out) | S1 | F4 |
| "200 usuários, ~10k queries/dia" | ~1B (700 in + 300 out) | S2 | F8 |
| "1000+ usuários, escala alta" | ~5B+ | S3 ou Storage Optimized | F32+ |

## Heurísticas regionais

| Cliente em / projeto pra | Default region |
|---|---|
| Brasil | `brazilsouth` |
| EUA | `eastus` ou `eastus2` |
| Europa | `westeurope` ou `northeurope` |
| Não especificado | Pergunta ao usuário (default fallback `brazilsouth` do `.env`) |

## Output do agent (visível ao usuário)

Após processar, o agent salva em `output/prj_<cliente>/` (ou `output/cost-azure/<timestamp>/`):

1. **`cost_report.md`** — Relatório de custo principal (legível)
2. **`scenario_used.json`** — Snapshot do cenário que ele construiu internamente (auditoria + reuso futuro)

O usuário nunca precisa criar esses arquivos manualmente — o agent gera ambos.

## Quando o usuário pode querer mexer no JSON

Casos avançados (raros):

- **Comparar variantes** do mesmo cenário (ex: F2 vs F4): pegar o `scenario_used.json` gerado, copiar, editar 1 campo, re-rodar via `--file`
- **Reusar cenário** em datas diferentes para acompanhar drift de preço: re-rodar o mesmo JSON em D+30, D+60
- **CI/CD pipeline** de cost estimation: scriptar com JSON fixo

Mas isso é exceção. O fluxo padrão é conversacional.
