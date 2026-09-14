"""
Máquina de estados do DOMA Spec (Onda 2.1).

O PROBLEMA, MEDIDO
------------------
O `logs/audit.jsonl` deste projeto (21/jul → 14/set/2026) registra **6 escritas
em `output/specs/` para 3 specs distintos**:

    26/jul 18:20   spec_ssas_comercial_brf.md
    26/jul 19:05   spec_ssas_comercial_brf.md        (regerado 45 min depois)
    26/jul 20:01   spec_ssas_brf_comercial.md        (renomeado — palavras trocadas)

    10/ago 01:41   spec_foundry_task_analyzer.md
    10/ago 15:34   foundry-ado-task-analyzer-spec.md (outra convenção de nome)

Duas patologias, não uma:

  1. **Regeneração do zero.** O Supervisor não tinha como saber que já existia
     spec em andamento, então recomeçava. Metade do trabalho foi refeito.

  2. **Perda de identidade.** `ssas_comercial_brf` virou `ssas_brf_comercial`;
     `spec_<nome>.md` virou `<nome>-spec.md`. Um `/resume` não acharia o
     trabalho anterior nem sabendo exatamente o que procurar.

A patologia 2 decide o design: **status não pode ser indexado por nome de
arquivo**, porque o nome é justamente o que deriva. Daí o `spec_id`, estável e
independente do path.

O QUE ESTE MÓDULO É
-------------------
Só o contrato: os estados, as arestas legais entre eles e as condições de cada
aresta. Sem I/O — quem lê e grava arquivo é o `store.py`. Manter puro aqui
significa que a tabela de transições inteira é testável sem tocar disco.

A REGRA QUE SEPARA MÁQUINA DE ESTADOS DE CAMPO DE TEXTO
-------------------------------------------------------
Toda transição fora da tabela levanta `TransicaoInvalida`. Um `status:` que
aceita qualquer valor é só um campo de texto com nome bonito — não impede o
Supervisor de pular do rascunho direto para concluído.
"""

from __future__ import annotations

from enum import Enum

# ─── Estados ─────────────────────────────────────────────────────────────────


class SpecStatus(str, Enum):
    """Estados possíveis de um spec.

    Herda de `str` para que o valor serialize direto no frontmatter YAML sem
    conversão manual (`status: rascunho`, não `status: SpecStatus.RASCUNHO`).
    """

    #: Recém-criado. Contém a intenção e pouco mais.
    RASCUNHO = "rascunho"

    #: KB-First e investigação concluídos; a **trilha** já pode ser decidida.
    #: É aqui que o item 2.2 ("trilha decidida DEPOIS da investigação") se
    #: materializa: sem um estado entre "escrevi" e "aprovado", a profundidade
    #: continuaria sendo decidida pelo nome do comando digitado.
    INVESTIGADO = "investigado"

    #: Humano aprovou. Esta é a fronteira do S4 — atravessá-la exige um "sim".
    PRONTO = "pronto"

    #: Delegação em curso.
    EM_EXECUCAO = "em-execucao"

    #: Artefato produzido, aguardando revisão.
    EM_REVISAO = "em-revisao"

    #: Aceito. Estado final.
    CONCLUIDO = "concluido"

    #: Abandonado deliberadamente. Estado final.
    #:
    #: NÃO estava na proposta original — foi acrescentado ao perceber que sem
    #: ele um spec abandonado fica preso em `em-execucao` para sempre e
    #: envenena o `/resume`, que passaria a oferecer retomar trabalho morto.
    #: Só humano cancela.
    CANCELADO = "cancelado"


class Trilha(str, Enum):
    """As quatro trilhas do item 2.3 — profundidade do processo.

    Escopo é só um sinal. Risco, requisito incerto, alcance arquitetural e
    necessidade de coordenação empurram para cima mesmo em tarefa pequena.
    """

    DIRETA = "direta"
    TAREFA = "tarefa"
    PIPELINE = "pipeline"
    PLATAFORMA = "plataforma"


#: Estados a partir dos quais não há saída automática.
ESTADOS_FINAIS: frozenset[SpecStatus] = frozenset({SpecStatus.CONCLUIDO, SpecStatus.CANCELADO})

