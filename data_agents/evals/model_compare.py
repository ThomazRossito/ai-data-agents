"""
Eval conceitual + comparação de modelos — "o especialista sabe do que fala?"

Uso:
    python -m data_agents.evals.model_compare --label kimi-k2.6
    python -m data_agents.evals.model_compare --label kimi-k2.6 --id genie-ontology
    python -m data_agents.evals.model_compare --label kimi-k2.6 --repeat 3
    python -m data_agents.evals.model_compare --compare logs/evals/a.json logs/evals/b.json

    make eval-model-compare LABEL=kimi-k2.6

Persiste em `logs/evals/model-compare-<label>-<timestamp>.json`.
Sem gate por padrão: é comparação, não CI. `--min-accuracy` liga um gate.

POR QUE EXISTE
--------------
Em 2026-09-14/15 a pergunta "me fale sobre o Genie Ontology" saiu errada
quatro vezes seguidas, de quatro jeitos, apesar de três correções de prompt e
um hook determinístico. Na quinta rodada saiu certa — mas quem buscou na web
foi o `general-purpose` (subagente built-in do Claude Code), não o
`databricks-engineer`, que tinha `tavily-search` disponível e não a usou em
NENHUMA das cinco. A suspeita passou do harness para o modelo. Suspeita se
resolve com medição, não com a sexta correção de prompt.

Este runner roda o PIPELINE INTEIRO (dispatcher → Supervisor → subagente →
tools), como `cli.py` faz, e mede por caso:

    correct              a resposta contém os grupos OR de `must_include`
    web_search_by        QUEM chamou tavily/firecrawl no turno (por agente)
    specialist_searched  o agente esperado (`agent_hint`) buscou na web
    negations            trechos "não existe"/"não é um produto" no texto final
    unverified_negation  eventos do negation guard no turno
    off_dispatch         delegações a agentes FORA da seleção do dispatcher
                         (ex.: `general-purpose`, que é built-in e sempre existe)
    cost / duration / turns / tokens

Rodar duas vezes — endpoint Moonshot e endpoint Anthropic — e comparar com
`--compare` é o objetivo. Troca de provedor é só ambiente:

    ANTHROPIC_BASE_URL=https://api.anthropic.com \\
    ANTHROPIC_API_KEY=<chave Anthropic> \\
    DEFAULT_MODEL=<id do modelo> \\
    TIER_MODEL_MAP='{"T0":"<id>","T1":"<id>","T2":"<id>","T3":"<id>"}' \\
    python -m data_agents.evals.model_compare --label anthropic

O run grava modelo, host do endpoint (nunca a chave), tier map, flag de
thinking e a config de thinking que `build_supervisor_options` efetivamente
montou — para que dois JSONs sejam comparáveis sem depender de memória.

COMO ATRIBUI TOOLS A AGENTES
----------------------------
Duas fontes, unidas:

  1. Stream do SDK: `AssistantMessage.parent_tool_use_id` aponta para o
     `ToolUseBlock` `Agent` do Supervisor; o `subagent_type` desse bloco dá o
     nome. Exato, sem depender de relógio.
  2. Logs: `workflows.jsonl` grava `workflow_step` (stage=started) no
     PreToolUse do `Agent` e `agent_delegation` no PostToolUse; tudo que
     `audit.jsonl` registrou ENTRE os dois pertence àquele agente. Foi com
     essa janela que se descobriu, na 5ª rodada, que quem chamou firecrawl
     foi o `general-purpose`.

Se a 1 não trouxer tool_use de subagente (o SDK pode não repassar), a 2
cobre. Se as duas discordarem, ambas ficam no JSON — o eval não escolhe.

CUSTO
-----
Contra Moonshot o SDK precifica como se fosse Anthropic; `pricing.py`
recalcula pelos tokens com a tabela Kimi. Contra Anthropic o `total_cost_usd`
do SDK é o correto. O campo `cost_basis` diz qual dos dois foi usado. Tokens
brutos (input/output/cache) ficam sempre — é a comparação mais justa.

O QUE ESTE EVAL NÃO DIZ
-----------------------
Um caso correto com busca feita pelo `general-purpose` conta como `correct`,
mas `specialist_searched=False`. Os dois números respondem perguntas
diferentes: "o sistema acertou?" e "o especialista sabe verificar?". O
segundo é a pergunta do usuário; o primeiro é o que ele vê na tela.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from data_agents.hooks.negation_guard_hook import _WEB_SEARCH_TOOLS, find_negations

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CASES_PATH = PACKAGE_DIR / "conceptual_cases.yaml"
AUDIT_LOG = REPO_ROOT / "logs" / "audit.jsonl"
WORKFLOWS_LOG = REPO_ROOT / "logs" / "workflows.jsonl"
EVALS_DIR = REPO_ROOT / "logs" / "evals"

#: Tools que contam como busca web. Fonte única: o negation guard — se ele
#: não conta curl/context7 como busca, este eval também não.
WEB_SEARCH_TOOLS: frozenset[str] = frozenset(_WEB_SEARCH_TOOLS)

#: Rótulo do Supervisor na atribuição de tools (chamadas fora de qualquer
#: delegação).
SUPERVISOR = "supervisor"

DEFAULT_TIMEOUT_S = 600
STDERR_TAIL_LINES = 12

# O subprocesso `claude` (Node) só enxerga os.environ — não lê `.env`, não
# conhece o Pydantic. É por isso que o `cli.py` faz `load_dotenv` antes de tudo;
# sem paridade aqui, o dispatcher (que usa `settings`) funciona e o Supervisor
# morre com exit code 1 — foi o 1º run deste eval (2026-09-15, 12/12 erros).

_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{6,}|dapi[a-f0-9]{8,}|tvly-[A-Za-z0-9_\-]{6,}|fc-[A-Za-z0-9_\-]{6,})"
)


def scrub_secrets(text: str) -> str:
    """Mascara prefixos conhecidos de chave antes de qualquer coisa ir para log/JSON."""
    return _SECRET_RE.sub(lambda m: m.group(0)[:4] + "…", text)


def load_env_file() -> bool:
    """Carrega `<repo>/.env` em os.environ SEM sobrescrever o que já está no shell.

    Assim `ANTHROPIC_BASE_URL=... make eval-model-compare` vence o `.env` — é o
    que permite rodar contra outro provedor sem editar arquivo. Mesmo padrão e
    mesmo motivo do `cli.py`.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover — python-dotenv é dependência declarada
        return False
    return bool(load_dotenv(REPO_ROOT / ".env", override=False))


