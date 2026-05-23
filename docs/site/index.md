# AI Data Agents

> Multi-agent system for **Data Engineering**, **Quality**, **Governance** and **Analytics** on **Databricks** + **Microsoft Fabric**.
> Built on the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) (Anthropic Messages API) served by [Moonshot Kimi K2.6](https://platform.moonshot.ai) via an Anthropic-compatible endpoint.

[![Version](https://img.shields.io/badge/Version-3.0.0--rc1-brightgreen)](https://github.com/ThomazRossito/ai-data-agents)
[![Python](https://img.shields.io/badge/Python-3.12+-blue)](#)
[![Databricks](https://img.shields.io/badge/Databricks-MCP-FF3621)](#)
[![Microsoft Fabric](https://img.shields.io/badge/Microsoft%20Fabric-MCP-0078D4)](#)

---

## What you'll find here

<div class="grid cards" markdown>

-   :material-rocket-launch: **[Getting Started](getting-started/index.md)**

    Install, configure `.env`, run your first query in ~5 minutes.

-   :material-book-open: **[Concepts](concepts/index.md)**

    Architecture (C4), Constitution (S1–S7), memory layer, hooks, tier system.

-   :material-school: **[Tutorials](tutorials/index.md)**

    End-to-end recipes: migrate SQL Server → Databricks, build a Medallion pipeline.

-   :material-text-box-search: **[Reference](reference/index.md)**

    15 agents · 17 MCPs · 39 slash commands · 10 ADRs · STRIDE threat model.

-   :material-swap-horizontal: **[Migration v2 → v3](migration/v2-to-v3.md)**

    Phase 7 namespace move broke imports. One-liner sed to update your code.

</div>

---

## The 60-second overview

1. The **Supervisor** (kimi-k2.6) receives a natural-language prompt and decides which specialist agent to delegate to.
2. **15 specialist agents** cover Databricks (engineering + AI/streaming), Fabric (engineering + RTI + ontology), migration, data quality, governance, contracts, mesh architecture, dbt, Python, and conversational fallback.
3. **17 MCP servers** give the agents real platform access — Unity Catalog, Lakehouses, Genie Spaces, DAX, Direct Lake, Kusto/KQL, ontologies, Azure pricing, GitHub, Tavily, and more.
4. **Pre/PostToolUse hooks** intercept every tool call: security blocks (22 destructive patterns), cost guard, output compression, structured audit logging, persistent memory.
5. **Constitution S1–S7** is the inviolable rulebook the Supervisor consults before any delegation — see [`concepts/constitution.md`](concepts/constitution.md).

---

## Quickstart

```bash
# Install (core only)
pip install ai-data-agents

# Or with all extras
pip install "ai-data-agents[ui,monitoring,viz,memory,ontology]"

# Configure credentials (one-time)
cp .env.example .env
# edit .env: ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, DATABRICKS_*, etc.

# Run your first query
ai-data-agents "liste as tabelas do schema silver"
```

Need a more detailed walkthrough? → **[Getting Started](getting-started/index.md)**.

---

## Project status

The project is on the **v3.0.0-rc1** release candidate. See [`CHANGELOG.md`](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/CHANGELOG.md) for the full history and [`docs/refactor-v3/PLAN.md`](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/docs/refactor-v3/PLAN.md) for what each refactor phase did.

Bake-time period: testing v3.0.0-rc1 against real workloads before promoting to `v3.0.0` final.
