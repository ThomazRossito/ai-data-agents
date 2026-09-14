"""DOMA Spec — máquina de estados e persistência dos specs (Onda 2.1)."""

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

__all__ = [
    "ESTADOS_FINAIS",
    "MAX_ITERACOES_REVISAO",
    "LimiteDeRevisaoExcedido",
    "SpecStatus",
    "TransicaoInvalida",
    "Trilha",
    "parse_status",
    "parse_trilha",
    "pode_transicionar",
    "proxima_iteracao_revisao",
    "transicoes_validas",
    "validar_transicao",
]
