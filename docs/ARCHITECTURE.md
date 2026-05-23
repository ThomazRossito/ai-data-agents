# Architecture — ai-data-agents

> Status: living document, updated when major architectural decisions land.
> Last updated: 2026-05-22 (v2.3.0 → v3.0 refactor in progress)

This document describes the system at C4 levels 1 (System Context) and 2 (Container). Component-level (level 3) decisions live in `docs/adr/`.

---

## 1. System Context (C4 — Level 1)

`ai-data-agents` is an **on-machine multi-agent orchestrator** that automates Data Engineering tasks on Databricks and Microsoft Fabric. It runs locally on the user's workstation, talks to LLM providers and data platforms over the network, and reads/writes the user's local files for outputs.

```mermaid
C4Context
    title System Context — ai-data-agents

    Person(de, "Data Engineer", "Operates pipelines, SQL,<br/>migrations, governance.")
    System(daa, "ai-data-agents", "Multi-agent orchestrator<br/>(CLI + optional UI).<br/>15 specialist agents,<br/>17 MCP servers, 17 KBs, 48 skills.")

    System_Ext(moonshot, "Moonshot Kimi K2.6 API", "Anthropic-compat endpoint.<br/>Primary LLM.")
    System_Ext(anthropic, "Anthropic API", "Fallback LLM (optional).")
    System_Ext(databricks, "Databricks Workspace", "Unity Catalog, Jobs,<br/>SQL Warehouses, AI/BI,<br/>Genie, LakeFlow.")
    System_Ext(fabric, "Microsoft Fabric", "Lakehouses, OneLake,<br/>Semantic Models, RTI,<br/>Notebooks.")
    System_Ext(srcdbs, "Source Databases", "SQL Server, PostgreSQL<br/>(for migrations).")
    System_Ext(ext, "External MCPs", "Context7, Tavily, GitHub,<br/>Firecrawl, Postgres, Memory.")

    Rel(de, daa, "Issues queries via CLI/UI")
    Rel(daa, moonshot, "LLM inference", "HTTPS / Messages API")
    Rel(daa, anthropic, "Optional fallback", "HTTPS")
    Rel(daa, databricks, "MCP tool calls", "REST + JDBC + Genie API")
    Rel(daa, fabric, "MCP tool calls", "REST + TDS + KQL")
    Rel(daa, srcdbs, "Migration source", "ODBC / psycopg2")
    Rel(daa, ext, "Docs, search, repo ops", "MCP stdio")
```

### Key external interactions

| Direction | Counterparty | Protocol | Purpose |
|---|---|---|---|
| Outbound | Moonshot Kimi API | HTTPS Messages API | Primary LLM for all agents (Anthropic-compat endpoint at `api.moonshot.ai/anthropic`) |
| Outbound | Databricks REST + JDBC | HTTPS / TDS | Tool calls for SQL, jobs, pipelines, Unity Catalog, AI/BI |
| Outbound | Microsoft Fabric REST + TDS + KQL | HTTPS | Lakehouse, Semantic Models, RTI, OneLake, Notebooks |
| Outbound | SQL Server / PostgreSQL | ODBC / pgwire | Read-only metadata extraction for migrations |
| Outbound | External MCP servers | stdio (npx/uvx subprocess) | Context7, Tavily, GitHub, Firecrawl, Memory KG |

### Trust boundaries

1. **User workstation** — the Trusted Computing Base. Holds `.env` with all credentials.
2. **Network** — untrusted. All credentials transit via TLS to platform APIs.
3. **Subprocess MCP servers** — partially trusted. They execute with the user's credentials but only their declared toolset; hooks intercept all calls.
4. **LLM providers** — untrusted with sensitive data. The output compressor strips large payloads; the security hook blocks credential echoing.

---

## 2. Container View (C4 — Level 2)

Inside `ai-data-agents`, the runtime divides into containers (logical, not Docker containers) that play distinct roles.

