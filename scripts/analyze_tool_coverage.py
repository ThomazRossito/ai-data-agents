"""
Análise estática — tools oferecidas vs tools efetivamente usadas.

Cruza o registry de agentes (agents/registry/*.md) com o histórico de tool calls
em logs/audit.jsonl para validar a premissa central do Tool Router:
agentes usam uma fração pequena (~15%) das tools MCP que recebem no schema.

Saída: relatório ASCII com macro / por agente / por MCP / top-N / dormentes.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.loader import preload_registry, _resolve_tools  # noqa: E402

AUDIT_PATH = PROJECT_ROOT / "logs" / "audit.jsonl"


def load_tools_offered_per_agent() -> dict[str, set[str]]:
    """Para cada agente, set de tools MCP oferecidas (aliases já resolvidos)."""
    registry = preload_registry()
    result: dict[str, set[str]] = {}
    for name, meta in registry.items():
        resolved = _resolve_tools(meta.tools)
        result[name] = {t for t in resolved if t.startswith("mcp__")}
    return result


def load_tool_calls_from_audit() -> Counter:
    """Conta chamadas por tool_name no audit.jsonl — só MCP tools."""
    counter: Counter = Counter()
    with open(AUDIT_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = entry.get("tool_name", "")
            if name.startswith("mcp__"):
                counter[name] += 1
    return counter


def group_by_mcp(tool_names) -> dict[str, set[str]]:
    """Agrupa tools pelo prefixo mcp__<server>__."""
    groups: dict[str, set[str]] = defaultdict(set)
    for t in tool_names:
        parts = t.split("__")
        if len(parts) >= 2:
            groups[parts[1]].add(t)
    return dict(groups)


def main() -> None:
    print("=" * 88)
    print("ANÁLISE ESTÁTICA — TOOLS OFERECIDAS vs USADAS")
    print("=" * 88)

    per_agent = load_tools_offered_per_agent()
    all_offered: set[str] = set()
    for tools in per_agent.values():
        all_offered |= tools

    called = load_tool_calls_from_audit()
    called_set = set(called.keys())

    total_calls = sum(called.values())
    dormant = all_offered - called_set
    coverage = len(called_set & all_offered) / len(all_offered) * 100 if all_offered else 0

    print("\nMACRO")
    print(f"   Tools MCP declaradas (união de agentes):   {len(all_offered):>4d}")
    print(f"   Tools MCP efetivamente chamadas:           {len(called_set):>4d}")
    print(f"   Cobertura global:                          {coverage:>4.1f}%")
    print(f"   Dormentes (declaradas e nunca chamadas):   {len(dormant):>4d}")
    print(f"   Total de chamadas MCP no audit.jsonl:      {total_calls:>4d}")

    print("\nPOR AGENTE — tools oferecidas no schema vs tools já usadas em histórico")
    rows = []
    for name, tools in per_agent.items():
        if not tools:
            continue
        intersect = tools & called_set
        pct = len(intersect) / len(tools) * 100
        rows.append((name, len(tools), len(intersect), pct))
    rows.sort(key=lambda r: -r[1])
    for name, offered, used, pct in rows:
        print(
            f"   {name:<26s}  oferecidas:{offered:>3d}   usadas:{used:>3d}   cobertura:{pct:>5.1f}%"
        )

    print("\nPOR MCP SERVER")
    offered_by_mcp = group_by_mcp(all_offered)
    called_by_mcp = group_by_mcp(called_set)
    mcps = sorted(set(offered_by_mcp) | set(called_by_mcp))
    for mcp in mcps:
        off = offered_by_mcp.get(mcp, set())
        cal = called_by_mcp.get(mcp, set())
        used = off & cal
        ghost = cal - off
        pct = len(used) / len(off) * 100 if off else 0
        calls_mcp = sum(v for k, v in called.items() if k in cal)
        print(
            f"   {mcp:<22s}  declaradas:{len(off):>3d}   usadas:{len(used):>3d}   "
            f"cobertura:{pct:>5.1f}%   ghost:{len(ghost):>2d}   total_calls:{calls_mcp:>4d}"
        )

    print("\nTOP 20 TOOLS MAIS CHAMADAS")
    for tool, count in called.most_common(20):
        offered_in = sum(1 for tools in per_agent.values() if tool in tools)
        in_registry = "R" if tool in all_offered else "ghost"
        print(f"   {count:>5d}   {tool:<55s}  agentes:{offered_in}  [{in_registry}]")

    print(f"\nDORMENTES — amostra de até 20 (declaradas, nunca chamadas em {total_calls} calls)")
    dormant_sorted = sorted(dormant)
    for tool in dormant_sorted[:20]:
        offered_in = sum(1 for tools in per_agent.values() if tool in tools)
        print(f"          {tool:<55s}  agentes:{offered_in}")
    if len(dormant) > 20:
        print(f"   ... +{len(dormant) - 20} outras tools dormentes")

    print("\n" + "=" * 88)
    print("CONCLUSÃO")
    print("=" * 88)
    used_pct = coverage
    dormant_pct = 100 - used_pct
    print(f"   Dos {len(all_offered)} tools MCP disponíveis no sistema,")
    print(f"   apenas {len(called_set & all_offered)} foram usados ({used_pct:.1f}%).")
    print(
        f"   {len(dormant)} tools ({dormant_pct:.1f}%) nunca foram chamados em {total_calls} requests."
    )
    if dormant_pct >= 60:
        print("   >> PREMISSA VALIDADA: há espaço claro para routing dinâmico.")
    elif dormant_pct >= 30:
        print("   >> PREMISSA PARCIAL: ganho existe mas menor que o estimado.")
    else:
        print("   >> PREMISSA NÃO CONFIRMADA: abortar proposta do Tool Router.")


if __name__ == "__main__":
    main()
