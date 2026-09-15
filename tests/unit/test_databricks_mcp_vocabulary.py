"""
Vocabulário do MCP Databricks (ai-dev-kit) — gate contra tools fantasmas.

Entre 2026-07 e 2026-09 `DATABRICKS_MCP_TOOLS` declarou 47 tools das quais 26
não existiam em NENHUM servidor e só 13 existiam no servidor instalado. Todo
agente com `databricks_all` recebia 34 nomes que devolviam "tool not found".
A suíte ficou verde o tempo todo porque nada comparava a lista com a realidade.

Estes testes comparam com `tests/fixtures/ai_dev_kit_tools.txt` — snapshot dos
`@mcp.tool` do fonte do servidor no SHA pinado, gerado por
`scripts/snapshot_ai_dev_kit_tools.py`. A CI não instala o servidor (compila
C++), então o snapshot é a fonte de verdade offline.

Três coisas precisam concordar, e há teste para cada par:
    server_config.AI_DEV_KIT_COMMIT  ↔  # commit: do fixture  ↔  SHA no pyproject.toml
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from data_agents.mcp_servers.databricks import server_config as sc
from data_agents.mcp_servers.databricks.server_config import (
    AI_DEV_KIT_COMMIT,
    DATABRICKS_AIBI_TOOLS,
    DATABRICKS_COMPUTE_TOOLS,
    DATABRICKS_MCP_READONLY_TOOLS,
    DATABRICKS_MCP_TOOLS,
    DATABRICKS_PIPELINES_TOOLS,
    DATABRICKS_SERVING_TOOLS,
    DATABRICKS_UC_ADMIN_TOOLS,
    DATABRICKS_VECTOR_SEARCH_TOOLS,
    LEGACY_TOOL_MAP,
)

_REPO = Path(__file__).resolve().parents[2]
_FIXTURE = _REPO / "tests" / "fixtures" / "ai_dev_kit_tools.txt"
_PREFIX = "mcp__databricks__"


def _curto(tool: str) -> str:
    return tool.removeprefix(_PREFIX)


@pytest.fixture(scope="module")
def snapshot() -> tuple[str, set[str]]:
    assert _FIXTURE.is_file(), (
        f"{_FIXTURE} ausente — rode scripts/snapshot_ai_dev_kit_tools.py <raiz-do-ai-dev-kit>"
    )
    sha, nomes = "", set()
    for linha in _FIXTURE.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha.startswith("# commit:"):
            sha = linha.split(":", 1)[1].strip()
        elif linha and not linha.startswith("#"):
            nomes.add(linha)
    assert sha and nomes, "fixture malformado"
    return sha, nomes


# ─── Sem fantasmas ────────────────────────────────────────────────────────────


class TestSemFantasmas:
    def test_toda_tool_oferecida_existe_no_servidor(self, snapshot) -> None:
        _, reais = snapshot
        fantasmas = sorted(_curto(t) for t in DATABRICKS_MCP_TOOLS if _curto(t) not in reais)
        assert not fantasmas, (
            f"tools em DATABRICKS_MCP_TOOLS que NÃO existem no servidor: {fantasmas}. "
            "É exatamente a regressão de 2026-07 (26 fantasmas). Ou o nome está errado, "
            "ou o pin do ai-dev-kit mudou sem regravar o snapshot."
        )

    def test_toda_tool_do_servidor_esta_oferecida_ou_excluida_de_proposito(self, snapshot) -> None:
        """Nada some em silêncio: exclusão tem que ser deliberada e documentada."""
        _, reais = snapshot
        oferecidas = {_curto(t) for t in DATABRICKS_MCP_TOOLS}
        excluidas_de_proposito = {"generate_and_upload_pdf"}  # depende de plutoprint (C++)
        nao_oferecidas = reais - oferecidas
        assert nao_oferecidas == excluidas_de_proposito, (
            f"tools do servidor fora da lista sem justificativa: "
            f"{sorted(nao_oferecidas - excluidas_de_proposito)}. Ofereça ou documente a exclusão "
            "em server_config.py E neste teste."
        )

    def test_sem_duplicatas(self) -> None:
        assert len(DATABRICKS_MCP_TOOLS) == len(set(DATABRICKS_MCP_TOOLS))

    def test_prefixo(self) -> None:
        errados = [t for t in DATABRICKS_MCP_TOOLS if not t.startswith(_PREFIX)]
        assert not errados, errados


# ─── Os três SHAs concordam ──────────────────────────────────────────────────


class TestPinSincronizado:
    def test_server_config_e_fixture(self, snapshot) -> None:
        sha_fix, _ = snapshot
        assert sha_fix.startswith(AI_DEV_KIT_COMMIT), (
            f"server_config.AI_DEV_KIT_COMMIT={AI_DEV_KIT_COMMIT!r} mas o fixture foi gerado "
            f"em {sha_fix[:7]} — o vocabulário pode não corresponder"
        )

    def test_pyproject_e_fixture(self, snapshot) -> None:
        sha_fix, _ = snapshot
        pyproject = (_REPO / "pyproject.toml").read_text(encoding="utf-8")
        shas = set(re.findall(r"ai-dev-kit@([0-9a-f]{7,40})#subdirectory", pyproject))
        assert shas, "pyproject.toml não pina o ai-dev-kit por SHA"
        assert len(shas) == 1, (
            f"pyproject pina SHAs diferentes para tools-core e mcp-server: {shas}"
        )
        (sha_py,) = shas
        assert sha_fix.startswith(sha_py) or sha_py.startswith(sha_fix), (
            f"pyproject pina {sha_py[:7]} mas o snapshot é de {sha_fix[:7]} — "
            "subiu o pin sem regravar o snapshot (ou vice-versa)"
        )

    def test_makefile_e_pyproject(self) -> None:
        """O atalho `make install-databricks-admin` tem que instalar o MESMO commit."""
        pyproject = (_REPO / "pyproject.toml").read_text(encoding="utf-8")
        makefile = (_REPO / "Makefile").read_text(encoding="utf-8")
        (sha_py,) = set(re.findall(r"ai-dev-kit@([0-9a-f]{7,40})#subdirectory", pyproject))
        m = re.search(r"AI_DEV_KIT_SHA\s*:=\s*([0-9a-f]{7,40})", makefile)
        assert m, "Makefile sem AI_DEV_KIT_SHA"
        assert m.group(1) == sha_py, (
            f"Makefile instala {m.group(1)[:7]}, pyproject pina {sha_py[:7]} — dois caminhos "
            "de instalação divergentes"
        )


# ─── Readonly explícito, não heurístico ──────────────────────────────────────


class TestReadonlyExplicito:
    #: Tools que aceitam action mutante em alguma forma — NUNCA podem estar no readonly.
    #: Extraído do código do servidor (ver comentários em server_config.py).
    _MUTANTES = {
        "manage_ka", "manage_mas", "manage_dashboard", "manage_app", "manage_cluster",
        "manage_sql_warehouse", "manage_workspace_files", "manage_volume_files",
        "manage_workspace", "manage_genie", "manage_jobs", "manage_job_runs",
        "manage_lakebase_database", "manage_lakebase_branch", "manage_lakebase_sync",
        "generate_lakebase_credential", "delete_tracked_resource", "manage_pipeline",
        "manage_pipeline_run", "execute_sql", "execute_sql_multi", "execute_code",
        "manage_uc_objects", "manage_uc_grants", "manage_uc_storage", "manage_uc_connections",
        "manage_uc_tags", "manage_uc_security_policies", "manage_uc_monitors",
        "manage_uc_sharing", "manage_metric_views", "manage_vs_endpoint", "manage_vs_index",
        "manage_vs_data",
    }  # fmt: skip

    def test_readonly_e_subconjunto_do_total(self) -> None:
        extras = set(DATABRICKS_MCP_READONLY_TOOLS) - set(DATABRICKS_MCP_TOOLS)
        assert not extras, f"readonly cita tools fora de DATABRICKS_MCP_TOOLS: {extras}"

    def test_nenhuma_tool_mutante_no_readonly(self) -> None:
        vazadas = sorted(
            _curto(t) for t in DATABRICKS_MCP_READONLY_TOOLS if _curto(t) in self._MUTANTES
        )
        assert not vazadas, (
            f"tools com action de escrita no alias readonly: {vazadas}. Com action-dispatch, "
            "`manage_x(action='delete')` passa por qualquer agente que tenha a tool — o "
            "readonly só pode ter tools que NUNCA mutam."
        )

    def test_execute_sql_fora_do_readonly(self) -> None:
        """Leitura SQL vai pelo gerenciado `databricks_sql_readonly`, não por aqui."""
        for proibida in ("execute_sql", "execute_sql_multi", "execute_code"):
            assert _PREFIX + proibida not in DATABRICKS_MCP_READONLY_TOOLS

    def test_mutantes_e_readonly_cobrem_o_servidor(self, snapshot) -> None:
        """Toda tool do servidor foi classificada — ou muta, ou é readonly, ou excluída."""
        _, reais = snapshot
        classificadas = self._MUTANTES | {_curto(t) for t in DATABRICKS_MCP_READONLY_TOOLS}
        classificadas |= {"generate_and_upload_pdf"}
        sem_classe = sorted(reais - classificadas)
        assert not sem_classe, (
            f"tools novas no servidor sem classificação readonly/mutante: {sem_classe} — "
            "decida e registre em server_config.py e neste teste"
        )

    def test_heuristica_antiga_nao_voltou(self) -> None:
        """O readonly era `[t for t in TOOLS if 'list_' in t or 'get_' in t...]`. Não pode voltar."""
        src = Path(sc.__file__).read_text(encoding="utf-8")
        assert "kw in t" not in src and "for kw in [" not in src, (
            "heurística por prefixo de nome reapareceu em server_config.py — com action-dispatch "
            "ela classifica `manage_pipeline` como escrita e `list_compute` como leitura por acaso"
        )


# ─── Sub-aliases ─────────────────────────────────────────────────────────────


class TestSubAliases:
    @pytest.mark.parametrize(
        "alias",
        [
            DATABRICKS_AIBI_TOOLS,
            DATABRICKS_SERVING_TOOLS,
            DATABRICKS_COMPUTE_TOOLS,
            DATABRICKS_PIPELINES_TOOLS,
            DATABRICKS_UC_ADMIN_TOOLS,
            DATABRICKS_VECTOR_SEARCH_TOOLS,
        ],
        ids=["aibi", "serving", "compute", "pipelines", "uc_admin", "vector_search"],
    )
    def test_sub_alias_e_subconjunto_e_nao_vazio(self, alias: list[str]) -> None:
        assert alias, "alias vazio"
        fora = set(alias) - set(DATABRICKS_MCP_TOOLS)
        assert not fora, f"sub-alias cita tools fora do total: {fora}"

    def test_aibi_cobre_o_que_o_databricks_engineer_promete(self) -> None:
        """A descrição do agente cita Genie, AI/BI, KA e MAS."""
        curtos = {_curto(t) for t in DATABRICKS_AIBI_TOOLS}
        for esperado in (
            "manage_genie",
            "ask_genie",
            "manage_dashboard",
            "manage_ka",
            "manage_mas",
        ):
            assert esperado in curtos


# ─── Mapa de migração ────────────────────────────────────────────────────────


class TestLegacyMap:
    def test_nenhum_nome_legado_esta_oferecido(self) -> None:
        """Se um nome legado voltou a ser oferecido, ou o servidor o adicionou (bom — tire do mapa)
        ou alguém reintroduziu um fantasma (ruim)."""
        oferecidas = {_curto(t) for t in DATABRICKS_MCP_TOOLS}
        colisao = sorted(set(LEGACY_TOOL_MAP) & oferecidas)
        assert not colisao, f"nomes no LEGACY_TOOL_MAP que estão oferecidos: {colisao}"

    def test_alvos_do_mapa_citam_tools_reais(self, snapshot) -> None:
        """Cada sugestão do mapa deve apontar para uma tool que existe (ou para o gerenciado)."""
        _, reais = snapshot
        nomes_reais = reais | {"databricks_sql_readonly"}
        for legado, sugestao in LEGACY_TOOL_MAP.items():
            if "(sem equivalente" in sugestao:
                continue
            # qualquer token snake_case da sugestão — com ou sem parênteses
            citadas = set(re.findall(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b", sugestao))
            assert citadas & nomes_reais, (
                f"LEGACY_TOOL_MAP[{legado!r}] sugere {sugestao!r}, mas nada ali é tool real"
            )


# ─── Agentes só citam tools que existem ──────────────────────────────────────


class TestAgentesCitamToolsReais:
    """Nome de tool no CORPO do agente é instrução para o modelo — se não existe,
    o modelo tenta chamar e recebe "tool not found". Até 2026-09-14 quatro agentes
    citavam `mcp__databricks__describe_table`, `list_catalogs`, `list_warehouses`,
    `create_or_update_genie`... nenhuma existia no servidor instalado."""

    _CITACAO_RE = re.compile(r"mcp__databricks__([a-z][a-z0-9_]*)")

    def test_toda_citacao_em_agente_existe_no_servidor(self, snapshot) -> None:
        _, reais = snapshot
        registry = _REPO / "data_agents" / "agents" / "registry"
        problemas = []
        for md in sorted(registry.glob("*.md")):
            if md.name.startswith("_"):
                continue
            citadas = set(self._CITACAO_RE.findall(md.read_text(encoding="utf-8")))
            fantasmas = sorted(c for c in citadas if c not in reais)
            if fantasmas:
                problemas.append(f"{md.name}: {fantasmas}")
        assert not problemas, (
            "agentes citam tools `mcp__databricks__*` que não existem no servidor "
            "(ver LEGACY_TOOL_MAP em server_config.py para o equivalente):\n" + "\n".join(problemas)
        )


class TestPyprojectAceitaReferenciaDireta:
    """`pkg @ git+...` no pyproject exige `tool.hatch.metadata.allow-direct-references`.

    Sem a chave, hatchling recusa a metadata e `pip install -e .` falha para TODO
    MUNDO — inclusive quem nunca vai instalar o extra. Derrubou 4 jobs na PR #52.
    Este teste dá a mensagem certa antes da CI dar a errada.
    """

    def test_chave_presente_quando_ha_referencia_direta(self) -> None:
        try:
            import tomllib  # 3.11+ (o projeto exige >=3.11; o sandbox local é 3.10)
        except ModuleNotFoundError:  # pragma: no cover
            import tomli as tomllib  # type: ignore[no-redef]

        texto = (_REPO / "pyproject.toml").read_text(encoding="utf-8")
        dados = tomllib.loads(texto)
        deps = list(dados["project"].get("dependencies", []))
        for extra in dados["project"].get("optional-dependencies", {}).values():
            deps.extend(extra)
        diretas = [d for d in deps if " @ " in d]
        if not diretas:
            pytest.skip("nenhuma referência direta no pyproject")
        permitido = (
            dados.get("tool", {})
            .get("hatch", {})
            .get("metadata", {})
            .get("allow-direct-references")
        )
        assert permitido is True, (
            f"{len(diretas)} dependência(s) por referência direta "
            f"({diretas[0][:50]}...), mas `[tool.hatch.metadata] allow-direct-references` "
            "não é true — hatchling vai recusar a metadata e o `pip install -e .` falha"
        )
