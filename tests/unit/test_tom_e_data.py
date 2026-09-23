"""
Tom de especialista sênior + data de hoje nos prompts (pedido do autor, set/2026).

Regras pedidas: especialista Databricks com mais de 10 anos, sem marcas de
texto gerado, resposta humana e curta, coerente com a doc oficial, com link
oficial, e ciente de que estamos em setembro de 2026.

Duas invariantes técnicas que estes testes travam:
  1. A data é dinâmica e vai SEMPRE no fim do prompt. O cache_prefix.md
     continua estático e o prompt do agente continua COMEÇANDO por ele —
     senão o prompt caching compartilhado quebra.
  2. Quem escreve a resposta final é o Supervisor. Regra de estilo só no
     subagente não muda o que o usuário lê.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from data_agents.agents import temporal
from data_agents.agents.temporal import current_date_note

_REPO = Path(__file__).resolve().parents[2]
_DIA = date(2026, 9, 22)


@pytest.fixture(autouse=True)
def _dia_fixo(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(temporal, "hoje", lambda: _DIA)


class TestNotaDeData:
    def test_formato(self) -> None:
        nota = current_date_note()
        assert "Hoje é 2026-09-22 (setembro de 2026)" in nota
        assert "documentação oficial" in nota

    def test_mes_por_extenso_sem_depender_de_locale(self) -> None:
        assert "(janeiro de 2027)" in current_date_note(date(2027, 1, 5))
        assert "(dezembro de 2026)" in current_date_note(date(2026, 12, 31))


class TestDataNosPrompts:
    def test_agente_comeca_pelo_cache_prefix_e_termina_com_a_data(self) -> None:
        from data_agents.agents.loader import _load_cache_prefix, load_agent

        _, agente = load_agent(_REPO / "data_agents/agents/registry/databricks-engineer.md")
        assert agente.prompt.startswith(_load_cache_prefix()), (
            "o prefixo compartilhado tem que continuar byte-idêntico no início"
        )
        assert agente.prompt.endswith(current_date_note(_DIA))

    def test_supervisor_termina_com_a_data(self) -> None:
        cap: dict = {}
        fake = MagicMock(side_effect=lambda **kw: (cap.update(kw), MagicMock())[1])
        with patch("data_agents.agents.supervisor.ClaudeAgentOptions", fake):
            with patch("data_agents.agents.supervisor.build_mcp_registry", return_value={}):
                from data_agents.agents.supervisor import build_supervisor_options

                build_supervisor_options(agent_names=["databricks-engineer"])
        assert cap["system_prompt"].endswith(current_date_note(_DIA))

    def test_geral_tem_a_data(self) -> None:
        from data_agents.commands.geral import GERAL_SYSTEM, _geral_system

        assert _geral_system() == GERAL_SYSTEM + current_date_note(_DIA)

    def test_party_tem_a_data(self) -> None:
        from data_agents.commands.party import _build_agent_options

        opts = _build_agent_options("databricks-engineer")
        assert opts.system_prompt.endswith(current_date_note(_DIA))

    def test_cache_prefix_continua_sem_data(self) -> None:
        texto = (_REPO / "data_agents/agents/cache_prefix.md").read_text(encoding="utf-8")
        assert not re.search(r"\b20\d\d-\d\d-\d\d\b", texto), "data no cache_prefix quebra o cache"


class TestTom:
    @pytest.fixture(scope="class")
    def prefixo(self) -> str:
        return (_REPO / "data_agents/agents/cache_prefix.md").read_text(encoding="utf-8")

    def test_regras_globais_de_escrita(self, prefixo: str) -> None:
        assert "Escreva como um engenheiro sênior" in prefixo
        assert "Quer que eu aprofunde" in prefixo, "a marca a evitar tem que estar nomeada"
        assert "docs.databricks.com" in prefixo and "learn.microsoft.com" in prefixo

    def test_link_so_se_foi_aberto(self, prefixo: str) -> None:
        """Link oficial sim; link de memória não — é a alucinação mais fácil de cometer."""
        assert "Só cite URL que você abriu" in prefixo

    def test_supervisor_e_dono_do_estilo_da_resposta_final(self) -> None:
        from data_agents.agents.prompts.supervisor_prompt import SUPERVISOR_SYSTEM_PROMPT as p

        assert "You write the final answer, so the style rules are yours" in p
        assert "never add a URL nobody opened" in p

    def test_persona_do_databricks_engineer(self) -> None:
        bruto = (_REPO / "data_agents/agents/registry/databricks-engineer.md").read_text(
            encoding="utf-8"
        )
        corpo = " ".join(bruto.split())  # o markdown quebra linha no meio das frases
        assert "mais de dez anos de plataforma" in corpo
        assert "learn.microsoft.com/azure/databricks" in corpo
        assert "Genie Agents, antigos Genie Spaces" in corpo

    def test_ninguem_forca_ingles(self) -> None:
        """A regra de idioma é espelhar o usuário (supervisor_prompt + cache_prefix).
        /geral, /party e o modo dev do Chainlit forçavam EN-US."""
        for f in ("commands/geral.py", "commands/party.py", "ui/chainlit_app.py"):
            texto = (_REPO / "data_agents" / f).read_text(encoding="utf-8")
            assert "Always respond in English" not in texto, f


class TestRodadaDe22Set:
    """Rodada real após o primeiro ajuste de tom (2026-09-22): sem emoji e sem oferta
    no fim, mas ainda longa, com narração antes da resposta, link invisível no
    terminal e um status errado ("Genie One MCP server (Beta)" — a doc de 21/09 diz
    GA e deprecia o endpoint Beta)."""

    def test_cli_mostra_a_url_dos_links(self) -> None:
        """Rich com hyperlinks=True imprime só o texto do link; a URL some no terminal
        e no copiar/colar. O usuário pediu link oficial — tem que dar para ver."""
        src = (_REPO / "data_agents/cli.py").read_text(encoding="utf-8")
        chamadas = re.findall(r"Markdown\((.*)\)\)", src)
        assert chamadas, "cli.py deveria renderizar Markdown"
        assert all("hyperlinks=False" in c for c in chamadas), chamadas

    def test_rich_imprime_a_url_com_hyperlinks_false(self) -> None:
        import io

        from rich.console import Console
        from rich.markdown import Markdown

        buf = io.StringIO()
        Console(file=buf, width=200, color_system=None).print(
            Markdown(
                "[doc](https://docs.databricks.com/aws/en/genie/genie-ontology)", hyperlinks=False
            )
        )
        assert "https://docs.databricks.com/aws/en/genie/genie-ontology" in buf.getvalue()

    def test_supervisor_nao_narra_roteamento(self) -> None:
        from data_agents.agents.prompts.supervisor_prompt import SUPERVISOR_SYSTEM_PROMPT as p

        assert "DOMA Express Routing -> Delegating directly" not in p
        assert "please wait for the structured backlog" not in p
        assert "Do not narrate routing or ask the user to wait" in p

    def test_status_so_de_pagina_aberta(self) -> None:
        from data_agents.agents.prompts.supervisor_prompt import SUPERVISOR_SYSTEM_PROMPT as p

        prefixo = (_REPO / "data_agents/agents/cache_prefix.md").read_text(encoding="utf-8")
        assert "Snippet de busca e blog não definem status" in " ".join(prefixo.split())
        assert "A search snippet or a blog post does not set status" in " ".join(p.split())

    def test_dataset_cobre_o_status_do_genie_one_mcp(self) -> None:
        from data_agents.evals.model_compare import load_cases

        casos = {c.id: c for c in load_cases()}
        c = casos["genie-one-mcp-status"]
        assert ["system.ai.genie_one_mcp"] in c.must_include
        assert c.verificado_em == "2026-09-22"
