# ai-data-agents — Claude Code plugin

> **Phase 12 of the v3 refactor.** This plugin brings the 15 specialist agents
> and 48 skills from [ai-data-agents](https://github.com/ThomazRossito/ai-data-agents)
> into Claude Code natively, so you can use `/databricks-engineer`,
> `/fabric-engineer`, etc. without leaving your IDE.

## What you get

After installing this plugin, Claude Code gains:

- **15 specialist subagents** for Data Engineering, Quality, Governance, Analytics on Databricks + Microsoft Fabric.
- **48 operational skills** (playbooks) covering Spark, Delta Lake, LakeFlow, Direct Lake, Star Schema, dbt, CDC, RAG, Kafka, Flink, ontologies, and more.

The plugin is a **view** over the source-of-truth project. The Python CLI distribution (`pip install ai-data-agents`) and this plugin are two faces of the same content — agents and skills live in the same repo and are synced by `scripts/build_plugin.sh`.

## Install

```bash
# Add the marketplace
claude plugin marketplace add ThomazRossito/ai-data-agents

# Install the plugin
claude plugin install ai-data-agents@thomazrossito-marketplace
```

Then restart your Claude Code session.

## What is NOT included in v3.0-rc1

To keep the plugin minimal and resilient to spec changes, the v3.0-rc1 plugin includes only **agents** and **skills**.

| Feature | Where it lives |
|---|---|
| 39 slash commands (`/sql`, `/fabric`, `/migrate`, ...) | Python CLI only (`pip install ai-data-agents`). Plugin users invoke agents via natural language. |
| 17 MCP servers (Databricks, Fabric, Genie, ...) | Python CLI only. Plugin users configure MCPs separately via Claude Code's MCP settings. |
| Hooks (security, cost guard, audit) | Python CLI only. |
| Memory layer (ShortTerm + LongTerm + Ledger) | Python CLI only. |

Why the split: the plugin distribution channel is for **agent + skill discoverability** inside Claude Code. The Python CLI is the full-fidelity execution environment with hooks, memory, audit, and MCP orchestration.

If you want all of it, use:

```bash
pip install ai-data-agents
ai-data-agents "..."
```

See [the docs site](https://thomazrossito.github.io/ai-data-agents/) for the full feature comparison.

## How the plugin stays in sync with the source

The `agents/` and `skills/` directories in this plugin are **generated** by `scripts/build_plugin.sh` (in the parent repo) from the canonical sources:

- Agents: `data_agents/agents/registry/*.md`
- Skills: `skills/<domain>/<name>/SKILL.md` (flattened to `plugins/ai-data-agents/skills/<name>/SKILL.md`)

CI workflow `plugin-validate.yml` runs on every PR and verifies the plugin is in sync. Out-of-sync = build fails. Manual update:

```bash
bash scripts/build_plugin.sh
git add plugins/ai-data-agents/
git commit -m "chore(plugin): sync agents + skills"
```

## Reporting issues

Plugin-specific bugs (install fails, agent doesn't load): open an issue at
<https://github.com/ThomazRossito/ai-data-agents/issues> with the `plugin` label.

Content bugs (agent prompt wrong, skill outdated): same repo — the plugin is a view; the fix goes to `data_agents/agents/registry/` or `skills/`.

## License

MIT — see the [LICENSE](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/LICENSE) in the parent repo.
