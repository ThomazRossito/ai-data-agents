"""Testes de validação do config/settings.py."""

import pytest
from data_agents.config.settings import Settings


class TestSettingsValidation:
    """Testes para validação de configurações."""

    def test_default_values(self):
        """Verifica que os valores padrão são razoáveis."""
        # Instancia com valores explícitos para ignorar .env do ambiente CI
        s = Settings(
            anthropic_api_key="test-key",
            default_model="kimi-k2.6",
            max_budget_usd=5.0,
            max_turns=50,
            log_level="INFO",
        )
        assert s.max_budget_usd == 5.0
        assert s.max_turns == 50
        assert s.log_level == "INFO"
        assert s.default_model == "kimi-k2.6"

    def test_budget_must_be_positive(self):
        """Verifica que budget negativo ou zero é rejeitado."""
        with pytest.raises(ValueError, match="maior que zero"):
            Settings(max_budget_usd=0)

        with pytest.raises(ValueError, match="maior que zero"):
            Settings(max_budget_usd=-1.0)

    def test_max_turns_must_be_positive(self):
        """Verifica que max_turns menor que 1 é rejeitado."""
        with pytest.raises(ValueError, match="pelo menos 1"):
            Settings(max_turns=0)

    def test_high_budget_emits_warning(self):
        """Verifica que budget alto emite warning."""
        with pytest.warns(UserWarning, match="muito alto"):
            Settings(max_budget_usd=150.0)

    def test_high_turns_emits_warning(self):
        """Verifica que max_turns alto emite warning."""
        with pytest.warns(UserWarning, match="muito alto"):
            Settings(max_turns=300)


class TestPlatformCredentials:
    """Testes para validação de credenciais por plataforma."""

    def test_no_credentials_returns_not_ready(self):
        """Sem credenciais, nenhuma plataforma de dados deve estar ready."""
        # Força TODOS os campos de credencial a string vazia para isolar do .env local.
        # Inclui os novos MCPs externos para garantir que o teste não vaze credenciais reais.
        s = Settings(
            databricks_host="",
            databricks_token="",
            databricks_sql_warehouse_id="",
            azure_tenant_id="",
            azure_client_id="",
            azure_client_secret="",
            fabric_workspace_id="",
            kusto_service_uri="",
            kusto_service_default_db="",
            # MCPs externos — explicitamente vazios para isolar do .env
            tavily_api_key="",
            github_personal_access_token="",
            firecrawl_api_key="",
            postgres_url="",
            # Migration source — sem fontes configuradas
            migration_sources="{}",
            migration_default_source="",
        )
        status = s.validate_platform_credentials()
        # MCPs sem credenciais obrigatórias são sempre ready — excluídos desta verificação.
        # context7: plano free não requer credenciais (repos públicos).
        # memory_mcp: knowledge graph local, sem autenticação.
        # fabric_ontology: auth via Azure CLI (az login), sem env vars extras.
        # azure_pricing: Azure Retail Prices API é pública, sem auth.
        CREDENTIAL_FREE_MCPS = {
            "context7",
            "memory_mcp",
            "fabric_ontology",
            "azure_pricing",
        }
        for platform, info in status.items():
            if platform != "anthropic" and platform not in CREDENTIAL_FREE_MCPS:
                assert not info["ready"], f"{platform} deveria estar not ready"

    def test_databricks_ready_with_credentials(self):
        """Com host e token, Databricks deve estar ready."""
        s = Settings(
            databricks_host="https://adb-123.azuredatabricks.net",
            databricks_token="dapi12345",
        )
        status = s.validate_platform_credentials()
        assert status["databricks"]["ready"]
        assert status["databricks"]["missing"] == []

    def test_databricks_not_ready_without_token(self):
        """Sem token, Databricks não deve estar ready."""
        # Força token vazio para isolar do ambiente de CI (que pode ter DATABRICKS_TOKEN)
        s = Settings(
            databricks_host="https://adb-123.azuredatabricks.net",
            databricks_token="",
        )
        status = s.validate_platform_credentials()
        assert not status["databricks"]["ready"]
        assert "DATABRICKS_TOKEN" in status["databricks"]["missing"]

    def test_fabric_ready_with_credentials(self):
        """Com tenant_id e workspace_id, Fabric deve estar ready."""
        s = Settings(
            azure_tenant_id="tenant-123",
            fabric_workspace_id="ws-456",
        )
        status = s.validate_platform_credentials()
        assert status["fabric"]["ready"]

    def test_fabric_semantic_ready_with_azure_credentials(self):
        """fabric_semantic pronto quando tenant_id e workspace_id configurados."""
        s = Settings(
            azure_tenant_id="tenant-123",
            fabric_workspace_id="ws-456",
        )
        status = s.validate_platform_credentials()
        assert status["fabric_semantic"]["ready"]

    def test_fabric_semantic_shares_fabric_credentials(self):
        """fabric_semantic not ready quando credenciais Azure ausentes."""
        s = Settings(azure_tenant_id="", fabric_workspace_id="")
        status = s.validate_platform_credentials()
        assert not status["fabric_semantic"]["ready"]

    def test_get_available_platforms_filters_correctly(self):
        """Apenas plataformas com credenciais devem aparecer."""
        # Passa explicitamente credenciais de Fabric/RTI como vazias para isolar
        # o teste do .env local (que pode ter credenciais reais preenchidas)
        s = Settings(
            databricks_host="https://adb-123.azuredatabricks.net",
            databricks_token="dapi12345",
            azure_tenant_id="",
            azure_client_id="",
            azure_client_secret="",
            fabric_workspace_id="",
            kusto_service_uri="",
            kusto_service_default_db="",
        )
        available = s.get_available_platforms()
        assert "databricks" in available
        assert "fabric" not in available
        assert "fabric_rti" not in available

    def test_fabric_official_ready_with_azure_credentials(self):
        """fabric_official pronto quando tenant_id e workspace_id configurados."""
        s = Settings(
            azure_tenant_id="tenant-123",
            fabric_workspace_id="ws-456",
        )
        status = s.validate_platform_credentials()
        assert status["fabric_official"]["ready"]

    def test_fabric_official_not_ready_without_azure(self):
        """fabric_official not ready quando credenciais Azure ausentes."""
        s = Settings(azure_tenant_id="", fabric_workspace_id="")
        status = s.validate_platform_credentials()
        assert not status["fabric_official"]["ready"]


