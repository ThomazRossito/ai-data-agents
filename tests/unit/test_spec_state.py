"""
Testes da máquina de estados do DOMA Spec.

O teste que carrega o contrato é `TestTabelaExaustiva`: ele percorre os 49
pares (7 estados × 7 estados) e confere cada um contra uma tabela escrita à
mão aqui, independente da implementação. Se alguém editar `_TRANSICOES` em
`state.py`, esta tabela discorda e o teste falha — que é exatamente o
comportamento desejado para um contrato.

Testar só os caminhos felizes deixaria passar a falha que importa: uma aresta
NOVA aparecer sem ninguém perceber (por exemplo `rascunho → concluido`, que
anularia a aprovação humana inteira).
"""

from __future__ import annotations

import itertools

import pytest

from data_agents.spec.state import (
    ESTADOS_FINAIS,
    MAX_ITERACOES_REVISAO,
    LimiteDeRevisaoExcedido,
    SpecStatus,
    TransicaoInvalida,
    Trilha,
    parse_status,
    parse_trilha,
    pode_transicionar,
    proxima_iteracao_revisao,
    transicoes_validas,
    validar_transicao,
)

S = SpecStatus

#: O contrato, escrito à mão e independente de state.py.
#: chave = estado de origem · valor = destinos permitidos AO AGENTE.
CONTRATO_AGENTE: dict[SpecStatus, set[SpecStatus]] = {
    S.RASCUNHO: {S.INVESTIGADO},
    S.INVESTIGADO: {S.PRONTO},
    S.PRONTO: {S.EM_EXECUCAO},
    S.EM_EXECUCAO: {S.EM_REVISAO, S.CONCLUIDO},
    S.EM_REVISAO: {S.EM_EXECUCAO, S.CONCLUIDO},
    S.CONCLUIDO: set(),
    S.CANCELADO: set(),
}

#: Destinos que SÓ o humano alcança, a partir de qualquer estado não-final.
CONTRATO_HUMANO_EXTRA: set[SpecStatus] = {S.RASCUNHO, S.CANCELADO}


class TestTabelaExaustiva:
    """Percorre os 49 pares possíveis. Nenhuma aresta entra ou sai sem aviso."""

    @pytest.mark.parametrize("de,para", list(itertools.product(list(S), list(S))))
    def test_aresta_do_agente(self, de: SpecStatus, para: SpecStatus) -> None:
        esperado = para in CONTRATO_AGENTE[de]
        assert pode_transicionar(de, para) is esperado, (
            f"{de.value} → {para.value}: implementação diz "
            f"{pode_transicionar(de, para)}, contrato diz {esperado}"
        )

    @pytest.mark.parametrize("de,para", list(itertools.product(list(S), list(S))))
    def test_aresta_do_humano(self, de: SpecStatus, para: SpecStatus) -> None:
        if de in ESTADOS_FINAIS:
            esperado = para in CONTRATO_AGENTE[de]
        else:
            esperado = para in (CONTRATO_AGENTE[de] | (CONTRATO_HUMANO_EXTRA - {de}))
        assert pode_transicionar(de, para, por_humano=True) is esperado, (
            f"{de.value} → {para.value} (humano): implementação diz "
            f"{pode_transicionar(de, para, por_humano=True)}, contrato diz {esperado}"
        )

    def test_nenhum_estado_alcanca_concluido_sem_passar_por_execucao(self) -> None:
        """Nenhum atalho do rascunho/investigado/pronto direto para concluído."""
        for origem in (S.RASCUNHO, S.INVESTIGADO, S.PRONTO):
            assert not pode_transicionar(origem, S.CONCLUIDO, por_humano=True), (
                f"{origem.value} → concluido existiria e pularia a aprovação humana"
            )

    def test_estados_finais_nao_tem_saida(self) -> None:
        for final in ESTADOS_FINAIS:
            assert transicoes_validas(final) == frozenset()
            assert transicoes_validas(final, por_humano=True) == frozenset(), (
                f"{final.value} é final — nem o humano reabre por transição; "
                "um spec novo deve ser criado"
            )


class TestValidarTransicao:
    def test_caminho_feliz_completo(self) -> None:
        """O percurso canônico de uma trilha pipeline, ponta a ponta."""
        caminho = [
            (S.RASCUNHO, S.INVESTIGADO),
            (S.INVESTIGADO, S.PRONTO),
            (S.PRONTO, S.EM_EXECUCAO),
            (S.EM_EXECUCAO, S.EM_REVISAO),
            (S.EM_REVISAO, S.CONCLUIDO),
        ]
        for de, para in caminho:
            validar_transicao(de, para, trilha=Trilha.PIPELINE)  # não deve levantar

    def test_transicao_para_si_mesmo_levanta(self) -> None:
        with pytest.raises(TransicaoInvalida, match="para ele mesmo"):
            validar_transicao(S.EM_EXECUCAO, S.EM_EXECUCAO)

    def test_pulo_ilegal_tem_mensagem_acionavel(self) -> None:
        with pytest.raises(TransicaoInvalida) as exc:
            validar_transicao(S.RASCUNHO, S.EM_EXECUCAO)
        assert "investigado" in str(exc.value), "erro deve dizer o que É possível"

    def test_reabrir_sem_humano_explica_que_precisa_de_humano(self) -> None:
        with pytest.raises(TransicaoInvalida, match="ação humana"):
            validar_transicao(S.EM_EXECUCAO, S.RASCUNHO)

    def test_cancelar_sem_humano_explica_que_precisa_de_humano(self) -> None:
        with pytest.raises(TransicaoInvalida, match="ação humana"):
            validar_transicao(S.EM_REVISAO, S.CANCELADO)

    def test_humano_reabre_e_cancela(self) -> None:
        validar_transicao(S.EM_EXECUCAO, S.RASCUNHO, por_humano=True)
        validar_transicao(S.EM_REVISAO, S.CANCELADO, por_humano=True)


