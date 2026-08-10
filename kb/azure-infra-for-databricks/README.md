# KB — azure-infra-for-databricks

Knowledge Base que dá o **sizing de referência da camada de infraestrutura Azure**
que hospeda um deploy Databricks greenfield (vNet, NAT, Private Endpoints, Log
Analytics, Key Vault, Firewall, Defender, Bastion).

## Por que existe

Num greenfield, essa camada representa **35-45% do custo total** e não é
"Databricks" — logo ficava fora da estimativa dos agents de cost. Sem ela, o
número saía ~4× menor que o real. Este KB torna a camada visível e dá defaults
enterprise auditáveis.

## Quem consome

- `azure-cost-calculator` (via `kb_domains: [azure-pricing, azure-infra-for-databricks]`)
- `databricks-cost-calculator` (indiretamente, ao escalar greenfield → WF-07)

O loader injeta o `index.md` no system prompt do agent automaticamente quando o
domínio está no `kb_domains` do frontmatter.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `index.md` | Stack de referência por ambiente + regra de ativação + sanity-check + otimizações |
| `patterns/retail-api-queries.md` | Queries `$filter` exatas por serviço na Azure Retail Prices API + snapshot SEA |
| `concepts/pricing-sources.md` | URLs oficiais Microsoft + justificativa técnica de cada Private Endpoint |
| `README.md` | Este arquivo |

## Sanity-check embutido

Se a estimativa de Azure Infra vier **abaixo de ~$3.000/mo para 4 ambientes
enterprise**, provavelmente falta: Firewall, Defender, log ingest realista
(≥100 GB/env) ou PEPs suficientes (≥6/env). O agent deve revisar antes de entregar.

## Manutenção

Os preços no snapshot (`patterns/retail-api-queries.md`) têm data (2026-07).
Re-verificar contra a Retail API antes de qualquer commit comercial. O modo
preferencial é consumir a API em runtime via MCP `azure_pricing`, não hardcode.
