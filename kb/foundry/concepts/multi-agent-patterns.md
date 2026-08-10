# Padrões de Orquestração Multi-Agente

> Snapshot verificado via busca web, ago/2026. Complementa
> `concepts/foundry-agent-platform.md` §2 — leia aquele arquivo primeiro para o contexto
> das três camadas multi-agente do Foundry (Connected Agents/A2A, Multi-agent Workflows,
> Microsoft Agent Framework). Este arquivo aprofunda os **padrões de orquestração** em si,
> aplicáveis dentro dessas camadas.

---

## 1. Connected Agents (A2A) — Roteamento Declarativo

Já introduzido em `foundry-agent-platform.md` §2.1. O ponto central para design: quando um
agente é registrado como Connected Agent de outro, **o orquestrador não precisa de lógica
de roteamento hard-coded** — ele decide qual agente-tool invocar interpretando a
linguagem natural da tarefa, do mesmo jeito que decidiria qual tool de código chamar.

**Quando usar:** composição rasa (1 nível de delegação), poucos agentes conectados, sem
necessidade de estado compartilhado complexo entre chamadas.

**Quando NÃO usar:** processos com múltiplas etapas sequenciais dependentes, necessidade
de retry/compensation, ou > 1 nível de handoff — nesses casos, considere Multi-agent
Workflows ou Microsoft Agent Framework.

---

## 2. Semantic Kernel — "Azure AI Agent"

**Semantic Kernel (SK)** é o SDK de orquestração de agentes da Microsoft anterior ao
Microsoft Agent Framework (que o unifica com AutoGen — ver §3). Pontos relevantes para
design de sistemas multi-agente:

- **"Azure AI Agent" é um *agent type* dentro do SK** — ou seja, ao construir um agente
  no SK, "Azure AI Agent" é uma das implementações possíveis (ligada ao Foundry Agent
  Service), ao lado de outros agent types do próprio SK.
- **Plugins** em SK podem ser: **código nativo** (funções Python/C#/Java decoradas),
  **OpenAPI** (qualquer API descrita via spec OpenAPI vira plugin automaticamente), ou
  **MCP** (mesmo padrão usado neste projeto).
- **Function calling automático** — o SK decide automaticamente qual plugin/função
  invocar com base na instrução do usuário e nas descrições das funções disponíveis
  (mesmo princípio de tool-use nativo dos modelos, mas com a camada de orquestração do
  SK por cima).

---

## 3. Microsoft Agent Framework (Public Preview)

Já introduzido em `foundry-agent-platform.md` §2.3. Pontos de design relevantes:

- **Unifica AutoGen + Semantic Kernel** num único SDK/runtime — quem já tinha
  investimento em qualquer um dos dois tem caminho de migração/convergência, em vez de
  escolher entre frameworks concorrentes.
- **Open-source.**
- **Status: Public Preview** — não é GA. Trate qualquer API específica deste framework
  como sujeita a mudança; **sempre confirme via context7/tavily** antes de especificar
  código concreto numa spec de produção.
- É, segundo as fontes verificadas, **o caminho atual recomendado** para orquestração
  multi-agente com mais controle programático do que Connected Agents oferece.

### 3.1 Padrão Magentic-One (Stable)

**Status: Stable** (dentro do ecossistema AutoGen/Agent Framework — não confundir com o
status GA/Preview do framework como um todo, que é Public Preview).

Magentic-One é um padrão de orquestração **generalista** onde um agente orquestrador
central ("Orchestrator") coordena um time de agentes especialistas para resolver tarefas
abertas e complexas, mantendo um **ledger de progresso** (rastreamento do que já foi
tentado, o que funcionou, o que não funcionou) para decidir o próximo passo — em vez de
um fluxo fixo predefinido.

**Quando usar:** tarefas abertas/exploratórias onde a sequência de agentes não pode ser
totalmente predefinida (ex.: pesquisa multi-etapa, resolução de problemas com
tentativa-e-erro).

### 3.2 Outros Padrões de Orquestração

Além de Magentic-One, os padrões usuais de orquestração multi-agente aplicam-se dentro do
Microsoft Agent Framework (e são padrões gerais da indústria, não exclusivos da
Microsoft):

| Padrão | Descrição | Quando usar |
|---|---|---|
| **Sequential** | Agente A → Agente B → Agente C, cada um recebe o output do anterior | Pipeline linear com dependência estrita de output (ex.: DDL → validação → reconciliação) |
| **Concurrent** | Múltiplos agentes trabalham em paralelo sobre a mesma entrada, resultados agregados no fim | Perspectivas independentes sobre a mesma pergunta (ex.: `/party` deste projeto) |
| **Handoff** | Um agente transfere o controle completo da conversa para outro quando reconhece que está fora do seu escopo | Escalação (mesmo princípio do `escalation_rules` deste projeto) |
| **Group Chat** | Múltiplos agentes participam de uma conversa compartilhada, com um moderador decidindo quem fala a seguir | Deliberação/revisão colaborativa entre especialistas com pontos de vista distintos |

Este projeto (`ai-data-agents`) já implementa versões análogas destes padrões de forma
declarativa: Sequential ≈ DOMA com dependência de artefato (Step 0.9 do Supervisor);
Concurrent ≈ `/party`; Handoff ≈ `escalation_rules` + Step 3.5 do Supervisor. Ao desenhar
uma spec de agentes Foundry, é válido citar esse paralelo para o usuário como referência
de familiaridade — mas não assuma que a implementação subjacente é idêntica sem verificar.

---

## 4. Multi-Agent Workflows — Quando Preferir sobre Connected Agents

Ver `foundry-agent-platform.md` §2.2 para a definição. Regra de decisão simples ao
escolher entre as três camadas:

1. **Só preciso que um agente chame outro por linguagem natural, sem estado complexo?**
   → Connected Agents (A2A).
2. **Preciso de um processo multi-etapa com estado, retries e possível long-running
   step?** → Multi-agent Workflows.
3. **Preciso de controle programático fino sobre a orquestração (padrões
   sequential/concurrent/handoff/group-chat/Magentic-One), possivelmente unificando
   investimento prévio em AutoGen ou Semantic Kernel?** → Microsoft Agent Framework
   (lembrando: Public Preview).

Nunca escolha a opção mais complexa "por precaução" — como no Supervisor deste projeto
(Step 0, "Minimum agents principle"), prefira a camada mais simples que resolve o
problema real.