class TestMcpRegistryCompleteness:
    """Guards contra regressões de migração parcial de MCPs para factory Python.

    Motivação: commit 0a446c8 migrou fabric_community para ALL_MCP_CONFIGS mas
    silenciosamente deixou fabric_official para trás (zero env no .mcp.json
    depois de esvaziar o arquivo). Resultado: server sumiu, tools OneLake
    ficaram ghost por semanas. Estes testes quebram o CI se alguma migração
    parcial futura tentar remover um server do registry Python.
    """

    def test_all_mcp_configs_contains_expected_servers(self):
        """ALL_MCP_CONFIGS deve conter todos os MCP servers esperados."""
        from data_agents.config.mcp_servers import ALL_MCP_CONFIGS

        expected = {
            "databricks",
            "databricks_genie",
            "fabric",
            "fabric_official",
            "fabric_sql",
            "fabric_rti",
            "fabric_semantic",
            "context7",
            "tavily",
            "github",
            "firecrawl",
            "postgres",
            "memory_mcp",
            "migration_source",
        }
        missing = expected - set(ALL_MCP_CONFIGS.keys())
        assert not missing, f"MCP servers ausentes do registry: {missing}"

    def test_fabric_official_config_has_correct_shape(self):
        """fabric_official deve usar npx com o pacote oficial Microsoft."""
        from data_agents.mcp_servers.fabric.server_config import get_fabric_official_mcp_config

        config = get_fabric_official_mcp_config()
        assert "fabric_official" in config

        server = config["fabric_official"]
        assert server["type"] == "stdio"
        assert server["command"] == "npx"
        args = server["args"]
        assert any(a.startswith("@microsoft/fabric-mcp") for a in args)
        assert "--mode" in args and "all" in args

    def test_fabric_official_readonly_excludes_destructive_tools(self):
        """Readonly alias deve excluir upload/delete/create_directory em OneLake."""
        from data_agents.mcp_servers.fabric.server_config import FABRIC_OFFICIAL_MCP_READONLY_TOOLS

        destructive = [
            "mcp__fabric_official__onelake_upload_file",
            "mcp__fabric_official__onelake_delete_file",
            "mcp__fabric_official__onelake_create_directory",
        ]
        for tool in destructive:
            assert tool not in FABRIC_OFFICIAL_MCP_READONLY_TOOLS, (
                f"{tool} é destrutivo e não deveria estar no readonly set"
            )
        # E deve conter pelo menos o download (leitura) para o alias ter utilidade
        assert "mcp__fabric_official__onelake_download_file" in FABRIC_OFFICIAL_MCP_READONLY_TOOLS

    def test_fabric_official_aliases_registered_in_loader(self):
        """agents/loader.py deve expor os aliases fabric_official_all/readonly."""
        from data_agents.agents.loader import MCP_TOOL_SETS

        assert "fabric_official_all" in MCP_TOOL_SETS
        assert "fabric_official_readonly" in MCP_TOOL_SETS
        # Readonly deve ser subset estrito do all
        all_tools = set(MCP_TOOL_SETS["fabric_official_all"])
        ro_tools = set(MCP_TOOL_SETS["fabric_official_readonly"])
        assert ro_tools.issubset(all_tools)
        assert ro_tools != all_tools, "readonly deve ser estritamente menor que all"


