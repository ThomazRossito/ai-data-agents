# ADR-011: Claude Code plugin — minimal scope (agents + skills only) for v3.0-rc1

> **Status**: Accepted
> **Date**: 2026-05-23
> **Deciders**: @ThomazRossito
> **Tags**: distribution, plugin, claude-code, scope

## Context

Phase 12 of the v3 refactor adds a third distribution channel to `ai-data-agents`,
on top of the existing two (`pip install` and source clone): the
[Claude Code plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces).

A Claude Code plugin can contain:

- `agents/*.md` — subagents
- `skills/<name>/SKILL.md` — operational skills
- `commands/*.md` — slash commands (one `.md` per command)
- `hooks/hooks.json` — Pre/Post tool-use interceptors
- `.mcp.json` — MCP server registrations

Our project has all five components, but with different shapes:

| Component | Project shape | Plugin shape | Compatibility |
|---|---|---|---|
| Agents | `data_agents/agents/registry/*.md` (single dir, flat) | `agents/*.md` (same) | **direct** |
| Skills | `skills/<domain>/<name>/SKILL.md` (grouped by domain) | `skills/<name>/SKILL.md` (flat) | **flatten** |
| Slash commands | `data_agents/config/commands.yaml` (aggregated YAML, 39 entries) | `commands/<name>.md` (one file per command) | **convert** |
| Hooks | Python modules + registered via `agents/supervisor.py::build_supervisor_options` | `hooks/hooks.json` (declarative event handlers) | **incompatible** |
| MCPs | Python `server_config.py` per MCP + registered in `config/mcp_servers.py` | `.mcp.json` per plugin | **partially convertible** |

## Decision

For v3.0-rc1, the plugin includes **only agents and skills**. The other three
components stay in the Python CLI distribution and are explicitly documented
as out-of-scope in the plugin README.

Rationale per component:

### Agents (✅ included)
Direct copy of `data_agents/agents/registry/*.md` (15 files, excluding the
template). Source-of-truth lives in the project; the plugin is a generated
view kept in sync by `scripts/build_plugin.sh` and gated by
`plugin-validate.yml`. Adding a new agent is one PR to the project; the
plugin auto-syncs on the next push.

### Skills (✅ included)
Flattened from `skills/<domain>/<name>/` to `skills/<name>/` via the build
script. Domain grouping is a project convention for organizing 48 skills;
the plugin spec doesn't preserve it. Collision detection in the script
aborts the build if 2 skills end up with the same name (today there are
none).

### Slash commands (❌ deferred)
The plugin spec wants one `.md` per command with YAML frontmatter
(`description`, etc.) and body as the prompt template. Our `commands.yaml`
has 39 entries with `prompt_template`, `display_template`, `agent`,
`doma_mode`, `skills` — converting to 39 files is mechanical but introduces
a sync vector. **Defer to v3.1+** once the plugin spec stabilizes and we
have signal on whether plugin users miss slash commands (they can invoke
agents via natural language inside Claude Code).

### Hooks (❌ deferred)
Hooks in this project are Python modules with state (cost guard counters,
context budget tracking, HMAC ledger keys per session). The plugin
`hooks.json` is declarative event-handler descriptors — not a 1:1 mapping.
Porting would require re-implementing the hook layer as content rather
than code. Not worth it for a marketplace distribution; users who want
hooks should use the Python CLI.

### MCPs (❌ deferred)
MCP servers in this project carry per-platform credentials (Databricks PAT,
Azure SP, etc.) and per-user configuration (workspace IDs, hostname).
Bundling `.mcp.json` in the plugin would force every plugin user to use the
same MCP setup, which is wrong. Plugin users configure their own MCPs in
Claude Code's `~/.claude/settings.json` separately. Documented in the
plugin README.

## Consequences

### Positive

- **Time to market**: Phase 12 lands in days, not weeks. The 4 deferred
  components are real work; agents+skills are not.
- **Smaller surface area to break**: when the Claude Code plugin spec
  evolves (it's young — sub-1-year), fewer files in our plugin = fewer
  things to fix.
- **Clear story for plugin users**: the README spells out exactly what they
  get vs the Python CLI. No surprises.
- **Sync via CI**: `plugin-validate.yml` re-runs `build_plugin.sh` on every
  PR and asserts zero diff. No drift between canonical and plugin view.

### Negative

- Plugin users **cannot** use `/sql`, `/fabric`, `/migrate` etc. — they
  invoke agents via natural language. Slightly worse UX than Python CLI
  for power users. Documented as a known gap.
- Plugin users **must** configure their own MCPs separately. The plugin
  doesn't auto-wire Databricks/Fabric. Documented as a known gap.
- Two release artifacts to attach per release (wheel/sdist + plugin
  tarball). Mitigated by the glob `dist/*.tar.gz` in `release.yml`.

### Neutral / Future

- v3.1+ work could re-evaluate hooks/commands inclusion based on real
  plugin user feedback. The deferral is not permanent; it's "later" not
  "never".
- If the plugin gets traction (≥100 installs from marketplace), the cost
  of porting `commands.yaml` → 39 individual `.md` files is justified.
  Until then, premature.
- Hooks are unlikely to ever go in the plugin — they're code, not content.
  That's a fundamental architecture difference, not a deferral.

## References

- [Claude Code plugin documentation](https://code.claude.com/docs/en/plugin-marketplaces)
- [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) — reference implementation of an Anthropic-managed marketplace
- ADR-007 (KB as Markdown) — same "content as plain Markdown" principle
- ADR-010 (MkDocs Material) — analogous "minimal toolchain" rationale
