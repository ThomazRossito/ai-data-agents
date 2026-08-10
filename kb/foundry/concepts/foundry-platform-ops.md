# Microsoft Foundry — Plataforma (Model Ops, Avaliação, Prompt Flow, RAG, Observabilidade)

> **Snapshot verificado, ago/2026.** Complementa `concepts/foundry-agent-platform.md`
> (camada de agentes) e `concepts/multi-agent-patterns.md` (padrões de orquestração). Este
> arquivo cobre a **plataforma Foundry além dos agentes**: catálogo/deploy de modelos,
> fine-tuning/grounding, avaliações, Prompt Flow, RAG com Azure AI Search, e
> observabilidade GenAI.
>
> ⚠️ **Domínio de alta volatilidade — mesma regra de ouro do restante da KB `kb/foundry/`.**
> Nomes exatos de pacote pip/classe/método do SDK, endpoints de API REST, e qualquer
> parâmetro concreto de avaliação/Prompt Flow **NÃO estão confirmados neste arquivo** a
> menos que explicitamente marcado — sempre re-confirme via `context7` ou `tavily` antes de
> usar em uma spec formal ou decisão de arquitetura.

---

## 1. Ciclo de Vida da Plataforma — 5 Estágios

O Microsoft Foundry organiza o trabalho de construir uma solução de IA generativa em cinco
estágios sequenciais (iterativos — não é um funil estritamente linear, é comum voltar a um
estágio anterior):

1. **Explorar catálogo** — navegar o catálogo de modelos disponíveis (multi-provedor — ver
   `concepts/foundry-agent-platform.md` §1) e escolher um ponto de partida.
2. **Prototipar** — experimentar prompts, RAG, ou um agente com o(s) modelo(s)
   escolhido(s), iterando rapidamente sobre o design da solução.
3. **Customizar** — fine-tuning e/ou grounding do modelo/solução com dados próprios quando
   o comportamento genérico do modelo base não é suficiente.
4. **Avaliar** — medir qualidade (groundedness, relevance, completeness) e segurança
   (safety) da solução antes de promover para produção (ver §3).
5. **Deploy & monitorar** — publicar a solução e observar seu comportamento em produção via
   tracing/observabilidade GenAI (ver §5).

**Nunca pule o estágio de avaliação (4) antes de deploy (5)** — é o mesmo princípio de
"documento-always + aprovação antes de ação irreversível" já usado neste projeto para
migrações e infraestrutura nova.

---

## 2. Catálogo e Deploy de Modelos

O Foundry expõe um **catálogo de modelos multi-provedor** (não exclusivo a um fornecedor —
ver `concepts/foundry-agent-platform.md` §1 para os provedores já confirmados) com fluxo de
deploy gerenciado pela plataforma.

- **Nunca fixe um modelo específico como "o" modelo correto para uma solução** — a lista de
  modelos disponíveis no catálogo muda; oriente sempre a verificar o catálogo vigente antes
  de especificar um modelo numa spec de produção (mesma regra já aplicada em
  `concepts/foundry-agent-platform.md`).
- ⚠️ **Verificar:** fluxo exato de deploy (self-service vs. approval gate), SKUs de
  hospedagem de modelo, e nomes exatos de qualquer API/SDK de deploy — não confirmados
  neste snapshot.

---

## 3. Fine-Tuning e Grounding

Customização de um modelo/solução com dados próprios, usada quando o comportamento
genérico do modelo base do catálogo não atende ao caso de uso:

- **Fine-tuning** — ajuste dos pesos/comportamento do modelo com dataset próprio.
- **Grounding** — ancorar as respostas do modelo em dados/documentos próprios (fonte de
  verdade externa ao modelo), reduzindo alucinação sem necessariamente treinar pesos novos.
  RAG (§4) é a técnica mais comum de grounding, mas não é a única.

⚠️ **Verificar:** formatos de dataset aceitos para fine-tuning, limites/quotas, e se o
fine-tuning é oferecido para todos os modelos do catálogo ou um subconjunto — não
confirmados neste snapshot.

---

## 4. Avaliações (Evaluations)

O Foundry oferece avaliação estruturada de qualidade e segurança para soluções de IA
generativa (prompts, RAG, agentes) antes de promoção a produção:

- **Métricas de qualidade** — groundedness (a resposta é sustentada pelos dados/contexto
  fornecidos?), relevance (a resposta responde à pergunta?), completeness (a resposta cobre
  tudo que foi perguntado?). Cada métrica é pontuada em **escala 1–5**.
- **Métricas de safety** — avaliação de segurança da resposta (conteúdo nocivo, jailbreak,
  etc.) complementar às métricas de qualidade.
- **Nunca declare uma solução "pronta para produção" sem rodar avaliação de qualidade E
  segurança** — mesmo princípio de auditoria de si mesmo já aplicado neste agente (Regra de
  Ouro) e de validação de sugestões no `task-architect` (nunca aplicar mudança sem
  validação explícita).

