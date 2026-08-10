#!/usr/bin/env python3
"""
Plugin Mirror Sync — regenera plugins/ai-data-agents/{agents,skills} a partir
das fontes únicas do projeto.

Fonte de verdade:
  data_agents/agents/registry/*.md   → plugins/ai-data-agents/agents/*.md
  skills/**/SKILL.md (achatado)      → plugins/ai-data-agents/skills/<nome>/

O layout achatado (dropar o diretório de domínio, manter só o nome do
diretório da skill) replica o mapeamento já usado por scripts/build_plugin.sh
— este script é a versão Python do mesmo espelhamento, com dois adicionais:

  1. Atualiza as contagens ("N specialist agents + M skills") no `description`
     de plugins/ai-data-agents/.claude-plugin/plugin.json.
  2. Exclui __pycache__/*.pyc/*.pyo/.DS_Store do espelho de skills (esses
     artefatos já são ignorados pelo .gitignore do projeto — não são
     rastreados pelo git independentemente do que este script faça, então
     excluí-los aqui não afeta o diff de nenhum CI existente; só evita lixo
     solto em disco).

Uso:
  python scripts/sync_plugin_mirror.py

Idempotente: o script sempre limpa (rm -rf) e reconstrói agents/ e skills/ a
partir da fonte antes de recopiar — rodar duas vezes seguidas não produz
nenhuma mudança adicional, e agentes/skills removidos da fonte não sobrevivem
no espelho (staleness reversa).

Curadoria futura: popule EXCLUDE_AGENTS (abaixo) para impedir que um agente
específico do registry seja espelhado no plugin, mesmo existindo na fonte.
Hoje a política é espelhar TODOS os agentes do registry (conjunto vazio).
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Agentes do registry que NUNCA devem ser espelhados no plugin, mesmo
# existindo em data_agents/agents/registry/. Vazio por padrão — a política
# atual é espelhar TODOS os agentes do registry.
EXCLUDE_AGENTS: set[str] = set()

# Nomes de diretório que nunca são uma skill de verdade (scaffolding).
_SKILL_SCAFFOLD_NAMES = {"TEMPLATE", "_template"}

# Artefatos incidentais que nunca devem ser copiados para o espelho de uma
# skill: bytecode compilado (específico de máquina/versão de Python) e lixo
# de SO. Ver nota no docstring do módulo sobre por que isso é seguro.
_SKILL_COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store")

_DESCRIPTION_COUNTS_RE = re.compile(r"\d+ specialist agents \+ \d+ skills")


class SkillNameCollisionError(RuntimeError):
    """Duas skills de origens diferentes achatariam para o mesmo nome no espelho."""


def registry_agent_files(project_root: Path = _PROJECT_ROOT) -> list[Path]:
    """Agentes do registry a espelhar: todo *.md exceto _template.md e EXCLUDE_AGENTS."""
    registry_dir = project_root / "data_agents" / "agents" / "registry"
    return [
        md
        for md in sorted(registry_dir.glob("*.md"))
        if not md.name.startswith("_") and md.stem not in EXCLUDE_AGENTS
    ]


def discover_skill_dirs(project_root: Path = _PROJECT_ROOT) -> list[Path]:
    """Todo diretório que contém um SKILL.md diretamente, em qualquer profundidade sob skills/.

    Cobre os dois layouts que coexistem hoje em skills/:
      (a) skills/<domínio>/<nome>/SKILL.md   — a maioria das skills
      (b) skills/<nome>/SKILL.md             — skills "soltas" (migration, python)
    """
    skills_root = project_root / "skills"
    dirs = []
    for skill_md in sorted(skills_root.rglob("SKILL.md")):
        skill_dir = skill_md.parent
        if skill_dir.name in _SKILL_SCAFFOLD_NAMES:
            continue
        dirs.append(skill_dir)
    return dirs


def sync_agents(project_root: Path = _PROJECT_ROOT) -> int:
    """Espelha data_agents/agents/registry/*.md -> plugins/ai-data-agents/agents/*.md.

    Cópia byte a byte (shutil.copy2 preserva conteúdo + metadados). O
    diretório de destino é sempre limpo antes de recopiar — garante que
    agentes removidos do registry não sobrevivam no espelho (staleness
    reversa) e que o sync é idempotente.
    """
    target_dir = project_root / "plugins" / "ai-data-agents" / "agents"
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True)

    count = 0
    for md in registry_agent_files(project_root):
        shutil.copy2(md, target_dir / md.name)
        count += 1
    return count


def sync_skills(project_root: Path = _PROJECT_ROOT) -> int:
    """Achata skills/**/<nome>/SKILL.md -> plugins/ai-data-agents/skills/<nome>/.

    Mesmo tratamento de limpar-e-reconstruir do sync_agents: remove órfãos e
    garante idempotência. Levanta SkillNameCollisionError se duas skills de
    domínios diferentes tiverem o mesmo nome de diretório final — o layout
    achatado do plugin não suporta isso.
    """
    target_root = project_root / "plugins" / "ai-data-agents" / "skills"
    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True)

    seen: dict[str, Path] = {}
    count = 0
    for skill_dir in discover_skill_dirs(project_root):
        name = skill_dir.name
        if name in seen:
            raise SkillNameCollisionError(
                f"colisão de nome de skill: '{name}' vem tanto de "
                f"'{seen[name].relative_to(project_root)}' quanto de "
                f"'{skill_dir.relative_to(project_root)}' — o layout achatado do "
                "plugin não suporta duas skills com o mesmo nome de diretório."
            )
        seen[name] = skill_dir
        shutil.copytree(skill_dir, target_root / name, ignore=_SKILL_COPY_IGNORE)
        count += 1
    return count


def update_plugin_manifest_counts(
    agents_count: int, skills_count: int, project_root: Path = _PROJECT_ROOT
) -> None:
    """Atualiza só as contagens no description do plugin.json — resto do JSON intacto."""
    manifest_path = project_root / "plugins" / "ai-data-agents" / ".claude-plugin" / "plugin.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    description = data["description"]
    new_description, n_subs = _DESCRIPTION_COUNTS_RE.subn(
        f"{agents_count} specialist agents + {skills_count} skills", description
    )
    if n_subs == 0:
        raise ValueError(
            "padrão 'N specialist agents + M skills' não encontrado em "
            f"{manifest_path} — description atual: {description!r}"
        )
    data["description"] = new_description

    manifest_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def sync_plugin_mirror(project_root: Path = _PROJECT_ROOT) -> tuple[int, int]:
    """Ponto de entrada programático: roda os três passos e retorna (agentes, skills)."""
    agents_count = sync_agents(project_root)
    skills_count = sync_skills(project_root)
    update_plugin_manifest_counts(agents_count, skills_count, project_root)
    return agents_count, skills_count


def main() -> int:
    registry_dir = _PROJECT_ROOT / "data_agents" / "agents" / "registry"
    skills_dir = _PROJECT_ROOT / "skills"
    manifest_path = _PROJECT_ROOT / "plugins" / "ai-data-agents" / ".claude-plugin" / "plugin.json"

    if not registry_dir.is_dir():
        print(f"fonte não encontrada: {registry_dir}", file=sys.stderr)
        return 1
    if not skills_dir.is_dir():
        print(f"fonte não encontrada: {skills_dir}", file=sys.stderr)
        return 1
    if not manifest_path.is_file():
        print(f"manifesto do plugin não encontrado: {manifest_path}", file=sys.stderr)
        return 1

    agents_count, skills_count = sync_plugin_mirror()
    print(f"✓ synced {agents_count} agents -> plugins/ai-data-agents/agents/")
    print(f"✓ synced {skills_count} skills -> plugins/ai-data-agents/skills/")
    print(
        f"✓ plugin.json description updated: {agents_count} specialist agents "
        f"+ {skills_count} skills"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
