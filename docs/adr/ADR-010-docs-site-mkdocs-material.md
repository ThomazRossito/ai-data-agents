# ADR-010: Docs site built with MkDocs Material, deployed via GitHub Pages

> **Status**: Accepted
> **Date**: 2026-05-23
> **Deciders**: @ThomazRossito
> **Tags**: docs, tooling, deployment

## Context

By the end of v3 (Phases 1–10), the project accumulated significant prose
content that lives in scattered Markdown files:

- `README.md` — quickstart, agent table, architecture overview
- `docs/ARCHITECTURE.md` — C4 levels 1+2 in Mermaid + query lifecycle
- `docs/SECURITY_THREAT_MODEL.md` — STRIDE applied to 4 trust boundaries
- `docs/adr/ADR-001..010.md` — 10 architectural decisions in Michael Nygard format
- `docs/refactor-v3/PLAN.md` + `inventory.md` + `test-classification.md`
- `kb/constitution.md` + per-domain `index.md` (17 domains)
- `CHANGELOG.md` — full release history with migration notes
- Skill READMEs and various `kb/*/concepts/*.md` / `kb/*/patterns/*.md`

Three pain points motivate consolidating these into a single navigable site:

1. **Discovery**: a new user landing on the GitHub repo has to manually
   click around the file tree to find e.g. "how does the memory layer
   work?". A flat list of files is harder to navigate than a sidebar.
2. **Versioned reference**: when someone reads `data_agents.agents.loader`
   they want function-level reference, not just the source comments. A
   docs site can render this with cross-references.
3. **Migration guidance**: v3 is a breaking change (Phase 7 namespace
   move). A first-class `migration/v2-to-v3.md` page that's visible from
   a nav bar (not buried in CHANGELOG) reduces friction for v2 users
   trying to upgrade.

Options considered:

| Tool | Strengths | Weaknesses for this project |
|---|---|---|
| **MkDocs Material** | Pure Markdown (no MDX), rich theme out-of-the-box, mkdocstrings for API ref when wanted, deploy GH Pages 1-click via `mkdocs gh-deploy`, Python ecosystem nativo | Less customizable than Docusaurus for React widgets |
| Docusaurus | React widgets, internationalization, versioning built-in | Requires Node toolchain; MDX (custom syntax) adds friction for contributors used to plain Markdown; heavier dep tree |
| Sphinx | Industry standard for Python docs; mature autodoc | reStructuredText (default) is friction; Markdown via myst_parser works but feels grafted on; theme work is heavier |
| Hand-rolled HTML | Full control | Maintenance cost; defeats the purpose |

## Decision

Adopt **MkDocs Material** as the docs framework, deployed to **GitHub Pages**
via a workflow that builds on every push to `main` and `refactor/v3.0`.

Initial scope (Phase 11):
- 4 navigation sections: **Getting Started**, **Concepts**, **Tutorials**,
  **Reference**.
- Migration guide for v2 → v3 prominently linked from the landing page.
- Re-use existing Markdown wherever possible (link to `docs/ARCHITECTURE.md`,
  `docs/SECURITY_THREAT_MODEL.md`, ADRs) — do **not** duplicate content.
- mkdocstrings (auto-gen Python API reference) **deferred** — adds a
  maintenance vector (docstrings as contract) that's premature before
  v3.0 final. Reopen post-3.0.0 if user feedback asks for it.

Build/deploy:
- `mkdocs.yml` at repo root.
- `make docs-serve` for localhost preview (port 8000 by default).
- `make docs-build` produces static HTML in `site/` (gitignored).
- `.github/workflows/docs.yml` builds on push and pushes to `gh-pages` branch.
- `[docs]` extra in `pyproject.toml` to install `mkdocs-material` only when
  the docs maintainer needs it.

## Consequences

### Positive

- New users get a single URL (`https://thomazrossito.github.io/ai-data-agents/`)
  that surfaces everything: how to install, key concepts, working tutorials,
  migration guide for breaking changes.
- The 10 ADRs become more discoverable — index page + sidebar navigation
  rather than a directory listing.
- Lint-friendly: docs build on every push catches broken links / missing
  pages before they hit production (`mkdocs build --strict`).
- Plain Markdown lowers the contribution bar — anyone who can edit a `.md`
  file can update the docs.

### Negative

- Adds `mkdocs-material` as a maintenance dependency. Mitigation: scoped
  to `[docs]` optional install — only the maintainer building the site
  needs it. End users don't.
- Two-place edits when content lives in both repo Markdown and the docs
  site. Mitigation: prefer **linking** to source Markdown (e.g. ADRs) over
  duplicating; the site is a navigation layer, not a content fork.
- mkdocstrings deferred means the API reference today is "read the
  docstring in the source". For a project this size (mostly declarative
  agents, not a big library API), that's acceptable.

### Neutral / Future

- If demand for versioned docs emerges (e.g. v2 and v3 docs simultaneously),
  add the `mike` plugin — supported by Material.
- Localization (`pt-BR` second locale) is straightforward when needed —
  Material supports `i18n` plugin.
- If the project pivots to a SaaS shape, Docusaurus might be revisited
  for its React widget ecosystem. Not on the horizon.

## References

- [MkDocs Material](https://squidfunk.github.io/mkdocs-material/)
- [Why MkDocs over Sphinx for new Python projects](https://github.com/squidfunk/mkdocs-material/issues/4334)
- ADR-007 (KB as Markdown) — same minimalism rationale applied to docs.