def provider_env() -> dict[str, str]:
    """Credenciais/endpoint que o Pydantic resolveu, para injetar no subprocesso.

    O transporte do SDK faz `{**os.environ, **options.env}` (subprocess_cli.py),
    então isto garante que o `claude` vê exatamente o provedor que `settings`
    vê — mesmo se o `.env` não foi carregado no shell.
    """
    from data_agents.config.settings import settings

    out: dict[str, str] = {}
    if settings.anthropic_api_key:
        out["ANTHROPIC_API_KEY"] = str(settings.anthropic_api_key)
    if settings.anthropic_base_url:
        out["ANTHROPIC_BASE_URL"] = str(settings.anthropic_base_url)
    return out


# ─── Modelos ──────────────────────────────────────────────────────────────────


@dataclass
class ConceptualCase:
    id: str
    prompt: str
    must_include: list[list[str]]
    fonte: list[str] = field(default_factory=list)
    verificado_em: str = ""
    fato: str = ""
    expect_web_search: bool = True
    agent_hint: str = ""


@dataclass
class CaseResult:
    case_id: str
    run: int
    correct: bool
    missing_groups: list[list[str]]
    negations: list[str]
    web_search: bool
    web_search_by: list[str]
    web_search_tools: list[str]
    specialist_searched: bool
    dispatched: list[str]
    dispatcher_confidence: float
    dispatcher_reason: str
    delegations_attempted: list[str]
    delegations_completed: list[str]
    off_dispatch_delegations: list[str]
    unverified_negation_events: int
    tools_by_agent_stream: dict[str, list[str]]
    tools_by_agent_log: dict[str, list[str]]
    tools_used: list[str]
    response_chars: int
    response_preview: str
    models_seen: list[str]
    num_turns: int
    duration_s: float
    sdk_cost_usd: float | None
    cost_usd: float
    cost_basis: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    thinking: str
    error: str | None = None


