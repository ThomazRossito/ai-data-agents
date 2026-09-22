#!/usr/bin/env python3
"""
sync_databricks_skills.py — traz as skills oficiais da Databricks para skills/databricks/.

FLUXO (item 1.5 da Onda 1)
--------------------------
    databricks aitools install --path <tmp>            # CLI baixa as skills oficiais
    python scripts/sync_databricks_skills.py <tmp>      # este script sincroniza

O CLI grava os arquivos crus num diretório à escolha (`--path`) sem tocar em
agente nenhum nem gravar estado. Este script pega esse diretório e sincroniza
com `skills/databricks/`, onde o loader dos agentes lê.

POR QUE NÃO `--scope project` DIRETO
------------------------------------
`--scope project` instala como plugin do Claude Code em `.claude/`. Isso
(a) não é onde `agents/loader.py` lê (`skills/<domínio>/<nome>/SKILL.md`),
(b) contorna o índice `skill_domains`, o espelho `plugins/` e os lints, e
(c) mudaria o mecanismo de entrega de skills no meio da Onda 1. `--path` +
sync mantém a arquitetura: skills versionadas no repo, testadas na CI.

O custo: `databricks aitools list/update` não rastreiam instalações por
`--path`. O rastreio é nosso — `skills/databricks/UPSTREAM.json` — e o
`--check` deste script compara o que está no repo com o que o CLI baixaria.

TRÊS CLASSES DE DIRETÓRIO EM skills/databricks/
-----------------------------------------------
  upstream   veio do CLI; este script SUBSTITUI e REMOVE conforme a fonte
  custom     nasceu aqui (ver CUSTOM abaixo e PROVENANCE.md); NUNCA tocado
  scaffold   TEMPLATE/; nunca tocado

Um diretório upstream que sumiu da fonte é REMOVIDO — é assim que os renomes
oficiais se aplicam (`databricks-bundles` some, `databricks-dabs` entra). O
script imprime o que removeu para que o commit registre.

Uso:
    python scripts/sync_databricks_skills.py <dir-do-aitools>           # sincroniza
    python scripts/sync_databricks_skills.py <dir-do-aitools> --check   # só compara, exit 1 se divergir
    python scripts/sync_databricks_skills.py --list                     # mostra classes atuais
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills" / "databricks"
MANIFEST = SKILLS_DIR / "UPSTREAM.json"

#: Skills que NASCERAM neste repositório. Não existem no catálogo oficial e
#: `databricks aitools` não as conhece. Este script nunca as toca.
#: Espelha a seção 2 de skills/databricks/PROVENANCE.md e é protegido por
#: tests/unit/test_functional.py::TestCustomSkillsSurvive.
CUSTOM: frozenset[str] = frozenset(
    {
        "databricks-genie-health-check",
        "databricks-observability-migration",
        "pricing",
    }
)

#: Diretórios de scaffolding — nunca são skill de verdade.
SCAFFOLD: frozenset[str] = frozenset({"TEMPLATE", "_template"})

#: Renomes conhecidos (antigo → novo) — só para a mensagem de saída ser
#: informativa. O mecanismo não depende disto: qualquer upstream ausente na
#: fonte é removido, qualquer presente é gravado.
RENOMES_CONHECIDOS: dict[str, str] = {
    "databricks-bundles": "databricks-dabs",
    "databricks-config": "databricks-core",
    "databricks-spark-declarative-pipelines": "databricks-pipelines",
    "databricks-lakebase-autoscale": "databricks-lakebase",
    "databricks-lakebase-provisioned": "databricks-lakebase",
    "databricks-genie": "databricks-agent-bricks + databricks-data-discovery",
}

_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store")


class SyncError(RuntimeError):
    pass


def _skill_dirs(root: Path) -> dict[str, Path]:
    """Diretórios que contêm SKILL.md diretamente, por nome."""
    if not root.is_dir():
        return {}
    out: dict[str, Path] = {}
    for d in sorted(root.iterdir()):
        if d.is_dir() and (d / "SKILL.md").is_file():
            out[d.name] = d
    return out


def classificar(skills_dir: Path = SKILLS_DIR) -> dict[str, list[str]]:
    """Separa os diretórios atuais em upstream / custom / scaffold."""
    atuais = _skill_dirs(skills_dir)
    scaffold = sorted(d.name for d in skills_dir.iterdir() if d.is_dir() and d.name in SCAFFOLD)
    custom = sorted(n for n in atuais if n in CUSTOM)
    upstream = sorted(n for n in atuais if n not in CUSTOM and n not in SCAFFOLD)
    return {"upstream": upstream, "custom": custom, "scaffold": scaffold}


def _validar_fonte(fonte: Path) -> dict[str, Path]:
    skills = _skill_dirs(fonte)
    if not skills:
        raise SyncError(
            f"{fonte} não contém nenhum <skill>/SKILL.md — é a saída de "
            "`databricks aitools install --path {fonte}`?"
        )
    colisao = sorted(set(skills) & CUSTOM)
    if colisao:
        raise SyncError(
            f"a fonte upstream traz skills com o MESMO nome das custom: {colisao}. "
            "Ou a Databricks publicou algo homônimo, ou a lista CUSTOM está errada. "
            "Resolva antes de sincronizar — sobrescrever apagaria trabalho local."
        )
    return skills


def diff(fonte: Path, skills_dir: Path = SKILLS_DIR) -> dict[str, list[str]]:
    """O que mudaria. Chaves: adicionar, remover, atualizar (conteúdo diferente)."""
    novos = _validar_fonte(fonte)
    classes = classificar(skills_dir)
    atuais_upstream = set(classes["upstream"])

    adicionar = sorted(set(novos) - atuais_upstream)
    remover = sorted(atuais_upstream - set(novos))
    atualizar: list[str] = []
    for nome in sorted(set(novos) & atuais_upstream):
        if not _arvores_iguais(novos[nome], skills_dir / nome):
            atualizar.append(nome)
    return {"adicionar": adicionar, "remover": remover, "atualizar": atualizar}


def _arvores_iguais(a: Path, b: Path) -> bool:
    def snapshot(root: Path) -> dict[str, bytes]:
        out = {}
        for p in root.rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".pyo"}:
                if p.name == ".DS_Store":
                    continue
                out[str(p.relative_to(root))] = p.read_bytes()
        return out

    return snapshot(a) == snapshot(b)


def sync(fonte: Path, skills_dir: Path = SKILLS_DIR, *, versao: str = "") -> dict[str, list[str]]:
    """Aplica a fonte sobre skills_dir. Devolve o mesmo dict de `diff`."""
    novos = _validar_fonte(fonte)
    mudancas = diff(fonte, skills_dir)

    for nome in mudancas["remover"]:
        shutil.rmtree(skills_dir / nome)
    for nome in mudancas["adicionar"] + mudancas["atualizar"]:
        destino = skills_dir / nome
        if destino.exists():
            shutil.rmtree(destino)
        shutil.copytree(novos[nome], destino, ignore=_IGNORE)

    _gravar_manifest(skills_dir, sorted(novos), versao)
    return mudancas


def _gravar_manifest(skills_dir: Path, upstream: list[str], versao: str) -> None:
    manifest = {
        "fonte": "databricks/databricks-agent-skills via `databricks aitools install --path`",
        "versao_aitools": versao or "desconhecida — rode `databricks aitools version`",
        "sincronizado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "upstream": upstream,
        "custom": sorted(CUSTOM),
        "nota": (
            "Gerado por scripts/sync_databricks_skills.py. `databricks aitools list/update` "
            "NÃO rastreiam instalação por --path; este arquivo é o rastreio. Para "
            "atualizar: make refresh-databricks-skills."
        ),
    }
    (skills_dir / "UPSTREAM.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def ler_manifest(skills_dir: Path = SKILLS_DIR) -> dict | None:
    p = skills_dir / "UPSTREAM.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _imprimir_mudancas(m: dict[str, list[str]]) -> None:
    for nome in m["adicionar"]:
        origem = [a for a, n in RENOMES_CONHECIDOS.items() if n == nome]
        sufixo = f"   (renome de {', '.join(origem)})" if origem else ""
        print(f"  + {nome}{sufixo}")
    for nome in m["remover"]:
        novo = RENOMES_CONHECIDOS.get(nome)
        sufixo = f"   → virou {novo}" if novo else "   (sumiu do catálogo oficial)"
        print(f"  - {nome}{sufixo}")
    for nome in m["atualizar"]:
        print(f"  ~ {nome}")
    if not any(m.values()):
        print("  (nada a mudar)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("fonte", nargs="?", type=Path, help="dir gerado por `aitools install --path`")
    ap.add_argument("--check", action="store_true", help="só compara; exit 1 se divergir")
    ap.add_argument(
        "--list", action="store_true", help="classifica o que está em skills/databricks/"
    )
    ap.add_argument(
        "--versao", default="", help="saída de `databricks aitools version`, para o manifest"
    )
    ap.add_argument(
        "--skills-dir",
        type=Path,
        default=None,
        help="destino (default: skills/databricks/ do repo). Testes DEVEM passar isto — em "
        "2026-09-22 um teste sem ele sobrescreveu o diretório real com fixtures.",
    )
    args = ap.parse_args(argv)
    # Resolvido AQUI, em tempo de chamada — nunca como default de parâmetro de
    # função (default é avaliado na definição e ignora monkeypatch/override).
    skills_dir: Path = args.skills_dir if args.skills_dir is not None else SKILLS_DIR

    if args.list:
        c = classificar(skills_dir)
        for k in ("upstream", "custom", "scaffold"):
            print(f"{k} ({len(c[k])}): {', '.join(c[k])}")
        m = ler_manifest(skills_dir)
        if m:
            print(
                f"\nUPSTREAM.json: {len(m['upstream'])} skills, aitools {m['versao_aitools']}, {m['sincronizado_em']}"
            )
        else:
            print("\nUPSTREAM.json: ausente — nunca sincronizado por este script")
        return 0

    if args.fonte is None:
        ap.error("informe o diretório fonte (ou --list)")

    try:
        if args.check:
            m = diff(args.fonte, skills_dir)
            print(f"diff fonte → {skills_dir}:")
            _imprimir_mudancas(m)
            return 1 if any(m.values()) else 0
        m = sync(args.fonte, skills_dir, versao=args.versao)
        print("sincronizado:")
        _imprimir_mudancas(m)
        print(f"\n✓ UPSTREAM.json gravado. Custom preservadas: {', '.join(sorted(CUSTOM))}")
        print(
            "  Próximo: bash scripts/build_plugin.sh && python scripts/lint_skills.py && make test-fast"
        )
        return 0
    except SyncError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
