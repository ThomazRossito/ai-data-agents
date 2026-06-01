"""
Redação de PII — Mascaramento de dados sensíveis antes da transmissão externa.

Motivação
---------
O subsistema de memória envia texto derivado da conversa para um LLM externo
(Moonshot Kimi K2, via endpoint compatível Anthropic) em três pontos:

  - ``memory.extractor``   → buffer da sessão inteiro (flush de memória)
  - ``utils.summarizer``   → error_text + context_snippet (LESSON_LEARNED)
  - ``memory.compiler``    → conteúdo de memórias (checagem de contradição)

O conteúdo mais sensível não é metadado de schema (nome de coluna), e sim o
``tool_output`` — as linhas reais retornadas por queries contra dados de cliente.

Este módulo redige PII **na camada de captura** (``hooks.memory_hook``), antes
do dado entrar no buffer ou no caminho de ``LESSON_LEARNED``. Como a persistência
em disco (daily logs, arquivos de lesson) também deriva do buffer, redigir aqui
cobre transmissão **e** persistência num único ponto.

Estratégia de mascaramento: **placeholder tipado** (``[CPF]``, ``[EMAIL]``…).
Preserva o sentido semântico para o extractor ("ali havia um CPF") sem expor o
valor. A ordem de aplicação dos padrões importa — ver ``_REDACTORS``.

Escopo: foco em PII brasileira + segredos comuns. Não é um DLP completo;
é defesa em profundidade. A redação erra para o lado seguro (prefere redigir a
mais do que de menos), por isso números ambíguos (ex.: 11 dígitos contíguos)
são tratados como CPF.
"""

from __future__ import annotations

import re

# Cada redator é (rótulo, padrão compilado). A ordem é significativa: padrões
# mais específicos/longos vêm antes para não serem "comidos" parcialmente por
# padrões mais curtos (ex.: CNPJ de 14 dígitos antes de CPF de 11; telefone
# formatado antes de CPF, que captura a forma de 11 dígitos contíguos).
_REDACTORS: list[tuple[str, re.Pattern[str]]] = [
    # E-mail
    (
        "[EMAIL]",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    ),
    # Segredos no formato chave=valor / chave: valor (token, senha, api key, bearer)
    (
        "[SECRET]",
        re.compile(
            r"(?i)\b(?:api[_-]?key|apikey|token|secret|password|passwd|pwd|bearer|"
            r"authorization|client[_-]?secret|refresh[_-]?token|access[_-]?token)"
            r"\b\s*[:=]\s*\S+"
        ),
    ),
    # Cartão de crédito — grupos 4-4-4-(1 a 4), 13 a 16 dígitos. Estrito o
    # bastante para não capturar telefones (DD 9XXXX-XXXX) nem CPFs.
    (
        "[CARTAO]",
        re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{1,4}\b"),
    ),
    # CNPJ — 14 dígitos, formatado (12.345.678/0001-90) ou contíguo
    (
        "[CNPJ]",
        re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),
    ),
    # CPF — 11 dígitos, formatado (123.456.789-00) ou contíguo. Vem ANTES do
    # telefone: números de 11 dígitos contíguos (sem separador) são tratados
    # como CPF (erra para o lado seguro — redige). Formas com separador/parênteses
    # não casam aqui e caem no padrão de telefone abaixo.
    (
        "[CPF]",
        re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    ),
    # Telefone BR — exige formatação (parênteses no DDD, prefixo +55 ou separador
    # espaço/hífen) para não colidir com o CPF contíguo de 11 dígitos.
    (
        "[TELEFONE]",
        re.compile(
            r"(?:\+55[\s-]?)?\(\d{2}\)[\s-]?9?\d{4}[\s-]?\d{4}"  # (DD) 9XXXX-XXXX
            r"|\+55[\s-]?\d{2}[\s-]?9?\d{4}[\s-]?\d{4}"  # +55 DD 9XXXX-XXXX
            r"|\b\d{2}[\s-]9?\d{4}[\s-]?\d{4}\b"  # DD 9XXXX-XXXX (separador após DDD)
            r"|\b9?\d{4}[\s-]\d{4}\b"  # XXXXX-XXXX local (com separador)
        ),
    ),
    # CEP — apenas a forma formatada (12345-678) para reduzir falsos positivos.
    (
        "[CEP]",
        re.compile(r"\b\d{5}-\d{3}\b"),
    ),
]


def redact_pii(text: str) -> str:
    """Redige PII/segredos em ``text``, substituindo por placeholders tipados.

    Função pura e idempotente sobre os placeholders (rodar de novo não altera
    ``[CPF]`` etc.). Não consulta settings — o controle por flag fica no chamador.

    Args:
        text: Texto de entrada (pode ser vazio).

    Returns:
        Texto com os valores sensíveis substituídos por ``[CPF]``, ``[EMAIL]``,
        ``[TELEFONE]``, ``[CNPJ]``, ``[CARTAO]``, ``[CEP]``, ``[SECRET]``.
    """
    if not text:
        return text

    redacted = text
    for label, pattern in _REDACTORS:
        redacted = pattern.sub(label, redacted)
    return redacted


def redact_pii_with_counts(text: str) -> tuple[str, dict[str, int]]:
    """Como :func:`redact_pii`, mas também retorna a contagem por tipo redigido.

    Útil para observabilidade (logar *quantos* itens foram redigidos, nunca o
    valor). A contagem é feita por aplicação sequencial dos padrões, então
    reflete o que cada redator efetivamente substituiu.

    Args:
        text: Texto de entrada.

    Returns:
        Tupla ``(texto_redigido, {rotulo: quantidade})``. O dicionário só
        contém chaves com quantidade > 0.
    """
    counts: dict[str, int] = {}
    if not text:
        return text, counts

    redacted = text
    for label, pattern in _REDACTORS:
        redacted, n = pattern.subn(label, redacted)
        if n:
            counts[label] = counts.get(label, 0) + n
    return redacted, counts
