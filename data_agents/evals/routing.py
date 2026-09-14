"""
Evals de roteamento — mede o dispatcher contra o modelo de verdade.

Uso:
    python -m data_agents.evals.routing                    # roda todos os casos
    python -m data_agents.evals.routing --id fabric-rti-kql
    python -m data_agents.evals.routing --limit 5
    python -m data_agents.evals.routing --min-accuracy 0.95

    make eval-routing

Persiste em `logs/evals/routing-<timestamp>.jsonl`.
Exit code 0 se routing_accuracy >= --min-accuracy (default 0.90), senão 1.

O QUE ISTO MEDE (e o que o resto da suíte não mede)
---------------------------------------------------
`tests/unit/test_dispatcher.py` testa as funções do dispatcher com mocks:
dado um JSON de resposta, o parse extrai os agentes certos? A política de
fallback expande na faixa certa de confidence? Tudo verdadeiro e tudo
insuficiente — em 2026-09-13 esses testes estavam verdes enquanto o
dispatcher falhava em 100% das queries reais, porque o modelo gastava o
orçamento inteiro em `thinking` e nunca emitia texto.

Este runner fala com a API. É a única coisa no projeto que responde
"o roteamento funciona?" em vez de "o código do roteamento está correto?".

MÉTRICAS
--------
routing_accuracy  casos aprovados / total. É o gate.
fallback_rate     fração de casos em que o dispatcher NÃO decidiu e o
                  fallback assumiu. O bug de 2026-09-13 daria 1.00 aqui.
                  Qualquer valor > 0 merece investigação antes da accuracy.
avg_selected      largura média da seleção crua (proxy de foco).
avg_final         largura média DEPOIS de apply_fallback_policy — este é o
                  número que vira tokens no system prompt do Supervisor.

CRITÉRIO DE APROVAÇÃO (score_case)
----------------------------------
Um caso passa quando as três condições valem sobre a seleção CRUA:
  1. expect_any vazio, ou pelo menos um dos nomes está selecionado
  2. expect_all inteiramente contido na seleção
  3. nenhum nome de forbid está selecionado
  4. len(selected) <= max_agents (default 5, o teto do próprio contrato
     do dispatcher: "1 a 5 nomes")

A condição 4 é o que dá dente ao eval. Sem ela, o fallback — que devolve o
registry inteiro — satisfaz trivialmente "o agente esperado está na lista" e
o eval marcaria 100% justamente quando o roteamento está morto.

Avalia-se a seleção CRUA, não a final: a crua é a decisão do dispatcher, que
é o que está sendo medido. A final (pós-fallback) entra só como métrica de
custo em `avg_final`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CASES_PATH = PACKAGE_DIR / "routing_cases.yaml"

#: Teto de largura default. Vem do _DISPATCHER_SYSTEM_PROMPT ("1 a 5 nomes"),
#: não de uma escolha arbitrária deste módulo.
DEFAULT_MAX_AGENTS = 5

#: Gate default de routing_accuracy.
DEFAULT_MIN_ACCURACY = 0.90

#: `reason` exatos que o dispatcher devolve quando NÃO decidiu e caiu no
#: fallback de carregar todos os agentes. Espelham os returns de
#: `select_agents` — se um novo for adicionado lá, some aqui também.
_FALLBACK_REASONS = frozenset({"no_content", "invalid_json", "empty_selection"})

#: Mesmos casos, porém com sufixo variável (`http_error:429`, `unexpected:KeyError`).
_FALLBACK_PREFIXES = ("http_error:", "network_error:", "unexpected:")


# ─── Modelos ──────────────────────────────────────────────────────────────────


@dataclass
class RoutingCase:
    id: str
    prompt: str
    expect_any: list[str] = field(default_factory=list)
    expect_all: list[str] = field(default_factory=list)
    forbid: list[str] = field(default_factory=list)
    max_agents: int = DEFAULT_MAX_AGENTS
    note: str = ""

    @property
    def mentioned_agents(self) -> set[str]:
        """Todo nome de agente citado no caso — usado pelo lint do dataset."""
        return set(self.expect_any) | set(self.expect_all) | set(self.forbid)


@dataclass
class RoutingResult:
    case_id: str
    passed: bool
    selected: list[str]
    final: list[str]
    confidence: float
    reason: str
    used_fallback: bool
    failures: list[str]


# ─── Carga ────────────────────────────────────────────────────────────────────


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[RoutingCase]:
    """Carrega os casos do YAML e valida a forma (não os nomes — isso é do lint)."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "cases" not in data:
        raise ValueError(f"YAML inválido em {path}: esperado chave 'cases'")

    cases: list[RoutingCase] = []
    vistos: set[str] = set()
    for entry in data["cases"]:
        if not isinstance(entry, dict):
            raise ValueError(f"Entrada inválida (não é dict): {entry}")
        for required in ("id", "prompt"):
            if required not in entry:
                raise ValueError(f"Caso sem campo obrigatório '{required}': {entry}")

        case_id = str(entry["id"])
        if case_id in vistos:
            raise ValueError(f"id duplicado no dataset: {case_id!r}")
        vistos.add(case_id)

        max_agents = int(entry.get("max_agents", DEFAULT_MAX_AGENTS))
        if max_agents < 1:
            raise ValueError(f"{case_id}: max_agents deve ser >= 1, veio {max_agents}")

        cases.append(
            RoutingCase(
                id=case_id,
                prompt=str(entry["prompt"]).strip(),
                expect_any=list(entry.get("expect_any") or []),
                expect_all=list(entry.get("expect_all") or []),
                forbid=list(entry.get("forbid") or []),
                max_agents=max_agents,
                note=str(entry.get("note", "")).strip(),
            )
        )
    return cases


