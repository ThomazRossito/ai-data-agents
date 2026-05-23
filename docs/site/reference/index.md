# Reference

Live inventory from the codebase:

- **[Agents (15)](agents.md)** — the specialist roster with tier, MCPs, KBs, skills
- **[MCP Servers (17)](mcps.md)** — Databricks, Fabric, Genie, Semantic, Ontology, Pricing, GitHub, Tavily, etc.
- **[Slash Commands (39)](slash-commands.md)** — `/sql`, `/fabric`, `/migrate`, `/quality`, `/governance`, etc.
- **[ADRs (10)](adrs.md)** — architectural decisions in Michael Nygard format
- **[Security](security.md)** — STRIDE threat model + secrets handling

For machine-readable inventory:

```bash
make inventory      # counts of agents / MCPs / KBs / skills / commands / hooks
```

For drift prevention:

```bash
make lint-all       # 5 structural lints + doc-sync check (CI gate)
```
