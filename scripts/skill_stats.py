"""
Skill Stats — Relatório de uso de Skills pelos agentes.

Lê logs/audit.jsonl e mostra quais Skills foram acessadas, por quem e quantas vezes.
Permite saber se as Skills injetadas estão sendo realmente consultadas pelos agentes.

Uso:
  python scripts/skill_stats.py                 # últimas 7 sessões
  python scripts/skill_stats.py --days 30       # últimos 30 dias
  python scripts/skill_stats.py --verbose       # inclui timestamps de cada acesso
  python scripts/skill_stats.py --not-used      # skills disponíveis mas nunca acessadas

Também acessível via: make skill-stats
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

_AUDIT_LOG = _PROJECT_ROOT / "logs" / "audit.jsonl"
_SKILLS_DIR = _PROJECT_ROOT / "skills"


def _load_audit_entries(since: datetime) -> list[dict]:
    """Lê o audit.jsonl e retorna entradas após `since`."""
    if not _AUDIT_LOG.exists():
        return []

    entries = []
    with open(_AUDIT_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts_str = entry.get("timestamp", "")
                if ts_str:
                    ts = datetime.fromisoformat(ts_str)
                    if ts >= since:
                        entries.append(entry)
            except (json.JSONDecodeError, ValueError):
                continue
    return entries


def _get_all_skill_paths() -> list[str]:
    """Retorna paths relativos de todos os SKILL.md disponíveis."""
    paths = []
    for p in sorted(_SKILLS_DIR.rglob("SKILL.md")):
        if not any(part.startswith("_") or part.upper() == "TEMPLATE" for part in p.parts):
            paths.append(str(p.relative_to(_PROJECT_ROOT)))
    return paths


def _is_skill_access(file_path: str) -> bool:
    """Retorna True se o file_path aponta para um arquivo dentro de skills/."""
    return "skills/" in file_path and file_path.endswith(".md")


def run_stats(days: int = 7, verbose: bool = False, show_not_used: bool = False) -> None:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    entries = _load_audit_entries(since)

    if not entries:
        print(f"\nNenhuma entrada no audit log desde {since.strftime('%Y-%m-%d')}.")
        if not _AUDIT_LOG.exists():
            print(f"Arquivo não encontrado: {_AUDIT_LOG}")
            print("Execute o sistema ao menos uma vez para gerar logs de auditoria.")
        return

    # ── Filtra acessos a skills ────────────────────────────────────
    skill_accesses: list[dict] = []
    for entry in entries:
        fp = entry.get("file_path", "")
        if fp and _is_skill_access(fp):
            skill_accesses.append(entry)

    # ── Contagens ─────────────────────────────────────────────────
    # skill_path → lista de timestamps
    by_skill: dict[str, list[str]] = defaultdict(list)
    for acc in skill_accesses:
        skill_path = acc["file_path"]
        # Normaliza para path relativo à raiz
        if skill_path.startswith(str(_PROJECT_ROOT)):
            skill_path = skill_path[len(str(_PROJECT_ROOT)) + 1 :]
        by_skill[skill_path].append(acc["timestamp"])

    total_entries = len(entries)
    total_reads = sum(1 for e in entries if e.get("tool_name") == "Read")
    total_skill_reads = len(skill_accesses)

    # ── Relatório ─────────────────────────────────────────────────
    print(f"\n{'=' * 64}")
    print(f"  Skill Usage Report — últimos {days} dias")
    print(f"  Período: {since.strftime('%Y-%m-%d')} → {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'=' * 64}")
    print(f"\n  Total de tool calls auditadas : {total_entries}")
    print(f"  Calls de Read (todos arquivos) : {total_reads}")
    print(f"  Acessos a Skills               : {total_skill_reads}")

    if not by_skill:
        print("\n  ⚠️  Nenhuma Skill foi acessada neste período.")
        print("\n  Possíveis causas:")
        print("    • Os agentes ainda não foram invocados em tarefas que exigem skills")
        print("    • O índice de skills está sendo injetado, mas os agentes optaram por context7")
        print("    • As skills disponíveis não cobrem os domínios das tarefas executadas")
    else:
        print(f"\n  Skills acessadas ({len(by_skill)} únicas):")
        print(f"  {'-' * 60}")

        # Ordena por frequência (mais acessadas primeiro)
        sorted_skills = sorted(by_skill.items(), key=lambda x: len(x[1]), reverse=True)

        for skill_path, timestamps in sorted_skills:
            count = len(timestamps)
            last_access = max(timestamps)
            last_dt = datetime.fromisoformat(last_access).strftime("%Y-%m-%d %H:%M")
            bar = "█" * min(count, 20)
            skill_name = Path(skill_path).parent.name
            print(f"\n  {bar} {count}x")
            print(f"    📄 {skill_path}")
            print(f"       Skill: {skill_name} | Último acesso: {last_dt}")

            if verbose:
                for ts in sorted(timestamps):
                    dt = datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S")
                    print(f"         → {dt}")

    # ── Skills disponíveis mas nunca acessadas ────────────────────
    if show_not_used:
        all_skills = set(_get_all_skill_paths())
        accessed = set(by_skill.keys())
        not_used = sorted(all_skills - accessed)

        print(f"\n  {'=' * 60}")
        print(f"  Skills disponíveis mas NÃO acessadas: {len(not_used)}")
        print("  (considere se estas skills são relevantes para os agentes com skill_domains)")
        print(f"  {'-' * 60}")
        for sp in not_used:
            skill_name = Path(sp).parent.name
            domain = Path(sp).parts[1] if len(Path(sp).parts) > 2 else "root"
            print(f"    ○ [{domain}] {skill_name}")

    # ── Acessos a KBs (contexto comparativo) ──────────────────────
    kb_reads = [e for e in entries if "kb/" in e.get("file_path", "")]
    if kb_reads:
        kb_by_file: dict[str, int] = defaultdict(int)
        for e in kb_reads:
            fp = e["file_path"]
            if fp.startswith(str(_PROJECT_ROOT)):
                fp = fp[len(str(_PROJECT_ROOT)) + 1 :]
            kb_by_file[fp] += 1

        print(f"\n  {'=' * 60}")
        print(f"  KBs acessadas (comparativo): {sum(kb_by_file.values())} reads")
        for kp, cnt in sorted(kb_by_file.items(), key=lambda x: -x[1])[:5]:
            print(f"    {cnt}x  {kp}")

    print(f"\n{'=' * 64}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Relatório de uso de Skills operacionais pelos agentes."
    )
    parser.add_argument(
        "--days", type=int, default=7, help="Período de análise em dias. Padrão: 7."
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Exibe timestamps individuais de cada acesso."
    )
    parser.add_argument(
        "--not-used",
        action="store_true",
        help="Lista skills disponíveis mas nunca acessadas no período.",
    )
    args = parser.parse_args()
    run_stats(days=args.days, verbose=args.verbose, show_not_used=args.not_used)


if __name__ == "__main__":
    main()
