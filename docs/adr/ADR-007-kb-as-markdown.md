# ADR-007: Knowledge Base stored as Markdown with YAML frontmatter

> **Status**: Accepted
> **Date**: 2026-05-22
> **Deciders**: @ThomazRossito
> **Tags**: documentation, prompt-engineering, retrieval

## Context

Agents need access to domain knowledge: anti-patterns, schemas, conventions, regulatory references, industry KPIs. This knowledge has properties that constrain how to store it:

1. **It is consumed by LLMs primarily** — the format must be highly tokenizable and convey hierarchy via headers.
2. **It is maintained by humans** — must be diff-friendly, reviewable in PRs, no opaque blobs.
3. **It is referenced declaratively** — agents say "I need `kb_domains: [databricks, sql-patterns]`" and the loader must resolve that to content.
4. **It is potentially large** — 17 domains × ~7 files each × ~5KB each = ~600KB total. Loading all of it on every query is impractical.

Options for storage range from Markdown files to a vector database to a structured schema (YAML/JSON).

## Decision

**Store the Knowledge Base as Markdown files** in `kb/<domain>/`. Each domain has:

- `index.md` with YAML frontmatter (`domain`, `updated_at`, `agents: [list]`) and a navigation index of the domain's content.
- Sub-files: `concepts/<topic>.md`, `patterns/<topic>.md`, `anti-patterns/<topic>.md`, etc.

Agents reference domains by name in their frontmatter: `kb_domains: [databricks, sql-patterns]`.

The loader (`agents/loader.py::_load_kb_indexes`) **injects only the `index.md` content** into the agent's system prompt — not the full content of all files. The agent uses `Read("kb/<domain>/<file>.md")` to drill into specific files when needed.

This keeps prompt tokens bounded while giving the agent discoverability.

The 17 domains as of v2.3.0: `azure-pricing`, `checklists`, `data-contracts`, `data-mesh`, `data-quality`, `databricks`, `fabric`, `governance`, `industry` (10 verticals), `migration`, `pipeline-design`, `python-patterns`, `semantic-modeling`, `semantic-web`, `shared`, `spark-patterns`, `sql-patterns`.

Constitutional rules (`kb/constitution.md`) and routing (`kb/task_routing.md`) live at the root of `kb/`, not inside a domain.

## Consequences

### Positive
- Diff-friendly in PRs. Reviewers can read the change in plain English.
- Authoring is approachable — anyone who knows Markdown can contribute to KB.
- `index.md` injection keeps prompt size predictable (~5K extra tokens for the agent's declared domains).
- Domain isolation: changing `kb/databricks/` doesn't risk `kb/fabric/`.
- The KB serves double duty as project documentation (in `docs/`) and runtime context (via injection).

### Negative
- No automatic full-text search across the KB. An agent that doesn't know which file to read may miss content.
- Markdown has no schema enforcement — a contributor can break the frontmatter and only Phase-3 lint will catch it.
- "Versioning" of KB content is git history; no `version:` field in frontmatter (yet). When a regulation changes, the old guidance disappears from the file.

### Neutral / unknown
- Whether to add semantic search (e.g., embed each KB file with `fastembed`) to enable agents to discover unread content. Currently no — would add a dependency for marginal benefit.
- Whether to migrate to a docs-site format (MkDocs Material) for human consumption while keeping the same Markdown files. Deferred to Phase 11 of the v3 refactor.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| Vector database (Chroma/Qdrant) for KB | Semantic search; fuzzy matching | Heavy dep; binary blobs in git; harder to PR-review | Markdown is plenty for ~1MB of curated content |
| Structured YAML/JSON | Schema-enforced; queryable | Lossy for prose nuance; bad for LLM consumption | LLMs work better with Markdown hierarchy |
| Single monolithic `KB.md` | One file to read | 600KB file is unmaintainable | Domain split is the obvious win |
| Generate KB from code | Always consistent | Code can't express ANS/BACEN/SUSEP regulations | KB is irreducibly human knowledge |
| External hosted wiki (Notion/Confluence) | Rich editing | Off-repo; not versioned with code; auth complexity | Defeats single-source-of-truth |

## References

- `kb/` directory tree.
- `agents/loader.py::_load_kb_indexes` — injection logic.
- `kb/_templates/domain.md` — template for new KB domains.
- Phase 3 of `docs/refactor-v3/PLAN.md` — adds `scripts/lint_kb.py` to enforce structure.
