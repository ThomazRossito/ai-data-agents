"""
Hook de segurança — bloqueia comandos Bash potencialmente destrutivos e queries SQL de alto custo.
Aplicado como PreToolUse no Supervisor.

Implementa:
  - Regex com word boundaries para detecção precisa de comandos destrutivos
  - Detecção de padrões de evasão (base64, eval, xargs, hex encoding)
  - Bloqueio de pipe chains suspeitas
  - Detecção de queries SQL de alto custo: SELECT * sem WHERE/LIMIT (full table scan)
"""

import re
from typing import Any


# ─── Padrões destrutivos com regex (word boundaries) ──────────────

DESTRUCTIVE_PATTERNS: list[re.Pattern] = [
    # Filesystem destruction
    re.compile(r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/", re.IGNORECASE),
    re.compile(r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?~", re.IGNORECASE),
    re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f", re.IGNORECASE),
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r">\s*/dev/sd[a-z]", re.IGNORECASE),
    re.compile(r"\bdd\s+.*of=/dev/", re.IGNORECASE),
    re.compile(r"\bformat\s+[cC]:", re.IGNORECASE),
    # SQL destructive operations
    re.compile(r"\bDROP\s+(DATABASE|CATALOG|SCHEMA|TABLE|VIEW|FUNCTION)\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
    re.compile(r"\bALTER\s+TABLE\s+\S+\s+DROP\b", re.IGNORECASE),
    # Dangerous system commands
    re.compile(r"\bchmod\s+(-[a-zA-Z]+\s+)?777\s+/", re.IGNORECASE),
    re.compile(r"\bchown\s+(-[a-zA-Z]+\s+)?\S+\s+/", re.IGNORECASE),
    re.compile(r"\bkill\s+-9\s+-1\b", re.IGNORECASE),
    re.compile(r"\bshutdown\b", re.IGNORECASE),
    re.compile(r"\breboot\b", re.IGNORECASE),
    re.compile(r":\(\)\{.*?:\|.*?&.*?\};:", re.IGNORECASE),  # fork bomb
    # Git destructive operations
    re.compile(r"\bgit\s+push\s+.*--force\b", re.IGNORECASE),
    re.compile(r"\bgit\s+push\s+.*-f\b", re.IGNORECASE),
    re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE),
    re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*f", re.IGNORECASE),
    re.compile(r"\bgit\s+branch\s+-[a-zA-Z]*D\b"),  # force delete branch (-D only, case-sensitive)
]

# ─── Padrões de evasão (tentativas de bypass) ────────────────────

EVASION_PATTERNS: list[re.Pattern] = [
    # Base64 encoding para esconder comandos
    re.compile(r"\bbase64\s+(-d|--decode)\b", re.IGNORECASE),
    re.compile(r"\becho\s+\S+\s*\|\s*base64\s+(-d|--decode)", re.IGNORECASE),
    # eval / exec para execução dinâmica
    re.compile(r"\beval\s+", re.IGNORECASE),
    re.compile(r"\$\(\s*echo\s+.*\)", re.IGNORECASE),
    # xargs com comandos perigosos
    re.compile(r"\bxargs\s+.*\brm\b", re.IGNORECASE),
    re.compile(r"\bxargs\s+.*\bkill\b", re.IGNORECASE),
    # Hex/octal encoding
    re.compile(r"\\x[0-9a-fA-F]{2}", re.IGNORECASE),
    re.compile(r"\$'\\x", re.IGNORECASE),
    # Curl/wget piped to shell
    re.compile(r"\b(curl|wget)\s+.*\|\s*(bash|sh|zsh)\b", re.IGNORECASE),
    # Python/Perl/Ruby one-liners para bypass
    re.compile(r"\bpython[23]?\s+-c\s+.*import\s+os", re.IGNORECASE),
    re.compile(r"\bperl\s+-e\s+.*system\(", re.IGNORECASE),
]


# ─── Detecção de queries SQL de alto custo ───────────────────────

#: Padrão que captura SQL inline em comandos Bash (spark-sql -e, databricks query, etc.)
_SQL_IN_BASH = re.compile(
    r"(?:spark-sql\s+-e|beeline\s+-e|databricks\s+query\s+execute|bq\s+query)\s+"
    r"""(?P<q>["'](.+?)["'])""",
    re.IGNORECASE | re.DOTALL,
)

#: Campos de tool_input que podem carregar SQL — direto ou embutido em código.
#:
#: IMPORTANTE: inclui ``code``/``script``/``source`` porque tools de execução de
#: código (ex.: ``mcp__databricks__execute_code``) recebem o SQL dentro de um
#: programa (``spark.sql("DROP TABLE ...")``). Sem esses campos, essas tools
#: escapavam de TODA inspeção: ``block_destructive_commands`` só olha Bash e
#: ``check_sql_cost`` só olhava ``query``/``sql``/``statement``.
_SQL_TOOL_FIELDS = (
    "query",
    "sql",
    "statement",
    "statements",
    "sql_query",
    "code",
    "script",
    "source",
)


def _collect_sql_candidates(tool_input: dict) -> list[str]:
    """
    Coleta TODOS os valores inspecionáveis de ``tool_input``.

    Difere da versão anterior em dois pontos que eram bypass:

    1. **Varre todos os campos** em vez de parar no primeiro não-vazio. Uma tool
       pode receber ``sql`` benigno e ``statements`` destrutivo no mesmo payload.
    2. **Aceita listas/tuplas** de strings, não só ``str``. Valores não-string
       eram silenciosamente ignorados.
    """
    candidates: list[str] = []
    for field in _SQL_TOOL_FIELDS:
        value = tool_input.get(field)
        if isinstance(value, str):
            if value.strip():
                candidates.append(value)
        elif isinstance(value, (list, tuple)):
            candidates.extend(item for item in value if isinstance(item, str) and item.strip())
    return candidates


# ─── DDL destrutivo em tools SQL (MCP / direto) ─────────────────

#: Operações DDL/DML que requerem confirmação explícita antes de executar
_DESTRUCTIVE_SQL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"\bDROP\s+(DATABASE|CATALOG|SCHEMA|TABLE|VIEW|FUNCTION|PROCEDURE)\b", re.IGNORECASE
        ),
        "DROP detectado — esta operação é irreversível. Confirme com o usuário antes de executar.",
    ),
    (
        re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE),
        "TRUNCATE TABLE detectado — apaga todos os dados da tabela de forma irreversível. Confirme com o usuário.",
    ),
    (
        re.compile(r"\bDELETE\s+FROM\b(?!.*\bWHERE\b)", re.IGNORECASE | re.DOTALL),
        "DELETE FROM sem WHERE detectado — apagaria todos os registros da tabela. Adicione uma cláusula WHERE.",
    ),
    (
        re.compile(r"\bALTER\s+TABLE\s+\S+\s+DROP\s+(COLUMN|PARTITION)\b", re.IGNORECASE),
        "ALTER TABLE DROP detectado — remoção de coluna ou partição é irreversível. Confirme com o usuário.",
    ),
]


