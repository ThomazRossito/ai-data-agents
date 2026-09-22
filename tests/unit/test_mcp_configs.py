"""Testes de configuração dos servidores MCP."""

from data_agents.mcp_servers.databricks.server_config import (
    get_databricks_mcp_config,
    DATABRICKS_MCP_TOOLS,
)
from data_agents.mcp_servers.fabric.server_config import get_fabric_mcp_config, ALL_FABRIC_TOOLS
from data_agents.mcp_servers.fabric_rti.server_config import (
    get_fabric_rti_mcp_config,
    FABRIC_RTI_MCP_TOOLS,
)
from data_agents.mcp_servers.azure_devops.server_config import (
    get_azure_devops_mcp_config,
    AZURE_DEVOPS_MCP_TOOLS,
    AZURE_DEVOPS_MCP_READONLY_TOOLS,
)
from data_agents.config.mcp_servers import build_mcp_registry


def test_databricks_config_has_required_keys():
    config = get_databricks_mcp_config()
    assert "databricks" in config
    server = config["databricks"]
    assert server["type"] == "stdio"
    assert "command" in server
    assert "env" in server


def test_fabric_config_has_community_server():
    """Fabric config deve expor o servidor community (credenciais via .env/pydantic)."""
    config = get_fabric_mcp_config()
    assert "fabric_community" in config
    server = config["fabric_community"]
    assert server["type"] == "stdio"
    assert "command" in server
    assert "env" in server
    # Servidor oficial Microsoft foi removido do config Python —
    # é local-first (sem credenciais) e configurável separadamente via .mcp.json
    assert "fabric" not in config


def test_fabric_rti_config_has_required_keys():
    config = get_fabric_rti_mcp_config()
    assert "fabric_rti" in config
    assert config["fabric_rti"]["type"] == "stdio"


def test_registry_all_platforms():
    # Passa plataformas explícitas para não depender de credenciais do ambiente
    registry = build_mcp_registry(platforms=["databricks", "fabric", "fabric_rti"])
    assert "databricks" in registry
    # "fabric" plataforma → registra "fabric_community" (servidor community Python)
    assert "fabric_community" in registry
    # "fabric" plataforma → registra "fabric_community" (servidor community Python)
    # e também o alias "fabric" para conveniência.
    assert "fabric" in registry
    assert "fabric_rti" in registry


def test_registry_single_platform():
    registry = build_mcp_registry(platforms=["databricks"])
    assert "databricks" in registry
    assert "fabric" not in registry
    assert "fabric_rti" not in registry


def test_databricks_tools_format():
    for tool in DATABRICKS_MCP_TOOLS:
        assert tool.startswith("mcp__databricks__"), f"Tool com prefixo errado: {tool}"


def test_fabric_tools_format():
    for tool in ALL_FABRIC_TOOLS:
        assert tool.startswith("mcp__fabric"), f"Tool com prefixo errado: {tool}"


def test_rti_tools_format():
    for tool in FABRIC_RTI_MCP_TOOLS:
        assert tool.startswith("mcp__fabric_rti__"), f"Tool com prefixo errado: {tool}"


def test_azure_devops_config_has_required_keys():
    config = get_azure_devops_mcp_config()
    assert "azure_devops" in config
    server = config["azure_devops"]
    assert server["type"] == "stdio"
    assert server["command"] == "npx"
    assert "@azure-devops/mcp" in server["args"]
    assert "env" in server
    assert "PERSONAL_ACCESS_TOKEN" in server["env"]


def test_azure_devops_tools_format():
    for tool in AZURE_DEVOPS_MCP_TOOLS:
        assert tool.startswith("mcp__azure_devops__"), f"Tool com prefixo errado: {tool}"


def test_azure_devops_readonly_is_subset():
    tools = set(AZURE_DEVOPS_MCP_TOOLS)
    for tool in AZURE_DEVOPS_MCP_READONLY_TOOLS:
        assert tool in tools, f"Readonly tool ausente do conjunto completo: {tool}"


