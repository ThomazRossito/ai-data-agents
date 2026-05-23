# Security Policy

## Reporting a vulnerability

Thank you for taking the time to improve the security of `ai-data-agents`.

**Do not open a public GitHub issue for security vulnerabilities.** Instead, use one of the channels below:

### Preferred channel — GitHub Security Advisories

Open a private advisory at:
**[https://github.com/ThomazRossito/ai-data-agents/security/advisories/new](https://github.com/ThomazRossito/ai-data-agents/security/advisories/new)**

This keeps the conversation private until a fix is published, and gives you a CVE if applicable.

### Alternative channel — Email

Send a report to **thomaz.rossito@terra.com.br** with:

- A description of the vulnerability and its impact.
- Steps to reproduce (proof-of-concept welcome).
- The affected version (`pyproject.toml` → `version` field).
- Optional: any suggested fix.

Encrypt sensitive details with the maintainer's PGP key on request.

## What to expect

| Step | Target SLA |
|---|---|
| Acknowledgement of the report | within **72 hours** |
| Initial assessment (severity, scope) | within **7 days** |
| Patch availability for HIGH/CRITICAL | within **30 days** |
| Public disclosure | coordinated with reporter |

This is a best-effort SLA from a small-team project — actual response time may vary.

## Supported versions

Only the latest minor of the latest major receives security fixes.

| Version | Supported |
|---|---|
| `3.x.x` (planned) | ✅ |
| `2.3.x` | ✅ (current stable) |
| `2.2.x` and older | ❌ |

When `3.0.0` ships, `2.3.x` will receive critical-only patches for 90 days, then enter EOL.

## Scope

The following are **in scope** for security reports:

- The `data_agents` Python package and its modules.
- All MCP servers in `mcp_servers/` (custom implementations).
- Hooks in `hooks/` that process user input (security_hook, audit_hook).
- CI/CD workflows in `.github/workflows/`.
- Build and install scripts (`Makefile`, `start.sh`, `pyproject.toml`).
- Sample configuration in `.env.example`.

The following are **out of scope**:

- Third-party MCP servers (`@modelcontextprotocol/server-github`, `@upstash/context7-mcp`, etc.) — report upstream.
- Third-party Python packages — report to the upstream maintainers.
- The Claude Agent SDK (`claude-agent-sdk`) — report to Anthropic.
- The Moonshot Kimi API endpoint — report to Moonshot.
- Issues in user-supplied credentials, `.env` files, or local configuration.
- Social engineering of project maintainers.

## Classes of vulnerability we care about

- Prompt injection that bypasses Constitution S1–S7 invariants.
- Credential leakage (tokens, API keys, secrets) via logs, error messages, or audit trails.
- Destructive operations not caught by `hooks/security_hook.py` (DROP/DELETE/format/rm without WHERE).
- SQL injection or similar in custom MCP servers (`fabric_sql`, `migration_source`).
- Path traversal in file operations.
- Insecure deserialization in checkpoint/transcript files.
- Authentication/authorization bypasses in MCP custom auth flows.
- Bypasses of the Ledger HMAC integrity chain in audit logs.
- Supply-chain risks in dependencies (handled via Dependabot + `pip-audit` in CI).
- Code execution via crafted skill/KB/agent registry files.

## Safe Harbor

We will not pursue legal action against researchers who:

1. Report vulnerabilities through the channels above before public disclosure.
2. Do not access or modify data belonging to others.
3. Do not degrade service availability (no DoS testing on production endpoints).
4. Act in good faith and follow this policy.

## Acknowledgements

Reporters who follow this policy will be credited in `CHANGELOG.md` for the release that ships the fix, unless they prefer to remain anonymous.

---

*Last updated: 2026-05-22 — Maintained by [@ThomazRossito](https://github.com/ThomazRossito)*
