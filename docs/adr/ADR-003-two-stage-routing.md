# ADR-003: Two-Stage Routing via lightweight dispatcher

> **Status**: Accepted
> **Date**: 2026-05-22
> **Deciders**: @ThomazRossito
> **Tags**: performance, cost, prompt-engineering, model-compatibility

## Context

The `claude-agent-sdk` loads **all available subagents** into the Supervisor's system prompt at every call. With 15 agents, each carrying its frontmatter description + injected KB index + injected skills index + cache prefix, the Supervisor system prompt routinely reached **~80–100K tokens** of fixed overhead per query.

Symptoms observed:

- **Sonnet endpoint**: tolerable due to aggressive prompt caching and high throughput. Cost was high but latency acceptable.
- **Kimi K2.6 endpoint**: prompts above ~80K tokens caused the endpoint to hang for 30s–5min without streaming any output, or to return after a long wait with substantially degraded reasoning quality.

Two fixes were possible:

1. Reduce the per-agent prompt overhead (already done partially via cache prefix and KB index-only injection — diminishing returns left).
2. Load **only the relevant subset of agents** for each query.

The second approach requires routing intelligence — but routing intelligence itself is a model call. The challenge: do the routing call cheaper than the cost it saves.

## Decision

**Insert a lightweight Dispatcher call before the Supervisor.** The Dispatcher:

- Receives the user's query and only the **names + tier + truncated descriptions** of available agents (~3K tokens, not 80K).
- Returns JSON: `{"agents": [...], "confidence": 0.0-1.0, "reason": "..."}`.
- Confidence-based fallback policy:
  - `confidence ≥ 0.80` → pass `selected` directly to `build_supervisor_options(agent_names=selected)`.
  - `0.60 ≤ confidence < 0.80` → add common neighbors (`data-quality-steward`, `governance-auditor`).
  - `confidence < 0.60` → fallback to all delegatable agents (safe but expensive).
- Implementation in `agents/dispatcher.py::select_agents`. Uses `urllib` (no extra SDK overhead) against the same Anthropic-compat endpoint. Times out at 30s.
- Errors (HTTP, network, JSON parse) fall back to "load all agents" — never block the user.

Build the Supervisor with `agent_names=` filter. The Supervisor then sees only the prompts for the chosen agents (typical: 1–3 agents, ~15–25K tokens).

## Consequences

### Positive
- Supervisor prompt typical size drops from ~80K to ~20K tokens — **4× reduction**.
- Kimi K2.6 endpoint no longer hangs. Streaming works reliably.
- Dispatcher cost is ~$0.0001 per query — negligible vs the savings.
- Behavior on Anthropic endpoint also improves (cheaper, faster), even though there it was tolerable before.

### Negative
- Adds **one extra LLM round-trip** before the Supervisor starts. Adds ~1-2s latency for simple queries.
- Dispatcher can choose wrong (e.g., pick `data-quality-steward` when the user wanted Spark debugging). Mitigation: fallback policy + the user can always escape via slash commands which route deterministically.
- The Dispatcher's JSON parsing is fragile to model output drift; defensive fallback handles errors but quietly degrades to "load all".
- Two-tier routing logic adds a new file (`dispatcher.py`) and integration code in the CLI/UI entry points.

### Neutral / unknown
- Dispatcher confidence calibration could be improved with eval data; the 0.80 / 0.60 thresholds are heuristic.
- Whether to bypass the Dispatcher for slash commands (which already specify the agent deterministically) — currently slash commands skip the Dispatcher via `commands/parser.py`.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| Continue loading all agents | Simple | Breaks Kimi K2.6 entirely | Project depends on Kimi (ADR-001) |
| Lazy-load agents inside Supervisor based on a tool call | Adds no pre-call latency | Requires SDK feature that doesn't exist | Not viable |
| Static rule-based router (regex on keywords) | Zero LLM cost, deterministic | Brittle, misses ambiguous queries | Falls back too often to "all agents" — defeats the goal |
| Use Haiku/cheaper model as dispatcher | Slightly cheaper still | One more provider to manage; less reliable JSON | Marginal gain not worth complexity |
| Hierarchical Supervisor of Supervisors | Most "elegant" | 3-tier system; debugging nightmare | Over-engineering |

## References

- `agents/dispatcher.py` — full implementation.
- `agents/supervisor.py::build_supervisor_options(agent_names=...)` — accepts the filter.
- `agents/loader.py::preload_registry` — fast frontmatter-only load used by dispatcher.
- Inspired by retrieval-augmented routing patterns described in [Anthropic's MoO architecture posts](https://www.anthropic.com/research) and observed in production multi-agent systems.
