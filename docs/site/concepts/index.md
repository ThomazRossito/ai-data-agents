# Concepts

Five core concepts that shape every decision in the codebase:

1. **[Architecture](architecture.md)** — C4 levels 1+2 + query lifecycle
2. **[Constitution (S1–S7)](constitution.md)** — inviolable rules the Supervisor consults before delegating
3. **[Memory Layer](memory.md)** — three layers (ShortTerm SQLite + LongTerm FTS5 + Ledger HMAC)
4. **[Hooks](hooks.md)** — Pre/PostToolUse interception (security, cost guard, audit, output compression)
5. **[Tier System](tier-system.md)** — T0/T1/T2/T3 controlling maxTurns and effort per agent

If you only have time for one, read [Constitution](constitution.md) — it's the rulebook everything else implements.
