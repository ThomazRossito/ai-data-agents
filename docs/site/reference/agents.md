# Agents (15)

Live roster from `data_agents/agents/registry/`. Each agent is a single Markdown file with YAML frontmatter. Adding a new agent is a 1-file PR.

| Agent | Tier | Domain |
|---|---|---|
| **databricks-engineer** | T1 | Databricks platform expert: SQL, PySpark, DLT/LakeFlow, Jobs, CDC, Spark diagnosis, Genie Spaces, AI/BI Dashboards |
| **databricks-ai** | T1 | RAG, Vector Search, embeddings, LLMOps (MLflow), AI Functions, Kafka, Flink, Spark Structured Streaming |
| **fabric-engineer** | T1 | Microsoft Fabric platform expert: Lakehouse, Data Factory, Star Schema, Data Vault, Semantic Models, DAX, Direct Lake, FinOps |
| **migration-expert** | T1 | SQL Server / PostgreSQL → Databricks/Fabric (ASSESS → ANALYZE → DESIGN → TRANSPILE → RECONCILE) |
| **python-expert** | T1 | Pure Python (no PySpark): packages, APIs, CLIs, pandas/polars, testing |
| **dbt-expert** | T2 | dbt Core: models, sources, snapshots, tests |
| **data-quality-steward** | T2 | Cross-platform DQ: expectations, profiling, drift, SLA |
| **governance-auditor** | T2 | Access audit, lineage, PII classification, LGPD/GDPR, RLS/OLS |
| **data-contracts-engineer** | T2 | ODCS contracts, SLA, schema evolution, breaking changes |
| **data-mesh-architect** | T2 | Data Mesh architecture, domains, Data Products, federated governance |
| **fabric-rti** | T2 | Fabric Real-Time Intelligence: Eventstream, Eventhouse/KQL, Activator |
| **fabric-ontology** | T2 | OWL 2, RDF, SPARQL, rdflib, Fabric IQ Ontology |
| **business-analyst** | T3 | Convert transcripts/briefings → structured backlog (P0/P1/P2) |
| **geral** | T0 | Conceptual answers (no MCP, cheapest path) |
| **azure-cost-calculator** | T2 | Azure pricing — Retail Prices API, TCO, RI vs PAYG, USD↔BRL |

Source of truth: [`data_agents/agents/registry/`](https://github.com/ThomazRossito/ai-data-agents/tree/refactor/v3.0/data_agents/agents/registry).

## Phase 5 — Rich frontmatter

Each agent declares structured `stop_conditions` (when to halt and escalate) and `escalation_rules` (target agent + trigger + reason). The Supervisor consumes these as an authoritative whitelist for delegation decisions.

Aggregate: **93 stop_conditions + 66 escalation_rules** across all 15 agents. Lint rejects:

- Self-referencing escalation (agent → itself)
- Targets that don't exist in registry (typo guard)
- Missing required keys (`trigger`, `target`, `reason`)

See [`scripts/lint_registry.py`](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/scripts/lint_registry.py) and [Constitution S6](../concepts/constitution.md).

## Adding a new agent

```bash
cp data_agents/agents/registry/_template.md \
   data_agents/agents/registry/my-new-agent.md
# Edit the YAML frontmatter + Markdown body
make lint-registry        # validate
make test-fast            # ensure registry tests pass
```

No Python code change required — the loader picks up the new file automatically.
