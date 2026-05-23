# AI Data Agents — Gaps e Melhorias Identificados

> Documento gerado a partir de análise arquitetural aprofundada da sessão de 17/04/2026.
> Cada item foi identificado via inspeção direta do código-fonte do projeto.
>
> **Status (08/05/2026):** G1, G2 e G3 foram resolvidos ou verificados como já implementados.
> G4 e G5 permanecem como melhorias opcionais.

---

## Sumário de Prioridades

| ID | Título | Prioridade | Impacto | Esforço |
|----|--------|------------|---------|---------|
| G1 | Prompt Caching — premissa errada sobre Anthropic vs. OpenAI | ✅ Resolvido | Claude Code CLI gerencia cache_control automaticamente; arquitetura corrigida | — |
| G2 | `cache_prefix.md` abaixo do threshold mínimo de tokens | ✅ Resolvido | Expandido para 1197 tokens (>1024 mínimo Anthropic) | — |
| G3 | Sem sumarização ou truncamento do histórico de mensagens | ✅ Resolvido | `context_budget_hook.py` dispara `summarize_session` ao atingir 80% | — |
| G4 | Comandos slash customizados para Claude Code CLI | 🟡 P2 — Importante | Risco de erro humano em workflows de múltiplos passos | Baixo |
| G5 | Claude Code autônomo no pipeline de CI/CD | 🟡 P2 — Importante | Revisão de convenções arquiteturais não coberta por linters | Médio |

---

## G1 — Prompt Caching: premissa errada (Anthropic ≠ OpenAI)

### O que está errado

O comentário no `agents/supervisor.py` (linha 80-82) afirma:

> *"Os primeiros ~800 tokens de todos os agentes são byte-idênticos → o Claude API cacheia esse bloco uma única vez"*

Isso descreve o comportamento da **OpenAI**, não da **Anthropic**. A API do Claude **não possui cache implícito**. Sem o bloco `cache_control: {"type": "ephemeral"}` explícito no payload, cada chamada reprocessa e cobra o valor integral de todos os tokens de input — incluindo o `cache_prefix.md`, o system prompt do Supervisor e as 12 definições de sub-agentes.

O projeto acredita estar economizando 40-60% e não está economizando nada.

### Arquivos afetados

- `agents/supervisor.py` — comentário e `inject_cache_prefix=True`
- `agents/loader.py` — função `_load_cache_prefix()` e `load_agent()`
- `agents/cache_prefix.md` — o conteúdo em si (ver G2)

### Regras da Anthropic que se aplicam

| Regra | Valor |
|-------|-------|
| Ativação | Obrigatório `cache_control: {"type": "ephemeral"}` explícito |
| Máximo de breakpoints | 4 por requisição |
| Threshold mínimo (Sonnet/Haiku) | 1.024 tokens |
| Threshold mínimo (Opus) | 2.048 tokens |
| Custo de escrita no cache | 1.25× o preço base |
| Custo de leitura do cache | 0.10× o preço base (90% de desconto) |

### Onde aplicar `cache_control` (2 breakpoints prioritários)

**Breakpoint 1 — Final do system prompt do Supervisor:**
Cachearia: `cache_prefix.md` + protocolo DOMA completo + lista de agentes disponíveis + regras da Constituição. Estimativa: >2.048 tokens no total — atinge o threshold do Opus.

**Breakpoint 2 — Final da lista de tools/sub-agentes:**
12 sub-agentes com schemas completos de ferramentas geram volume significativo de tokens. Cachear esse bloco elimina reprocessamento a cada chamada do Supervisor.

### Bloqueio técnico

O `ClaudeAgentOptions` do SDK aceita `system_prompt` como string. Não está claro se o SDK expõe `cache_control` a nível de conteúdo. **Investigar o código-fonte do SDK antes de implementar** — pode ser necessário usar o `anthropic` Python SDK diretamente para montar os blocos de conteúdo com `cache_control`.

### Prioridade: 🔴 P0

O projeto está pagando preço cheio achando que está em desconto. Em sessões com `/party` ou workflows encadeados (4-8 chamadas ao Supervisor), o impacto de custo é imediato e mensurável.

---

## G2 — `cache_prefix.md` abaixo do threshold mínimo

### O que está errado

O `agents/cache_prefix.md` tem aproximadamente **800 tokens**. O threshold mínimo da Anthropic para ativar o cache é de **1.024 tokens** (Sonnet/Haiku) e **2.048 tokens** (Opus). Mesmo que o G1 fosse corrigido com `cache_control` explícito, o bloco do `cache_prefix.md` isolado **nunca ativaria o cache**.

O cache só é efetivo quando o bloco marcado supera o threshold. A solução não é "só adicionar `cache_control`" — é garantir que o bloco marcado seja suficientemente grande.

### Solução