class TestProjectIdIsolation:
    """Testes para o isolamento de memória por project_id (Nível 1)."""

    @pytest.fixture(autouse=True)
    def _isolate_memory_env(self, monkeypatch):
        """Isola Settings() do ambiente: env vars do processo + .env do disco.

        Sem esse isolamento, os testes ficam dependentes do .env do dev (ex:
        MEMORY_DATA_DIR apontando pra fora do repo quebra o derive automático).
        CI passa porque não tem .env; localmente falha. Bloqueia ambas as fontes
        pra que o derive seja validado isoladamente.
        """
        # 1. Env vars do processo
        for var in (
            "MEMORY_DATA_DIR",
            "LONG_TERM_DB_PATH",
            "SHORT_TERM_DB_PATH",
            "EMBEDDER_CACHE_DB_PATH",
        ):
            monkeypatch.delenv(var, raising=False)
        # 2. .env do disco — pydantic-settings lê via model_config["env_file"]
        monkeypatch.setitem(Settings.model_config, "env_file", None)

    def test_explicit_project_id_used_literally(self):
        """Valor explícito não-'auto' deve ser usado como ID literal (após normalização)."""
        s = Settings(project_id="meu-projeto-x")
        assert s.project_id == "meu-projeto-x"
        assert s.short_term_db_path == "data_agents/memory/data/short_term__meu-projeto-x.db"
        assert s.long_term_db_path == "data_agents/memory/data/long_term__meu-projeto-x.db"

    def test_auto_resolves_to_cwd_name(self, tmp_path, monkeypatch):
        """project_id='auto' deve usar Path.cwd().name."""
        monkeypatch.chdir(tmp_path)
        s = Settings(project_id="auto")
        # tmp_path.name é gerado pelo pytest e é sempre não-vazio
        assert s.project_id == tmp_path.name
        # Phase 7: defaults agora prefixam com data_agents/memory/ (consistente
        # com namespace migration). Ver settings.py::derive_memory_db_paths.
        assert s.short_term_db_path == f"data_agents/memory/data/short_term__{tmp_path.name}.db"

    def test_empty_project_id_resolves_to_cwd_name(self, tmp_path, monkeypatch):
        """project_id vazio também aciona auto-detect (não fica vazio)."""
        monkeypatch.chdir(tmp_path)
        s = Settings(project_id="")
        assert s.project_id == tmp_path.name

    def test_invalid_chars_are_normalized(self):
        """Chars não-portáveis (espaços, /, !) viram hífen."""
        s = Settings(project_id="Projeto Com Espaços / E Barras!")
        # ç vira "" (não está em [A-Za-z0-9._-]), espaços/barras viram hífen
        assert "/" not in s.project_id
        assert " " not in s.project_id
        assert "!" not in s.project_id
        # Resultado deve ser usável como nome de arquivo
        assert "/" not in s.short_term_db_path.split("/")[-1]

    def test_path_override_wins_over_derived(self):
        """LONG_TERM_DB_PATH explícito sobrescreve o path derivado de project_id."""
        s = Settings(
            project_id="meu-projeto",
            long_term_db_path="/tmp/custom_long.db",
        )
        # long_term_db_path foi setado manualmente — vence o derive
        assert s.long_term_db_path == "/tmp/custom_long.db"
        # short_term continua sendo derivado de project_id
        assert s.short_term_db_path == "data_agents/memory/data/short_term__meu-projeto.db"

    def test_different_project_ids_produce_isolated_paths(self):
        """Garantia central do isolamento: IDs diferentes → arquivos diferentes."""
        s1 = Settings(project_id="projeto-a")
        s2 = Settings(project_id="projeto-b")
        assert s1.long_term_db_path != s2.long_term_db_path
        assert s1.short_term_db_path != s2.short_term_db_path
        assert s1.memory_data_dir != s2.memory_data_dir
        assert s1.embedder_cache_db_path != s2.embedder_cache_db_path

    def test_memory_data_dir_derived_as_subdir(self):
        """memory_data_dir vai como subdir (memory/data/<project_id>)."""
        s = Settings(project_id="meu-projeto")
        assert s.memory_data_dir == "data_agents/memory/data/meu-projeto"

    def test_embedder_cache_derived_with_suffix(self):
        """embedder_cache_db_path segue mesmo padrão dos outros SQLites (sufixo)."""
        s = Settings(project_id="meu-projeto")
        assert s.embedder_cache_db_path == "data_agents/memory/data/embedder_cache__meu-projeto.db"

    def test_memory_data_dir_override_wins(self):
        """MEMORY_DATA_DIR explícito sobrescreve o derive."""
        s = Settings(
            project_id="meu-projeto",
            memory_data_dir="/tmp/custom/dir",
        )
        assert s.memory_data_dir == "/tmp/custom/dir"
        # Outros paths continuam derivados normalmente
        assert "meu-projeto" in s.long_term_db_path

    def test_memory_store_uses_settings_memory_data_dir(self, tmp_path, monkeypatch):
        """MemoryStore() sem args deve usar settings.memory_data_dir."""
        from data_agents.config.settings import settings
        from data_agents.memory.store import MemoryStore

        custom_dir = tmp_path / "custom_memory"
        monkeypatch.setattr(settings, "memory_data_dir", str(custom_dir))
        store = MemoryStore()
        assert store.data_dir == custom_dir
        # Verifica que estrutura de subdirs foi criada
        assert (custom_dir / "architecture").is_dir()
        assert (custom_dir / "lesson_learned").is_dir()
        assert (custom_dir / "daily").is_dir()