# ─── Carga ────────────────────────────────────────────────────────────────────


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[ConceptualCase]:
    """Carrega e valida a FORMA dos casos. `must_include` é lista de grupos OR."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "cases" not in data:
        raise ValueError(f"YAML inválido em {path}: esperado chave 'cases'")

    cases: list[ConceptualCase] = []
    vistos: set[str] = set()
    for entry in data["cases"]:
        if not isinstance(entry, dict):
            raise ValueError(f"Entrada inválida (não é dict): {entry}")
        for required in ("id", "prompt", "must_include", "fonte", "verificado_em"):
            if required not in entry:
                raise ValueError(
                    f"Caso sem campo obrigatório '{required}': {entry.get('id', entry)}"
                )

        case_id = str(entry["id"])
        if case_id in vistos:
            raise ValueError(f"id duplicado: {case_id!r}")
        vistos.add(case_id)

        groups = entry["must_include"]
        if not isinstance(groups, list) or not groups:
            raise ValueError(f"{case_id}: must_include deve ser lista não-vazia de grupos")
        norm_groups: list[list[str]] = []
        for g in groups:
            if isinstance(g, str):
                g = [g]
            if not isinstance(g, list) or not g or not all(isinstance(t, str) and t for t in g):
                raise ValueError(f"{case_id}: grupo inválido em must_include: {g!r}")
            norm_groups.append([t for t in g])

        fonte = entry["fonte"]
        if isinstance(fonte, str):
            fonte = [fonte]
        if not fonte or not all(str(u).startswith("http") for u in fonte):
            raise ValueError(f"{case_id}: 'fonte' precisa de pelo menos uma URL (fato verificado)")

        cases.append(
            ConceptualCase(
                id=case_id,
                prompt=str(entry["prompt"]).strip(),
                must_include=norm_groups,
                fonte=[str(u) for u in fonte],
                verificado_em=str(entry["verificado_em"]),
                fato=str(entry.get("fato", "")).strip(),
                expect_web_search=bool(entry.get("expect_web_search", True)),
                agent_hint=str(entry.get("agent_hint", "")).strip(),
            )
        )
    return cases


# ─── Scoring (puro — sem rede) ───────────────────────────────────────────────


def score_must_include(text: str, groups: list[list[str]]) -> tuple[bool, list[list[str]]]:
    """Cada grupo precisa de ≥1 termo presente (case-insensitive). Retorna os que faltaram."""
    low = text.lower()
    missing = [g for g in groups if not any(t.lower() in low for t in g)]
    return (not missing), missing


def slug_agent(name: str) -> str:
    """`display_name_for()` do tracker devolve 'Databricks Engineer'; o registry usa
    'databricks-engineer'. Normaliza para comparar. 'General Purpose' → 'general-purpose'."""
    return "-".join(str(name).strip().lower().split())


def agent_name_from_input(tool_input: Any) -> str:
    if not isinstance(tool_input, dict):
        return "?"
    return str(
        tool_input.get("subagent_type")
        or tool_input.get("agent_name")
        or tool_input.get("name")
        or tool_input.get("agent")
        or "?"
    )


def attribute_tools_from_logs(
    audit_rows: list[dict[str, Any]], workflow_rows: list[dict[str, Any]]
) -> tuple[dict[str, list[str]], list[str], list[str]]:
    """
    Atribui cada tool call do audit ao agente cuja janela estava aberta.

    Janela abre em `workflow_step` com stage=started (PreToolUse do Agent) e
    fecha em `agent_delegation` (PostToolUse). Uma janela que nunca fecha é
    delegação que FALHOU (ex.: agente fora do `agents=`) — a próxima abertura
    substitui a anterior. Chamadas fora de janela são do Supervisor.

    Returns:
        (tools_by_agent, attempted, completed) — nomes em slug do registry.
    """
    events: list[tuple[str, int, str, str]] = []  # (ts, ordem, tipo, payload)
    for r in workflow_rows:
        ev = r.get("event")
        ts = str(r.get("timestamp", ""))
        agent = slug_agent(r.get("agent", "?"))
        if ev == "workflow_step" and r.get("stage") == "started":
            events.append((ts, 0, "start", agent))
        elif ev == "agent_delegation":
            events.append((ts, 2, "end", agent))
    for r in audit_rows:
        tool = str(r.get("tool_name", ""))
        if not tool or tool == "Agent":
            continue
        events.append((str(r.get("timestamp", "")), 1, "tool", tool))

    events.sort(key=lambda e: (e[0], e[1]))

    by_agent: dict[str, list[str]] = defaultdict(list)
    attempted: list[str] = []
    completed: list[str] = []
    current: str | None = None
    for _ts, _o, kind, payload in events:
        if kind == "start":
            current = payload
            attempted.append(payload)
        elif kind == "end":
            completed.append(payload)
            current = None
        else:
            by_agent[current or SUPERVISOR].append(payload)
    return dict(by_agent), attempted, completed


def merge_attribution(*sources: dict[str, list[str]]) -> dict[str, list[str]]:
    """União ordenada por agente — stream e logs podem ver partes diferentes."""
    out: dict[str, list[str]] = {}
    for src in sources:
        for agent, tools in src.items():
            bucket = out.setdefault(agent, [])
            for t in tools:
                if t not in bucket:
                    bucket.append(t)
    return out


def web_search_summary(tools_by_agent: dict[str, list[str]]) -> tuple[bool, list[str], list[str]]:
    """(houve busca?, agentes que buscaram, tools de busca usadas)."""
    by: list[str] = []
    used: list[str] = []
    for agent, tools in tools_by_agent.items():
        hits = [t for t in tools if t in WEB_SEARCH_TOOLS]
        if hits:
            by.append(agent)
            for h in hits:
                if h not in used:
                    used.append(h)
    return bool(by), by, used


def summarize(results: list[CaseResult]) -> dict[str, float]:
    """Agrega um run. Pura — usada no scoreboard, no --compare e nos testes."""
    n = len(results)
    if n == 0:
        return {
            "total": 0, "correct": 0, "accuracy": 0.0, "web_search_rate": 0.0,
            "specialist_search_rate": 0.0, "negation_rate": 0.0,
            "unverified_negation_rate": 0.0, "off_dispatch_rate": 0.0,
            "error_rate": 0.0, "total_cost_usd": 0.0, "avg_cost_usd": 0.0,
            "avg_duration_s": 0.0, "avg_turns": 0.0,
        }  # fmt: skip
    ok = sum(1 for r in results if r.correct)
    return {
        "total": n,
        "correct": ok,
        "accuracy": ok / n,
        "web_search_rate": sum(1 for r in results if r.web_search) / n,
        "specialist_search_rate": sum(1 for r in results if r.specialist_searched) / n,
        "negation_rate": sum(1 for r in results if r.negations) / n,
        "unverified_negation_rate": sum(1 for r in results if r.unverified_negation_events) / n,
        "off_dispatch_rate": sum(1 for r in results if r.off_dispatch_delegations) / n,
        "error_rate": sum(1 for r in results if r.error) / n,
        "total_cost_usd": round(sum(r.cost_usd for r in results), 6),
        "avg_cost_usd": round(sum(r.cost_usd for r in results) / n, 6),
        "avg_duration_s": round(sum(r.duration_s for r in results) / n, 1),
        "avg_turns": round(sum(r.num_turns for r in results) / n, 2),
    }


# ─── Logs: leitura incremental ───────────────────────────────────────────────


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)


def _read_new_rows(path: Path, skip: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if i < skip:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


# ─── Execução ────────────────────────────────────────────────────────────────


def _cost(result_msg: Any) -> tuple[float | None, float, str, int, int, int]:
    """(sdk_cost, cost_usd, cost_basis, in, out, cache)."""
    from data_agents.config.settings import settings
    from data_agents.utils.pricing import recompute_cost_from_message

    if result_msg is None:
        return None, 0.0, "sem ResultMessage", 0, 0, 0
    sdk_cost = getattr(result_msg, "total_cost_usd", None)
    bd = recompute_cost_from_message(result_msg)
    is_moonshot = "moonshot" in (settings.anthropic_base_url or "").lower()
    if is_moonshot:
        return (
            sdk_cost, bd.total_cost_usd, f"tabela-moonshot:{settings.default_model}",
            bd.input_tokens, bd.output_tokens, bd.cache_read_tokens,
        )  # fmt: skip
    return (
        sdk_cost, float(sdk_cost or 0.0), "sdk",
        bd.input_tokens, bd.output_tokens, bd.cache_read_tokens,
    )  # fmt: skip


async def run_case(case: ConceptualCase, run_idx: int, timeout_s: float) -> CaseResult:
    """Roda UM caso pelo pipeline inteiro e pontua. Nunca levanta — erro vira campo."""
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock, query

    from data_agents.agents.dispatcher import apply_fallback_policy, select_agents
    from data_agents.agents.loader import preload_registry
    from data_agents.agents.supervisor import build_supervisor_options
    from data_agents.hooks.migration_gate_hook import reset_migration_gate
    from data_agents.hooks.negation_guard_hook import reset_negation_guard

    # Mesmo reset por turno que cli.py/chainlit fazem — sem isto, a busca de um
    # caso "vale" para o seguinte e o negation guard fica cego.
    reset_migration_gate()
    reset_negation_guard()

    audit_before = _count_lines(AUDIT_LOG)
    wf_before = _count_lines(WORKFLOWS_LOG)
    t0 = time.monotonic()

    dispatched: list[str] = []
    confidence = 0.0
    reason = ""
    thinking_repr = "?"
    texts: list[str] = []
    models: list[str] = []
    agent_calls: dict[str, str] = {}  # tool_use_id do Agent → nome do subagente
    sub_tools: dict[str, list[str]] = defaultdict(list)
    result_msg: Any = None
    error: str | None = None

    async def _consume(options: Any) -> None:
        nonlocal result_msg
        async for m in query(prompt=case.prompt, options=options):
            if isinstance(m, AssistantMessage):
                if m.model and m.model not in models:
                    models.append(m.model)
                parent = getattr(m, "parent_tool_use_id", None)
                for b in m.content:
                    if isinstance(b, TextBlock):
                        if parent is None and b.text.strip():
                            texts.append(b.text)
                    elif isinstance(b, ToolUseBlock):
                        if parent is None:
                            if b.name == "Agent":
                                agent_calls[b.id] = agent_name_from_input(b.input)
                            else:
                                sub_tools[SUPERVISOR].append(b.name)
                        else:
                            sub_tools[agent_calls.get(parent, "?")].append(b.name)
            elif isinstance(m, ResultMessage):
                result_msg = m

    # stderr do subprocesso `claude`: sem isto, a falha vem como "Command failed
    # with exit code 1 — check stderr" e nada mais (1º run deste eval, 2026-09-15).
    stderr_tail: deque[str] = deque(maxlen=STDERR_TAIL_LINES)

    try:
        available = preload_registry()
        selected, confidence, reason = await select_agents(case.prompt, available)
        dispatched = apply_fallback_policy(selected, confidence, available)
        options = build_supervisor_options(agent_names=dispatched)
        options.include_partial_messages = False
        options.env = {**(options.env or {}), **provider_env()}
        options.stderr = lambda line: stderr_tail.append(line.rstrip()[:200])
        thinking_repr = json.dumps(getattr(options, "thinking", None), sort_keys=True, default=str)
        await asyncio.wait_for(_consume(options), timeout=timeout_s)
    except asyncio.TimeoutError:
        error = f"timeout após {timeout_s:.0f}s"
    except Exception as e:  # noqa: BLE001 — um caso quebrado não derruba o run
        error = f"{type(e).__name__}: {e}"
        if stderr_tail:
            error += " | stderr: " + " ⏎ ".join(scrub_secrets(ln) for ln in stderr_tail if ln)

    duration = time.monotonic() - t0
    final_text = "\n\n".join(texts)

    audit_rows = _read_new_rows(AUDIT_LOG, audit_before)
    wf_rows = _read_new_rows(WORKFLOWS_LOG, wf_before)
    by_log, attempted_log, completed_log = attribute_tools_from_logs(audit_rows, wf_rows)
    by_stream = dict(sub_tools)
    by_all = merge_attribution(by_stream, by_log)

    web, web_by, web_tools = web_search_summary(by_all)
    attempted = list(dict.fromkeys(list(agent_calls.values()) + attempted_log))
    completed = list(dict.fromkeys(completed_log))
    off_dispatch = [a for a in attempted if a not in set(dispatched)]
    hint = slug_agent(case.agent_hint) if case.agent_hint else ""
    specialist_searched = bool(hint) and hint in web_by

    correct, missing = score_must_include(final_text, case.must_include)
    negations = find_negations(final_text)
    unverified = sum(1 for r in wf_rows if r.get("event") == "unverified_negation")
    tools_used = list(dict.fromkeys(str(r.get("tool_name", "")) for r in audit_rows))

    sdk_cost, cost, basis, in_t, out_t, ca_t = _cost(result_msg)

    return CaseResult(
        case_id=case.id,
        run=run_idx,
        correct=correct and error is None,
        missing_groups=missing,
        negations=negations,
        web_search=web,
        web_search_by=web_by,
        web_search_tools=web_tools,
        specialist_searched=specialist_searched,
        dispatched=list(dispatched),
        dispatcher_confidence=float(confidence),
        dispatcher_reason=str(reason),
        delegations_attempted=attempted,
        delegations_completed=completed,
        off_dispatch_delegations=off_dispatch,
        unverified_negation_events=unverified,
        tools_by_agent_stream=by_stream,
        tools_by_agent_log=by_log,
        tools_used=tools_used,
        response_chars=len(final_text),
        response_preview=final_text[:600],
        models_seen=models,
        num_turns=int(getattr(result_msg, "num_turns", 0) or 0),
        duration_s=round(duration, 1),
        sdk_cost_usd=sdk_cost,
        cost_usd=cost,
        cost_basis=basis,
        input_tokens=in_t,
        output_tokens=out_t,
        cache_read_tokens=ca_t,
        thinking=thinking_repr,
        error=error,
    )


def _print_case_line(r: CaseResult, hint: str) -> None:
    status = "✅" if r.correct else "❌"
    if r.web_search:
        who = ", ".join(r.web_search_by)
        star = " (especialista)" if r.specialist_searched else f" (NÃO {hint})" if hint else ""
        web = f"🔎 {who}{star}"
    else:
        web = "🔎 nenhuma busca web"
    neg = f" · ❗negação×{len(r.negations)}" if r.negations else ""
    ung = f" · guard×{r.unverified_negation_events}" if r.unverified_negation_events else ""
    off = (
        f" · fora-do-dispatcher={r.off_dispatch_delegations}" if r.off_dispatch_delegations else ""
    )
    err = f" · ERRO: {r.error}" if r.error else ""
    print(
        f"      {status} {web}{neg}{ung}{off} · ${r.cost_usd:.4f} · {r.duration_s:.0f}s · "
        f"turns={r.num_turns} · dispatched={r.dispatched}{err}"
    )
    if r.missing_groups:
        print(f"      ↳ faltou: {r.missing_groups}")
    for n in r.negations[:2]:
        print(f"      ↳ «{n[:140]}»")


async def run_all(cases: list[ConceptualCase], repeat: int, timeout_s: float) -> list[CaseResult]:
    results: list[CaseResult] = []
    total = len(cases) * repeat
    i = 0
    for case in cases:
        for k in range(1, repeat + 1):
            i += 1
            tag = f" (run {k}/{repeat})" if repeat > 1 else ""
            print(f"  [{i}/{total}] {case.id}{tag}...", flush=True)
            r = await run_case(case, k, timeout_s)
            _print_case_line(r, slug_agent(case.agent_hint))
            results.append(r)
    return results


# ─── Metadados, persistência, scoreboard ─────────────────────────────────────


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def run_metadata(label: str, results: list[CaseResult]) -> dict[str, Any]:
    """Tudo que torna dois runs comparáveis. NUNCA inclui chaves — só o host."""
    from data_agents.config.settings import settings

    try:
        from importlib.metadata import version

        sdk_version = version("claude-agent-sdk")
    except Exception:  # noqa: BLE001
        sdk_version = "?"

    host = (
        urlparse(settings.anthropic_base_url or "").netloc or "api.anthropic.com (default do SDK)"
    )
    return {
        "label": label,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "default_model": settings.default_model,
        "endpoint_host": host,
        "tier_model_map": dict(settings.tier_model_map or {}),
        "moonshot_allow_thinking": bool(settings.moonshot_allow_thinking),
        "thinking_config": results[0].thinking if results else "?",
        "models_seen": sorted({m for r in results for m in r.models_seen}),
        "sdk_version": sdk_version,
        "python": sys.version.split()[0],
        "git_branch": _git("branch", "--show-current"),
        "git_commit": _git("rev-parse", "--short", "HEAD"),
    }


def persist(label: str, meta: dict[str, Any], results: list[CaseResult]) -> Path:
    EVALS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = "".join(c if c.isalnum() or c in "-._" else "-" for c in label) or "run"
    path = EVALS_DIR / f"model-compare-{safe}-{stamp}.json"
    payload = {"meta": meta, "summary": summarize(results), "cases": [asdict(r) for r in results]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def print_scoreboard(meta: dict[str, Any], s: dict[str, float]) -> None:
    print("\n═══ Model compare — scoreboard ═══")
    print(
        f"  run              : {meta['label']} · {meta['default_model']} @ {meta['endpoint_host']}"
    )
    print(
        f"  thinking         : allow={meta['moonshot_allow_thinking']} · config={meta['thinking_config']}"
    )
    print(f"  accuracy         : {s['accuracy']:.0%}  ({int(s['correct'])}/{int(s['total'])})")
    print(f"  web_search_rate  : {s['web_search_rate']:.0%}  (alguém buscou)")
    print(f"  specialist_search: {s['specialist_search_rate']:.0%}  (o ESPECIALISTA buscou)")
    print(
        f"  negation_rate    : {s['negation_rate']:.0%}  · guard={s['unverified_negation_rate']:.0%}"
    )
    print(f"  off_dispatch_rate: {s['off_dispatch_rate']:.0%}  (delegou fora do dispatcher)")
    print(f"  error_rate       : {s['error_rate']:.0%}")
    print(f"  custo            : ${s['total_cost_usd']:.4f} total · ${s['avg_cost_usd']:.4f}/caso")
    print(f"  duração          : {s['avg_duration_s']:.0f}s/caso · {s['avg_turns']:.1f} turns/caso")


# ─── --compare ───────────────────────────────────────────────────────────────


def _load_run(path: Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for k in ("meta", "summary", "cases"):
        if k not in data:
            raise ValueError(f"{path}: JSON de run sem chave '{k}'")
    return data


def _per_case(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Agrega repetições por case_id: k/n correto, k/n especialista buscou, custo médio."""
    acc: dict[str, dict[str, Any]] = {}
    for c in run["cases"]:
        a = acc.setdefault(
            c["case_id"],
            {"n": 0, "correct": 0, "web": 0, "spec": 0, "neg": 0, "off": 0, "cost": 0.0, "dur": 0.0, "who": set()},
        )  # fmt: skip
        a["n"] += 1
        a["correct"] += int(bool(c.get("correct")))
        a["web"] += int(bool(c.get("web_search")))
        a["spec"] += int(bool(c.get("specialist_searched")))
        a["neg"] += int(bool(c.get("negations")))
        a["off"] += int(bool(c.get("off_dispatch_delegations")))
        a["cost"] += float(c.get("cost_usd") or 0.0)
        a["dur"] += float(c.get("duration_s") or 0.0)
        a["who"].update(c.get("web_search_by") or [])
    return acc


