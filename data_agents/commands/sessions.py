"""
commands/sessions.py — Slash command /sessions

Lista sessões registradas no projeto, agregando informação do transcript
(hooks/transcript_hook.py) e do checkpoint (hooks/checkpoint.py).

Uso:
    /sessions          → tabela Rich com as últimas 20 sessões
    /sessions all      → todas as sessões
    /sessions <id>     → detalhes de uma sessão específica

A resume-session propriamente dita é responsabilidade de `/resume` (T4.3);
este módulo cuida apenas de listagem e inspeção.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table

from data_agents.hooks.checkpoint import (
    build_resume_prompt,
    list_sessions as list_checkpoint_sessions,
    load_session_by_id,
)
from data_agents.hooks.transcript_hook import (
    build_resume_prompt_from_transcript,
    list_transcripts,
    load_transcript,
)

_DEFAULT_LIMIT = 20

# Default budget for /resume: 30 turns x 2000 chars = ~15k tokens (~8% of 180k budget).
_RESUME_MAX_TURNS = 30
_RESUME_MAX_CHARS_PER_TURN = 2000

#: Orçamento reduzido de transcript quando existe spec aberto (Onda 2.1).
#:
#: O transcript é uma reconstrução cara e não-determinística do estado: 30 turns
#: custam ~15k tokens e ainda deixam o Supervisor inferindo em que pé o trabalho
#: parou. O frontmatter do spec responde isso em ~50 tokens e com autoridade —
#: `status` é fato registrado, não dedução a partir de conversa.
#:
#: Não zeramos o transcript porque ele carrega o que o spec não carrega: o que
#: o usuário disse de passagem, o que foi descartado e por quê, o tom da
#: decisão. O spec passa a ser a fonte do ESTADO; o transcript, do CONTEXTO.
_RESUME_MAX_TURNS_COM_SPEC = 10


def list_all_sessions() -> list[dict[str, Any]]:
    """
    Unifica sessões registradas em transcript e checkpoint.

    Transcript tem turns e custo acumulado; checkpoint tem o motivo de
    encerramento (budget_exceeded / user_reset / normal_exit / ...). Unimos
    pelo session_id. Entradas com transcript vazio mas com checkpoint ainda
    entram — permitem visualizar sessões antigas que nunca chegaram a gerar
    transcript (criadas antes de T4.1).

    Returns:
        Lista de dicts ordenada por last_timestamp desc.
    """
    transcripts = {t["session_id"]: t for t in list_transcripts()}
    checkpoints = {c["session_id"]: c for c in list_checkpoint_sessions()}

    merged: list[dict[str, Any]] = []
    for sid in set(transcripts) | set(checkpoints):
        t = transcripts.get(sid, {})
        c = checkpoints.get(sid, {})
        last_prompt = t.get("last_user_prompt") or c.get("last_prompt") or ""
        merged.append(
            {
                "session_id": sid,
                "first_timestamp": t.get("first_timestamp") or c.get("timestamp") or "",
                "last_timestamp": t.get("last_timestamp") or c.get("timestamp") or "",
                "turn_count": int(t.get("turn_count") or 0),
                "total_cost_usd": float(t.get("total_cost_usd") or c.get("cost_usd") or 0.0),
                "last_user_prompt": last_prompt[:120],
                "reason": c.get("reason") or "",
                "has_transcript": sid in transcripts,
                "has_checkpoint": sid in checkpoints,
            }
        )

    merged.sort(key=lambda s: s["last_timestamp"], reverse=True)
    return merged


def render_sessions_table(console: Console, limit: int = _DEFAULT_LIMIT) -> int:
    """
    Renderiza uma tabela Rich com as sessões mais recentes.

    Args:
        console: Rich Console onde imprimir.
        limit: Número máximo de linhas a exibir (None/0 = todas).

    Returns:
        Quantidade de sessões exibidas.
    """
    sessions = list_all_sessions()
    if not sessions:
        console.print(
            "[dim]Nenhuma sessão registrada. Arquivos aparecem em "
            "`logs/sessions/<id>.jsonl` após o primeiro turno.[/dim]"
        )
        return 0

    if limit and limit > 0:
        display = sessions[:limit]
    else:
        display = sessions

    table = Table(
        title=f"Sessões registradas ({len(display)}/{len(sessions)})",
        show_lines=False,
        header_style="bold cyan",
    )
    table.add_column("Session ID", style="yellow", no_wrap=True)
    table.add_column("Início", style="dim")
    table.add_column("Última atividade", style="dim")
    table.add_column("Turns", justify="right")
    table.add_column("Custo", justify="right")
    table.add_column("Status", style="magenta")
    table.add_column("Último prompt")

    for s in display:
        status_parts = []
        if s["has_transcript"]:
            status_parts.append("📝")
        if s["has_checkpoint"]:
            status_parts.append(f"💾 {s['reason']}" if s["reason"] else "💾")
        status = " ".join(status_parts) or "—"

        table.add_row(
            s["session_id"],
            (s["first_timestamp"] or "")[:19],
            (s["last_timestamp"] or "")[:19],
            str(s["turn_count"]) if s["turn_count"] else "—",
            f"${s['total_cost_usd']:.4f}",
            status,
            s["last_user_prompt"] or "[dim](sem prompt registrado)[/dim]",
        )

    console.print(table)
    if limit and len(sessions) > limit:
        console.print(
            f"[dim]...e mais {len(sessions) - limit} sessões. "
            f"Use `/sessions all` para ver todas.[/dim]"
        )
    return len(display)


def render_session_details(console: Console, session_id: str) -> bool:
    """
    Exibe o transcript completo de uma sessão.

    Args:
        console: Rich Console.
        session_id: ID da sessão a inspecionar.

    Returns:
        True se a sessão existia; False caso contrário.
    """
    entries = load_transcript(session_id)
    if not entries:
        console.print(
            f"[yellow]Sessão `{session_id}` não encontrada "
            f"(ou sem transcript). Use `/sessions` para listar.[/yellow]"
        )
        return False

    console.print(
        f"[bold cyan]Transcript de `{session_id}` ({len(entries)} entradas)[/bold cyan]\n"
    )
    for entry in entries:
        role = entry.get("role", "?")
        ts = (entry.get("timestamp") or "")[:19]
        content = entry.get("content") or ""
        tools = entry.get("tools_used") or []
        cost = entry.get("cost_usd")

        badge = "[green]👤 User[/green]" if role == "user" else "[blue]🤖 Assistant[/blue]"
        header = f"{badge} [dim]({ts})[/dim]"
        if tools:
            header += f" [dim]— tools: {', '.join(tools[:6])}[/dim]"
        if cost is not None:
            header += f" [dim]— ${cost:.4f}[/dim]"
        console.print(header)

        preview = content if len(content) <= 1000 else content[:1000] + "\n[dim]...(truncado)[/dim]"
        console.print(preview)
        console.print()

    return True


def find_last_session_id() -> str | None:
    """
    Retorna o session_id mais recente disponível (transcript ou checkpoint).

    Returns:
        session_id ou None se não houver nenhuma sessão registrada.
    """
    sessions = list_all_sessions()
    return sessions[0]["session_id"] if sessions else None


def build_spec_context(specs_dir: Any = None) -> str:
    """
    Bloco de retomada baseado nos specs abertos — a fonte de verdade do estado.

    Vazio quando não há spec aberto, e nesse caso o `/resume` se comporta
    exatamente como antes. Specs `concluido` e `cancelado` ficam de fora: o
    valor de `cancelado` existir no enum é justamente não oferecer retomada de
    trabalho que alguém encerrou de propósito.

    Falha em silêncio (devolve "") se o módulo de spec não puder ser lido. Um
    `/resume` que estoura porque um spec está malformado é pior que um `/resume`
    sem o bloco — o transcript ainda leva o usuário adiante.
    """
    try:
        from data_agents.spec.store import specs_abertos
    except Exception:  # noqa: BLE001 — /resume nunca pode quebrar por causa disto
        return ""

    try:
        abertos = specs_abertos(specs_dir)
    except Exception:  # noqa: BLE001
        return ""

    if not abertos:
        return ""

    linhas = [
        "## Trabalho em aberto — specs (FONTE DE VERDADE do estado)",
        "",
        "| spec_id | título | status | trilha | rev | arquivo |",
        "|---|---|---|---|---|---|",
    ]
    for s in sorted(abertos, key=lambda x: x.atualizado_em, reverse=True):
        nome = s.caminho.name if s.caminho else "?"
        linhas.append(
            f"| `{s.spec_id}` | {s.titulo} | **{s.status.value}** | "
            f"{s.trilha.value} | {s.iteracao_revisao} | `{nome}` |"
        )

    linhas += [
        "",
        "Retome pelo `status` de cada spec (Step 0.9.c) — **não recomece do zero**.",
        "Case o spec pelo campo `spec_id`, nunca pelo nome do arquivo.",
        "O bloco `<intencao-congelada>` de cada spec é do humano: leia, não reescreva.",
        "",
        "---",
        "",
    ]
    return "\n".join(linhas)


def build_resume_prompt_for_session(
    session_id: str,
    max_turns: int = _RESUME_MAX_TURNS,
    max_chars_per_turn: int = _RESUME_MAX_CHARS_PER_TURN,
) -> str | None:
    """
    Constrói o prompt de retomada para uma sessão.

    Ordem de precedência (Onda 2.1):

      1. **Specs abertos** — o estado autoritativo. `status` é fato registrado;
         o transcript é dedução a partir de conversa.
      2. **Transcript** — o contexto que o spec não guarda (o que foi descartado
         e por quê, o que o usuário disse de passagem). Quando há spec aberto, o
         orçamento cai de 30 para 10 turns: o estado já veio do frontmatter.
      3. **Checkpoint** — compatibilidade com sessões antigas, sem transcript.

    Args:
        session_id: ID da sessão.
        max_turns: Teto de turns do transcript. Reduzido automaticamente para
            `_RESUME_MAX_TURNS_COM_SPEC` quando há spec aberto — a menos que o
            chamador tenha passado um valor menor de propósito.
        max_chars_per_turn: Teto de caracteres por turno.

    Returns:
        Prompt pronto para o Supervisor, ou None se não houver absolutamente
        nada para retomar.
    """
    bloco_spec = build_spec_context()

    turns = min(max_turns, _RESUME_MAX_TURNS_COM_SPEC) if bloco_spec else max_turns

    prompt = build_resume_prompt_from_transcript(
        session_id, max_turns=turns, max_chars_per_turn=max_chars_per_turn
    )
    if prompt:
        return bloco_spec + prompt

    # Fallback: checkpoint-based (sessão sem transcript)
    checkpoint = load_session_by_id(session_id)
    if checkpoint:
        return bloco_spec + build_resume_prompt(checkpoint)

    # Sem transcript e sem checkpoint: se ainda assim há spec aberto, ele sozinho
    # já é motivo suficiente para retomar — é mais informativo que o transcript
    # de uma sessão que não deixou rastro.
    return bloco_spec or None


def handle_sessions_command(user_input: str, console: Console) -> None:
    """
    Dispatcher do slash command /sessions.

    Args:
        user_input: String completa digitada pelo usuário (com "/sessions ...").
        console: Rich Console para saída.
    """
    parts = user_input.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if not arg:
        render_sessions_table(console, limit=_DEFAULT_LIMIT)
        return

    if arg.lower() == "all":
        render_sessions_table(console, limit=0)
        return

    # Qualquer outro argumento é tratado como session_id para inspeção detalhada.
    render_session_details(console, arg)