O breakpoint de cache deve ser posicionado **depois** do `cache_prefix.md` + system prompt específico do Supervisor, não no meio. O bloco acumulado (prefixo + DOMA + regras) quase certamente supera 2.048 tokens e ativará o cache no Opus. O `cache_prefix.md` isolado com 800 tokens nunca ativará.

### Prioridade: 🔴 P0

Dependente do G1 — mas deve ser resolvido junto, não depois.

---

## G3 — Sem sumarização ou truncamento do histórico de mensagens

### O que está errado

O projeto possui três mecanismos relacionados a contexto, mas nenhum ataca o problema central:

| Mecanismo | O que faz | O que NÃO faz |
|-----------|-----------|---------------|
| `output_compressor_hook.py` | Comprime output de *tools* individuais (SQL, listas, Bash, Read) antes de entrar no contexto | Não toca no histórico de mensagens acumulado |
| `context_budget_hook.py` | Monitora tokens e dispara WARNING a 80%, ERROR a 95%, salva checkpoint | Não trunca nem sumariza o histórico — apenas avisa |
| `checkpoint.py` | Salva último prompt, custo e arquivos gerados | Não salva o histórico de mensagens — sessão reinicia do zero |

O `messages` do Supervisor cresce sem limite. Em workflows longos — `/party --full`, WF-01 com 4 agentes encadeados, múltiplas rodadas de refinamento — cada resposta de sub-agente entra completa no histórico. Após 3-4 workflows numa sessão, o Supervisor carrega centenas de kilobytes de mensagens anteriores a cada nova chamada, pagando o preço integral desses tokens repetidamente.

O `context_budget_hook.py` menciona `/memory flush` no log de alerta a 95%, mas esse comando não parece estar implementado.

### Solução arquitetural: Agente Sumarizador (Haiku)

Implementar uma chamada lateral ao Claude Haiku quando o uso de contexto ultrapassa **65-70%** do budget. O Haiku recebe o histórico de mensagens antigas e retorna um bloco estruturado de estado técnico que substitui essas mensagens no array.

**Prompt do sumarizador — estrutura de saída obrigatória:**

O sumarizador deve ser um **extrator de esquema**, não um resumidor de texto. A saída deve seguir 7 campos estruturados:

1. **Problema Central da Sessão** — uma frase com o objetivo técnico em execução
2. **Entidades Técnicas Identificadas** — nomes exatos: `catalog.schema.table`, IDs de pipeline, caminhos de arquivo, agentes chamados e resultado em uma linha
3. **Decisões Confirmadas pelo Usuário** — apenas o que foi explicitamente aprovado, com referência ao turn
4. **Estado de Execução** — EXECUTADO / EXECUTADO COM ERRO / PENDENTE / BLOQUEADO para cada ação relevante
5. **Artefatos Gerados** — caminhos exatos de PRDs, SPECs e arquivos de código (sem incluir o conteúdo)
6. **Restrições Ativas** — guardrails impostos pelo usuário durante a sessão que não estão no system prompt original
7. **Próximo Passo Esperado** — o que o pipeline espera que aconteça a seguir

**Regra crítica do prompt:** Nunca usar referências relativas como "a tabela mencionada anteriormente". Sempre usar nomes exatos e caminhos completos encontrados no histórico.

**Descarte explícito:** conteúdo completo de SQL/PySpark gerados, logs de execução de ferramentas MCP, confirmações genéricas do usuário, outputs verbosos de `list_tables`/`list_schemas`.

**Integração no histórico:**

```
[HISTÓRICO COMPRIMIDO — turns 1-38]
<bloco estruturado do Haiku>
[FIM DO HISTÓRICO COMPRIMIDO — turns 39+ seguem abaixo]
```

O Supervisor aprende a reconhecer esse marcador via uma linha no system prompt. Não inserir como mensagem de assistente — o Supervisor pode confundir estado confirmado com inferência própria.

### Por que Haiku e não Sonnet?

O sumarizador é uma tarefa de extração estruturada com entrada bem definida — não requer raciocínio complexo. Haiku custa ~20× menos que Opus e completa essa tarefa em <5 segundos. O investimento na sumarização se paga na primeira chamada do Supervisor que segue.

### Prioridade: 🟠 P1

Não é um bug — é uma lacuna arquitetural. Mas em sessões longas com workflows encadeados, o impacto em custo e a probabilidade de estourar o contexto são altos. Implementar após resolver G1 e G2.

---

## G4 — Comandos slash customizados para Claude Code CLI

### O que está errado

O projeto documenta dois processos de múltiplos passos no `CLAUDE.md` que dependem inteiramente de memória do desenvolvedor:

**Adicionar novo agente** — após criar `agents/registry/<nome>.md`, é obrigatório:
1. Atualizar `SUPERVISOR_SYSTEM_PROMPT` em `agents/prompts/supervisor_prompt.py`
2. Atualizar testes em `tests/test_agents.py`

