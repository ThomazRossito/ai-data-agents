"""
Isolamento do SDK em relação ao host (hotfix 2026-09-14).

O CASO
------
    $ python data_agents/cli.py "me fale sobre o Genie Ontology"
    🎯 Dispatcher: databricks-engineer (conf=95% · 1/25 agentes · Genie Ontology é
                   feature nativa do Databricks ...)
    🤖 Delegando para → geral · T0...
    🤖 Delegando para → ai-data-agents:geral...
    → "Não existe um produto oficial chamado 'Genie Ontology'."

O dispatcher acertou. O Supervisor delegou a `geral` — que nem devia estar na
sessão (o dispatcher carregou 1 agente) — e depois a `ai-data-agents:geral`, o
mesmo agente vindo do PLUGIN que este projeto publica e que o usuário tem
instalado no Claude Code. Com `setting_sources=None`, o subprocesso do SDK lê
`~/.claude/settings.json` e traz os plugins do host; os 25 agentes entram por
fora do `agents=` e o two-stage routing deixa de significar qualquer coisa.

`geral` é T0 sem tools: respondeu do treinamento e afirmou que a feature não
existe. Existe — doc oficial da Databricks, 11/set/2026.

TRÊS GATES
----------
  1. `setting_sources` tem que ser `["project"]` — nunca None, nunca incluir "user".
  2. O prompt do Supervisor proíbe afirmar inexistência sem verificar e manda
     confiar no dispatcher.
  3. O `geral` carrega a regra de nunca afirmar inexistência.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO = Path(__file__).resolve().parents[2]


def _capturar_options(**kwargs_build) -> dict:
    cap: dict = {}
    mock_class = MagicMock(side_effect=lambda **kw: (cap.update(kw), MagicMock())[1])
    with patch("data_agents.agents.supervisor.ClaudeAgentOptions", mock_class):
        with patch("data_agents.agents.supervisor.build_mcp_registry", return_value={}):
            from data_agents.agents.supervisor import build_supervisor_options

            build_supervisor_options(**kwargs_build)
    return cap


class TestSettingSources:
    def test_e_apenas_project(self) -> None:
        cap = _capturar_options()
        assert cap.get("setting_sources") == ["project"], (
            f"setting_sources={cap.get('setting_sources')!r}. Tem que ser ['project']: "
            "None carrega ~/.claude e traz os plugins do host para dentro da sessão — "
            "foi assim que `ai-data-agents:geral` apareceu por fora do dispatcher."
        )

    def test_nunca_inclui_user(self) -> None:
        cap = _capturar_options()
        assert "user" not in (cap.get("setting_sources") or []), (
            "'user' em setting_sources reabre a porta para plugins e MCPs instalados no host"
        )

    def test_mantem_project_para_o_claude_md(self) -> None:
        """O SDK exige 'project' para carregar CLAUDE.md. `[]` isolaria demais."""
        cap = _capturar_options()
        assert "project" in (cap.get("setting_sources") or [])

    def test_vale_tambem_com_agent_names(self) -> None:
        """O caminho do dispatcher (agent_names=...) é justamente o que estava sendo anulado."""
        with patch("data_agents.agents.supervisor.load_all_agents") as mock_load:
            mock_load.return_value = {"databricks-engineer": MagicMock()}
            cap = _capturar_options(agent_names=["databricks-engineer"])
        assert cap.get("setting_sources") == ["project"]


class TestPromptDoSupervisor:
    @pytest.fixture(scope="class")
    def prompt(self) -> str:
        from data_agents.agents.prompts.supervisor_prompt import SUPERVISOR_SYSTEM_PROMPT

        return SUPERVISOR_SYSTEM_PROMPT

    def test_proibe_afirmar_inexistencia_sem_verificar(self, prompt: str) -> None:
        baixo = prompt.lower()
        assert "does not exist without verifying" in baixo, (
            "o prompt precisa proibir explicitamente 'não existe' sem verificação"
        )
        assert "não existe" in baixo, "a frase em português que o modelo produz deve estar citada"

    def test_perguntas_sobre_produto_nao_vao_para_geral(self, prompt: str) -> None:
        assert "is NOT a `geral` question" in prompt
        assert "tavily" in prompt.lower()

    def test_manda_confiar_no_dispatcher(self, prompt: str) -> None:
        assert "Trust the dispatcher" in prompt
        assert "🎯 Dispatcher:" in prompt, (
            "o marcador que o Supervisor vê na tela deve estar citado"
        )

    def test_caso_real_documentado(self, prompt: str) -> None:
        """O prompt carrega o exemplo real para o modelo reconhecer o padrão."""
        assert "Genie Ontology" in prompt


class TestAgenteGeral:
    @pytest.fixture(scope="class")
    def corpo(self) -> str:
        return (_REPO / "data_agents" / "agents" / "registry" / "geral.md").read_text(
            encoding="utf-8"
        )

    def test_regra_de_nunca_afirmar_inexistencia(self, corpo: str) -> None:
        baixo = corpo.lower()
        assert "nunca" in baixo and "não existe" in baixo, (
            "geral.md precisa da regra explícita: nunca escrever 'não existe' sobre produto/feature"
        )

    def test_oferece_a_frase_de_hedge(self, corpo: str) -> None:
        assert "Não encontrei esse termo" in corpo, (
            "o agente precisa de uma frase pronta para quando não reconhece o termo — "
            "sem ela, o modelo improvisa e improviso vira 'não existe'"
        )

    def test_aponta_para_agente_com_busca(self, corpo: str) -> None:
        assert "busca web" in corpo.lower()

    def test_continua_sem_tools(self, corpo: str) -> None:
        """A correção é comportamental, não dar tools ao geral — ele é o caminho barato."""
        from data_agents.utils.frontmatter import parse_yaml_frontmatter

        meta, _ = parse_yaml_frontmatter(corpo)
        assert meta.get("tools") == [] and meta.get("mcp_servers") == []
        assert meta.get("tier") == "T0"
