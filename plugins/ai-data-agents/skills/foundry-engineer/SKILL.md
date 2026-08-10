---
name: foundry-engineer
description: "Playbook operacional para o foundry-engineer: template de especificação de agentes Microsoft Foundry (Connected Agents/A2A, tools, orquestração), playbook de plataforma (catálogo/deploy de modelos, avaliações, Prompt Flow, RAG/Azure AI Search, observabilidade), checklist de governança, e quando usar context7/tavily para confirmar APIs antes de afirmar. Leia ANTES de produzir qualquer spec de agentes ou de plataforma Foundry. Análise de árvore de tasks NÃO está aqui — ver skills/task-architecture/task-architect/SKILL.md."
---

# Skill: Foundry Engineer — Playbooks Operacionais

<!-- type: concept -->
## Quando Usar Cada Playbook Abaixo

| Pedido do usuário | Playbook |
|---|---|
| "Cria uma especificação de agentes para X" / "Desenha um sistema multi-agente no Foundry" | §1 — Template de Spec de Agentes Foundry |
| "Desenha minha solução de RAG/avaliação/Prompt Flow" / "Como faço deploy de modelo no Foundry?" | §2 — Playbook de Plataforma Foundry |
| Qualquer um dos dois, sempre | §3 — Checklist de Governança + §4 — Quando Confirmar via context7/tavily |
| "Analisa minha árvore de tasks" / backlog / WBS | **Fora de escopo** — delegar para `task-architect`, ver `skills/task-architecture/task-architect/SKILL.md` |

---

<!-- type: pattern -->
## §1 — Template de Spec de Agentes Foundry

Antes de preencher, leia `kb/foundry/concepts/foundry-agent-platform.md` e
`kb/foundry/concepts/multi-agent-patterns.md` — não preencha nenhuma célula de
"SDK/pacote/modelo" sem confirmar via context7/tavily (ver §4).

```markdown
# Especificação de Agentes — Microsoft Foundry (ex-Azure AI Foundry) — <nome do sistema>

## 1. Objetivo e Escopo
- Objetivo de negócio: <o que o sistema resolve>
- Fora de escopo: <o que este sistema explicitamente NÃO faz>
- Consumidor(es): <quem interage com o sistema — usuário final, outro sistema, etc.>

## 2. Inventário de Agentes
| Agente | Papel (1 frase) | Domínio de responsabilidade | Tools |
|---|---|---|---|
| orchestrator | Recebe o pedido, decide qual(is) agente(s) acionar | Roteamento | Connected Agents registrados como tool |
| <agente-1> | ... | ... | file search / code interpreter / Bing grounding / Azure AI Search / Azure Functions / OpenAPI / MCP |

> Modelo: NÃO fixe um nome de modelo específico aqui. Escreva "a definir — consultar
> catálogo de modelos vigente no Foundry" a menos que o usuário já tenha uma escolha
> confirmada e você tenha validado que ela está disponível.

## 3. Orquestração
- Padrão escolhido: <Connected Agents (A2A) | Multi-agent Workflows | Microsoft Agent
  Framework — sequential/concurrent/handoff/group-chat/Magentic-One>
- Justificativa: <por que este padrão e não outro — usar a árvore de decisão de
  `kb/foundry/concepts/multi-agent-patterns.md` §4>
- Fluxo de handoff/delegação: <diagrama textual ou tabela de "quando A aciona B">

## 4. Status GA vs. Preview (auditado nesta sessão)
| Feature/serviço citado | Status | Fonte |
|---|---|---|
| Foundry Agent Service | GA | kb/foundry/concepts/foundry-agent-platform.md (verificar se ainda válido) |
| Connected Agents (A2A) | GA | idem |
| Microsoft Agent Framework | Public Preview | idem |
| Toolboxes | Public Preview | idem |
| Foundry Toolkit (VS Code) | GA | idem |
| <qualquer item novo citado> | ⚠️ verificar | context7/tavily — <o que foi buscado> |

## 5. Governança
- Modo: <advisory/read-only | write com aprovação humana>
- PII: <nenhuma prevista | escalado para governance-auditor em <ponto>>
- Audit trail: <onde as decisões/execuções do sistema são registradas>

## 6. Itens Marcados "⚠️ Verificar"
<lista consolidada — nada deve ficar sem esta seção se algo não foi confirmado>
```

---

<!-- type: pattern -->
## §2 — Playbook de Plataforma Foundry (Modelos, Avaliação, Prompt Flow, RAG, Observabilidade)

Leia `kb/foundry/concepts/foundry-platform-ops.md` para o conteúdo completo antes de
aplicar estes passos.

