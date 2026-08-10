# Microsoft Foundry (ex-Azure AI Foundry) — Plataforma de Agentes

> **Snapshot verificado via busca web, ago/2026.** Este produto foi **renomeado**: o nome
> atual é **Microsoft Foundry**; o nome anterior era "Azure AI Foundry". Refira-se ao
> produto sempre como **"Microsoft Foundry (ex-Azure AI Foundry)"** na primeira menção de
> um documento, para evitar confusão com material antigo que ainda usa o nome antigo.
>
> ⚠️ **Este é um domínio de alta volatilidade.** Trate cada afirmação de status (GA vs.
> Public Preview) como válida em ago/2026 — **sempre re-confirme via `context7` ou
> `tavily`** antes de usar qualquer um destes fatos numa spec formal ou decisão de
> arquitetura. Nomes exatos de pacote pip/classe/método do SDK Python **NÃO estão
> confirmados neste arquivo** — ver seção "O Que Precisa Ser Verificado" abaixo.

---

## 1. Foundry Agent Service — Visão Geral

**Status: GA.**

O Foundry Agent Service é o serviço de hospedagem e execução de agentes do Microsoft
Foundry. Pontos-chave verificados:

- **Construído sobre a OpenAI Responses API** — a interface de execução de agentes segue
  o mesmo contrato da Responses API da OpenAI.
- **Wire-compatible com agentes OpenAI** — agentes construídos para o padrão de agentes
  da OpenAI podem rodar no Foundry Agent Service sem reescrita do protocolo de
  comunicação.
- **Hosted agents: GA desde julho/2026.** Cada sessão de um hosted agent roda em um
  **sandbox isolado por VM** (isolamento forte por sessão — não é apenas isolamento de
  processo/container).
- **Modelos servidos:** não é exclusivo a modelos OpenAI — o serviço também serve
  modelos de outros provedores (ex.: DeepSeek, xAI, Meta, entre outros disponíveis no
  catálogo do Foundry). **Não fixe um modelo específico como "o" modelo correto** — a
  lista de modelos disponíveis muda; oriente sempre a verificar o catálogo atual do
  Foundry antes de especificar um modelo numa spec de produção.

---

## 2. Multi-Agente — Três Camadas Distintas

O Foundry oferece três formas de compor múltiplos agentes, com maturidade e propósito
diferentes. Não são intercambiáveis — escolher a errada gera complexidade desnecessária.

### 2.1 Connected Agents (A2A)

Um agente é **registrado como "tool" de outro agente**. O agente orquestrador delega
tarefas aos agentes conectados **via linguagem natural** — não há necessidade de escrever
lógica de roteamento customizada (sem "if intent == X then call agent Y" hard-coded).

- Baseado no padrão aberto **A2A (Agent2Agent)**.
- Melhor para: composição simples de especialistas onde o orquestrador só precisa decidir
  "qual agente chamar" com base na tarefa, sem estado complexo entre chamadas.

### 2.2 Multi-Agent Workflows

Uma **camada stateful** acima dos agentes individuais, oferecendo:
- Gerenciamento de contexto entre etapas.
- Retries automáticos.
- **Compensation** (rollback/compensação lógica quando uma etapa falha após outras já
  terem sido executadas).
- Suporte a **long-running steps** (etapas que podem levar minutos/horas).

Melhor para: processos de negócio multi-etapa com necessidade de recuperação de falha e
persistência de estado — não apenas roteamento simples.

### 2.3 Microsoft Agent Framework (Public Preview)

**Status: Public Preview** (não GA — trate como instável/sujeito a mudança de API).

SDK/runtime **open-source** que **unifica AutoGen e Semantic Kernel** numa única
superfície de orquestração multi-agente. Este é, segundo as fontes verificadas de
ago/2026, **o caminho atual recomendado** para quem precisa de orquestração multi-agente
com mais controle programático do que o Connected Agents oferece (ver
`concepts/multi-agent-patterns.md` para os padrões de orquestração disponíveis dentro
dele, incluindo Magentic-One).

---

## 3. Tools Built-in do Agent Service

Ferramentas nativas disponíveis para um agente hospedado no Foundry Agent Service:

| Tool | Descrição |
|---|---|
| File search / retrieval | Busca semântica sobre arquivos anexados ao agente |
| Code interpreter | Execução de código em sandbox para análise/transformação de dados |
| Bing grounding | Busca web em tempo real via Bing, com citações |
| Azure AI Search | Integração com índices de busca vetorial/híbrida gerenciados no Azure |
| Azure Functions | Invocação de funções serverless customizadas como tool |
| OpenAPI | Qualquer API descrita via especificação OpenAPI vira tool automaticamente |
| **MCP** | Model Context Protocol — mesmo padrão aberto usado neste projeto para os
próprios MCP servers (`data_agents/mcp_servers/`); um agente Foundry pode consumir
qualquer MCP server compatível |

### Toolboxes (Public Preview)

**Status: Public Preview.** Um **endpoint único gerenciado** que agrega múltiplas
tools/skills/MCP servers atrás de uma única superfície de conexão — reduz a necessidade
de o agente gerenciar múltiplas credenciais/endpoints de tool individualmente.

---

## 4. Padrões Abertos Nativos

O Foundry adota dois padrões abertos como cidadãos de primeira classe, não como add-ons:

- **A2A (Agent2Agent)** — protocolo de comunicação agente-para-agente, base do Connected
  Agents (§2.1).
- **MCP (Model Context Protocol)** — mesmo protocolo usado neste projeto
  (`data_agents/mcp_servers/`) para conectar agentes a ferramentas/dados externos.

Isso significa que uma especificação de agentes Foundry pode, em princípio, interoperar
com agentes/tools construídos fora do ecossistema Microsoft, desde que falem A2A ou MCP —
mas **confirme via context7/tavily** o nível de compatibilidade real antes de prometer
isso numa spec formal, pois detalhes de implementação evoluem rápido.

---

## 5. Ferramental de Desenvolvimento

- **Foundry Toolkit para VS Code** — **Status: GA.** Extensão oficial para desenvolver,
  testar e depurar agentes Foundry diretamente no VS Code.

---

## 6. O Que Precisa Ser Verificado (NUNCA afirmar sem checar)

Os seguintes pontos **NÃO** têm fonte confirmada suficiente para serem tratados como fato
em uma spec formal — sempre resolver via `context7` (se houver biblioteca indexada) ou
`tavily` (busca web) antes de escrever:

- **Nome exato do pacote pip / módulo Python do SDK** (ex.: candidatos possíveis como
  `azure-ai-projects` ou `azure-ai-agents` circulam, mas **não foram confirmados** — não
  afirme qual é o correto sem verificar a documentação oficial atual).
- **Nomes exatos de classes/métodos** do SDK Python (ex.: como se cria um Connected
  Agent programaticamente, qual classe representa um "AgentClient", etc.).
- **Lista definitiva e atual de modelos disponíveis** no Foundry (OpenAI e não-OpenAI) —
  muda com frequência; nunca fixar "GPT-4o" ou "o1-mini" como resposta correta em uma
  spec — oriente a consultar o catálogo de modelos vigente.
- **Preços/SKUs de hosted agents e sandboxes VM-isolados** — fora do escopo deste agente;
  se necessário, escalar para `azure-cost-calculator`, que também deve verificar preços
  via API de pricing ao invés de citar de memória.
- **Qualquer roadmap ou data futura de GA** para features hoje em Public Preview
  (Microsoft Agent Framework, Toolboxes) — não prometa datas não confirmadas.