**Adicionar novo MCP** — processo de 5 passos em ordem específica:
1. Criar `mcp_servers/<nome>/` com `server_config.py`
2. Registrar em `config/mcp_servers.py`
3. Adicionar credenciais em `config/settings.py`
4. Adicionar aliases em `agents/loader.py` → `MCP_TOOL_SETS`
5. Atualizar `tests/test_settings.py`

Esquecer qualquer um desses passos gera bugs silenciosos: o agente existe mas o Supervisor não sabe que pode delegá-lo, ou o MCP existe mas nenhum agente tem o alias correto para usá-lo.

### Solução

Dois comandos slash customizados em `.claude/commands/`:

- `/add-agent` — scaffolda o arquivo `.md` de registry com frontmatter YAML completo, lembra os dois passos obrigatórios, e valida se o YAML é sintaticamente correto
- `/add-mcp` — guia pelos 5 passos em sequência, valida cada arquivo modificado antes de passar para o próximo

### Prioridade: 🟡 P2

Não causa bug imediato — causa erro humano ocasional. Baixo esforço de implementação, alto valor para onboarding de novos contribuidores.

---

## G5 — Claude Code autônomo no pipeline de CI/CD

### O que está errado

O CI atual (GitHub Actions `ci.yml`) cobre validações determinísticas: Ruff, Mypy, pytest, Bandit. Nenhuma dessas ferramentas consegue verificar:

- Se um novo agente adicionado em `agents/registry/` tem o `supervisor_prompt.py` atualizado
- Se um novo MCP seguiu os 5 passos documentados no `CLAUDE.md`
- Se o frontmatter YAML do agente declara um tier coerente com os MCPs que usa
- Se uma Skill modificada ainda segue o formato correto após edição

Essas são **convenções arquiteturais** — verificáveis apenas com julgamento semântico, não com regras mecânicas.

### Solução

Um step de Claude Code no CI disparado apenas quando há mudanças em `agents/registry/` ou `mcp_servers/` ou `skills/`:

```yaml
- name: Architectural Convention Review
  if: contains(github.event.head_commit.message, '[skip-arch-review]') == false
  run: |
    claude --headless --print \
      "Revise as mudanças em diff abaixo contra as convenções do CLAUDE.md.
       Verifique: (1) agentes novos têm supervisor_prompt.py atualizado?
       (2) MCPs novos seguiram os 5 passos? (3) frontmatter YAML é coerente?
       Retorne PASS ou FAIL com justificativa." \
      < git_diff.txt
```

O resultado é postado como comentário no PR via `gh pr comment`.

### Custo vs. benefício

Não faz sentido rodar em todo push — tem custo de API e latência. Rodar apenas em PRs com mudanças nos diretórios críticos. Evitar como substituto de Ruff/Mypy/Bandit — esses são determinísticos e gratuitos; Claude Code no CI é para julgamento arquitetural.

### Prioridade: 🟡 P2

Valor real para times com múltiplos contribuidores. Para uso solo, o CLAUDE.md e o `.claude/settings.local.json` já cobrem bem.

---

## Roadmap Recomendado

```
Semana 1 (P0 — corrige bug ativo de custo)
├── G1: Investigar se o SDK expõe cache_control no system_prompt
├── G1: Implementar breakpoints explícitos no Supervisor (system + tools)
└── G2: Reposicionar breakpoint para cobrir bloco acumulado >2048 tokens

Semana 2-3 (P1 — previne estouro de contexto em sessões longas)
├── G3: Implementar chamada lateral ao Haiku com prompt estruturado
├── G3: Integrar sumarizador como step automático no context_budget_hook (65%)
└── G3: Implementar /memory flush que dispara sumarização manual

Semana 4+ (P2 — melhoria de DX e qualidade do processo)
├── G4: Implementar /add-agent e /add-mcp como comandos Claude Code CLI
└── G5: Adicionar step de revisão arquitetural no CI para PRs em diretórios críticos
```

---

## Impacto Financeiro Estimado (referência)

| Gap | Cenário | Custo atual (estimado) | Custo após fix |
|-----|---------|----------------------|----------------|
| G1+G2 | Sessão com 6 chamadas ao Supervisor (system prompt ~3K tokens) | ~$0.27/sessão em tokens de input repetidos | ~$0.03/sessão (90% desconto no cache) |
| G3 | Workflow WF-01 completo (4 agentes, ~40 turns) | Histórico completo em cada chamada subsequente | Histórico comprimido após turn 25 (~60% de redução) |

> Valores estimados com base em preços públicos da Anthropic (Opus: $15/1M input tokens, Haiku: $0.80/1M input tokens). Impacto real depende do volume de sessões.