class TestRegraDaTrilha:
    """em-execucao → concluido pula a revisão: só vale na trilha direta."""

    def test_trilha_direta_pode_pular_revisao(self) -> None:
        validar_transicao(S.EM_EXECUCAO, S.CONCLUIDO, trilha=Trilha.DIRETA)

    @pytest.mark.parametrize("trilha", [Trilha.TAREFA, Trilha.PIPELINE, Trilha.PLATAFORMA])
    def test_demais_trilhas_nao_podem(self, trilha: Trilha) -> None:
        with pytest.raises(TransicaoInvalida, match="pula a revisão"):
            validar_transicao(S.EM_EXECUCAO, S.CONCLUIDO, trilha=trilha)

    def test_default_de_trilha_e_conservador(self) -> None:
        """Sem trilha informada, o atalho NÃO é liberado.

        Default permissivo aqui seria pior que não ter a regra: quem esquecer
        de passar `trilha` ganharia o atalho de graça.
        """
        with pytest.raises(TransicaoInvalida, match="pula a revisão"):
            validar_transicao(S.EM_EXECUCAO, S.CONCLUIDO)


class TestTetoDeRevisao:
    @pytest.mark.parametrize("iteracao", range(MAX_ITERACOES_REVISAO))
    def test_abaixo_do_teto_passa(self, iteracao: int) -> None:
        validar_transicao(
            S.EM_REVISAO, S.EM_EXECUCAO, trilha=Trilha.PIPELINE, iteracao_revisao=iteracao
        )

    def test_no_teto_levanta(self) -> None:
        with pytest.raises(LimiteDeRevisaoExcedido, match="escale para humano"):
            validar_transicao(
                S.EM_REVISAO,
                S.EM_EXECUCAO,
                trilha=Trilha.PIPELINE,
                iteracao_revisao=MAX_ITERACOES_REVISAO,
            )

    def test_teto_nao_bloqueia_a_conclusao(self) -> None:
        """Estourar o teto impede mais uma volta, não impede fechar o spec."""
        validar_transicao(
            S.EM_REVISAO,
            S.CONCLUIDO,
            trilha=Trilha.PIPELINE,
            iteracao_revisao=MAX_ITERACOES_REVISAO + 5,
        )

    def test_limite_e_subclasse_de_transicao_invalida(self) -> None:
        """Quem só captura TransicaoInvalida não deixa o loop passar por engano."""
        assert issubclass(LimiteDeRevisaoExcedido, TransicaoInvalida)


class TestContadorDeIteracao:
    def test_incrementa_so_na_volta_da_revisao(self) -> None:
        assert proxima_iteracao_revisao(S.EM_REVISAO, S.EM_EXECUCAO, 0) == 1
        assert proxima_iteracao_revisao(S.EM_REVISAO, S.EM_EXECUCAO, 2) == 3

    @pytest.mark.parametrize(
        "de,para",
        [
            (S.RASCUNHO, S.INVESTIGADO),
            (S.PRONTO, S.EM_EXECUCAO),
            (S.EM_EXECUCAO, S.EM_REVISAO),
            (S.EM_REVISAO, S.CONCLUIDO),
        ],
    )
    def test_nao_incrementa_no_resto(self, de: SpecStatus, para: SpecStatus) -> None:
        assert proxima_iteracao_revisao(de, para, 7) == 7


class TestParsers:
    """O frontmatter é escrito por um LLM — nada ali pode ser assumido válido."""

    @pytest.mark.parametrize("bruto", ["rascunho", "  PRONTO  ", "Em-Revisao"])
    def test_status_aceita_variacao_de_caixa_e_espaco(self, bruto: str) -> None:
        assert isinstance(parse_status(bruto), SpecStatus)

    def test_status_desconhecido_lista_os_validos(self) -> None:
        with pytest.raises(TransicaoInvalida) as exc:
            parse_status("em-andamento")
        assert "rascunho" in str(exc.value) and "concluido" in str(exc.value)

    @pytest.mark.parametrize("lixo", [None, 42, ["rascunho"], {"status": "pronto"}])
    def test_status_de_tipo_errado_levanta(self, lixo: object) -> None:
        with pytest.raises(TransicaoInvalida, match="deve ser string"):
            parse_status(lixo)

    def test_status_idempotente(self) -> None:
        assert parse_status(SpecStatus.PRONTO) is SpecStatus.PRONTO

    def test_trilha_desconhecida_lista_as_validas(self) -> None:
        with pytest.raises(TransicaoInvalida) as exc:
            parse_trilha("mega")
        assert "plataforma" in str(exc.value)

    def test_trilha_idempotente(self) -> None:
        assert parse_trilha(Trilha.DIRETA) is Trilha.DIRETA

    def test_todo_status_do_enum_faz_round_trip(self) -> None:
        for s in SpecStatus:
            assert parse_status(s.value) is s
        for t in Trilha:
            assert parse_trilha(t.value) is t
