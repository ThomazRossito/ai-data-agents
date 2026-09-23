"""
Data de hoje para os prompts.

Nenhum prompt do projeto dizia ao modelo que dia é hoje. O treino termina
numa data anterior, e sem a data corrente "atual", "recente" e "GA" são
julgados pelo calendário do treino (numa rodada de 2026-09-15 o agente
escreveu "knowledge base interna com cutoff em ago/2025" sobre um produto
lançado em jun/2026). Pedido do autor, set/2026: "estamos no ano 2026 mês 09".

A nota vai sempre no FIM do prompt, nunca no cache_prefix.md: o prefixo
compartilhado precisa ser byte-idêntico entre execuções (prompt caching).
Uma linha que muda uma vez por dia na cauda custa um miss de cache na cauda,
uma vez por dia; o prefixo continua cacheado.
"""

from __future__ import annotations

from datetime import date

_MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)  # fmt: skip


def hoje() -> date:
    """Data local da máquina. Isolada numa função para os testes fixarem o dia."""
    return date.today()


def current_date_note(today: date | None = None) -> str:
    """Bloco markdown com a data de hoje, para anexar ao FIM de um system prompt."""
    d = today or hoje()
    return (
        "\n\n---\n\n"
        "## Data de hoje\n\n"
        f"Hoje é {d.isoformat()} ({_MESES[d.month - 1]} de {d.year}). "
        "Seu conhecimento de treino termina antes disso: lançamentos, renomes e mudanças "
        "de status (Preview → GA) desse intervalo você não conhece de memória. Para "
        'qualquer afirmação datada — versão, status, nome de produto, "atual", "recente" — '
        "confirme na documentação oficial antes de afirmar.\n"
    )