# ─── Ações destrutivas em tools "action-dispatch" ────────────────

#: Valores do campo ``action`` que executam operação irreversível.
#:
#: POR QUE ISTO EXISTE (auditoria 2026-09-13):
#: MCP servers modernos consolidam dezenas de operações em poucas tools, usando
#: um argumento ``action`` para escolher a operação — por exemplo
#: ``manage_pipeline(action="delete")`` ou ``manage_uc_objects(action="drop")``.
#:
#: O ``allowed_tools`` do Agent SDK filtra por **nome de tool**, e o nome
#: (``manage_pipeline``) é benigno. Logo, a granularidade de permissão
#: DESAPARECE: um agente com o alias ``databricks_all`` poderia deletar um
#: pipeline de produção sem que nenhum hook visse.
#:
#: Este hook devolve a granularidade, inspecionando o valor de ``action``.
#:
#: CASAMENTO POR VERBO, NÃO POR STRING EXATA (correção 2026-09-14)
#: A primeira versão comparava ``action in _DESTRUCTIVE_ACTIONS`` — string
#: exata. Ao adotar o servidor do ai-dev-kit e ler o vocabulário REAL de actions
#: no fonte dele, apareceram estes, que passavam ilesos:
#:
#:     manage_uc_security_policies  drop_column_mask, drop_row_filter
#:     manage_uc_sharing            remove_table, revoke_from_recipient, rotate_token
#:     manage_cluster               terminate
#:
#: A regra agora é: o **primeiro token** da action (antes do primeiro ``_``) é o
#: verbo, e é ele que se compara. ``drop_column_mask`` → ``drop`` → bloqueado.
#: A action inteira também é comparada, para verbos sem sufixo e para os que
#: não são prefixo (``rotate_token`` é destrutivo para o token antigo).
_DESTRUCTIVE_VERBS: frozenset[str] = frozenset(
    {
        "delete",
        "drop",
        "destroy",
        "remove",
        "purge",
        "truncate",
        "revoke",
        # Cluster em execução: mata trabalho em andamento. `stop` de pipeline
        # NÃO entra — parar um pipeline descontrolado é ação de segurança
        # legítima e reiniciável; bloquear seria pior que permitir.
        "terminate",
    }
)