1. **Identifique o(s) estágio(s) do ciclo de 5 estágios** que o pedido cobre: explorar
   catálogo → prototipar → customizar (fine-tune/grounding) → avaliar → deploy &
   monitorar.
2. **Se envolver escolha de modelo:** nunca fixe um nome específico — escreva "a definir,
   consultar catálogo vigente" e liste os critérios de escolha (custo, latência,
   capacidade) em vez do nome do modelo.
3. **Se envolver RAG:** declare explicitamente o tipo de retrieval — vetorial, keyword,
   híbrido, ou agentic — e os conectores de ingestão (SharePoint/Blob/Cosmos/outro).
   "RAG" sozinho nunca é suficiente para uma spec de produção.
4. **Se envolver Prompt Flow:** desenhe o pipeline como um DAG de nós explícito (prompts,
   chamadas de modelo, código, lógica condicional) — não descreva apenas em prosa.
5. **Se envolver avaliação:** especifique as métricas de qualidade (groundedness,
   relevance, completeness — escala 1-5) e as métricas de safety a rodar, e o threshold
   mínimo de aprovação para cada uma antes de promover a produção.
6. **Se envolver deploy:** confirme que um plano de avaliação (passo 5) já foi definido
   ANTES de recomendar deploy — nunca recomende "pronto para produção" sem isso.
7. **Se envolver observabilidade:** recomende habilitar tracing desde a prototipagem, não
   apenas em produção.
8. **Confirme via context7/tavily** qualquer nome de SDK/API/endpoint citado (ver §4).
9. **Produza o documento** seguindo o Formato de Resposta do agente (ver
   `data_agents/agents/registry/foundry-engineer.md` §Formato de Resposta).

### Exemplo de Tabela de Plano de Avaliação

| Dimensão | Métrica | Escala | Threshold de aprovação |
|---|---|---|---|
| Qualidade | Groundedness | 1-5 | ≥ 4 |
| Qualidade | Relevance | 1-5 | ≥ 4 |
| Qualidade | Completeness | 1-5 | ≥ 3 |
| Segurança | Safety (⚠️ verificar métricas exatas) | — | Sem violações críticas |

---

<!-- type: constraint -->
## §3 — Checklist de Governança (rodar sempre, nas duas frentes)

- [ ] Nenhum dado pessoal real (nome de cliente, CPF, e-mail, etc.) foi incluído
  literalmente no relatório/spec sem passar por `governance-auditor` primeiro.
- [ ] O sistema/solução proposta opera em modo advisory/read-only por padrão — qualquer
  escrita automática em sistema externo (Jira, ADO, Databricks, Fabric) exige aprovação
  humana explícita antes de ser especificada como automática.
- [ ] Existe audit trail declarado — onde decisões/sugestões ficam registradas para
  revisão posterior.
- [ ] Nenhuma solução foi recomendada como "pronta para produção" sem um plano de
  avaliação (qualidade + safety) explícito.
- [ ] O documento final foi salvo em `output/specs/` ou `output/architecture/` (nunca
  apenas comunicado no chat), quando o pedido exigia um artefato reutilizável.

---

<!-- type: constraint -->
## §4 — Quando Confirmar via context7/tavily (obrigatório, não opcional)

Use **context7** quando:
- A pergunta envolve uma biblioteca/SDK que pode estar indexada (ex.: confirmar
  assinatura de uma API de um SDK conhecido).

Use **tavily** quando:
- A pergunta envolve um fato de produto/plataforma que muda com o tempo (status GA vs.
  preview, nome de produto, lista de modelos disponíveis, features novas do Foundry) —
  isto é o caso mais comum para este agente, dado o ritmo de mudança do Microsoft Foundry.

**Gatilhos que exigem confirmação antes de escrever a afirmação na spec:**
- Qualquer nome de pacote pip / módulo npm / classe / método de SDK.
- Qualquer nome de modelo concreto (GPT-*, o1-*, DeepSeek-*, etc.) apresentado como
  "recomendado" ou "disponível".
- Qualquer alegação de status GA vs. Public Preview de uma feature.
- Qualquer nome de SDK/API de avaliação, Prompt Flow, ou Azure AI Search.
- Qualquer alegação de preço/SKU (nesse caso, prefira escalar para
  `azure-cost-calculator` em vez de responder você mesmo).

**Se a busca não confirmar o fato:** escreva **"⚠️ verificar"** no documento, no lugar da
afirmação categórica, e explique o que especificamente precisa ser checado por um humano
antes de ir para produção.