# ─── Scoring (puro — sem rede, testável offline) ─────────────────────────────


def is_fallback_reason(reason: str) -> bool:
    """True quando o `reason` indica que o dispatcher não decidiu."""
    if reason in _FALLBACK_REASONS:
        return True
    return reason.startswith(_FALLBACK_PREFIXES)


def score_case(case: RoutingCase, selected: list[str]) -> tuple[bool, list[str]]:
    """
    Pontua uma seleção crua contra as expectativas do caso.

    Função pura: mesma entrada, mesma saída, sem rede. É o que os testes
    unitários exercitam para garantir que o eval tem dente antes de gastar
    uma chamada de API.

    Returns:
        (passed, failures) — failures vazio quando passed é True.
    """
    failures: list[str] = []
    sel = set(selected)

    if case.expect_any and not (sel & set(case.expect_any)):
        failures.append(f"nenhum de expect_any={case.expect_any} foi selecionado")

    faltando = [a for a in case.expect_all if a not in sel]
    if faltando:
        failures.append(f"expect_all incompleto: faltam {faltando}")

    proibidos = [a for a in case.forbid if a in sel]
    if proibidos:
        failures.append(f"selecionou agente proibido: {proibidos}")

    if len(selected) > case.max_agents:
        failures.append(
            f"seleção larga demais: {len(selected)} > max_agents={case.max_agents} "
            f"(sinal típico de fallback — o dispatcher não decidiu)"
        )

    return (not failures), failures


def summarize(results: list[RoutingResult]) -> dict[str, float]:
    """Agrega as métricas de um run. Pura — usada no scoreboard e nos testes."""
    total = len(results)
    if total == 0:
        return {
            "total": 0,
            "passed": 0,
            "routing_accuracy": 0.0,
            "fallback_rate": 0.0,
            "avg_selected": 0.0,
            "avg_final": 0.0,
        }
    passed = sum(1 for r in results if r.passed)
    fallbacks = sum(1 for r in results if r.used_fallback)
    return {
        "total": total,
        "passed": passed,
        "routing_accuracy": passed / total,
        "fallback_rate": fallbacks / total,
        "avg_selected": sum(len(r.selected) for r in results) / total,
        "avg_final": sum(len(r.final) for r in results) / total,
    }


# ─── Execução ────────────────────────────────────────────────────────────────


async def run_case(case: RoutingCase, available: dict) -> RoutingResult:
    """Roda um caso contra o dispatcher real e pontua."""
    from data_agents.agents.dispatcher import apply_fallback_policy, select_agents

    try:
        selected, confidence, reason = await select_agents(case.prompt, available)
    except Exception as e:  # noqa: BLE001 — um caso quebrado não derruba o run
        return RoutingResult(
            case_id=case.id,
            passed=False,
            selected=[],
            final=[],
            confidence=0.0,
            reason=f"exception:{type(e).__name__}",
            used_fallback=True,
            failures=[f"exception: {type(e).__name__}: {e}"],
        )

    final = apply_fallback_policy(selected, confidence, available)
    used_fallback = is_fallback_reason(reason)
    passed, failures = score_case(case, selected)

    return RoutingResult(
        case_id=case.id,
        passed=passed,
        selected=selected,
        final=final,
        confidence=confidence,
        reason=reason,
        used_fallback=used_fallback,
        failures=failures,
    )