#: Actions destrutivas cujo verbo NÃO é o primeiro token.
_DESTRUCTIVE_EXACT: frozenset[str] = frozenset(
    {
        "rotate_token",  # invalida o token vigente de um recipient Delta Sharing
    }
)

#: Mantido por compatibilidade com testes e leitores antigos — é a união.
_DESTRUCTIVE_ACTIONS: frozenset[str] = _DESTRUCTIVE_VERBS | _DESTRUCTIVE_EXACT


def _action_is_destructive(action: str) -> bool:
    """True se a action, ou seu verbo-prefixo, for destrutiva."""
    verbo_completo = action.strip().lower()
    if not verbo_completo:
        return False
    if verbo_completo in _DESTRUCTIVE_EXACT or verbo_completo in _DESTRUCTIVE_VERBS:
        return True
    prefixo = verbo_completo.split("_", 1)[0]
    return prefixo in _DESTRUCTIVE_VERBS


#: Campos que carregam o verbo da operação em tools action-dispatch.
_ACTION_FIELDS = ("action", "operation", "op", "mode")


async def check_destructive_action(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
) -> dict[str, Any]:
    """
    Bloqueia tools ``action-dispatch`` quando o verbo é destrutivo.

    Complementa ``check_sql_cost``: aquele inspeciona o SQL, este inspeciona a
    intenção declarada no argumento. Sem ele, a migração para MCP servers com
    tools consolidadas removeria silenciosamente o controle por tool.
    """
    if not input_data or not isinstance(input_data, dict):
        return {}

    tool_input: dict = input_data.get("tool_input", {}) or {}
    if not isinstance(tool_input, dict):
        return {}

    tool_name: str = input_data.get("tool_name", "") or ""

    for field in _ACTION_FIELDS:
        value = tool_input.get(field)
        if not isinstance(value, str):
            continue
        verbo = value.strip().lower()
        if _action_is_destructive(verbo):
            alvo = (
                tool_input.get("name")
                or tool_input.get("full_name")
                or tool_input.get("path")
                or tool_input.get("id")
                or "(alvo não informado)"
            )
            return _deny(
                f"Ação destrutiva bloqueada — '{tool_name}' foi chamada com "
                f"{field}='{verbo}' sobre {alvo}. Operações irreversíveis exigem "
                f"confirmação explícita do usuário antes de executar. "
                f"Se a intenção for real, peça a confirmação e explique o impacto."
            )

    return {}


# ─── Escrita em caminhos sensíveis ───────────────────────────────

#: Caminhos que um agente nunca deve sobrescrever.
#:
#: Denylist (não allowlist) por decisão: os agentes geram artefatos em muitos
#: lugares legítimos, e restringir a `output/` quebraria fluxos válidos. Aqui
#: bloqueamos só o que não tem motivo nenhum para ser reescrito por um agente
#: no meio de uma sessão.
#:
#: Adicionado pela auditoria 2026-09-13: `Write` estava na allowlist do
#: Supervisor e não havia NENHUM HookMatcher de PreToolUse para ele — escrita
#: em qualquer caminho era livre.
_PROTECTED_WRITE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"(^|/)\.env(\.|$)"),
        "arquivo de credenciais (.env) — edite manualmente; segredos nunca "
        "devem ser escritos por um agente (viola S5).",
    ),
    (
        re.compile(r"(^|/)\.git/"),
        "diretório interno do Git — sobrescrever corrompe o repositório.",
    ),
    (
        re.compile(r"(^|/)\.github/workflows/"),
        "workflow de CI/CD — alterar o pipeline de validação a partir de um "
        "agente remove a própria rede de segurança. Edite via PR revisada.",
    ),
    (
        re.compile(r"(^|/)data_agents/"),
        "código-fonte do framework — o agente deve gerar artefatos em `output/`, "
        "não reescrever o sistema que o executa.",
    ),
    (
        re.compile(r"(^|/)\.claude/"),
        "configuração do Claude Code — alteração deve ser deliberada e revisada.",
    ),
    (
        re.compile(r"(^|/)(id_rsa|id_ed25519|\.ssh/|\.aws/credentials|\.databrickscfg)"),
        "credencial de sistema — nunca deve ser escrita por um agente (viola S5).",
    ),
]

#: Tools que escrevem em disco e devem ser inspecionadas.
_WRITE_TOOLS = frozenset({"Write", "Edit", "NotebookEdit"})

#: Campos de tool_input que carregam o caminho de destino.
_PATH_FIELDS = ("file_path", "path", "notebook_path", "filename")