```mermaid
C4Container
    title Container View — ai-data-agents process

    Person(de, "Data Engineer")

    Container_Boundary(cli, "Entry points") {
        Container(maincli, "CLI", "Python · prompt_toolkit + Rich", "Interactive loop, single-query mode,<br/>slash command parser.")
        Container(chainlit, "Chainlit UI", "Python · Chainlit", "Web chat UI (opt-in via [ui] extra).<br/>Port 8513.")
        Container(monitor, "Monitoring", "Python · Streamlit", "Dashboard over logs/*.jsonl<br/>(opt-in via [monitoring]). Port 8511.")
        Container(viz, "Visualization", "Python · FastAPI + Three.js", "3D office view (opt-in via [viz]).<br/>Port 8512.")
    }

    Container_Boundary(core, "Core orchestration") {
        Container(dispatcher, "Two-Stage Dispatcher", "Python", "Lightweight call to Kimi K2.6 picks<br/>1-5 relevant agents per query.<br/>~3K tokens, ~$0.0001/dispatch.")
        Container(supervisor, "Supervisor", "Python · claude-agent-sdk", "Orchestrator. Plans, delegates,<br/>synthesizes. Never executes MCP<br/>or generates SQL directly (S1, S2).")
        Container(agents, "15 Specialist Agents", "Markdown + YAML frontmatter", "T0/T1/T2/T3 tiers.<br/>Each has tools, MCPs, KBs, skills.")
    }

    Container_Boundary(intercept, "Interception layer") {
        Container(hooks, "Hooks", "Python", "PreToolUse: security, SQL cost.<br/>PostToolUse: audit, cost guard, memory,<br/>context budget, output compressor.")
    }

    Container_Boundary(integration, "Integration layer") {
        Container(mcps, "17 MCP Servers", "stdio subprocesses", "Databricks, Fabric (community/official/SQL/RTI/<br/>Semantic/OneLake/Notebook/Ontology),<br/>Genie, Migration Source, Context7,<br/>Tavily, GitHub, Firecrawl, Postgres,<br/>Memory KG, Azure Pricing.")
    }

    Container_Boundary(persist, "Persistence layer") {
        ContainerDb(shortterm, "ShortTermMemory", "SQLite + FTS5", "TTL 3 days. Captures session<br/>context. Optional embeddings.")
        ContainerDb(longterm, "LongTermMemory", "SQLite + FTS5", "Persistent semantic index of<br/>memories. No TTL.")
        ContainerDb(ledger, "Ledger", "JSONL + HMAC-SHA256", "Append-only audit log of every<br/>tool call. Tamper-evident.")
        ContainerDb(store, "MemoryStore", ".md files + index", "Memories as Markdown with YAML<br/>frontmatter. 8 typed categories.")
        ContainerDb(kb, "Knowledge Base", "17 .md domain trees", "Anti-patterns, conventions, schemas.<br/>Injected by kb_domains in frontmatter.")
        ContainerDb(skills, "Skills", "48 SKILL.md operational playbooks", "Domain-specific runbooks.<br/>Discovered via skill_domains index.")
    }

    Container_Boundary(prov, "External platforms (re-shown)") {
        System_Ext(extplat, "Moonshot · Databricks · Fabric · Source DBs · External MCPs", "")
    }

    Rel(de, maincli, "Types queries / commands")
    Rel(de, chainlit, "Browser chat")
    Rel(maincli, dispatcher, "Routes via")
    Rel(chainlit, dispatcher, "Routes via")
    Rel(dispatcher, supervisor, "Selected agents")
    Rel(supervisor, agents, "Agent tool delegation")
    Rel(supervisor, hooks, "Tool calls intercepted by")
    Rel(agents, hooks, "Tool calls intercepted by")
    Rel(hooks, mcps, "Approved calls forwarded to")
    Rel(mcps, extplat, "Outbound calls")
    Rel(hooks, ledger, "Append-only writes")
    Rel(hooks, shortterm, "Captures context")
    Rel(supervisor, longterm, "Reads memory")
    Rel(longterm, store, "Backed by")
    Rel(agents, kb, "Reads via kb_domains")
    Rel(agents, skills, "Reads via skill_domains")
    Rel(monitor, ledger, "Reads")
    Rel(viz, ledger, "Reads")
```

### Containers explained

#### Entry points (4)
- **CLI** (`main.py`, ~1.7K LOC): primary interface. `prompt_toolkit` with persistent history. Slash commands parsed via `commands/parser.py`. Streaming output via Rich.
- **Chainlit UI** (`ui/chainlit_app.py`, ~2.1K LOC): web chat, opt-in via `pip install ".[ui]"`. Mirror of CLI capabilities.
- **Monitoring** (`monitoring/app.py`, Streamlit): dashboard reading `logs/audit.jsonl`, `logs/sessions.jsonl`, `logs/workflows.jsonl`.
- **Visualization** (`visualization/server.py`, FastAPI + Three.js): 3D scene of agents in motion. Tailing JSONLs via WebSocket. Niche, demo-oriented.

