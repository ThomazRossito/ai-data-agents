"""
Parser de Slash Commands para o AI Data Agents CLI.

As definições de comandos vivem em `config/commands.yaml` — fonte única de verdade.
Este módulo é apenas um loader + parser + help generator.

Uso:
    from data_agents.commands.parser import parse_command, get_help_text

    result = parse_command("/sql SELECT * FROM tabela")
    if result:
        print(result.agent, result.doma_prompt)
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

# Extensões de texto que expandimos inline no prompt quando o usuário passa
# um path de arquivo como argumento de um slash command. Outras (binárias,
# PDF, imagens) NÃO expandimos — o agente que use Read se precisar.
_INLINE_EXPAND_SUFFIXES = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
    ".tsv",
    ".log",
    ".sql",
    ".py",
    ".jsonl",
    ".xml",
    ".html",
    ".sh",
}

# Limite de tamanho pra expansão automática (500 KB).
# Acima disso, mantemos o path original e deixamos o agente usar Read.
_INLINE_EXPAND_MAX_BYTES = 500 * 1024


def _maybe_expand_file(task: str) -> str:
    """
    Se `task` for um path absoluto OU relativo a um arquivo existente com
    extensão de texto e dentro do limite de tamanho, retorna uma string
    com o conteúdo embutido inline. Caso contrário, retorna o `task` original.

    Motivação: comandos como `/brief <path>` ou `/plan <path>` antes
    dependiam do agente fazer Read() do arquivo. O claude-agent-sdk
    encapsula resultados de Read em arquivos .md como bloco `document`,
    que o Moonshot Kimi K2.6 rejeita com erro 400 ("Input tag 'document'
    found using 'type' does not match any of the expected tags").

    Embutir o conteúdo aqui evita a tool call do Read e mantém tudo como
    bloco `text` puro, compatível com qualquer endpoint Messages-like.
    """
    candidate = task.strip().strip("'\"")
    if not candidate or candidate.startswith("/") is False and "/" not in candidate:
        # Não parece path — pode ser texto normal tipo "qual a diferença entre X"
        if not candidate.lower().endswith(tuple(_INLINE_EXPAND_SUFFIXES)):
            return task

    p = Path(candidate).expanduser()
    if not p.is_absolute():
        # Resolve relativo a cwd
        p = Path.cwd() / p
    try:
        if not p.is_file():
            return task
        if p.suffix.lower() not in _INLINE_EXPAND_SUFFIXES:
            return task
        size = p.stat().st_size
        if size > _INLINE_EXPAND_MAX_BYTES:
            return task  # grande demais — deixa o agente decidir
        content = p.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return task

    # Embute com cabeçalho de proveniência pro agente saber o que é
    return f"[Arquivo: `{p}` · {size} bytes]\n\n```{p.suffix.lstrip('.') or 'text'}\n{content}\n```"


@dataclass(frozen=True)
class CommandResult:
    """Resultado do parsing de um slash command."""

    command: str
    agent: str | None
    doma_prompt: str
    doma_mode: str
    display_message: str


@dataclass(frozen=True)
class CommandDefinition:
    """Definição de um slash command carregada do YAML."""

    name: str
    agent: str | None
    doma_mode: str
    description: str
    skills: list[str]
    prompt_template: str
    display_template: str


_COMMANDS_YAML = Path(__file__).resolve().parent.parent / "config" / "commands.yaml"


def _load_registry() -> dict[str, CommandDefinition]:
    with _COMMANDS_YAML.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    registry: dict[str, CommandDefinition] = {}
    for name, cfg in (data.get("commands") or {}).items():
        registry[name] = CommandDefinition(
            name=name,
            agent=cfg.get("agent"),
            doma_mode=cfg["doma_mode"],
            description=cfg["description"],
            skills=list(cfg.get("skills") or []),
            prompt_template=cfg["prompt_template"],
            display_template=cfg["display_template"],
        )
    return registry


COMMAND_REGISTRY: dict[str, CommandDefinition] = _load_registry()


def parse_command(user_input: str) -> CommandResult | None:
    """Parse um slash command. Retorna CommandResult ou None se inválido."""
    if not user_input.startswith("/"):
        return None

    parts = user_input.split(maxsplit=1)
    command_name = parts[0][1:].lower()
    task_raw = parts[1] if len(parts) > 1 else ""

    definition = COMMAND_REGISTRY.get(command_name)
    if definition is None:
        return None

    # Se task for um path de arquivo de texto, embute o conteúdo inline.
    # Evita que o agente faça Read() — que retorna bloco `document` rejeitado
    # pelo Moonshot Kimi K2.6.
    task_expanded = _maybe_expand_file(task_raw)

    return CommandResult(
        command=f"/{command_name}",
        agent=definition.agent,
        doma_prompt=definition.prompt_template.format(task=task_expanded),
        doma_mode=definition.doma_mode,
        display_message=definition.display_template.format(
            agent=definition.agent or "supervisor",
            # display sempre usa o raw — não polui o terminal com o conteúdo
            task=task_raw,
        ),
    )


def get_help_text() -> str:
    """Gera o texto de ajuda com todos os comandos (Rich markup)."""
    mode_badge = {
        "express": "[yellow]Express[/yellow]",
        "full": "[purple]Full[/purple]",
        "internal": "[cyan]Internal[/cyan]",
    }
    lines = ["[bold]Comandos disponíveis:[/bold]\n"]
    for name, definition in COMMAND_REGISTRY.items():
        badge = mode_badge.get(definition.doma_mode, definition.doma_mode)
        lines.append(f"  [bold green]/{name:<12}[/bold green] {badge:<20} {definition.description}")
    lines.append("")
    lines.append(
        "  [bold green]/help[/bold green]         [dim]Internal[/dim]              Exibe esta ajuda."
    )
    lines.append(
        "  [bold green]/exit[/bold green]         [dim]Internal[/dim]              Encerra a sessão."
    )
    lines.append("")
    lines.append("[bold]Controle de sessão:[/bold]\n")
    lines.append(
        "  [bold cyan]continuar[/bold cyan]     Retoma a sessão anterior a partir do checkpoint salvo."
    )
    lines.append(
        "  [bold cyan]limpar[/bold cyan]        Reseta a sessão atual (salva checkpoint antes)."
    )
    lines.append("  [bold cyan]sair[/bold cyan]          Encerra o AI Data Agents.")
    lines.append("")
    return "\n".join(lines)