def test_azure_devops_not_in_default_registry_without_credentials():
    # azure_devops requer credenciais reais — não deve aparecer se explicitamente
    # não incluído na lista de plataformas ativas.
    registry = build_mcp_registry(platforms=["databricks"])
    assert "azure_devops" not in registry


# ─── databricks_sql: MCP GERENCIADO (HTTP) — auditoria 2026-09-13 ────────────
# Primeiro MCP não-stdio do projeto. Tools enumeradas ao vivo contra o
# workspace via JSON-RPC `tools/list`, não copiadas de documentação.


def test_databricks_sql_uses_http_transport():
    """Managed MCP é HTTP, não stdio: {type, url, headers} sem command/args."""
    from data_agents.mcp_servers.databricks_sql.server_config import (
        get_databricks_sql_mcp_config,
    )

    cfg = get_databricks_sql_mcp_config()["databricks_sql"]
    assert cfg["type"] == "http"
    assert "url" in cfg and "headers" in cfg
    assert "command" not in cfg, "config HTTP não deve ter 'command' (isso é stdio)"
    assert "args" not in cfg, "config HTTP não deve ter 'args' (isso é stdio)"


def test_databricks_sql_url_is_well_formed(monkeypatch):
    """A URL precisa ser o endpoint gerenciado, sem barra dupla."""
    from data_agents.config.settings import settings
    from data_agents.mcp_servers.databricks_sql.server_config import (
        get_databricks_sql_mcp_config,
    )

    # com barra final e com esquema
    monkeypatch.setattr(settings, "databricks_host", "https://adb-123.azuredatabricks.net/")
    url = get_databricks_sql_mcp_config()["databricks_sql"]["url"]
    assert url == "https://adb-123.azuredatabricks.net/api/2.0/mcp/sql"
    assert "//api" not in url.replace("https://", ""), "barra dupla na URL"

    # sem esquema — deve ser normalizado para https
    monkeypatch.setattr(settings, "databricks_host", "adb-123.azuredatabricks.net")
    url = get_databricks_sql_mcp_config()["databricks_sql"]["url"]
    assert url.startswith("https://")


def test_databricks_sql_auth_is_bearer_header(monkeypatch):
    """PAT vai no header Authorization, não em argv (não vaza em ps/argv)."""
    from data_agents.config.settings import settings
    from data_agents.mcp_servers.databricks_sql.server_config import (
        get_databricks_sql_mcp_config,
    )

    monkeypatch.setattr(settings, "databricks_token", "dapi-TESTE")
    cfg = get_databricks_sql_mcp_config()["databricks_sql"]
    assert cfg["headers"]["Authorization"] == "Bearer dapi-TESTE"


def test_databricks_sql_tools_format():
    from data_agents.mcp_servers.databricks_sql.server_config import (
        DATABRICKS_SQL_MCP_TOOLS,
    )

    assert DATABRICKS_SQL_MCP_TOOLS, "lista de tools não pode estar vazia"
    for tool in DATABRICKS_SQL_MCP_TOOLS:
        assert tool.startswith("mcp__databricks_sql__"), tool


def test_databricks_sql_readonly_excludes_destructive_tool():
    """
    O servidor anota `execute_sql` com destructiveHint=true e
    `execute_sql_read_only` com readOnlyHint=true. O alias readonly precisa
    honrar isso — senão 'somente leitura' volta a depender só dos nossos hooks.
    """
    from data_agents.mcp_servers.databricks_sql.server_config import (
        DATABRICKS_SQL_MCP_READONLY_TOOLS,
        DATABRICKS_SQL_MCP_TOOLS,
    )

    assert "mcp__databricks_sql__execute_sql" not in DATABRICKS_SQL_MCP_READONLY_TOOLS
    assert "mcp__databricks_sql__execute_sql_read_only" in DATABRICKS_SQL_MCP_READONLY_TOOLS
    assert set(DATABRICKS_SQL_MCP_READONLY_TOOLS).issubset(set(DATABRICKS_SQL_MCP_TOOLS))


