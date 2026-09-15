"""
Gate de sincronia entre a máquina de estados e o prompt do Supervisor.

O `data_agents/spec/` impõe o contrato em Python, mas quem decide transicionar é
o modelo lendo o `SUPERVISOR_SYSTEM_PROMPT`. Se alguém acrescentar um estado ao
enum e esquecer do prompt, o Supervisor nunca alcança esse estado — o código
fica correto e o comportamento, não. É a mesma classe de bug do dispatcher:
suíte verde, sistema quebrado.

Estes testes são baratos e grosseiros de propósito. Não julgam a qualidade da
instrução; só garantem que o vocabulário do contrato aparece onde o modelo lê.
"""

from __future__ import annotations

import pytest

from data_agents.spec.state import SpecStatus, Trilha


@pytest.fixture(scope="module")
def prompt() -> str:
    from data_agents.agents.prompts.supervisor_prompt import SUPERVISOR_SYSTEM_PROMPT

    return SUPERVISOR_SYSTEM_PROMPT


class TestVocabulario:
    @pytest.mark.parametrize("status", list(SpecStatus), ids=lambda s: s.value)
    def test_todo_status_aparece_no_prompt(self, status: SpecStatus, prompt: str) -> None:
        assert status.value in prompt, (
            f"o estado {status.value!r} existe em data_agents/spec/state.py mas não "
            "aparece no SUPERVISOR_SYSTEM_PROMPT — o Supervisor nunca vai alcançá-lo"
        )

    @pytest.mark.parametrize("trilha", list(Trilha), ids=lambda t: t.value)
    def test_trilha_direta_documentada_onde_importa(self, trilha: Trilha, prompt: str) -> None:
        """`direta` precisa estar no prompt: é a única que libera pular a revisão."""
        if trilha is Trilha.DIRETA:
            assert "direta" in prompt


class TestInstrucoesCriticas:
    def test_manda_procurar_antes_de_criar(self, prompt: str) -> None:
        """O comportamento que motivou a Onda 2.1 inteira."""
        assert "spec_id" in prompt
        assert "output/specs/" in prompt
        baixo = prompt.lower()
        assert "grep" in baixo, (
            "o prompt precisa dizer COMO procurar o spec existente; sem instrução "
            "concreta o Supervisor volta a criar do zero"
        )

    def test_avisa_para_nao_confiar_no_nome_do_arquivo(self, prompt: str) -> None:
        baixo = prompt.lower()
        assert "filename" in baixo or "nome do arquivo" in baixo, (
            "sem esse aviso o Supervisor casa spec por nome — e o nome é justamente "
            "o que derivou em 26/jul e 10/ago"
        )

    def test_protege_a_intencao_congelada(self, prompt: str) -> None:
        assert "<intencao-congelada>" in prompt
        assert "never rewrite it" in prompt.lower() or "nunca reescreva" in prompt.lower()

    def test_proibe_reabrir_concluido(self, prompt: str) -> None:
        baixo = prompt.lower()
        assert "do not reopen" in baixo or "não reabra" in baixo

    def test_cita_o_teto_de_revisao(self, prompt: str) -> None:
        from data_agents.spec.state import MAX_ITERACOES_REVISAO

        assert str(MAX_ITERACOES_REVISAO) in prompt, (
            f"o teto de {MAX_ITERACOES_REVISAO} iterações não aparece no prompt — "
            "o Supervisor não saberia quando parar de iterar na revisão"
        )
        assert "iteracao_revisao" in prompt

    def test_aponta_para_a_fonte_de_verdade(self, prompt: str) -> None:
        """O prompt não é o contrato; o módulo é. O prompt tem que dizer isso."""
        assert "data_agents/spec/state.py" in prompt