def render_comparison(a: dict[str, Any], b: dict[str, Any]) -> str:
    """Tabela lado a lado. Pura — testável sem rede."""
    ma, mb = a["meta"], b["meta"]
    sa, sb = a["summary"], b["summary"]
    la = (ma.get("label") or "A")[:18]
    lb = (mb.get("label") or "B")[:18]
    out: list[str] = []
    out.append("═══ Comparação ═══")
    out.append(
        f"  A = {ma.get('label')} · {ma.get('default_model')} @ {ma.get('endpoint_host')} · thinking={ma.get('thinking_config')}"
    )
    out.append(
        f"  B = {mb.get('label')} · {mb.get('default_model')} @ {mb.get('endpoint_host')} · thinking={mb.get('thinking_config')}"
    )
    out.append("")
    hdr = f"  {'métrica':<26}{la:>20}{lb:>20}"
    out.append(hdr)
    out.append("  " + "─" * (len(hdr) - 2))

    def pct(s: dict[str, Any], k: str) -> str:
        return f"{float(s.get(k, 0.0)):.0%}"

    rows = [
        ("accuracy", pct(sa, "accuracy"), pct(sb, "accuracy")),
        ("web_search_rate", pct(sa, "web_search_rate"), pct(sb, "web_search_rate")),
        (
            "specialist_search_rate",
            pct(sa, "specialist_search_rate"),
            pct(sb, "specialist_search_rate"),
        ),
        ("negation_rate", pct(sa, "negation_rate"), pct(sb, "negation_rate")),
        (
            "unverified_negation_rate",
            pct(sa, "unverified_negation_rate"),
            pct(sb, "unverified_negation_rate"),
        ),
        ("off_dispatch_rate", pct(sa, "off_dispatch_rate"), pct(sb, "off_dispatch_rate")),
        ("error_rate", pct(sa, "error_rate"), pct(sb, "error_rate")),
        (
            "avg_cost_usd",
            f"${float(sa.get('avg_cost_usd', 0)):.4f}",
            f"${float(sb.get('avg_cost_usd', 0)):.4f}",
        ),
        (
            "total_cost_usd",
            f"${float(sa.get('total_cost_usd', 0)):.4f}",
            f"${float(sb.get('total_cost_usd', 0)):.4f}",
        ),
        (
            "avg_duration_s",
            f"{float(sa.get('avg_duration_s', 0)):.0f}s",
            f"{float(sb.get('avg_duration_s', 0)):.0f}s",
        ),
        (
            "avg_turns",
            f"{float(sa.get('avg_turns', 0)):.1f}",
            f"{float(sb.get('avg_turns', 0)):.1f}",
        ),
    ]
    for name, va, vb in rows:
        out.append(f"  {name:<26}{va:>20}{vb:>20}")

    pa, pb = _per_case(a), _per_case(b)
    ids = list(dict.fromkeys(list(pa) + list(pb)))
    out.append("")
    out.append(
        f"  {'caso':<28}{'correto A':>10}{'correto B':>10}{'espec. A':>10}{'espec. B':>10}  quem buscou (A | B)"
    )
    out.append("  " + "─" * 100)
    for cid in ids:
        xa, xb = pa.get(cid), pb.get(cid)

        def frac(x: dict[str, Any] | None, k: str) -> str:
            return "—" if not x else f"{x[k]}/{x['n']}"

        who_a = ",".join(sorted(xa["who"])) if xa and xa["who"] else "-"
        who_b = ",".join(sorted(xb["who"])) if xb and xb["who"] else "-"
        out.append(
            f"  {cid[:28]:<28}{frac(xa, 'correct'):>10}{frac(xb, 'correct'):>10}"
            f"{frac(xa, 'spec'):>10}{frac(xb, 'spec'):>10}  {who_a} | {who_b}"
        )
    out.append("")
    out.append(
        "  Leitura: 'correto' é o que o usuário vê; 'espec.' é se o agente esperado\n"
        "  buscou na web. Um sistema pode acertar via general-purpose e ainda assim\n"
        "  ter um especialista que não verifica — são perguntas diferentes."
    )
    return "\n".join(out)