def _detect_protected_write(path: str) -> tuple[bool, str]:
    """Verifica se um caminho de escrita cai em área protegida."""
    normalized = path.replace("\\", "/")
    for pattern, reason in _PROTECTED_WRITE_PATTERNS:
        if pattern.search(normalized):
            return True, reason
    return False, ""


async def block_sensitive_writes(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
) -> dict[str, Any]:
    """
    Bloqueia escrita em caminhos críticos (PreToolUse em Write/Edit/NotebookEdit).

    Denylist deliberada — ver ``_PROTECTED_WRITE_PATTERNS``. Tools que não
    escrevem em disco passam sem interferência.
    """
    if not input_data or not isinstance(input_data, dict):
        return {}

    if input_data.get("tool_name") not in _WRITE_TOOLS:
        return {}

    tool_input: dict = input_data.get("tool_input", {}) or {}

    for field in _PATH_FIELDS:
        value = tool_input.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        blocked, reason = _detect_protected_write(value)
        if blocked:
            return _deny(f"Escrita bloqueada em '{value}' — {reason}")

    return {}


def _detect_destructive_sql(sql: str) -> tuple[bool, str]:
    """
    Verifica se uma string SQL contém DDL/DML destrutivo.

    Retorna (bloqueado: bool, motivo: str).
    Aplicado a tools SQL (MCP e diretas), não só ao Bash.
    """
    for pattern, reason in _DESTRUCTIVE_SQL_PATTERNS:
        if pattern.search(sql):
            return True, reason
    return False, ""


# ─── Padrões SQL adicionais de segurança ────────────────────────

# WHERE trivial (sempre verdadeiro — bypass de filtro)
_TRIVIAL_WHERE = re.compile(
    r"\bWHERE\s+(?:1\s*=\s*1|'[^']*'\s*=\s*'[^']*'|TRUE\b)",
    re.IGNORECASE,
)

# UNION SELECT — extração de dados de outra tabela
_UNION_SELECT = re.compile(r"\bUNION\s+(?:ALL\s+)?SELECT\b", re.IGNORECASE)

# OR trivial (bypass de WHERE: "... OR 1=1")
_OR_TRIVIAL = re.compile(r"\bOR\s+(?:1\s*=\s*1|TRUE\b)", re.IGNORECASE)

# Multi-statement (separados por ponto-e-vírgula com keywords SQL)
_MULTI_STATEMENT = re.compile(
    r";\s*(?:SELECT|INSERT|UPDATE|DELETE|DROP|TRUNCATE|CREATE|ALTER|EXEC)\b",
    re.IGNORECASE,
)


def _detect_expensive_sql(sql: str) -> tuple[bool, str]:
    """
    Analisa uma string SQL e sinaliza padrões de alto custo de computação.

    Retorna (bloqueado: bool, motivo: str).

    Padrões detectados
    ------------------
    1. SELECT * sem WHERE **e** sem LIMIT/TOP → full table scan garantido.
    2. SELECT * sem LIMIT/TOP → pode retornar toda a tabela mesmo com WHERE parcial.
    3. WHERE trivial (WHERE 1=1, OR 1=1) → bypassa filtros de linha.
    4. UNION SELECT → pode extrair dados de outras tabelas.
    5. Multi-statement (;SELECT, ;DROP) → operação combinada não autorizada.
    """
    s = sql.upper().strip()

    if not s or "SELECT" not in s or "FROM" not in s:
        return False, ""

    # Ignora statements que não retornam dados ao agente (INSERT...SELECT, CTAS, MERGE, etc.)
    leading = re.match(r"\b(\w+)\b", s)
    if leading and leading.group(1) in ("INSERT", "CREATE", "MERGE", "UPDATE", "REPLACE"):
        return False, ""

    # Multi-statement: sempre bloqueia
    if _MULTI_STATEMENT.search(sql):
        return (
            True,
            "Query com múltiplos statements (;SELECT, ;DROP, etc.) não é permitida. "
            "Execute cada statement separadamente.",
        )

    # UNION SELECT: pode vazar dados de outras tabelas
    if _UNION_SELECT.search(sql):
        return (
            True,
            "UNION SELECT detectado — pode extrair dados de outras tabelas. "
            "Use subqueries explícitas se precisar combinar resultados.",
        )

    has_star = bool(re.search(r"\bSELECT\s+\*", s))
    has_where = bool(re.search(r"\bWHERE\b", s))
    has_limit = bool(re.search(r"\bLIMIT\b", s))
    has_top = bool(re.search(r"\bSELECT\s+TOP\s+\d+\b", s))  # T-SQL / Fabric style

    # WHERE trivial ou OR trivial: trata como se não tivesse filtro
    has_trivial_where = bool(_TRIVIAL_WHERE.search(sql)) or bool(_OR_TRIVIAL.search(sql))
    has_real_where = has_where and not has_trivial_where

    has_row_filter = has_real_where or has_limit or has_top

    if has_trivial_where:
        return (
            True,
            "Condição WHERE trivial detectada (WHERE 1=1 / OR 1=1 / OR TRUE). "
            "Substitua por um filtro real de partição ou condição de negócio.",
        )

    if has_star and not has_real_where and not has_limit and not has_top:
        return (
            True,
            "SELECT * sem WHERE e sem LIMIT pode escanear TBs de dados em tabelas de produção. "
            "Use: SELECT col1, col2 FROM tabela WHERE particao = 'valor' LIMIT 1000",
        )

    if has_star and not has_row_filter:
        return (
            True,
            "SELECT * sem LIMIT/TOP pode retornar milhões de linhas. "
            "Adicione LIMIT <n> ou selecione apenas as colunas necessárias.",
        )

    # SELECT genérico sem qualquer filtro de linha (não necessariamente SELECT *)
    has_any_select = bool(re.search(r"\bSELECT\b", s))
    if has_any_select and not has_row_filter:
        has_group = bool(re.search(r"\bGROUP\s+BY\b", s))
        if not has_group:
            return (
                True,
                "Query SELECT sem WHERE, LIMIT ou GROUP BY pode escanear toda a tabela. "
                "Adicione filtros de partição ou LIMIT para evitar custos desnecessários.",
            )

    return False, ""


