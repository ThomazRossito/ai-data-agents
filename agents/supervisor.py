"""
Módulo principal do Agent Supervisor.

Constrói o ClaudeAgentOptions com:
  - System prompt do orquestrador
  - Subagents especialistas carregados dinamicamente via agents/registry/
  - Servidores MCP das plataformas com credenciais configuradas
  - Hooks de auditoria, segurança e compressão de output
  - Configurações de modelo, custo e permissões

Arquitetura de Agentes:
  Os agentes são definidos como arquivos Markdown em agents/registry/*.md
  com frontmatter YAML. O loader dinâmico (agents/loader.py) instancia
  AgentDefinition para cada arquivo, permitindo adicionar novos agentes
  sem modificar código Python.

  Para adicionar um novo agente: crie agents/registry/nome-agente.md
  seguindo o template em agents/registry/_template.md.

Modos de thinking:
  - DOMA Full (/plan): thinking enabled com budget de 8000 tokens — para planejamento complexo
  - Demais modos: thinking disabled — economiza custo/latência em tarefas pontuais
"""

import copy
import re
from pathlib import Path
from typing import Any, Literal, cast

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

from agents.loader import load_all_agents
from agents.prompts.supervisor_prompt import SUPERVISOR_SYSTEM_PROMPT
from config.mcp_servers import build_mcp_registry
from config.settings import settings
from hooks.audit_hook import audit_tool_usage
from hooks.context_budget_hook import track_context_budget
from hooks.cost_guard_hook import log_cost_generating_operations
from hooks.memory_hook import capture_session_context, pre_track_lesson_timing
from hooks.output_compressor_hook import compress_tool_output
from hooks.security_hook import block_destructive_commands, check_sql_cost
from hooks.workflow_tracker import pre_track_workflow_events, track_workflow_events


# ─── Model Failover ──────────────────────────────────────────────────────────

#: Mapa primary → fallback para degradação de modelo em rate-limit / overload.
#:
#: A família K2.6 da Moonshot expõe um modelo único na API (`kimi-k2.6`), com
#: thinking ligado/desligado via parâmetro — não há mais cascata por nome de
#: modelo. Mantemos o map para compatibilidade da função build_failover_options
#: e para permitir fallback futuro a um modelo lateral (ex: kimi-k2.5) caso a
#: Moonshot adicione variantes leves.
FAILOVER_MODEL_MAP: dict[str, str] = {
    "kimi-k2.6": "kimi-k2.6",  # modelo único — fallback é retry no mesmo modelo
}

#: Modelo de fallback padrão quando o primary não está no FAILOVER_MODEL_MAP.
_DEFAULT_FALLBACK_MODEL = "kimi-k2.6"

#: Padrões de mensagem de erro que indicam sobrecarga ou rate-limit do modelo.
_OVERLOAD_PATTERNS: list[re.Pattern] = [
    re.compile(r"rate.?limit", re.IGNORECASE),
    re.compile(r"overloaded", re.IGNORECASE),
    re.compile(r"529", re.IGNORECASE),
    re.compile(r"too many requests", re.IGNORECASE),
    re.compile(r"capacity", re.IGNORECASE),
    re.compile(r"throttl", re.IGNORECASE),
]


def is_rate_limit_error(exc: BaseException) -> bool:
    """
    Detecta se uma exceção indica sobrecarga ou rate-limit do modelo.

    Analisa a mensagem de erro e o tipo da exceção para identificar erros
    HTTP 429 (Rate Limited) e HTTP 529 (Overloaded) da API Anthropic.
    """
    msg = str(exc).lower()
    return any(p.search(msg) for p in _OVERLOAD_PATTERNS)


def build_failover_options(primary_options: ClaudeAgentOptions) -> ClaudeAgentOptions:
    """
    Retorna uma cópia de ClaudeAgentOptions com modelo de fallback.

    Aplica o FAILOVER_MODEL_MAP. Como K2.6 é modelo único na API, o fallback
    atual é retry no mesmo modelo (útil pra rate limit transitório). O mapa
    está pronto para receber um modelo lateral de fallback no futuro.

    Args:
        primary_options: Opções originais com o modelo primário.

    Returns:
        Nova instância de ClaudeAgentOptions com modelo de fallback configurado.
    """
    primary_model = primary_options.model or _DEFAULT_FALLBACK_MODEL
    fallback_model = FAILOVER_MODEL_MAP.get(primary_model, _DEFAULT_FALLBACK_MODEL)
    fallback_opts = copy.copy(primary_options)
    fallback_opts.model = fallback_model
    return fallback_opts


