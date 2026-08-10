"""
Testes para scripts/sync_plugin_mirror.py — guardião do drift entre as fontes
únicas (data_agents/agents/registry/, skills/) e o espelho gerado em
plugins/ai-data-agents/.

Duas frentes:
  - Testes isolados (tmp_path): exercitam sync_agents/sync_skills/
    update_plugin_manifest_counts/discover_skill_dirs em um projeto sintético
    — cobrem exclusão de _template, EXCLUDE_AGENTS, colisão de nomes de
    skill, staleness reversa e idempotência.
  - TestRealRepoDriftGuard: compara o repositório de verdade (registry/skills
    vs. plugins/ai-data-agents/) e falha se alguém editar/adicionar/remover
    agentes ou skills sem rodar `python scripts/sync_plugin_mirror.py` antes
    de commitar.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.sync_plugin_mirror import (
    EXCLUDE_AGENTS,
    SkillNameCollisionError,
    _SKILL_COPY_IGNORE,
    discover_skill_dirs,
    registry_agent_files,
    sync_agents,
    sync_plugin_mirror,
    sync_skills,
    update_plugin_manifest_counts,
)

_REAL_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _tree_contents(root: Path) -> dict[str, bytes]:
    """Enumera arquivo->bytes sob `root`, aplicando o mesmo filtro de sync_skills.

    Usa o _SKILL_COPY_IGNORE do próprio módulo sincronizado — assim a
    comparação nunca acusa divergência nos artefatos (__pycache__, *.pyc,
    .DS_Store) que a sincronização deliberadamente não copia.
    """
    result: dict[str, bytes] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        ignored = _SKILL_COPY_IGNORE(dirpath, dirnames + filenames)
        dirnames[:] = [d for d in dirnames if d not in ignored]
        rel_dir = Path(dirpath).relative_to(root)
        for fname in filenames:
            if fname in ignored:
                continue
            rel_path = fname if str(rel_dir) == "." else str(rel_dir / fname)
            result[rel_path] = (Path(dirpath) / fname).read_bytes()
    return result


# ─── Fixture: projeto sintético isolado em tmp_path ───────────────────────────


def _make_fake_project(tmp_path: Path) -> Path:
    """Monta um projeto mínimo com registry + skills + plugin.json, isolado em tmp_path."""
    root = tmp_path / "fake-project"

    registry = root / "data_agents" / "agents" / "registry"
    registry.mkdir(parents=True)
    (registry / "_template.md").write_text("template, não deve ser copiado\n", encoding="utf-8")
    (registry / "agent-a.md").write_text("---\nname: agent-a\n---\nAgente A\n", encoding="utf-8")
    (registry / "agent-b.md").write_text("---\nname: agent-b\n---\nAgente B\n", encoding="utf-8")

    skill_one = root / "skills" / "domain1" / "skill-one"
    skill_one.mkdir(parents=True)
    (skill_one / "SKILL.md").write_text("---\nname: skill-one\n---\nSkill One\n", encoding="utf-8")

    loose_skill = root / "skills" / "loose-skill"
    loose_skill.mkdir(parents=True)
    (loose_skill / "SKILL.md").write_text(
        "---\nname: loose-skill\n---\nSkill solta\n", encoding="utf-8"
    )

    template_scaffold = root / "skills" / "domain1" / "TEMPLATE"
    template_scaffold.mkdir(parents=True)
    (template_scaffold / "SKILL.md").write_text("scaffold\n", encoding="utf-8")

    plugin_dir = root / "plugins" / "ai-data-agents" / ".claude-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps(
            {
                "name": "ai-data-agents",
                "version": "0.0.0",
                "description": "Brings 3 specialist agents + 7 skills into Claude Code natively.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return root


@pytest.fixture
def fake_project(tmp_path: Path) -> Path:
    return _make_fake_project(tmp_path)


# ─── sync_agents ───────────────────────────────────────────────────────────────


class TestSyncAgents:
    def test_copies_all_agents_except_template(self, fake_project: Path) -> None:
        count = sync_agents(fake_project)
        target = fake_project / "plugins" / "ai-data-agents" / "agents"
        assert count == 2
        assert sorted(p.name for p in target.glob("*.md")) == ["agent-a.md", "agent-b.md"]
        assert not (target / "_template.md").exists()

    def test_copy_is_byte_identical(self, fake_project: Path) -> None:
        sync_agents(fake_project)
        src = fake_project / "data_agents" / "agents" / "registry" / "agent-a.md"
        dst = fake_project / "plugins" / "ai-data-agents" / "agents" / "agent-a.md"
        assert dst.read_bytes() == src.read_bytes()

    def test_exclude_agents_removes_from_mirror(
        self, fake_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("scripts.sync_plugin_mirror.EXCLUDE_AGENTS", {"agent-b"})
        count = sync_agents(fake_project)
        target = fake_project / "plugins" / "ai-data-agents" / "agents"
        assert count == 1
        assert [p.name for p in target.glob("*.md")] == ["agent-a.md"]

    def test_removes_stale_mirrored_agent(self, fake_project: Path) -> None:
        # Agente que só existe no espelho (removido do registry) deve sumir.
        target = fake_project / "plugins" / "ai-data-agents" / "agents"
        target.mkdir(parents=True, exist_ok=True)
        (target / "ghost-agent.md").write_text("agente fantasma\n", encoding="utf-8")

        sync_agents(fake_project)

        assert not (target / "ghost-agent.md").exists()

    def test_idempotent(self, fake_project: Path) -> None:
        sync_agents(fake_project)
        target = fake_project / "plugins" / "ai-data-agents" / "agents"
        snapshot = {p.name: p.read_bytes() for p in target.glob("*.md")}

        sync_agents(fake_project)

        assert {p.name: p.read_bytes() for p in target.glob("*.md")} == snapshot


# ─── sync_skills ────────────────────────────────────────────────────────────────


class TestSyncSkills:
    def test_flattens_domain_and_loose_layouts(self, fake_project: Path) -> None:
        count = sync_skills(fake_project)
        target = fake_project / "plugins" / "ai-data-agents" / "skills"
        assert count == 2
        assert (target / "skill-one" / "SKILL.md").exists()
        assert (target / "loose-skill" / "SKILL.md").exists()

    def test_skips_template_scaffold(self, fake_project: Path) -> None:
        sync_skills(fake_project)
        target = fake_project / "plugins" / "ai-data-agents" / "skills"
        assert not (target / "TEMPLATE").exists()

    def test_removes_stale_mirrored_skill(self, fake_project: Path) -> None:
        target = fake_project / "plugins" / "ai-data-agents" / "skills" / "ghost-skill"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("fantasma\n", encoding="utf-8")

        sync_skills(fake_project)

        assert not target.exists()

    def test_excludes_pycache_and_ds_store(self, fake_project: Path) -> None:
        skill_dir = fake_project / "skills" / "domain1" / "skill-one"
        pycache = skill_dir / "__pycache__"
        pycache.mkdir()
        (pycache / "mod.cpython-311.pyc").write_bytes(b"\x00")
        (skill_dir / ".DS_Store").write_bytes(b"\x00")

        sync_skills(fake_project)

        mirrored = fake_project / "plugins" / "ai-data-agents" / "skills" / "skill-one"
        assert not (mirrored / "__pycache__").exists()
        assert not (mirrored / ".DS_Store").exists()
        assert (mirrored / "SKILL.md").exists()  # conteúdo real ainda foi copiado

    def test_collision_raises(self, fake_project: Path) -> None:
        # Duas skills-fonte diferentes, mesmo nome de diretório final.
        dup = fake_project / "skills" / "domain2" / "skill-one"
        dup.mkdir(parents=True)
        (dup / "SKILL.md").write_text("duplicata\n", encoding="utf-8")

        with pytest.raises(SkillNameCollisionError):
            sync_skills(fake_project)

    def test_idempotent(self, fake_project: Path) -> None:
        sync_skills(fake_project)
        target = fake_project / "plugins" / "ai-data-agents" / "skills"
        before = sorted(str(p.relative_to(target)) for p in target.rglob("*"))

        sync_skills(fake_project)

        after = sorted(str(p.relative_to(target)) for p in target.rglob("*"))
        assert before == after


# ─── update_plugin_manifest_counts ──────────────────────────────────────────────


class TestUpdateManifestCounts:
    def test_updates_counts_preserves_other_fields(self, fake_project: Path) -> None:
        update_plugin_manifest_counts(22, 57, fake_project)
        manifest = fake_project / "plugins" / "ai-data-agents" / ".claude-plugin" / "plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert "22 specialist agents + 57 skills" in data["description"]
        assert data["name"] == "ai-data-agents"
        assert data["version"] == "0.0.0"

    def test_manifest_stays_valid_json(self, fake_project: Path) -> None:
        update_plugin_manifest_counts(1, 1, fake_project)
        manifest = fake_project / "plugins" / "ai-data-agents" / ".claude-plugin" / "plugin.json"
        json.loads(manifest.read_text(encoding="utf-8"))  # não deve lançar


# ─── sync_plugin_mirror fim-a-fim (fake project) ────────────────────────────────


def test_sync_plugin_mirror_end_to_end_is_idempotent(fake_project: Path) -> None:
    first = sync_plugin_mirror(fake_project)
    second = sync_plugin_mirror(fake_project)
    assert first == second == (2, 2)


# ─── Guardião do drift: compara o repositório real ──────────────────────────────


class TestRealRepoDriftGuard:
    """Lê o repositório de verdade (não tmp_path) — falha se o espelho estiver desatualizado.

    Rode `python scripts/sync_plugin_mirror.py` para corrigir qualquer falha
    aqui antes de commitar mudanças em data_agents/agents/registry/ ou skills/.
    """

    def test_every_registry_agent_has_identical_mirror(self) -> None:
        mirror_dir = _REAL_PROJECT_ROOT / "plugins" / "ai-data-agents" / "agents"
        missing = []
        different = []
        for src in registry_agent_files(_REAL_PROJECT_ROOT):
            mirrored = mirror_dir / src.name
            if not mirrored.exists():
                missing.append(src.name)
            elif mirrored.read_bytes() != src.read_bytes():
                different.append(src.name)

        assert not missing, (
            f"agentes do registry sem espelho em plugins/ai-data-agents/agents/: "
            f"{missing} — rode `python scripts/sync_plugin_mirror.py`"
        )
        assert not different, (
            f"agentes com espelho desatualizado (conteúdo divergente): {different} "
            "— rode `python scripts/sync_plugin_mirror.py`"
        )

    def test_no_orphan_agent_mirrors(self) -> None:
        mirror_dir = _REAL_PROJECT_ROOT / "plugins" / "ai-data-agents" / "agents"
        expected_names = {src.name for src in registry_agent_files(_REAL_PROJECT_ROOT)}
        actual_names = {p.name for p in mirror_dir.glob("*.md")}
        orphans = actual_names - expected_names
        assert not orphans, (
            f"agentes órfãos no espelho (sem fonte no registry, ou excluídos via "
            f"EXCLUDE_AGENTS): {orphans} — rode `python scripts/sync_plugin_mirror.py`"
        )

    def test_excluded_agents_are_not_mirrored(self) -> None:
        mirror_dir = _REAL_PROJECT_ROOT / "plugins" / "ai-data-agents" / "agents"
        for excluded in EXCLUDE_AGENTS:
            assert not (mirror_dir / f"{excluded}.md").exists(), (
                f"'{excluded}' está em EXCLUDE_AGENTS mas ainda existe no espelho"
            )

    def test_every_skill_directory_is_byte_identical_to_mirror(self) -> None:
        """Compara a árvore INTEIRA de cada skill (não só o SKILL.md) contra o espelho."""
        mirror_root = _REAL_PROJECT_ROOT / "plugins" / "ai-data-agents" / "skills"
        problems = []
        for skill_dir in discover_skill_dirs(_REAL_PROJECT_ROOT):
            name = skill_dir.name
            mirrored_dir = mirror_root / name
            if not mirrored_dir.is_dir():
                problems.append(f"{name}: espelho ausente em plugins/ai-data-agents/skills/")
                continue

            expected = _tree_contents(skill_dir)
            actual = _tree_contents(mirrored_dir)
            if expected != actual:
                missing = sorted(set(expected) - set(actual))
                extra = sorted(set(actual) - set(expected))
                differing = sorted(
                    p for p in (set(expected) & set(actual)) if expected[p] != actual[p]
                )
                problems.append(
                    f"{name}: missing={missing} extra={extra} differing={differing}"
                )

        assert not problems, (
            "skills com árvore divergente do espelho — rode "
            "`python scripts/sync_plugin_mirror.py`:\n" + "\n".join(problems)
        )

    def test_no_orphan_skill_mirrors(self) -> None:
        mirror_root = _REAL_PROJECT_ROOT / "plugins" / "ai-data-agents" / "skills"
        expected_names = {
            skill_dir.name for skill_dir in discover_skill_dirs(_REAL_PROJECT_ROOT)
        }
        actual_names = {p.name for p in mirror_root.iterdir() if p.is_dir()}
        orphans = actual_names - expected_names
        assert not orphans, (
            f"diretórios de skill órfãos no espelho (sem fonte em skills/): {orphans} "
            "— rode `python scripts/sync_plugin_mirror.py`"
        )

    def test_plugin_manifest_counts_match_reality(self) -> None:
        manifest_path = (
            _REAL_PROJECT_ROOT
            / "plugins"
            / "ai-data-agents"
            / ".claude-plugin"
            / "plugin.json"
        )
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        description = data["description"]

        expected_agents = len(registry_agent_files(_REAL_PROJECT_ROOT))
        expected_skills = len(discover_skill_dirs(_REAL_PROJECT_ROOT))

        assert f"{expected_agents} specialist agents" in description, (
            f"description do plugin.json não reflete os {expected_agents} agentes "
            "reais do registry — rode `python scripts/sync_plugin_mirror.py`"
        )
        assert f"{expected_skills} skills" in description, (
            f"description do plugin.json não reflete as {expected_skills} skills "
            "reais — rode `python scripts/sync_plugin_mirror.py`"
        )