async def run_all(cases: list[RoutingCase]) -> list[RoutingResult]:
    """Roda todos os casos sequencialmente. Cada dispatch custa ~$0.0001."""
    from data_agents.agents.loader import preload_registry

    available = preload_registry()
    total_agentes = len(available)
    print(f"  registry: {total_agentes} agentes disponíveis\n")

    results: list[RoutingResult] = []
    for i, case in enumerate(cases, 1):
        print(f"  [{i}/{len(cases)}] {case.id}...", flush=True)
        result = await run_case(case, available)
        status = "✅" if result.passed else "❌"
        flag = " ⚠️ FALLBACK" if result.used_fallback else ""
        print(
            f"      {status} {len(result.selected)}/{total_agentes} "
            f"conf={result.confidence:.0%}{flag} → {result.selected}"
        )
        for failure in result.failures:
            print(f"      ↳ {failure}")
        results.append(result)
    return results


# ─── Persistência e scoreboard ───────────────────────────────────────────────


def persist(results: list[RoutingResult], metrics: dict[str, float]) -> Path:
    """Grava o run em logs/evals/routing-<timestamp>.jsonl."""
    evals_dir = REPO_ROOT / "logs" / "evals"
    evals_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = evals_dir / f"routing-{stamp}.jsonl"

    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "summary", "timestamp": stamp, **metrics}) + "\n")
        for r in results:
            f.write(
                json.dumps(
                    {
                        "type": "case",
                        "case_id": r.case_id,
                        "passed": r.passed,
                        "selected": r.selected,
                        "n_final": len(r.final),
                        "confidence": r.confidence,
                        "reason": r.reason,
                        "used_fallback": r.used_fallback,
                        "failures": r.failures,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    return path


def print_scoreboard(metrics: dict[str, float], min_accuracy: float) -> None:
    print("\n═══ Routing scoreboard ═══")
    print(f"  routing_accuracy : {metrics['routing_accuracy']:.1%}  (gate ≥ {min_accuracy:.0%})")
    print(f"  fallback_rate    : {metrics['fallback_rate']:.1%}")
    print(f"  avg_selected     : {metrics['avg_selected']:.1f} agentes (decisão crua)")
    print(f"  avg_final        : {metrics['avg_final']:.1f} agentes (vira system prompt)")
    print(f"  casos            : {int(metrics['passed'])}/{int(metrics['total'])}")

    if metrics["fallback_rate"] > 0:
        print(
            "\n  ⚠️  fallback_rate > 0 — em algum caso o dispatcher NÃO decidiu e o\n"
            "      fallback carregou o registry inteiro. Investigue isto ANTES da\n"
            "      accuracy: costuma ser causa, não consequência."
        )


# ─── CLI ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Eval de roteamento do dispatcher.")
    parser.add_argument("--id", help="roda apenas o caso com este id")
    parser.add_argument("--limit", type=int, help="roda apenas os primeiros N casos")
    parser.add_argument(
        "--min-accuracy",
        type=float,
        default=DEFAULT_MIN_ACCURACY,
        help=f"gate de routing_accuracy (default {DEFAULT_MIN_ACCURACY})",
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    args = parser.parse_args(argv)

    try:
        cases = load_cases(args.cases)
    except (OSError, ValueError) as e:
        print(f"erro carregando casos: {e}", file=sys.stderr)
        return 2

    if args.id:
        cases = [c for c in cases if c.id == args.id]
        if not cases:
            print(f"nenhum caso com id={args.id!r}", file=sys.stderr)
            return 2
    if args.limit:
        cases = cases[: args.limit]

    print(f"\n🎯 Eval de roteamento — {len(cases)} casos\n")
    results = asyncio.run(run_all(cases))
    metrics = summarize(results)
    path = persist(results, metrics)
    print_scoreboard(metrics, args.min_accuracy)
    print(f"\n  run salvo em {path.relative_to(REPO_ROOT)}")

    if metrics["routing_accuracy"] < args.min_accuracy:
        print(
            f"\n❌ routing_accuracy {metrics['routing_accuracy']:.1%} abaixo do "
            f"gate de {args.min_accuracy:.0%}"
        )
        return 1
    print(f"\n✅ routing_accuracy {metrics['routing_accuracy']:.1%} — gate satisfeito")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