#: Teto de idas e vindas na revisão antes de escalar para humano.
#:
#: Sem teto, um revisor teimoso e um executor teimoso entram em loop e queimam
#: orçamento sem convergir. Três é palpite informado, não medição — ajuste
#: quando houver histórico real de `iteracao_revisao` nos specs.
MAX_ITERACOES_REVISAO = 3


# ─── Tabela de transições ────────────────────────────────────────────────────

#: Arestas permitidas ao **agente**. Qualquer par fora daqui é inválido.
_TRANSICOES: dict[SpecStatus, frozenset[SpecStatus]] = {
    SpecStatus.RASCUNHO: frozenset({SpecStatus.INVESTIGADO}),
    SpecStatus.INVESTIGADO: frozenset({SpecStatus.PRONTO}),
    SpecStatus.PRONTO: frozenset({SpecStatus.EM_EXECUCAO}),
    SpecStatus.EM_EXECUCAO: frozenset({SpecStatus.EM_REVISAO, SpecStatus.CONCLUIDO}),
    SpecStatus.EM_REVISAO: frozenset({SpecStatus.EM_EXECUCAO, SpecStatus.CONCLUIDO}),
    SpecStatus.CONCLUIDO: frozenset(),
    SpecStatus.CANCELADO: frozenset(),
}

#: Transições que SÓ o humano pode fazer, de qualquer estado não-final.
#:
#: `rascunho` reabre um spec (o humano mexeu na `<intencao-congelada>` e o
#: trabalho anterior deixou de valer). `cancelado` o encerra. Nenhuma das duas
#: pode ser decidida pelo agente: são justamente as que anulam ou descartam
#: aprovação humana anterior.
_TRANSICOES_HUMANAS: frozenset[SpecStatus] = frozenset({SpecStatus.RASCUNHO, SpecStatus.CANCELADO})


# ─── Exceções ────────────────────────────────────────────────────────────────


class TransicaoInvalida(ValueError):
    """Aresta que não existe na tabela, ou que exige autoridade humana."""


class LimiteDeRevisaoExcedido(TransicaoInvalida):
    """`em-revisao → em-execucao` além de MAX_ITERACOES_REVISAO."""


# ─── API ─────────────────────────────────────────────────────────────────────


def transicoes_validas(atual: SpecStatus, *, por_humano: bool = False) -> frozenset[SpecStatus]:
    """Estados alcançáveis a partir de `atual`.

    Args:
        atual: estado corrente do spec.
        por_humano: True quando a transição parte de uma ação humana explícita
            (edição do bloco `<intencao-congelada>`, cancelamento). Libera as
            arestas de `_TRANSICOES_HUMANAS`.
    """
    base = _TRANSICOES[atual]
    if not por_humano or atual in ESTADOS_FINAIS:
        return base
    return base | (_TRANSICOES_HUMANAS - {atual})


def pode_transicionar(de: SpecStatus, para: SpecStatus, *, por_humano: bool = False) -> bool:
    """Versão booleana de `validar_transicao` — não considera trilha nem iteração."""
    return para in transicoes_validas(de, por_humano=por_humano)


