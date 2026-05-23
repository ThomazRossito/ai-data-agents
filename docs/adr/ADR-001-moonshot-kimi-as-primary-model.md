# ADR-001: Moonshot Kimi K2.6 as the primary model

> **Status**: Accepted
> **Date**: 2026-05-22 (recording retroactive decision from v2.x)
> **Deciders**: @ThomazRossito
> **Tags**: model, cost, provider, supply-chain

## Context

The project initially targeted Anthropic Claude Sonnet directly. Two pressures emerged:

1. **Cost per query** was high. Sonnet pricing at the time was $3/M input + $15/M output tokens. For a system that delegates frequently (Supervisor → Dispatcher → multiple agents) the per-query cost regularly hit $0.50–$2.00 even for trivial requests.
2. **Anthropic-compat endpoints** appeared in 2025-2026: Moonshot, DeepSeek, Z.AI, and others exposed `/anthropic` paths that speak the Messages API protocol. Some are dramatically cheaper.

Moonshot's Kimi K2.6 (released April 2026) presented:

- 1T-parameter MoE architecture.
- 256k context window.
- $0.55/M input + $2.65/M output — roughly **5× cheaper** than Sonnet.
- Native Anthropic Messages API compatibility at `https://api.moonshot.ai/anthropic`.
- Single-model line (no model variant choice — same model handles all tiers).

Trade-offs:

- Moonshot does **not stream `thinking` events** during reasoning. The endpoint accepts the parameter but the client may hang for minutes with no feedback.
- The `claude-agent-sdk` reports cost assuming **Anthropic Sonnet pricing**, so `total_cost_usd` is **~5× inflated** vs reality.
- Provider concentration risk: depending on Moonshot ties the project's economics to a single non-US provider.

## Decision

**Adopt Moonshot Kimi K2.6 as the primary model** for the Supervisor, all 15 agents, the Dispatcher, and the memory extractor.

Specifically:

- `DEFAULT_MODEL=kimi-k2.6` in `.env.example` and `Settings.default_model`.
- `ANTHROPIC_BASE_URL=https://api.moonshot.ai/anthropic` configured by default.
- Implement `utils/pricing.py` to **recompute** cost using Moonshot's real price table. Persist both `total_cost_usd` (real) and `sdk_reported_cost_usd` (SDK inflated) in `logs/sessions.jsonl`.
- When `enable_thinking=True` is requested (DOMA Full / `/plan`), detect Moonshot endpoint and force `thinking={"type": "disabled"}` to avoid hangs. Log a warning.
- Keep `ANTHROPIC_BASE_URL` overridable — the same code path works against Anthropic if the user sets the variable to empty/Anthropic URL.

## Consequences

### Positive
- 5× cost reduction on a typical query.
- Larger context window (256k vs 200k) — accommodates Two-Stage Routing failure mode (load all 15 agents when dispatcher confidence is low).
- Single model line eliminates Sonnet-vs-Opus-vs-Haiku routing decisions; tier differentiation is via `max_turns` + `effort`, not model swap.

### Negative
- No streaming `thinking` — users see only spinner during planning phases.
- Provider concentration on Moonshot.
- SDK's `total_cost_usd` is structurally wrong against this endpoint; every consumer must use `utils/pricing.real_cost_from_message()`.
- Memory extractor and dispatcher chains run against a non-Anthropic endpoint with possibly different rate-limit / 5xx behavior.

### Neutral / unknown
- Long-term reliability of Moonshot endpoint (under 1 year old as of decision).
- Quality delta between Kimi K2.6 and Sonnet on data-engineering-specific tasks — anecdotally close but no formal benchmark in this repo yet.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| Stay on Anthropic Sonnet | Native cost reporting; production-tested; Anthropic stability | ~5× more expensive; no clear quality advantage for our workload | Cost dominated the decision |
| DeepSeek-v3 Anthropic-compat | Even cheaper than Moonshot | Lower context window at time of decision; less mature compat endpoint | Picked Moonshot for larger context |
| Multi-provider routing (Sonnet for Supervisor, Kimi for agents) | Best-of-both | Doubles credentials, doubles failure modes, doubles pricing tables to maintain | Over-engineering for the cost saved |
| Self-hosted open model (Llama 3.1, Qwen) | No external dependency | Operational cost, GPU requirement, quality regression on tool-use | Out of scope for an on-machine product |

## References

- `config/settings.py` — `default_model`, `anthropic_base_url`, `validate_anthropic_key`.
- `utils/pricing.py::PRICING_KIMI_K2_6`, `recompute_cost_from_message`.
- `agents/supervisor.py::build_supervisor_options` — thinking suppression for Moonshot.
- Future: ADR-XXX on adding a fallback provider when Moonshot rate-limits.