def test_databricks_sql_aliases_registered_in_loader():
    from data_agents.agents.loader import MCP_TOOL_SETS

    assert "databricks_sql_all" in MCP_TOOL_SETS
    assert "databricks_sql_readonly" in MCP_TOOL_SETS


def test_databricks_sql_not_active_without_credentials(monkeypatch):
    """Sem HOST/TOKEN o MCP não deve ser ativado (evita erro silencioso no startup)."""
    from data_agents.config.settings import settings

    monkeypatch.setattr(settings, "databricks_host", "")
    monkeypatch.setattr(settings, "databricks_token", "")
    status = settings.validate_platform_credentials()
    assert status["databricks_sql"]["ready"] is False


# ─── tavily (hotfix 2026-09-15) ──────────────────────────────────────────────


def test_tavily_usa_o_pacote_oficial_npm_pinado():
    """A config antiga era `uvx tavily-mcp`. O pacote PyPI com esse nome NÃO é o da
    Tavily e não expõe executável `tavily-mcp` (expõe check/mcp/tavily) — o
    servidor nunca subiu e `mcp__tavily__*` nunca apareceu em audit.jsonl.
    O oficial é o npm `tavily-mcp` (github.com/tavily-ai/tavily-mcp)."""
    from data_agents.mcp_servers.tavily.server_config import (
        TAVILY_MCP_NPM_VERSION,
        get_tavily_mcp_config,
    )

    cfg = get_tavily_mcp_config()["tavily"]
    assert cfg["type"] == "stdio"
    assert cfg["command"] == "npx", (
        "uvx tavily-mcp aponta para um pacote PyPI que não é o da Tavily"
    )
    assert cfg["args"][0] == "-y"
    assert cfg["args"][1] == f"tavily-mcp@{TAVILY_MCP_NPM_VERSION}", (
        "versão pinada, política do projeto"
    )
    assert "@latest" not in cfg["args"][1]
    assert "TAVILY_API_KEY" in cfg["env"]


def test_tavily_tools_batem_com_o_servidor_oficial():
    """Os nomes REAIS do servidor npm são underscore (`tavily_search`), não hífen
    como o README sugere. Snapshot em tests/fixtures/tavily_mcp_tools.txt
    (extraído do build do pacote). Foi o hífen que deixou o especialista sem
    tavily mesmo com o servidor conectado (2ª rodada do eval, 2026-09-15)."""
    from pathlib import Path

    from data_agents.mcp_servers.tavily.server_config import TAVILY_MCP_TOOLS, TAVILY_TOOL_PREFIX

    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "tavily_mcp_tools.txt"
    oficiais = {
        f"{TAVILY_TOOL_PREFIX}{ln.strip()}"
        for ln in fixture.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    }
    assert oficiais, "fixture vazio"
    sobrando = set(TAVILY_MCP_TOOLS) - oficiais
    assert not sobrando, f"tools que o servidor oficial NÃO registra: {sorted(sobrando)}"
    assert "mcp__tavily__tavily_search" in TAVILY_MCP_TOOLS
    assert not any("-" in t.split("__")[-1] for t in TAVILY_MCP_TOOLS), "hífen de novo não"


def test_tavily_alias_do_loader_usa_os_nomes_reais():
    """O alias `tavily_all` é o que entra no `tools:` dos agentes — é ELE que
    decide se o subagente enxerga a tool."""
    from data_agents.agents.loader import MCP_TOOL_SETS

    assert "mcp__tavily__tavily_search" in MCP_TOOL_SETS["tavily_all"]
    assert "mcp__tavily__tavily-search" not in MCP_TOOL_SETS["tavily_all"]