def validar_transicao(
    de: SpecStatus,
    para: SpecStatus,
    *,
    trilha: Trilha = Trilha.TAREFA,
    iteracao_revisao: int = 0,
    por_humano: bool = False,
) -> None:
    """Valida uma transição completa. Levanta se for ilegal; devolve None se ok.

    Além da tabela de arestas, aplica duas regras que dependem de contexto:

    **1. Pular a revisão só vale na trilha `direta`.**
       `em-execucao → concluido` existe na tabela porque uma pergunta pontual
       não tem o que revisar — exigir um estado de revisão ali seria atrito puro,
       e atrito puro é o que faz gente contornar a máquina de estados inteira.
       Nas outras três trilhas o caminho é `em-execucao → em-revisao → concluido`.

    **2. A revisão tem teto.**
       Voltar de `em-revisao` para `em-execucao` acima de
       `MAX_ITERACOES_REVISAO` levanta `LimiteDeRevisaoExcedido` — escale para
       humano em vez de continuar o loop.

    Args:
        de: estado atual.
        para: estado pretendido.
        trilha: trilha do spec (afeta a regra 1).
        iteracao_revisao: quantas voltas de revisão já aconteceram.
        por_humano: ação humana explícita (libera reabrir/cancelar).

    Raises:
        TransicaoInvalida: aresta inexistente, ou que exige humano.
        LimiteDeRevisaoExcedido: revisão além do teto.
    """
    if de is para:
        raise TransicaoInvalida(
            f"transição de {de.value!r} para ele mesmo não é transição — "
            "se a intenção é só atualizar o corpo do spec, grave sem mudar o status"
        )

    permitidas = transicoes_validas(de, por_humano=por_humano)
    if para not in permitidas:
        # Distinguir "não existe" de "precisa de humano" torna o erro acionável.
        if not por_humano and para in _TRANSICOES_HUMANAS and de not in ESTADOS_FINAIS:
            raise TransicaoInvalida(
                f"{de.value} → {para.value} exige ação humana explícita: reabrir "
                f"(editando o bloco <intencao-congelada>) ou cancelar não são "
                f"decisões do agente, porque anulam aprovação humana anterior"
            )
        legais = ", ".join(sorted(s.value for s in permitidas)) or "(nenhuma — estado final)"
        raise TransicaoInvalida(
            f"{de.value} → {para.value} não é transição legal. A partir de "
            f"{de.value!r} só é possível ir para: {legais}"
        )

    # Regra 1 — atalho da revisão só na trilha direta
    if (
        de is SpecStatus.EM_EXECUCAO
        and para is SpecStatus.CONCLUIDO
        and trilha is not Trilha.DIRETA
    ):
        raise TransicaoInvalida(
            f"em-execucao → concluido pula a revisão, o que só vale na trilha "
            f"'direta'; esta é '{trilha.value}'. Passe por em-revisao."
        )

    # Regra 2 — teto de revisão
    if de is SpecStatus.EM_REVISAO and para is SpecStatus.EM_EXECUCAO:
        if iteracao_revisao >= MAX_ITERACOES_REVISAO:
            raise LimiteDeRevisaoExcedido(
                f"revisão já rodou {iteracao_revisao}x (teto: {MAX_ITERACOES_REVISAO}). "
                "Mais uma volta provavelmente não converge — escale para humano."
            )


def proxima_iteracao_revisao(de: SpecStatus, para: SpecStatus, iteracao_atual: int) -> int:
    """Contador de revisão após uma transição. Só incrementa em em-revisao → em-execucao."""
    if de is SpecStatus.EM_REVISAO and para is SpecStatus.EM_EXECUCAO:
        return iteracao_atual + 1
    return iteracao_atual


def parse_status(valor: object) -> SpecStatus:
    """Converte um valor de frontmatter em SpecStatus, com erro legível.

    O frontmatter é escrito por um LLM — assumir que o valor é válido é o
    mesmo erro que assumir que `content[0]` é o bloco de texto.
    """
    if isinstance(valor, SpecStatus):
        return valor
    if not isinstance(valor, str):
        raise TransicaoInvalida(f"status deve ser string, veio {type(valor).__name__}: {valor!r}")
    try:
        return SpecStatus(valor.strip().lower())
    except ValueError:
        conhecidos = ", ".join(s.value for s in SpecStatus)
        raise TransicaoInvalida(f"status {valor!r} não existe. Conhecidos: {conhecidos}") from None


def parse_trilha(valor: object) -> Trilha:
    """Converte um valor de frontmatter em Trilha, com erro legível."""
    if isinstance(valor, Trilha):
        return valor
    if not isinstance(valor, str):
        raise TransicaoInvalida(f"trilha deve ser string, veio {type(valor).__name__}: {valor!r}")
    try:
        return Trilha(valor.strip().lower())
    except ValueError:
        conhecidas = ", ".join(t.value for t in Trilha)
        raise TransicaoInvalida(f"trilha {valor!r} não existe. Conhecidas: {conhecidas}") from None