# ─── CLI ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Eval conceitual + comparação de modelos.")
    parser.add_argument("--label", default="", help="rótulo do run (ex.: kimi-k2.6, anthropic)")
    parser.add_argument("--id", help="roda apenas o caso com este id")
    parser.add_argument("--limit", type=int, help="roda apenas os primeiros N casos")
    parser.add_argument(
        "--repeat", type=int, default=1, help="repete cada caso N vezes (variância)"
    )
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="segundos por caso"
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument(
        "--min-accuracy", type=float, default=None, help="gate opcional (exit 1 abaixo)"
    )
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("A.json", "B.json"))
    args = parser.parse_args(argv)

    if args.compare:
        try:
            a, b = _load_run(args.compare[0]), _load_run(args.compare[1])
        except (OSError, ValueError, json.JSONDecodeError) as e:
            print(f"erro lendo runs: {e}", file=sys.stderr)
            return 2
        print(render_comparison(a, b))
        return 0

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
    if args.repeat < 1:
        print("--repeat deve ser >= 1", file=sys.stderr)
        return 2

    # .env → os.environ ANTES de importar settings e ANTES do subprocesso `claude`.
    load_env_file()
    from data_agents.config.settings import settings

    env = provider_env()
    if "ANTHROPIC_API_KEY" not in env:
        print(
            "❌ ANTHROPIC_API_KEY ausente (nem no shell, nem em <repo>/.env). O subprocesso "
            "`claude` morreria com exit code 1 em todos os casos — abortando antes de gastar.",
            file=sys.stderr,
        )
        return 2

    label = args.label or settings.default_model
    host = urlparse(env.get("ANTHROPIC_BASE_URL", "")).netloc or "api.anthropic.com (default)"
    print(f"\n🧪 Eval conceitual — {len(cases)} caso(s) × {args.repeat} · label={label}")
    print(
        f"   modelo={settings.default_model} · endpoint={host} · chave=presente · "
        f"thinking_allow={settings.moonshot_allow_thinking}\n"
    )

    try:
        results = asyncio.run(run_all(cases, args.repeat, args.timeout))
    except KeyboardInterrupt:
        print("\n⚠️  interrompido")
        return 130

    meta = run_metadata(label, results)
    path = persist(label, meta, results)
    s = summarize(results)
    print_scoreboard(meta, s)
    print(f"\n  run salvo em {path.relative_to(REPO_ROOT)}")
    print("  compare com: python -m data_agents.evals.model_compare --compare <A.json> <B.json>")

    if s["error_rate"] >= 1.0:
        print(
            "\n❌ 100% dos casos com erro — isto NÃO é dado sobre o modelo, é falha de ambiente. "
            "Veja o campo `error` (traz o stderr do `claude`) no JSON antes de comparar.",
            file=sys.stderr,
        )
        return 1

    if args.min_accuracy is not None and s["accuracy"] < args.min_accuracy:
        print(f"\n❌ accuracy {s['accuracy']:.0%} abaixo do gate {args.min_accuracy:.0%}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
