"""
Configurações globais via Pydantic BaseSettings.
Carregadas automaticamente do arquivo .env na raiz do projeto.

Inclui validação de credenciais por plataforma e diagnóstico de startup.
"""

import logging
import warnings
from typing import ClassVar, TypedDict

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger("data_agents.config")


class _PlatformConfig(TypedDict):
    """Estrutura interna usada para validação de credenciais por plataforma."""

    fields: dict[str, str]
    required: list[str]


class Settings(BaseSettings):
    # --- Moonshot / Kimi K2 (compatibilidade Anthropic) ---
    # O claude-agent-sdk fala o protocolo da Messages API da Anthropic. A Moonshot
    # expõe um endpoint compatível em https://api.moonshot.ai/anthropic, então a
    # mesma variável (ANTHROPIC_API_KEY) é reutilizada — recebe a chave da Moonshot.
    # Em runtime, o SDK lê ANTHROPIC_AUTH_TOKEN ou ANTHROPIC_API_KEY como bearer.
    # Obtenha sua chave em: https://platform.moonshot.ai/console/api-keys
    anthropic_api_key: str = ""
    # URL base obrigatória para apontar o SDK para a Moonshot (Kimi K2).
    # Padrão: https://api.moonshot.ai/anthropic. Para Anthropic original, deixe vazio.
    anthropic_base_url: str = "https://api.moonshot.ai/anthropic"

    # --- Project Identity ---
    # Identificador único do projeto. Usado como sufixo nos nomes dos arquivos
    # SQLite de memória (long_term, short_term) para garantir isolamento entre
    # projetos que compartilham o mesmo filesystem.
    #
    # Comportamento:
    #   - "auto" (default) → deriva do nome do diretório atual via Path.cwd().name
    #   - qualquer outro valor → usado literalmente como ID
    #
    # Override via .env: PROJECT_ID=meu-projeto-x
    project_id: str = "auto"

    # --- Databricks ---
    databricks_host: str = ""
    databricks_token: str = ""
    databricks_sql_warehouse_id: str = ""

    # --- Microsoft Fabric / Azure ---
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""
    fabric_workspace_id: str = ""
    # Nome (slug) do workspace — necessário pra DFS API do OneLake
    # (onelake.dfs.fabric.microsoft.com/<NAME>/...). NÃO aceita GUID no path.
    # Configure no .env: FABRIC_WORKSPACE_NAME=poc-multiagent-fabric
    fabric_workspace_name: str = ""
    fabric_api_base_url: str = "https://api.fabric.microsoft.com/v1"
    # GUID do Lakehouse de ontologia — necessário para upload via ADLS Gen2 com URL correta.
    # Fabric UI → Lakehouse → Settings → ID (ou Fabric REST API /items).
    fabric_lakehouse_ontologia_id: str = ""
    fabric_mcp_server_path: str = "./mcp_servers/fabric/Fabric.Mcp.Server"
    # Comando do Fabric Community MCP — pode ser sobrescrito no .env com caminho absoluto
    # Exemplo conda: /opt/anaconda3/envs/multi_agents/bin/microsoft-fabric-mcp
    fabric_community_command: str = "microsoft-fabric-mcp"

    # --- Fabric SQL Analytics Endpoint (MCP Customizado — multi-lakehouse) ---
    # Resolve a limitação da REST API que só lista o schema dbo.
    # Conecta via TDS (pyodbc + AAD Bearer Token) ao SQL Analytics Endpoint.
    #
    # Registry de lakehouses (JSON) — recomendado para múltiplos lakehouses:
    #   FABRIC_SQL_LAKEHOUSES={"TARN_LH_DEV": "tarn-dev.datawarehouse.fabric.microsoft.com",
    #                          "TARN_LH_PROD": "tarn-prod.datawarehouse.fabric.microsoft.com"}
    #   FABRIC_SQL_DEFAULT_LAKEHOUSE=TARN_LH_DEV
    #
    # Como encontrar o endpoint: Portal Fabric → Lakehouse → SQL Analytics Endpoint → "Server"
    fabric_sql_lakehouses: str = "{}"  # JSON: {"NOME_LH": "endpoint.fabric.microsoft.com"}
    fabric_sql_default_lakehouse: str = ""  # lakehouse usado quando o agente não especifica
    # Backward compat (variáveis legadas para um único lakehouse)
    fabric_sql_endpoint: str = ""
    fabric_lakehouse_name: str = ""
    # Comando do servidor — instalado via pip install -e .
    # Exemplo conda: /opt/anaconda3/envs/multi_agents/bin/fabric-sql-mcp
    fabric_sql_command: str = "fabric-sql-mcp"

    # --- Databricks Genie (MCP Customizado — Conversation API + Space Management) ---
    # Resolve o gap do databricks-mcp-server que não expõe as tools de Genie.
    # Conecta à Genie REST API usando DATABRICKS_HOST + DATABRICKS_TOKEN (sem deps extras).
    #
    # Registry de Genie Spaces (JSON) — recomendado para múltiplos spaces:
    #   DATABRICKS_GENIE_SPACES={"retail-sales": "01f117197b5319fb972e10a45735b28c",
    #                             "hr-analytics": "01abc123..."}
    #   DATABRICKS_GENIE_DEFAULT_SPACE=retail-sales
    #
    # Como encontrar o Space ID:
    #   Databricks → AI/BI → Genie → abra o Space → copie o ID da URL
    databricks_genie_spaces: str = "{}"  # JSON: {"nome-amigavel": "space_id"}
    databricks_genie_default_space: str = ""  # space usado quando o agente não especifica
    # Comando do servidor — instalado via pip install -e .
    # Exemplo conda: /opt/anaconda3/envs/multi_agents/bin/databricks-genie-mcp
    databricks_genie_command: str = "databricks-genie-mcp"

    # --- Fabric Semantic MCP (MCP Customizado — introspecção de Semantic Models) ---
    # Resolve o gap do fabric_community que não expõe TMDL, medidas DAX, relacionamentos e RLS.
    # Usa Power BI REST API (getDefinition + executeQueries) e Fabric REST API v1.
    # Reutiliza as credenciais Azure (AZURE_TENANT_ID + AZURE_CLIENT_ID + AZURE_CLIENT_SECRET).
    # Requer permissão no Power BI Admin Portal:
    #   Tenant Settings → Developer Settings → "Allow service principals to use Power BI APIs"
    # Comando: fabric-semantic-mcp (entry point em pyproject.toml)
    # Exemplo conda: /opt/anaconda3/envs/multi_agents/bin/fabric-semantic-mcp
    fabric_semantic_command: str = "fabric-semantic-mcp"

    # --- Fabric Ontology MCP (IQ Ontology — entity types, relationships, bindings) ---
    # Auth via Azure CLI (az login) — sem credenciais extras no .env.
    # Comando: fabric-ontology-mcp (entry point em pyproject.toml)
    fabric_ontology_command: str = "fabric-ontology-mcp"

    # --- Fabric RTI ---
    kusto_service_uri: str = ""
    kusto_service_default_db: str = ""

    # --- Context7 (MCP — Documentação atualizada de bibliotecas) ---
    # Sem credenciais no plano gratuito (repos públicos).
    # Plano Pro requer conta em context7.com — configure CONTEXT7_API_KEY para ativá-lo.
    # Free: 1.000 requests/mês | Pro: $7/seat/mês (repos privados)
    context7_api_key: str = ""  # opcional — vazio = plano gratuito (repos públicos)

    # --- Tavily (MCP — Busca web otimizada para LLMs) ---
    # Obrigatório. Obtenha em: https://app.tavily.com/
    # Free: 1.000 créditos/mês (sem cartão) | Pago: $0.008/crédito
    tavily_api_key: str = ""

    # --- GitHub (MCP — Gestão de repositórios, issues e pull requests) ---
    # Obrigatório. Crie em: GitHub → Settings → Developer Settings → PAT (classic)
    # Escopos: repo, read:org (para repos privados)
    # Gratuito via Personal Access Token
    github_personal_access_token: str = ""

    # --- Firecrawl (MCP — Web scraping e crawling estruturado) ---
    # Obrigatório. Obtenha em: https://www.firecrawl.dev/app/api-keys
    # Free: 500 créditos/mês | Pago: a partir de $16/mês (3.000 créditos)
    firecrawl_api_key: str = ""

    # --- PostgreSQL (MCP — Queries somente leitura em banco PostgreSQL) ---
    # Connection string completa do banco alvo.
    # Formato: postgresql://usuario:senha@host:5432/banco
    # Formato cloud: postgresql://usuario:senha@host:5432/banco?sslmode=require
    # Gratuito (open source oficial da Anthropic)
    postgres_url: str = ""  # vazio = MCP postgres não será ativado

    # --- Migration Source (MCP Customizado — fontes de migração relacionais) ---
    # Registry de bancos de origem para migração (JSON). Suporta SQL Server e PostgreSQL.
    # Formato: {"NOME": {"type": "sqlserver|postgresql", "host": "...", "port": ..., "database": "...", "user": "...", "password": "..."}}
    # SQL Server requer ODBC Driver 17 ou 18 instalado no sistema.
    # PostgreSQL usa psycopg2-binary (sem dependência de sistema).
    migration_sources: str = "{}"
    migration_default_source: str = ""
    # Comando do servidor — instalado via pip install -e .
    # Exemplo conda: /opt/anaconda3/envs/multi_agents/bin/migration-source-mcp
    migration_source_command: str = "migration-source-mcp"

    # --- Azure Pricing MCP (custom — Azure Retail Prices API wrapper) ---
    # Sem credenciais (API pública). Defaults configuráveis via .env (opcionais).
    # Comando do servidor — instalado via pip install -e .
    azure_pricing_command: str = "azure-pricing-mcp"
    # Região default usada quando agent não especifica (arm region name)
    azure_pricing_default_region: str = "brazilsouth"
    # Currency default pra cotação (3-letter code)
    azure_pricing_default_currency: str = "USD"
    # Horas/mês padrão (Azure Pricing Calculator usa 730 = 365.25/12*24)
    azure_pricing_hours_per_month: float = 730.0

    # --- Permissões dos Agentes ---
    # "bypassPermissions" (padrão): agentes executam sem pedir confirmação — ideal para automação.
    # "acceptEdits": agentes pedem confirmação antes de operações write/execute — recomendado
    # em ambientes multi-usuário ou onde auditoria manual é necessária.
    # Override via .env: AGENT_PERMISSION_MODE=acceptEdits
    agent_permission_mode: str = "bypassPermissions"

    # --- Configurações do Sistema ---
    # Modelo padrão do Supervisor (orquestrador). Kimi K2.6 é o flagship unificado da
    # Moonshot (lançado em abr/2026), substituindo a série K2 que será descontinuada
    # em 25/05/2026. Thinking é ligado/desligado via parâmetro `thinking` (igual ao
    # Claude Sonnet — protocolo idêntico), não via modelo dedicado.
    default_model: str = "kimi-k2.6"
    max_budget_usd: float = 5.0
    max_turns: int = 50
    # Buffer máximo (bytes) para mensagens JSON entre Python e subprocess do
    # claude-agent-sdk. Default do SDK é 1 MB (1048576), insuficiente quando
    # agentes T1 (databricks-engineer, fabric-engineer, migration-expert)
    # retornam Discovery/Bash com YAMLs/JSONs grandes — caso típico é Discovery
    # de projeto Databricks completo (Dashboard JSON + Metric Views + LakeFlow).
    # 10 MB cobre praticamente todos os casos práticos.
    # Override via .env: MAX_BUFFER_SIZE=20971520 (20 MB) se Discovery seu for
    # ainda maior. Ref: anthropics/claude-agent-sdk-python#98
    max_buffer_size: int = 10 * 1024 * 1024  # 10 MB
    log_level: str = "INFO"
    # Nível de log para o console (o que o usuário vê no terminal).
    # "WARNING" esconde logs operacionais (OUTPUT COMPRIMIDO, custo, etc).
    # O arquivo JSONL sempre captura tudo em DEBUG independentemente.
    console_log_level: str = "WARNING"
    audit_log_path: str = "./logs/audit.jsonl"

    # --- UI / Monitoring / Visualization Ports ---
    # Portas distintas do projeto original (data-agents = 8503/8501) para
    # permitir rodar os dois projetos lado a lado sem conflito.
    # Override via .env: CHAINLIT_PORT=8513, MONITOR_PORT=8511, VISUALIZATION_PORT=8512
    chainlit_port: int = 8513
    monitor_port: int = 8511
    # Visualização 3D do escritório dos agentes (FastAPI + WebSocket).
    # Roda em porta intermediária entre monitor (8511) e chainlit (8513).
    # Subir via: python -m data_agents.visualization.server  OU  ./start.sh --with-viz
    visualization_port: int = 8512

    # --- Model Routing por Tier ---
    # Mapeamento tier -> modelo. Sobrescreve o `model:` do frontmatter de cada agente.
    # Se um tier não estiver no mapa, o agente usa o model declarado no seu próprio .md.
    #
    # Família Kimi K2.6 (Moonshot — abr/2026):
    #   kimi-k2.6  → modelo único da API (1T params MoE, 256k context).
    #                Thinking é ligado/desligado via parâmetro `thinking` no
    #                supervisor.py (não há modelo separado).
    #
    # Diferenciação por tier acontece via tier_turns_map e tier_effort_map abaixo,
    # não mais via modelo. Se desejar usar outro modelo (ex: kimi-k2.5 visão+texto),
    # configure aqui via .env: TIER_MODEL_MAP='{"T1": "kimi-k2.6", "T2": "kimi-k2.5"}'
    tier_model_map: dict[str, str] = {}

    # --- Token Budgets por Tier (Ch. 5 — Agent Loop) ---
    # Mapeamento tier -> maxTurns: limita o número máximo de chamadas de tool por sub-agente.
    # T0 (haiku, zero MCP): conversacional puro, sem tools — pouquíssimos turns necessários.
    # T1 (pipelines complexos, cross-platform) precisam de mais turns.
    # T2 (análise especializada, escopo restrito) precisam de menos.
    # T3 (conversacional com tools limitadas) precisam de poucos turns.
    # Override via .env: TIER_TURNS_MAP='{"T0": 3, "T1": 25, "T2": 15, "T3": 5}'
    tier_turns_map: dict[str, int] = {"T0": 3, "T1": 20, "T2": 12, "T3": 5}

    # --- Effort por Tier (Ch. 5 — Agent Loop) ---
    # Mapeamento tier -> effort: controla o nível de "esforço" do modelo por agente.
    # T0: "low" — Kimi K2.6 respondendo perguntas conceituais, sem raciocínio profundo necessário.
    # "high": raciocínio mais profundo, maior custo e latência — para tarefas complexas T1.
    # "medium": balanceado — para tarefas especializadas T2.
    # "low": rápido e eficiente — para tarefas conversacionais T3.
    # Override via .env: TIER_EFFORT_MAP='{"T0": "low", "T1": "high", "T2": "medium", "T3": "low"}'
    tier_effort_map: dict[str, str] = {"T0": "low", "T1": "high", "T2": "medium", "T3": "low"}

    # --- KB Injection ---
    # Se True, injeta o conteúdo dos index.md das KBs relevantes no prompt de cada agente.
    # Baseado no campo kb_domains do frontmatter. Desabilite para economizar tokens no prompt.
    inject_kb_index: bool = True

    # --- Idle Timeout ---
    # Tempo de inatividade (em minutos) antes de oferecer reset automático da sessão.
    # Se 0, desabilita o idle timeout. Padrão: 30 minutos.
    idle_timeout_minutes: int = 30

    # --- Memory System ---
    # Se True, habilita o sistema de memória persistente (captura + retrieval).
    # Desabilite para economizar custo do Kimi K2.6 lateral (~$0.003-0.01 por query).
    memory_enabled: bool = True
    # Se True, injeta memórias relevantes no system prompt antes de cada query.
    # Requer memory_enabled=True. Cada injeção custa ~$0.0003-0.001 (Kimi K2.6 lateral).
    memory_retrieval_enabled: bool = True
    # Se True, captura automaticamente contexto da sessão via hook PostToolUse.
    memory_capture_enabled: bool = True

    # --- Memory Decay (dias para atingir confidence 0.1) ---
    # Controla a velocidade de obsolescência de cada tipo de memória.
    # None = nunca decai (USER e ARCHITECTURE por padrão).
    # PROGRESS: tarefas em andamento ficam obsoletas rapidamente (padrão 7 dias).
    # FEEDBACK: orientações do usuário persistem mais (padrão 90 dias).
    # PIPELINE_STATUS: status de pipelines de dados (padrão 14 dias).
    # LESSON_LEARNED: lições de erros/performance (padrão 30 dias).
    # Override via .env: MEMORY_DECAY_PROGRESS_DAYS=14
    memory_decay_progress_days: float = 7.0
    memory_decay_feedback_days: float = 90.0
    memory_decay_pipeline_status_days: float = 14.0
    memory_decay_lesson_learned_days: float = 30.0

    # --- Lesson Learned Limits ---
    # Máximo de LESSON_LEARNED ativas por agente. Ao atingir o limite, a lesson
    # com menor confidence (mais decaída) é removida para dar lugar à nova.
    # Override via .env: MEMORY_LESSON_MAX_PER_AGENT=50
    memory_lesson_max_per_agent: int = 50

    # --- Skill Auto-Refresh ---
    # Se True, habilita a atualização automática das Skills via scripts/refresh_skills.py.
    # O script chama a Anthropic Messages API direta (sem MCP, sem agente) e usa o
    # tool nativo web_search para buscar docs atualizadas das plataformas.
    # Execute manualmente: make refresh-skills
    # Agendamento automático: configurado via SKILL_REFRESH_INTERVAL_DAYS.
    skill_refresh_enabled: bool = True
    # Intervalo em dias entre refreshes. Padrão: 3 dias.
    # Override via .env: SKILL_REFRESH_INTERVAL_DAYS=5
    skill_refresh_interval_days: int = 3
    # Domínios de skill a atualizar no refresh automático.
    # Override via .env: SKILL_REFRESH_DOMAINS=databricks,fabric
    skill_refresh_domains: str = "databricks,fabric"

    # --- Memory Instant Capture Patterns ---
    # Padrões regex para captura instantânea de memórias sem chamada LLM.
    # Cada padrão é uma string "regex::tipo" onde tipo é: feedback, architecture, progress.
    # Padrão vazio usa os 5 padrões default. Override via .env para adicionar novos tipos.
    # Ex: MEMORY_INSTANT_PATTERNS='["(?i)#concern\\s*[:\\-]?\\s*(.+)::architecture"]'
    memory_instant_patterns: list[str] = []

    # Máx de capturas instantâneas por output de tool (evita buffer bloat)
    memory_max_captures_per_output: int = 10

    # --- Memory Daily Log Cleanup ---
    # Se True, apaga daily logs compilados após N dias (reduz acúmulo de arquivos).
    # Logs compilados já tiveram seu conteúdo extraído para o store — são redundantes.
    # Override via .env: MEMORY_AUTO_CLEAN_DAILY_LOGS=true
    memory_auto_clean_daily_logs: bool = True
    # Quantos dias manter logs compilados antes de apagar. Padrão: 30 dias.
    # Override via .env: MEMORY_KEEP_COMPILED_DAYS=30
    memory_keep_compiled_days: int = 30

    # --- Memory Data Directory (raiz dos arquivos .md de memória) ---
    # Diretório onde o MemoryStore persiste as memórias como arquivos .md
    # organizados em subdiretórios por tipo (architecture/, data_asset/,
    # lesson_learned/, daily/, etc.).
    #
    # Se vazio (default), é derivado automaticamente a partir de project_id:
    #   "memory/data/<project_id>"
    #
    # Isso isola os arquivos .md entre projetos. Os SQLites de busca
    # (long_term, short_term) ficam na raiz com sufixo no nome, mas os
    # arquivos-fonte das memórias ficam num subdir por-projeto.
    # Override via .env: MEMORY_DATA_DIR=memory/data/meu-projeto
    memory_data_dir: str = ""

    # --- Short-term Memory (SQLite buffer com TTL) ---
    # Path do banco SQLite do buffer short-term. Relativo à raiz do projeto.
    # Se vazio (default), é derivado automaticamente a partir de project_id:
    #   "memory/data/short_term__<project_id>.db"
    # Isso garante isolamento entre projetos que copiam o diretório.
    # Override via .env: SHORT_TERM_DB_PATH=memory/data/short_term.db
    short_term_db_path: str = ""

    # --- Long-term Memory (SQLite FTS5 + embeddings opcionais) ---
    # Path do banco SQLite do índice long-term. Relativo à raiz do projeto.
    # Se vazio (default), é derivado automaticamente a partir de project_id:
    #   "memory/data/long_term__<project_id>.db"
    # Override via .env: LONG_TERM_DB_PATH=memory/data/long_term.db
    long_term_db_path: str = ""
    # Número máximo de memórias retornadas por busca no long-term.
    # Override via .env: LONG_TERM_SEARCH_LIMIT=8
    long_term_search_limit: int = 8
    # Se True, gera embeddings para as memórias long-term (requer fastembed).
    # Usa o mesmo modelo configurado em short_term_embedder_model.
    # Override via .env: LONG_TERM_EMBEDDER_ENABLED=true
    long_term_embedder_enabled: bool = False
    # Dias até uma entrada do buffer expirar. Padrão: 3 dias.
    # Override via .env: SHORT_TERM_TTL_DAYS=3
    short_term_ttl_days: float = 3.0
    # Se True, tenta usar LocalEmbedder (fastembed) para busca semântica.
    # Requer: pip install ".[memory]". Se False ou fastembed ausente, usa FTS5.
    # Override via .env: SHORT_TERM_EMBEDDER_ENABLED=true
    short_term_embedder_enabled: bool = False
    # Modelo fastembed a usar. Padrão: BAAI/bge-small-en-v1.5 (384 dims, ~25MB).
    # Override via .env: SHORT_TERM_EMBEDDER_MODEL=BAAI/bge-small-en-v1.5
    short_term_embedder_model: str = "BAAI/bge-small-en-v1.5"
    # Path do cache SQLite para embeddings (evita re-computação).
    # Se vazio (default), é derivado automaticamente a partir de project_id:
    #   "memory/data/embedder_cache__<project_id>.db"
    # Mesmo padrão dos outros SQLites: nome na raiz, sufixo identifica o projeto
    # (assim DBeaver consegue diferenciar caches de projetos distintos).
    # Override via .env: EMBEDDER_CACHE_DB_PATH=memory/data/embedder_cache.db
    embedder_cache_db_path: str = ""

    # --- Ledger (integridade do audit log) ---
    # Habilita assinatura HMAC-SHA256 de cada entrada do audit log.
    # Desabilitar só para debugging ou ambientes sem necessidade de auditoria.
    # Override via .env: LEDGER_ENABLED=false
    ledger_enabled: bool = True
    # Se True, verifica o hash de cada entrada ao carregar via Ledger.load_range().
    # Aumenta latência de leitura — manter False em produção, True para auditorias.
    # Override via .env: LEDGER_VERIFY_ON_LOAD=true
    ledger_verify_on_load: bool = False

    # --- Memory Extraction Model ---
    # Modelo usado pelo extractor (flush de sessão) para chamadas laterais (sem SDK).
    # K2.6 é o único modelo da API atualmente; para chamadas leves de extração,
    # passe `thinking={"type": "disabled"}` para reduzir latência e custo.
    # Override via .env: MEMORY_EXTRACTOR_MODEL=kimi-k2.5  (se desejar variante mais leve)
    memory_extractor_model: str = "kimi-k2.6"
    memory_extractor_max_tokens: int = 2048
    # Número máximo de memórias recuperadas por query (FTS5 long-term search).
    # Override via .env: MEMORY_RETRIEVAL_MAX=10
    memory_retrieval_max: int = 10

    # --- Output Compressor Limits ---
    # Limites de truncagem do output_compressor_hook.py.
    # Reduzir MAX_OUTPUT_CHARS economiza tokens de contexto em troca de menos detalhe.
    # Override via .env: COMPRESSOR_MAX_SQL_ROWS=20
    compressor_max_sql_rows: int = 20
    compressor_max_list_items: int = 15
    compressor_max_file_lines: int = 80
    compressor_max_bash_lines: int = 40
    compressor_max_output_chars: int = 3_500

    # Limites específicos para migration-expert (mcp__migration_source__*).
    # DDLs e schemas extraídos de SQL Server/PostgreSQL são legitimamente grandes.
    # Override via .env: COMPRESSOR_MIGRATION_MAX_FILE_LINES=300
    compressor_migration_max_file_lines: int = 300
    compressor_migration_max_output_chars: int = 10_000

    # --- Context Budget Thresholds ---
    # Limite de tokens de input por sessão (context window do Claude: 200K tokens).
    # 180K é o teto conservador para deixar margem para a resposta final.
    # Override via .env: CONTEXT_BUDGET_INPUT_LIMIT=180000
    context_budget_input_limit: int = 180_000
    # Limiares: 70% → WARNING, 80% → compactação automática, 95% → ERROR.
    context_budget_warn_threshold: float = 0.70
    context_budget_critical_threshold: float = 0.95
    # Limiar para disparar compactação autônoma: gera summary via Kimi K2.6, reconecta
    # o cliente com o summary injetado no system prompt — transparente ao usuário.
    context_budget_summarize_threshold: float = 0.80

    # --- S4 Autonomous Mode ---
    # Se True, o Supervisor auto-aprova delegações que atendem critérios de baixo risco:
    #   - read-only (sem writes em produção), OU
    #   - single-agent path (delegação a um único especialista), OU
    #   - custo estimado < s4_auto_approval_max_cost_usd
    # AND clarity_score >= s4_auto_approval_min_clarity_score
    # Por padrão OFF — ativar explicitamente quando confortável com autonomia total.
    # Override via .env: S4_AUTONOMOUS_MODE=true
    s4_autonomous_mode: bool = False
    # Score mínimo do Clarity Checkpoint para auto-aprovação (padrão: 4/5 = alta confiança).
    # Override via .env: S4_AUTO_APPROVAL_MIN_CLARITY_SCORE=4
    s4_auto_approval_min_clarity_score: int = 4
    # Custo máximo estimado (USD) para auto-aprovação. Acima disso, sempre pede confirmação.
    # Override via .env: S4_AUTO_APPROVAL_MAX_COST_USD=0.10
    s4_auto_approval_max_cost_usd: float = 0.10

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # --- Campos internos (não carregados do .env) ---
    _available_platforms: ClassVar[list[str]] = []

    # ─── Validators ───────────────────────────────────────────────

    @field_validator("project_id", mode="before")
    @classmethod
    def resolve_project_id(cls, v: str) -> str:
        """
        Resolve project_id:
          - "auto" ou vazio → deriva do nome do diretório atual (Path.cwd().name)
          - qualquer outro valor → usado literalmente

        Normaliza removendo caracteres não-portáteis para nome de arquivo
        (espaços, separadores de path, etc.) para evitar quebra de SQLite paths.
        """
        from pathlib import Path
        import re as _re

        if not v or v.strip().lower() == "auto":
            v = Path.cwd().name or "default"

        # Normaliza: substitui qualquer caractere que não seja [A-Za-z0-9._-] por hífen
        normalized = _re.sub(r"[^A-Za-z0-9._-]+", "-", v.strip()).strip("-")
        return normalized or "default"

    @model_validator(mode="after")
    def derive_memory_db_paths(self) -> "Settings":
        """
        Deriva paths de memória a partir de project_id quando vazios.

        Garante isolamento entre projetos que compartilham o filesystem (ex:
        quando alguém copia data-agents/ → ai-data-agents/, os arquivos não
        ficam misturados).

        Estrutura derivada:
          - memory_data_dir            → memory/data/<project_id>      (subdir)
          - long_term_db_path          → memory/data/long_term__<pid>.db  (raiz)
          - short_term_db_path         → memory/data/short_term__<pid>.db (raiz)
          - embedder_cache_db_path     → memory/data/embedder_cache__<pid>.db (raiz)

        SQLites na raiz pra DBeaver diferenciar via sufixo. Arquivos .md em
        subdir pra `rm -rf memory/data/<pid>/` apagar tudo de um projeto.

        Override manual via .env tem precedência: se o usuário definir
        explicitamente qualquer um desses paths, esse valor ganha.
        """
        # Phase 7: memory/ vive dentro do namespace data_agents/, então os paths
        # default são relativos a data_agents/memory/data/. Override via .env
        # tem precedência (se o usuário quer fora do pacote, ok).
        if not self.memory_data_dir:
            self.memory_data_dir = f"data_agents/memory/data/{self.project_id}"
        if not self.short_term_db_path:
            self.short_term_db_path = f"data_agents/memory/data/short_term__{self.project_id}.db"
        if not self.long_term_db_path:
            self.long_term_db_path = f"data_agents/memory/data/long_term__{self.project_id}.db"
        if not self.embedder_cache_db_path:
            self.embedder_cache_db_path = (
                f"data_agents/memory/data/embedder_cache__{self.project_id}.db"
            )
        return self

    @field_validator(
        "fabric_community_command",
        "fabric_sql_command",
        "databricks_genie_command",
        "fabric_semantic_command",
        "migration_source_command",
        "azure_pricing_command",
        mode="before",
    )
    @classmethod
    def validate_mcp_command(cls, v: str) -> str:
        """Valida que comandos MCP não contêm path separators ou metacaracteres shell."""
        import re as _re

        if not v:
            return v
        # Permite apenas nomes de comando simples: letras, dígitos, hífens, underscores, pontos
        # Bloqueia path separators (/ \), metacaracteres shell (; | & $ ` ( ) < > ! ~ {})
        if not _re.match(r"^[a-zA-Z0-9_./-]+$", v):
            raise ValueError(
                f"Comando MCP inválido: '{v}'. "
                "Use apenas letras, dígitos, hífens, underscores, pontos e barras de path. "
                "Metacaracteres shell (;|&$`()!~{}) não são permitidos."
            )
        # Bloqueia traversal e metacaracteres perigosos
        dangerous = ["..", ";", "|", "&", "$", "`", "(", ")", "<", ">", "!", "~", "{", "}"]
        for char in dangerous:
            if char in v:
                raise ValueError(f"Comando MCP inválido: '{v}' contém caractere proibido '{char}'.")
        return v

    @field_validator("anthropic_api_key")
    @classmethod
    def validate_anthropic_key(cls, v: str) -> str:
        """Valida que a API key (Moonshot/Kimi) está presente e tem formato esperado."""
        if not v or v.startswith("sk-ant-...") or v.startswith("sk-..."):
            warnings.warn(
                "⚠️  ANTHROPIC_API_KEY (chave Moonshot) não configurada. "
                "O sistema não funcionará sem ela. Obtenha em "
                "https://platform.moonshot.ai/console/api-keys e configure no .env.",
                UserWarning,
                stacklevel=2,
            )
        return v

    @field_validator("max_budget_usd")
    @classmethod
    def validate_budget(cls, v: float) -> float:
        """Garante que o budget máximo está dentro de limites razoáveis."""
        if v <= 0:
            raise ValueError("MAX_BUDGET_USD deve ser maior que zero.")
        if v > 100:
            warnings.warn(
                f"⚠️  MAX_BUDGET_USD={v} é muito alto. Considere reduzir para evitar custos inesperados.",
                UserWarning,
                stacklevel=2,
            )
        return v

    @field_validator("max_turns")
    @classmethod
    def validate_max_turns(cls, v: int) -> int:
        """Garante que max_turns está dentro de limites razoáveis."""
        if v < 1:
            raise ValueError("MAX_TURNS deve ser pelo menos 1.")
        if v > 200:
            warnings.warn(
                f"⚠️  MAX_TURNS={v} é muito alto. Sessões longas podem gerar custos elevados.",
                UserWarning,
                stacklevel=2,
            )
        return v

    # ─── Platform Validation ──────────────────────────────────────

    def validate_platform_credentials(self) -> dict[str, dict]:
        """
        Verifica quais plataformas têm credenciais válidas configuradas.

        Returns:
            Dict com status de cada plataforma:
            {
                "anthropic": {"ready": True, "missing": []},
                "databricks": {"ready": False, "missing": ["DATABRICKS_TOKEN"]},
                ...
            }
        """
        platforms: dict[str, _PlatformConfig] = {
            "anthropic": {
                "fields": {"ANTHROPIC_API_KEY": self.anthropic_api_key},
                "required": ["ANTHROPIC_API_KEY"],
            },
            "databricks": {
                "fields": {
                    "DATABRICKS_HOST": self.databricks_host,
                    "DATABRICKS_TOKEN": self.databricks_token,
                    "DATABRICKS_SQL_WAREHOUSE_ID": self.databricks_sql_warehouse_id,
                },
                "required": ["DATABRICKS_HOST", "DATABRICKS_TOKEN"],
            },
            "fabric": {
                "fields": {
                    "AZURE_TENANT_ID": self.azure_tenant_id,
                    "FABRIC_WORKSPACE_ID": self.fabric_workspace_id,
                },
                "required": ["AZURE_TENANT_ID", "FABRIC_WORKSPACE_ID"],
            },
            "fabric_official": {
                # MCP oficial Microsoft — usa cache `az login` local em runtime,
                # não recebe env vars. Gating aqui é apenas indicativo de "setup Fabric
                # existe"; a autenticação real acontece na primeira tool call.
                "fields": {
                    "AZURE_TENANT_ID": self.azure_tenant_id,
                    "FABRIC_WORKSPACE_ID": self.fabric_workspace_id,
                },
                "required": ["AZURE_TENANT_ID", "FABRIC_WORKSPACE_ID"],
            },
            "fabric_sql": {
                # SQL Analytics Endpoint — resolve limitação do schema dbo da REST API
                # Considera configurado se tiver registry OU variáveis legadas
                "fields": {
                    "AZURE_TENANT_ID": self.azure_tenant_id,
                    "FABRIC_SQL_LAKEHOUSES_OR_LEGACY": (
                        self.fabric_sql_lakehouses
                        if self.fabric_sql_lakehouses not in ("{}", "")
                        else self.fabric_sql_endpoint
                    ),
                },
                "required": ["AZURE_TENANT_ID", "FABRIC_SQL_LAKEHOUSES_OR_LEGACY"],
            },
            "databricks_genie": {
                # Reusa credenciais Databricks + pelo menos um space configurado
                "fields": {
                    "DATABRICKS_HOST": self.databricks_host,
                    "DATABRICKS_TOKEN": self.databricks_token,
                    "DATABRICKS_GENIE_SPACES_OR_DEFAULT": (
                        self.databricks_genie_spaces
                        if self.databricks_genie_spaces not in ("{}", "")
                        else self.databricks_genie_default_space
                    ),
                },
                "required": [
                    "DATABRICKS_HOST",
                    "DATABRICKS_TOKEN",
                    "DATABRICKS_GENIE_SPACES_OR_DEFAULT",
                ],
            },
            "fabric_semantic": {
                # Reutiliza credenciais Azure do fabric — considera pronto quando fabric está pronto
                "fields": {
                    "AZURE_TENANT_ID": self.azure_tenant_id,
                    "FABRIC_WORKSPACE_ID": self.fabric_workspace_id,
                },
                "required": ["AZURE_TENANT_ID", "FABRIC_WORKSPACE_ID"],
            },
            "fabric_notebook": {
                # MCP customizado pra notebook ops (create/run/edit determinístico).
                # Reutiliza credenciais Azure do fabric — mesmas do fabric_semantic.
                "fields": {
                    "AZURE_TENANT_ID": self.azure_tenant_id,
                    "AZURE_CLIENT_ID": self.azure_client_id,
                    "AZURE_CLIENT_SECRET": self.azure_client_secret,
                    "FABRIC_WORKSPACE_ID": self.fabric_workspace_id,
                },
                "required": ["AZURE_TENANT_ID", "AZURE_CLIENT_ID", "FABRIC_WORKSPACE_ID"],
            },
            "fabric_onelake": {
                # MCP customizado pra OneLake file ops via DFS API direta.
                # Requer FABRIC_WORKSPACE_NAME (slug do workspace) — DFS API
                # não aceita GUID no path.
                "fields": {
                    "AZURE_TENANT_ID": self.azure_tenant_id,
                    "AZURE_CLIENT_ID": self.azure_client_id,
                    "AZURE_CLIENT_SECRET": self.azure_client_secret,
                    "FABRIC_WORKSPACE_NAME": self.fabric_workspace_name,
                },
                "required": ["AZURE_TENANT_ID", "AZURE_CLIENT_ID", "FABRIC_WORKSPACE_NAME"],
            },
            "fabric_rti": {
                "fields": {
                    "KUSTO_SERVICE_URI": self.kusto_service_uri,
                    "KUSTO_SERVICE_DEFAULT_DB": self.kusto_service_default_db,
                },
                "required": ["KUSTO_SERVICE_URI", "KUSTO_SERVICE_DEFAULT_DB"],
            },
            # ── MCPs externos (sem plataforma de dados própria) ──────────────
            # Context7: sem credenciais obrigatórias no plano free → sempre "ready"
            "context7": {
                "fields": {"_no_credentials_required": "true"},
                "required": [],  # free tier não requer credenciais
            },
            # Tavily: requer API key
            "tavily": {
                "fields": {"TAVILY_API_KEY": self.tavily_api_key},
                "required": ["TAVILY_API_KEY"],
            },
            # GitHub: requer Personal Access Token
            "github": {
                "fields": {"GITHUB_PERSONAL_ACCESS_TOKEN": self.github_personal_access_token},
                "required": ["GITHUB_PERSONAL_ACCESS_TOKEN"],
            },
            # Firecrawl: requer API key
            "firecrawl": {
                "fields": {"FIRECRAWL_API_KEY": self.firecrawl_api_key},
                "required": ["FIRECRAWL_API_KEY"],
            },
            # Postgres: requer connection string
            "postgres": {
                "fields": {"POSTGRES_URL": self.postgres_url},
                "required": ["POSTGRES_URL"],
            },
            # Migration Source: requer registry com ao menos uma fonte configurada
            "migration_source": {
                "fields": {
                    "MIGRATION_SOURCES": (
                        self.migration_sources if self.migration_sources not in ("{}", "") else ""
                    ),
                },
                "required": ["MIGRATION_SOURCES"],
            },
            # Memory MCP: sem credenciais → sempre "ready"
            "memory_mcp": {
                "fields": {"_no_credentials_required": "true"},
                "required": [],
            },
            # Fabric IQ Ontology: auth via Azure CLI (`az login`) — sem env vars
            # adicionais. Considerado sempre "ready" porque está em
            # ALWAYS_ACTIVE_MCPS (config/mcp_servers.py); a autenticação real
            # acontece na primeira tool call e falha graciosamente se faltar
            # `az login`.
            "fabric_ontology": {
                "fields": {"_no_credentials_required": "true"},
                "required": [],
            },
        }

        results: dict[str, dict] = {}

        for platform, config in platforms.items():
            missing = [
                name
                for name in config["required"]
                if not config["fields"].get(name, "").strip()
                or config["fields"].get(name, "").startswith("sk-ant-...")
            ]
            results[platform] = {
                "ready": len(missing) == 0,
                "missing": missing,
            }

        return results

    def get_available_platforms(self) -> list[str]:
        """Retorna lista de plataformas MCP com credenciais válidas."""
        status = self.validate_platform_credentials()
        return [name for name, info in status.items() if info["ready"] and name != "anthropic"]

    def startup_diagnostics(self) -> None:
        """
        Executa diagnóstico completo no startup e emite warnings/errors.
        Chamado uma vez no início da aplicação.
        """
        status = self.validate_platform_credentials()

        # Anthropic é obrigatória
        if not status["anthropic"]["ready"]:
            logger.error(
                "❌ ANTHROPIC_API_KEY não configurada. O sistema não funcionará. "
                "Configure no .env ou como variável de ambiente."
            )

        # Plataformas de dados — pelo menos uma deve estar configurada
        data_platforms = [
            "databricks",
            "databricks_genie",
            "fabric",
            "fabric_sql",
            "fabric_rti",
            "migration_source",
        ]
        any_ready = any(status[p]["ready"] for p in data_platforms)

        if not any_ready:
            logger.warning(
                "⚠️  Nenhuma plataforma de dados configurada. "
                "Configure pelo menos Databricks ou Fabric no .env para usar os MCP servers."
            )

        # Diagnóstico individual
        for platform in data_platforms:
            info = status[platform]
            if info["ready"]:
                logger.info(f"✅ {platform.upper()}: credenciais configuradas.")
            elif info["missing"]:
                logger.warning(
                    f"⚠️  {platform.upper()}: variáveis ausentes: {', '.join(info['missing'])}. "
                    f"MCP server desta plataforma não será ativado."
                )

        # MCPs externos (sem plataforma de dados própria)
        external_mcps = [
            "context7",
            "memory_mcp",
            "fabric_ontology",
            "tavily",
            "github",
            "firecrawl",
            "postgres",
        ]
        for mcp in external_mcps:
            info = status[mcp]
            if info["ready"]:
                logger.info(f"✅ {mcp.upper()}: configurado.")
            elif info["missing"]:
                logger.info(
                    f"ℹ️  {mcp.upper()}: variáveis ausentes: {', '.join(info['missing'])}. "
                    f"Configure no .env para ativar."
                )

        logger.info(
            f"📋 Configuração: model={self.default_model}, "
            f"budget=${self.max_budget_usd}, max_turns={self.max_turns}"
        )


settings = Settings()