#### Core orchestration (3 logical containers)
- **Two-Stage Dispatcher** (`agents/dispatcher.py`): solves the "Kimi K2.6 chokes on huge prompts" problem. Calls the LLM with only agent names+descriptions (~3K tokens) to pick 1-5 relevant agents. Confidence-based fallback expands to all agents if confidence < 60%.
- **Supervisor** (`agents/supervisor.py` + `agents/prompts/supervisor_prompt.py`): the orchestrator. Reads the Constitution (S1–S7), runs Clarity Checkpoint (DOMA), delegates via Agent tool. Never executes MCP directly.
- **Specialist agents** (`agents/registry/*.md`): 15 agents defined declaratively. Loaded by `agents/loader.py` into `AgentDefinition` from the SDK. Each carries: tools, MCP servers, KB domains, skill domains, tier (T0/T1/T2/T3), max_turns, effort.

#### Interception layer
- **Hooks** (`hooks/*.py` + `compression/`, `workflow/`): 11 hook files. PreToolUse blocks destructive commands and expensive SQL. PostToolUse audits, classifies cost (HIGH/MEDIUM/LOW), captures memory context, tracks the context budget (70%/80%/95% thresholds), and compresses verbose tool outputs. The session lifecycle hook initializes ShortTermMemory and the Ledger session key.

#### Integration layer
- **17 MCP servers** registered in `config/mcp_servers.py::ALL_MCP_CONFIGS`:
  - **8 custom**: `azure_pricing`, `databricks_genie`, `fabric_notebook`, `fabric_onelake`, `fabric_ontology`, `fabric_semantic`, `fabric_sql`, `migration_source`. Each has its own `server.py` in `mcp_servers/<name>/`.
  - **9 external** (subprocess via npx/uvx): `context7`, `databricks` (Databricks-Solutions wrapper), `fabric` (community + official), `fabric_rti`, `firecrawl`, `github`, `memory_mcp`, `postgres`, `tavily`.
  - 4 are **always active** (no credentials required): `context7`, `memory_mcp`, `fabric_ontology` (uses `az login`), `azure_pricing`.

#### Persistence layer
- **ShortTermMemory** (`memory/short_term.py`): SQLite with FTS5 + optional fastembed. Session-scoped, TTL 3 days, isolated per `PROJECT_ID`.
- **LongTermMemory** (`memory/long_term.py`): SQLite FTS5 + optional embeddings. Persistent semantic search.
- **Ledger** (`memory/ledger.py`): HMAC-SHA256-signed audit JSONL. Per-session key. Tamper-evident chain.
- **MemoryStore** (`memory/store.py`): `.md` files with YAML frontmatter, 8 typed categories (USER, FEEDBACK, ARCHITECTURE, PROGRESS, DATA_ASSET, PLATFORM_DECISION, PIPELINE_STATUS, LESSON_LEARNED). Decay rules per type.
- **Knowledge Base** (`kb/`): 17 domains × ~7 .md files each. Agents discover via `kb_domains` in frontmatter. Optional injection of `index.md` into system prompt.
- **Skills** (`skills/`): 48 SKILL.md operational playbooks. Discovered via `skill_domains` indexing. Read by agents via `Read` tool when needed.

---

## 3. Query lifecycle (sequence)

