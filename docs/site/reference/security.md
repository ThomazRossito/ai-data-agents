# Security

## Threat model

The full STRIDE threat model lives in [`docs/SECURITY_THREAT_MODEL.md`](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/docs/SECURITY_THREAT_MODEL.md). It covers 4 trust boundaries (User → Supervisor → Subagent → MCP → Platform) and 2 cross-cutting concerns (Hooks layer, Memory layer).

## Vulnerability reporting

**Do not** open public GitHub issues for security vulnerabilities. See [`SECURITY.md`](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/SECURITY.md) for the responsible disclosure process.

## Local security audit

One command runs the full security review:

```bash
make security-review
```

Three steps in sequence:

1. **bandit** — Python security lint over `data_agents/` (skips B101 assert checks)
2. **pip-audit** — CVE in transitive deps via OSV database
3. **Secrets regex scan** — 8 well-known credential patterns + contextual heuristic for `SECRET=value`

## CI security gates

| Workflow | Frequency | What it catches |
|---|---|---|
| `.github/workflows/ci.yml` job `security-audit` | every push/PR | pip-audit (HIGH/CRITICAL CVEs fail) |
| `.github/workflows/ci.yml` job `bandit` | every push/PR | bandit -ll (low+ severity) |
| `.github/workflows/codeql.yml` | every push/PR | Python static analysis (GitHub CodeQL) |
| `.github/workflows/security.yml` | every PR | Dependency review for license + advisory |

## Secrets management

| What | Where | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | `.env` (gitignored) | Moonshot key, used for kimi-k2.6 + summarizer Haiku fallback |
| `DATABRICKS_TOKEN` | `.env` (gitignored) | PAT, scoped to workspace |
| `AZURE_CLIENT_SECRET` | `.env` (gitignored) | Service principal credential for Fabric |
| `FABRIC_WORKSPACE_ID` | `.env` (gitignored) | Not strictly secret, but workspace-coupled |
| `TAVILY_API_KEY`, `GITHUB_PERSONAL_ACCESS_TOKEN`, `FIRECRAWL_API_KEY` | `.env` (gitignored) | Optional MCPs |
| HMAC ledger key | generated per-session, not persisted | See `data_agents/memory/ledger.py` |

`.gitignore` blocks `.env`, `.env.personal`, `.env.flow`, `.env.bak`, `*.pem`, `*.key`. `scripts/security_review.sh` adds a regex tripwire for accidental commits of inline credentials.

## Hardening checklist for production deploys

If you're running ai-data-agents in a non-personal context:

- [ ] Set `LEDGER_ENABLED=true` for tamper-evident audit chains
- [ ] Set `AGENT_PERMISSION_MODE=acceptEdits` instead of default `bypassPermissions` — requires confirmation before writes
- [ ] Set `MAX_BUDGET_USD` per session to a hard cap (raises on exceed)
- [ ] Configure `S4_AUTONOMOUS_MODE=false` to require human approval for multi-agent delegations (default `false` already)
- [ ] Pin the package version (`ai-data-agents==3.0.0`) in your install; don't track HEAD
- [ ] Rotate `DATABRICKS_TOKEN` quarterly; scope it to least-privilege groups in Unity Catalog
- [ ] Limit MCP server access via firewall — `databricks-mcp-server` and `microsoft-fabric-rti-mcp` should only need outbound HTTPS

## Known open issues

See the **Top-3 debts** section of [`docs/SECURITY_THREAT_MODEL.md`](https://github.com/ThomazRossito/ai-data-agents/blob/refactor/v3.0/docs/SECURITY_THREAT_MODEL.md#9-top-3-debts-to-prioritize-post-phase-10).