⚠️ **Verificar:** nome exato do serviço/SDK de avaliação, se as avaliações rodam via
Foundry portal, SDK Python, ou ambos, e se há métricas adicionais além das três de
qualidade citadas — não confirmados neste snapshot.

---

## 5. Prompt Flow

**Prompt Flow** é a camada de orquestração de pipelines de LLM do Foundry — permite
compor um pipeline (prompts, chamadas de modelo, código Python, lógica condicional) como um
**DAG de nós**, com suporte tanto a **design visual** quanto a **código**.

- **Versionamento** — um flow é um artefato versionável, como qualquer outro código.
- **Avaliação** — um Prompt Flow pode ser conectado diretamente às avaliações do §4 para
  medir a qualidade do pipeline como um todo, não apenas de uma chamada isolada de modelo.
- **Deploy** — um Prompt Flow validado pode ser publicado como endpoint.

**Quando considerar Prompt Flow:** a solução precisa de mais do que uma única chamada de
modelo — múltiplos passos (retrieval → prompt → pós-processamento → validação), lógica
condicional entre nós, ou necessidade de visualizar/auditar o pipeline como um grafo
explícito.

⚠️ **Verificar:** nome exato do formato de arquivo do flow, se o "código" é Python puro ou
um DSL próprio, e o mecanismo exato de versionamento (Git nativo vs. registro proprietário
do Foundry) — não confirmados neste snapshot.

---

## 6. RAG com Azure AI Search

A técnica de grounding mais comum no Foundry combina retrieval sobre um índice do
**Azure AI Search** com geração via modelo do catálogo:

- **Retrieval vetorial + keyword (híbrido)** — Azure AI Search suporta busca vetorial
  (embeddings), busca por palavra-chave tradicional, e a combinação híbrida das duas no
  mesmo índice.
- **Conectores de ingestão** — SharePoint, Blob Storage, Cosmos DB (entre outras fontes)
  podem alimentar o índice do Azure AI Search sem pipeline de ingestão customizado para
  cada uma.
- **Agentic retrieval** — um padrão em que o próprio agente decide dinamicamente *quando* e
  *o quê* buscar no índice (em vez de um passo de retrieval fixo antes de toda chamada ao
  modelo) — mais controle sobre custo/latência vs. RAG ingênuo "sempre buscar".

**Ao especificar RAG numa spec Foundry:** declare explicitamente se o retrieval é vetorial,
keyword, híbrido, ou agentic — "RAG" sozinho é ambíguo demais para uma spec de produção.

⚠️ **Verificar:** nomes exatos dos SDKs de indexação/query do Azure AI Search, limites de
tamanho de índice/chunk, e detalhes de configuração de cada conector de ingestão citado —
não confirmados neste snapshot. Custo de Azure AI Search (SKU, unidades de busca) está fora
do escopo deste agente — escalar para `azure-cost-calculator`.

---

## 7. Observabilidade GenAI (Tracing)

O Foundry oferece observabilidade dedicada a soluções de IA generativa — **tracing** de
chamadas de modelo, passos de um Prompt Flow, ou execuções de agente, para diagnóstico e
auditoria em produção.

- **Por que é diferente de observabilidade tradicional de app** — uma chamada de LLM tem
  dimensões próprias a rastrear (prompt exato enviado, tokens consumidos, latência por
  passo de um pipeline multi-etapa, qual tool/agente foi invocado em cada handoff) que
  APM genérico não captura nativamente.
- **Uso recomendado:** habilitar tracing desde o estágio de prototipagem (§1, estágio 2) —
  não apenas em produção — para diagnosticar comportamento inesperado do modelo/pipeline
  antes do deploy.

⚠️ **Verificar:** nome exato do serviço/SDK de tracing, se há integração nativa com
OpenTelemetry, e retenção/custo de logs de tracing — não confirmados neste snapshot.

---

## 8. O Que Precisa Ser Verificado (consolidado)

Ver também `concepts/foundry-agent-platform.md` §6 (itens da camada de agentes). Itens
específicos de plataforma/ops não confirmados neste snapshot:

- Fluxo exato de deploy de modelo (self-service vs. approval gate) e SKUs de hospedagem.
- Formatos de dataset e limites/quotas de fine-tuning.
- Nome exato do serviço/SDK de avaliação e onde ele roda (portal vs. SDK vs. ambos).
- Formato de arquivo e mecanismo de versionamento do Prompt Flow.
- Nomes exatos de SDK/API de indexação e query do Azure AI Search, e detalhes de
  configuração de cada conector de ingestão (SharePoint/Blob/Cosmos).
- Nome exato do serviço/SDK de tracing e integração (ou não) com OpenTelemetry.
- Qualquer preço/SKU (Azure AI Search, avaliação, tracing) — sempre escalar para
  `azure-cost-calculator`, nunca citar de memória.