A typical query flows through the containers in this order:

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant CLI as CLI
    participant D as Dispatcher
    participant S as Supervisor
    participant H as Hooks
    participant A as Agent (e.g. databricks-engineer)
    participant M as MCP Server
    participant L as Ledger
    participant Mem as Memory

    U->>CLI: "/sql SELECT count(*) FROM bronze.events"
    CLI->>Mem: inject_context() — retrieve relevant memories
    Mem-->>CLI: memory context (FTS5 search)
    CLI->>D: select_agents(query)
    D-->>CLI: [databricks-engineer], confidence=0.92
    CLI->>S: build_supervisor_options(agent_names=[databricks-engineer])
    S->>A: Agent(prompt="...")
    A->>H: PreToolUse(tool=execute_sql, input=...)
    H->>H: security_hook → block_destructive_commands
    H->>H: security_hook → check_sql_cost
    alt SQL blocked
        H-->>A: deny with reason
    else SQL approved
        H-->>A: allowed
        A->>M: mcp__databricks__execute_sql
        M-->>A: rows
        A->>H: PostToolUse(output)
        H->>L: audit_tool_usage → append signed entry
        H->>Mem: capture_session_context
        H->>H: cost_guard_hook → classify HIGH/MED/LOW
        H->>H: output_compressor_hook → compress if >threshold
        H-->>A: (possibly compressed) output
    end
    A-->>S: result
    S-->>CLI: synthesized response
    CLI->>U: rendered output
    Note over CLI,L: On session end:<br/>flush memory, log metrics,<br/>checkpoint, ledger flush.
```

---

## 4. Cross-cutting concerns

### Cost control
- **Recompute on egress**: `utils/pricing.py` recalculates cost using Moonshot's real price table; the SDK uses Anthropic Sonnet prices and inflates ~5×.
- **Tier-based budget**: `tier_turns_map` and `tier_effort_map` cap each agent's resources by role.
- **Cost guard hook**: classifies each tool call and alerts at 5+ HIGH ops or estimated cost over `MAX_BUDGET_USD`.
- **Output compressor**: caps SQL rows, file lines, list items; reduces ~40-70% of tool output tokens before they reach the LLM.

### Security
- **Constitution S1–S7**: invariant rules enforced both at the supervisor system prompt and at hook level.
- **Pre-tool hooks**: pattern-block destructive shell commands (22 regex patterns), evasion attempts (base64, eval, xargs+rm), and expensive SQL (`SELECT *` without `WHERE`/`LIMIT`).
- **Ledger HMAC**: per-session key signs every audit entry. Tampering invalidates the chain.
- **Config drift detection**: `config/snapshot.py` freezes settings at startup; drift detection in runtime flags potential prompt-injection attempts.

### Observability
- `logs/app.jsonl` — structured logs (JSONLFormatter).
- `logs/audit.jsonl` — every tool call with HMAC signature.
- `logs/sessions.jsonl` — per-session cost/turns/duration metrics.
- `logs/workflows.jsonl` — workflow steps + clarity checkpoints + agent delegations.
- `logs/compression.jsonl` — output compression metrics.

### Extensibility
- New agent → drop a `.md` in `agents/registry/`, no code change.
- New MCP server → follow `mcp_servers/_template/` + register in `ALL_MCP_CONFIGS`.
- New KB domain → drop a directory under `kb/`, reference from agent `kb_domains`.
- New skill → drop a `SKILL.md` under `skills/<domain>/<name>/`.
- New slash command → entry in `config/commands.yaml`.

---

## 5. What this architecture explicitly is NOT

- It is **not** a generic agent framework (CrewAI/LangGraph). Agents and MCPs are tightly bound to Databricks + Fabric.
- It is **not** a SaaS service. There is no multi-tenant tier, no API gateway, no managed deployment. The user runs the process locally.
- It is **not** a no-code product. It assumes Python, Databricks/Fabric credentials, and CLI/Python familiarity.
- It is **not** a chat-only product. The CLI is primary; UIs are optional extras.

---

## 6. Where to find the details

| Question | Look here |
|---|---|
| Why a specific architecture choice? | `docs/adr/ADR-XXX-*.md` |
| What are the inviolable rules? | `kb/constitution.md` |
| How does an agent get configured? | `agents/registry/_template.md` |
| How does memory work end-to-end? | `memory/` + `docs/adr/ADR-002-memory-three-layers.md` |
| What hooks intercept calls? | `hooks/` + `agents/supervisor.py::build_supervisor_options` |
| What MCPs exist and what they expose? | `mcp_servers/` + `docs/refactor-v3/inventory.md` |
| What slash commands are available? | `config/commands.yaml` |
| How is cost computed and capped? | `utils/pricing.py` + `hooks/cost_guard_hook.py` |
| What is the refactor roadmap? | `docs/refactor-v3/PLAN.md` |

---

*This document is the source of truth for system-level architecture. When the architecture changes, this file changes first (in the same PR).*
