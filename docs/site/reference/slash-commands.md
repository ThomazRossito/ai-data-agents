# Slash Commands (39)

Source of truth: [`data_agents/config/commands.yaml`](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/data_agents/config/commands.yaml).
Validated by `scripts/lint_commands.py`.

## Distribution

- **Express** (24): direct delegation, no PRD, no approval gate
- **Full** (5): DOMA Full flow (Clarity Checkpoint → Plan → Approval → Delegation)
- **Internal** (10): system commands (no agent target — handled by CLI directly)

## Full list

### Engineering — Databricks

| Command | Mode | Agent |
|---|---|---|
| `/sql` | express | databricks-engineer |
| `/spark` | express | databricks-engineer |
| `/pipeline` | express | databricks-engineer |
| `/cdc` | express | databricks-engineer |
| `/diagnose` | express | databricks-engineer |
| `/genie` | express | databricks-engineer |
| `/dashboard` | express | databricks-engineer |
| `/ai` | express | databricks-ai |
| `/streaming` | express | databricks-ai |

### Engineering — Fabric

| Command | Mode | Agent |
|---|---|---|
| `/fabric` | express | fabric-engineer |
| `/semantic` | express | fabric-engineer |
| `/schema` | express | fabric-engineer |
| `/medallion` | express | fabric-engineer |
| `/finops` | express | fabric-engineer |
| `/catalog` | express | fabric-engineer |
| `/ontology` | express | fabric-ontology |

### Other engineering

| Command | Mode | Agent |
|---|---|---|
| `/dbt` | express | dbt-expert |
| `/python` | express | python-expert |
| `/migrate` | express | migration-expert |
| `/cost-azure` | express | azure-cost-calculator |

### Analysis & quality

| Command | Mode | Agent |
|---|---|---|
| `/quality` | express | data-quality-steward |
| `/governance` | express | governance-auditor |
| `/contract` | express | data-contracts-engineer |
| `/mesh` | express | data-mesh-architect |

### Planning

| Command | Mode | Agent |
|---|---|---|
| `/plan` | full | Supervisor (with thinking enabled) |
| `/brief` | full | business-analyst |
| `/review` | full | Supervisor |

### Multi-agent

| Command | Mode | Notes |
|---|---|---|
| `/party` | internal | Parallel execution — flags `--quality` `--arch` `--engineering` `--migration` `--full` |
| `/analyze-project` | internal | 4 specialists in parallel, output to `output/analyze-project/` |
| `/workflow` | internal | Predefined WF-01 to WF-06 |

### Conversational & utility

| Command | Mode | Notes |
|---|---|---|
| `/geral` | internal | Direct response, no Supervisor, no MCP, ~95% cheaper |
| `/health` | internal | Platform connectivity (Databricks, Fabric) |
| `/status` | internal | Current session state |
| `/memory` | internal | Query persistent memory |
| `/sessions` | internal | List recorded sessions |
| `/resume` | internal | Resume previous session |
| `/ship` | internal | Archive completed task with lessons learned |
| `/mcp` | internal | MCP server status |

## Adding a slash command

1. Edit `data_agents/config/commands.yaml`:
    ```yaml
    commands:
      mycommand:
        agent: target-agent-name
        doma_mode: express
        description: One-line description shown in /help
        skills: []
        prompt_template: "[DOMA EXPRESS] Delegate to {agent}. Task: {task}"
        display_template: '[bold yellow]🚀 Routing to {agent}[/bold yellow]'
    ```
2. `make lint-commands` — validates agent exists, format ok.
3. `make test-fast` — ensures parser tests pass.
4. (Optional) Add to `data_agents/commands/parser.py` if special handler needed.

The command is available immediately — no Python code change for plain dispatch.
