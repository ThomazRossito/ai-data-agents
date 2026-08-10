---
domain: foundry
updated_at: 2026-08-09
agents: [foundry-engineer]
mcp_validated: "not-applicable — context7/tavily are live-lookup MCPs, not a fixed dataset"
---

# KB: Microsoft Foundry — Índice

**Domínio:** Microsoft Foundry (ex-Azure AI Foundry) **completo** — plataforma de agentes
(Foundry Agent Service, Connected Agents/A2A, Multi-agent workflows, Microsoft Agent
Framework, Magentic-One, Toolboxes) **e** plataforma de IA generativa (catálogo/deploy de
modelos, fine-tuning/grounding, avaliações, Prompt Flow, RAG com Azure AI Search,
observabilidade GenAI).
**Agentes:** foundry-engineer

> **Nota histórica:** este domínio se chamava `agent-architecture` e o agente
> `agent-architect`. Em 2026-08-09 foi reestruturado: a parte de análise/otimização de
> árvores de tasks (que é agnóstica de plataforma) foi extraída para o domínio
> `kb/task-architecture/` e o agente `task-architect`. Este domínio (`kb/foundry/`) e o
> agente `foundry-engineer` cobrem exclusivamente o Microsoft Foundry.

---

## Conteúdo Disponível

### Conceitos (`concepts/`)

| Arquivo | Conteúdo |
|---|---|
| `concepts/foundry-agent-platform.md` | Microsoft Foundry (ex-Azure AI Foundry): Foundry Agent Service, hosted agents, tools built-in, Toolboxes, dev tooling — snapshot verificado ago/2026, com status GA/preview explícito |
| `concepts/multi-agent-patterns.md` | Connected Agents (A2A), Multi-agent workflows, Microsoft Agent Framework (AutoGen + Semantic Kernel), Semantic Kernel "Azure AI Agent", padrão Magentic-One e demais padrões de orquestração |
| `concepts/foundry-platform-ops.md` | Plataforma além dos agentes: ciclo de 5 estágios (explorar → prototipar → customizar → avaliar → deploy/monitorar), catálogo/deploy de modelos, fine-tuning/grounding, avaliações (groundedness/relevance/completeness + safety), Prompt Flow, RAG com Azure AI Search, observabilidade GenAI |

> Análise/otimização de árvore de tasks parent/child **não vive mais aqui** — ver
> `kb/task-architecture/index.md` e o agente `task-architect`.

---

## Regra de Negócio Crítica — Fundamentação Obrigatória

Este é o domínio de KB **mais volátil** do projeto: Microsoft Foundry é um produto
recém-renomeado (era "Azure AI Foundry") em evolução ativa — GA/preview shifts, pacotes
novos e renomeações são esperados. **Nenhum conteúdo abaixo deve ser tratado como
permanentemente verdadeiro.** Toda vez que uma resposta depender de precisão factual
sobre nome de SDK/pacote/classe/método/modelo concreto, o agente **DEVE** confirmar via
`context7` (docs de biblioteca) ou `tavily` (busca web) antes de afirmar — e marcar
**"⚠️ verificar"** explicitamente quando não conseguir confirmar. Isso vale mesmo para
conteúdo marcado "GA" nestes arquivos: GA de agosto/2026 pode não ser GA quando a
pergunta for feita.

### O que NUNCA deve ser reaproveitado sem re-auditoria
Qualquer nome de pacote pip, classe Python, método de SDK, endpoint de API REST, ou
modelo concreto (ex.: "use `azure-ai-projects`", "use GPT-4o") citado em uma spec anterior
gerada por este ou outro agente — sempre re-confirmar antes de repetir.

---

## Regras de Negócio — Plataforma Foundry

- Toda afirmação de status GA vs. Public Preview é reconfirmada antes de entrar numa spec
  formal — nunca copiada de memória, mesmo que já esteja marcada "GA" nesta KB.
- Nenhum modelo específico do catálogo é fixado como "a" escolha correta numa spec —
  sempre "a definir, consultar catálogo vigente".
- Nenhuma solução (prompt, RAG, agente) é declarada "pronta para produção" sem avaliação
  de qualidade (groundedness/relevance/completeness) E segurança (safety) — ver
  `concepts/foundry-platform-ops.md` §4.
- RAG é sempre especificado com o tipo de retrieval explícito (vetorial/keyword/híbrido/
  agentic) — "RAG" sozinho é ambíguo demais para uma spec de produção.
- Preço/SKU de qualquer serviço Foundry (Azure AI Search, hospedagem de modelo, avaliação)
  nunca é citado de memória — escalar para `azure-cost-calculator`.
- PII em exemplos de spec (dados de prompt, documentos de grounding/RAG) é escalada para
  `governance-auditor` antes de incluir no documento.