def build_supervisor_options(
    platforms: list[str] | None = None,
    enable_thinking: bool = False,
    agent_names: list[str] | None = None,
) -> ClaudeAgentOptions:
    """
    Constrói e retorna o ClaudeAgentOptions para o Agent Supervisor.

    Os agentes especialistas são carregados dinamicamente a partir dos
    arquivos Markdown em agents/registry/. Para adicionar um novo agente,
    basta criar um arquivo .md no registry — nenhuma modificação de código
    é necessária.

    Args:
        platforms: Plataformas MCP a ativar. None = detecta por credenciais disponíveis.
                   Opções: "databricks", "fabric", "fabric_rti"
        enable_thinking: Se True, ativa thinking adaptive com effort=high.
                         Use apenas para DOMA Full (/plan) — tarefas de planejamento complexo.
                         False por padrão para economizar custo e latência.
                         Compatível com Opus 4.7 (que rejeita a sintaxe antiga budget_tokens).
        agent_names: Se passado, carrega APENAS esses agentes (Two-Stage Routing).
                     Reduz drasticamente o tamanho do system prompt do Supervisor
                     (~80K tokens fixos → ~20K tokens com 3 agentes).
                     Use em conjunto com agents.dispatcher.select_agents() para
                     fazer routing inteligente antes da chamada principal.
                     None (default): carrega todos os 14 agentes do registry
                     (comportamento legado, compatível mas caro em modelos
                     com throughput menor que Sonnet — ex: Kimi K2.6 trava).

    Returns:
        ClaudeAgentOptions configurado e pronto para uso com query() ou ClaudeSDKClient.
    """
    # Thinking no Kimi K2.6 (Moonshot):
    #   ⚠️ Verificado em produção: o endpoint Anthropic-compat da Moonshot ACEITA
    #   o parâmetro thinking={"type":"adaptive"} mas NÃO emite events streaming
    #   durante o raciocínio (pode travar 5+ min sem qualquer feedback ou jamais
    #   completar). Diferente do Claude Sonnet que streama text_delta em tempo real.
    #
    #   Por isso, quando rodando contra Moonshot (anthropic_base_url contém
    #   "moonshot"), forçamos thinking=disabled mesmo com enable_thinking=True.
    #   O /plan continua funcionando — só sem o reasoning estendido extra.
    #
    #   Se a Moonshot habilitar streaming de thinking no futuro, basta remover
    #   essa detecção e voltar ao comportamento Claude-style.
    is_moonshot = "moonshot" in (settings.anthropic_base_url or "").lower()

    if enable_thinking and is_moonshot:
        import logging as _log

        _log.getLogger("data_agents.supervisor").warning(
            "thinking adaptive solicitado (/plan) mas endpoint é Moonshot — "
            "thinking não streama lá. Usando thinking=disabled para evitar travada."
        )
        thinking_config: Any = {"type": "disabled"}
    elif enable_thinking:
        # Endpoint Anthropic original (ou outro compat. com streaming): usa adaptive
        thinking_config = {"type": "adaptive", "effort": "high"}
    else:
        thinking_config = {"type": "disabled"}

    supervisor_model = settings.default_model

    # Servidores MCP (plataformas com credenciais disponíveis)
    mcp_registry = build_mcp_registry(platforms)

    # Carregamento dinâmico de agentes via Markdown/YAML.
    # Filtra mcp_servers dos agentes para conter apenas servidores disponíveis no registry.
    # Isso evita referências a servidores sem credenciais (ex: fabric_rti sem KUSTO_SERVICE_URI).
    #
    # inject_cache_prefix=True (padrão): prepend agents/cache_prefix.md ao topo de cada agente.
    # Os primeiros ~800 tokens de todos os agentes são byte-idênticos → o Claude API cacheia
    # esse bloco uma única vez e o reutiliza em todas as chamadas, reduzindo ~40-60% o custo
    # de tokens de input. Inspirado em Ch. 9 — Fork Agents & Prompt Cache (claude-code-from-source).
    #
    # tier_turns_map + tier_effort_map (Ch. 5 — Agent Loop):
    # Controla maxTurns e effort por tier, prevenindo que sub-agentes consumam
    # mais tokens do que o necessário para seu escopo de trabalho.
    agents = load_all_agents(
        available_mcp_servers=set(mcp_registry.keys()),
        tier_model_map=settings.tier_model_map if settings.tier_model_map else None,
        tier_turns_map=settings.tier_turns_map if settings.tier_turns_map else None,
        tier_effort_map=settings.tier_effort_map if settings.tier_effort_map else None,
        inject_kb_index=settings.inject_kb_index,
        inject_cache_prefix=True,
    )

    # ── Two-Stage Routing: filtra agentes carregados ─────────────────────────
    # Se `agent_names` foi passado (vem do dispatcher), carrega APENAS esses.
    # Reduz tamanho do system prompt do Supervisor de ~80K para ~15-25K tokens.
    # Sem isso, modelos como Kimi K2.6 travam processando o prompt gigante.
    if agent_names is not None:
        import logging as _log

        _logger = _log.getLogger("data_agents.supervisor")
        before = len(agents)
        agents = {name: agents[name] for name in agent_names if name in agents}
        after = len(agents)
        if not agents:
            _logger.warning(
                f"agent_names={agent_names} resultou em 0 agentes válidos — "
                f"recarregando todos como fallback"
            )
            agents = load_all_agents(
                available_mcp_servers=set(mcp_registry.keys()),
                tier_model_map=settings.tier_model_map if settings.tier_model_map else None,
                tier_turns_map=settings.tier_turns_map if settings.tier_turns_map else None,
                tier_effort_map=settings.tier_effort_map if settings.tier_effort_map else None,
                inject_kb_index=settings.inject_kb_index,
                inject_cache_prefix=True,
            )
        else:
            _logger.info(f"Lazy load ativo: {after}/{before} agentes carregados → {list(agents)}")

    # Raiz do projeto — garante que agentes resolvam caminhos relativos
    # corretamente independente do cwd do processo (ex: Chainlit vs main.py).
    project_root = Path(__file__).parent.parent

    return ClaudeAgentOptions(
        # --- Working Directory: âncora todos os agentes na raiz do projeto ---
        cwd=project_root,
        # --- Modelo e System Prompt ---
        # supervisor_model = settings.default_model (kimi-k2.6 por padrão).
        # Thinking é controlado via thinking_config, não trocando o modelo.
        model=supervisor_model,
        system_prompt=SUPERVISOR_SYSTEM_PROMPT,
        # --- Tools do Supervisor (planejamento e delegação apenas) ---
        allowed_tools=[
            "Agent",  # Invocar subagents especialistas
            "Read",  # Ler arquivos locais (KBs, schemas, configs, skills)
            "Grep",  # Buscar conteúdo em arquivos
            "Glob",  # Encontrar arquivos por padrão
            "Write",  # Salvar PRDs e artefatos em output/
            "AskUserQuestion",  # Esclarecer ambiguidades com o usuário
            "Bash",  # Executar comandos auxiliares (mkdir, etc.)
        ],
        # --- Subagents Especialistas (carregados dinamicamente do registry) ---
        agents=agents,
        # --- Servidores MCP (plataformas com credenciais disponíveis) ---
        mcp_servers=mcp_registry,
        # --- Controle de Execução ---
        # Configurável via AGENT_PERMISSION_MODE no .env:
        #   "bypassPermissions" (padrão) — agentes executam sem confirmação
        #   "acceptEdits" — agentes pedem confirmação antes de writes/executes
        permission_mode=cast(
            Literal["default", "acceptEdits", "plan", "bypassPermissions", "dontAsk", "auto"],
            settings.agent_permission_mode,
        ),
        max_turns=settings.max_turns,
        max_budget_usd=settings.max_budget_usd,
        # --- Buffer JSON entre Python ↔ subprocess do claude-agent-sdk ---
        # Default do SDK é 1 MB e quebra com CLIJSONDecodeError quando agentes T1
        # retornam Discovery com YAML/JSON grandes (ex: dashboard .lvdash.json).
        # Ref: anthropics/claude-agent-sdk-python#98
        max_buffer_size=settings.max_buffer_size,
        # --- Streaming parcial para feedback visual em tempo real ---
        include_partial_messages=True,
        # --- Thinking: desabilitado por padrão; ativo via enable_thinking=True ---
        thinking=thinking_config,
        effort="high",
        # --- Hooks de Auditoria, Custo e Segurança ---
        # Hooks use generic dict[str, Any] signatures; SDK expects its own union input types.
        # Behavior is correct at runtime — suppress the list-item mismatch below.
        hooks={
            "PostToolUse": [
                HookMatcher(hooks=[audit_tool_usage]),  # type: ignore[list-item]
                HookMatcher(hooks=[log_cost_generating_operations]),  # type: ignore[list-item]
                # Rastreia delegações de agentes, workflows e Clarity Checkpoint.
                HookMatcher(hooks=[track_workflow_events]),  # type: ignore[list-item]
                # Captura contexto da sessão para o sistema de memória persistente.
                # Acumula sem chamar LLM — flush ocorre no final da sessão.
                HookMatcher(hooks=[capture_session_context]),  # type: ignore[list-item]
                # Monitora tokens acumulados da sessão (Ch. 5 — Agent Loop).
                # Emite WARNING a 80% e ERROR a 95% do limite do context window.
                HookMatcher(hooks=[track_context_budget]),  # type: ignore[list-item]
                # RTK-style: comprime output verboso das tools antes de enviar ao modelo.
                # Executado por último para que audit/cost_guard observem o output original.
                HookMatcher(hooks=[compress_tool_output]),  # type: ignore[list-item]
            ],
            "PreToolUse": [
                HookMatcher(
                    matcher="Bash",
                    hooks=[block_destructive_commands],  # type: ignore[list-item]
                ),
                # check_sql_cost: detecta SELECT * sem WHERE/LIMIT em QUALQUER tool
                # (Bash com spark-sql, execute_sql via MCP, etc.)
                # Sem matcher → intercepta todas as tools.
                HookMatcher(
                    hooks=[check_sql_cost],  # type: ignore[list-item]
                ),
                # pre_track: emite agent_start / tool_call para callbacks de progresso
                # registrados pelo CLI e UI — feedback visual em tempo real.
                HookMatcher(
                    hooks=[pre_track_workflow_events],  # type: ignore[list-item]
                ),
                # pre_track_lesson_timing: registra t0 de cada tool call para slow_op detection.
                # Deve ser PreToolUse — PostToolUse seria sempre ~0s (tool já terminou).
                HookMatcher(
                    hooks=[pre_track_lesson_timing],  # type: ignore[list-item]
                ),
            ],
        },
    )