async def check_sql_cost(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
) -> dict[str, Any]:
    """
    Detecta e bloqueia queries SQL de alto custo de computação.

    Verifica dois tipos de chamada:
    - **Bash**: extrai SQL inline de comandos spark-sql, beeline, databricks query, bq query.
    - **Tools SQL diretas**: qualquer tool cujo tool_input contenha campos ``query``,
      ``sql`` ou ``statement`` (ex: execute_query, run_statement, mcp SQL tools).
    """
    if not input_data or not isinstance(input_data, dict):
        return {}

    tool_name: str = input_data.get("tool_name", "")
    tool_input: dict = input_data.get("tool_input", {}) or {}

    sql_candidates: list[str] = []

    if tool_name == "Bash":
        command: str = tool_input.get("command", "")
        m = _SQL_IN_BASH.search(command)
        if m:
            sql_candidates = [m.group("q").strip("'\"")]
    else:
        sql_candidates = _collect_sql_candidates(tool_input)

    if not sql_candidates:
        return {}

    # Cada candidato é inspecionado: basta UM ser destrutivo/caro para negar.
    for sql_candidate in sql_candidates:
        # 1. DDL destrutivo — bloqueia antes de verificar custo (prioridade máxima)
        blocked, reason = _detect_destructive_sql(sql_candidate)
        if blocked:
            return _deny(f"SQL bloqueado — operação destrutiva detectada: {reason}")

        # 2. SELECT de alto custo
        blocked, reason = _detect_expensive_sql(sql_candidate)
        if blocked:
            return _deny(f"Query bloqueada — alto custo detectado: {reason}")

    return {}


async def block_destructive_commands(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
) -> dict[str, Any]:
    """
    Bloqueia comandos Bash que contêm padrões destrutivos ou de evasão.

    Retorna deny com mensagem explicativa se algum padrão for detectado.
    Para comandos não-Bash, retorna {} sem interferir.
    """
    # Proteção contra eventos de teardown do SDK
    if not input_data or not isinstance(input_data, dict):
        return {}

    if input_data.get("tool_name") != "Bash":
        return {}

    command: str = input_data.get("tool_input", {}).get("command", "")

    if not command.strip():
        return {}

    # Verificar padrões destrutivos
    for pattern in DESTRUCTIVE_PATTERNS:
        match = pattern.search(command)
        if match:
            return _deny(
                f"Comando bloqueado: padrão destrutivo detectado '{match.group()}'. "
                f"Confirme com o usuário antes de executar operações destrutivas."
            )

    # Verificar padrões de evasão
    for pattern in EVASION_PATTERNS:
        match = pattern.search(command)
        if match:
            return _deny(
                f"Comando bloqueado: possível tentativa de evasão detectada '{match.group()}'. "
                f"Comandos com encoding, eval ou pipe para shell são proibidos por segurança."
            )

    return {}


def _deny(reason: str) -> dict[str, Any]:
    """Helper para construir resposta de deny padronizada."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
