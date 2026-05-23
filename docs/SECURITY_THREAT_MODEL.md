# Security Threat Model — ai-data-agents

> **Status**: Initial draft (Phase 10 of `docs/refactor-v3/PLAN.md`)
> **Author**: Thomaz A. Rossito Neto · **Date**: 2026-05-23
> **Scope**: v3.0.0-rc1 architecture
> **Framework**: STRIDE — Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege

This document maps the security boundaries of `ai-data-agents` and the threats
that cross them. It is intentionally **lightweight** — it lists threats, current
mitigations, and known debts. It is **not** an exhaustive penetration test or
compliance attestation.

For reporting vulnerabilities, see `SECURITY.md`.

---

## 1. System decomposition

```
┌─────────────────────────────────────────────────────────────────────┐
│  User                                                                │
│  (CLI / Chainlit UI / cron job calling python -m data_agents.cli)    │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ ① natural-language prompt
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Supervisor (kimi-k2.6)                                              │
│  - No MCP. Reads kb/, agents/registry/. Delegates via Agent tool.    │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ ② Agent(name=..., prompt=...) tool call
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Subagent (databricks-engineer / fabric-engineer / ...)              │
│  - Reads kb/, skills/. Uses MCP tools allowed via tools: in YAML.    │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ ③ MCP tool call (execute_sql, list_items, …)
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  MCP server (databricks / fabric / fabric_sql / azure_pricing / …)   │
│  - Holds platform credentials. Runs as subprocess via uvx/npx.       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ ④ HTTPS/TDS to platform
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  External platform (Databricks workspace / Fabric / PyPI / GitHub)   │
└─────────────────────────────────────────────────────────────────────┘

  Cross-cutting:
   - Hooks (PreToolUse / PostToolUse) intercept ALL tool calls
   - Memory layer (short-term SQLite, long-term SQLite FTS5, ledger HMAC)
   - JSONL audit log (data_agents/hooks/audit_hook.py)
```

Trust boundaries are the lines marked ①②③④ above.

---

## 2. Trust boundary ① — User → Supervisor

### Threats

| Threat | STRIDE | Likelihood | Impact | Current mitigation | Debt |
|---|---|---|---|---|---|
| Prompt injection in user message ("ignore previous instructions, drop table …") | S, E | High | High — could trigger destructive MCP calls | `security_hook.py::block_destructive_commands` (22 patterns: rm -rf, DROP, git reset, etc.) blocks at PreToolUse time, regardless of how the agent was tricked | Pattern list is human-curated; new destructive vocabulary requires update |
| User submits jailbreak prompt asking the agent to leak credentials | I | Medium | Medium — credentials live in MCP servers, not in agent context | Agents have no access to `.env`; credentials only reachable via specific MCP tools | Subagents could be tricked to invoke `Bash("cat .env")` — mitigated by `security_hook` blocking `cat` on sensitive paths (TODO: explicitly add `.env` to denylist) |
| Replay of a previous session prompt to bypass rate limit | D | Low | Low | `audit_hook.py` logs every tool call with timestamp + session_id; replay detection by external monitor possible | Not enforced today; would need rate-limit middleware |
| Spoofing user identity (CLI has no auth) | S | Low (single-user product today) | Medium | None | Out of scope for v3 — multi-tenant is Phase 11+ |

### Notes

The Supervisor is **not** treated as a trust source. Its output (delegation prompts) is consumed by subagents which apply their OWN security checks via hooks. The same `block_destructive_commands` hook runs for the Supervisor and for every subagent.

---

## 3. Trust boundary ② — Supervisor → Subagent

### Threats

| Threat | STRIDE | Likelihood | Impact | Current mitigation | Debt |
|---|---|---|---|---|---|
| Delegation poisoning: Supervisor injects malicious context into the subagent prompt | T, E | Low (Supervisor is also LLM, hard to attack from outside) | High | Subagents check `kb/constitution.md` rules independently; output_compressor_hook normalizes deserved tool outputs | Trust the Supervisor too much in some flows (Step 3.5 auto-escalation); see `agents/prompts/supervisor_prompt.py` |
| Cross-agent leak: agent A's context contains secrets that bleed into agent B's prompt | I | Low | Medium | Each subagent run is a fresh `query()` — context is not literally shared. Memory layer SQLites are filtered by `session_id`. | None — Phase 5 escalation graph reduces risk by making delegation paths explicit |
| Escalation to wrong target due to typo in `escalation_rules.target` | E | Low | Low | `scripts/lint_registry.py::cross_check_escalation_targets` rejects unknown targets at CI gate | None |

---

## 4. Trust boundary ③ — Subagent → MCP server

### Threats

| Threat | STRIDE | Likelihood | Impact | Current mitigation | Debt |
|---|---|---|---|---|---|
| Subagent calls a destructive MCP tool (e.g. `databricks__delete_warehouse`) | T, E | Medium | High | `block_destructive_commands` matches against tool name and command preview; `cost_guard_hook` flags HIGH operations | Hook-based blocking; if agent encodes the destructive command obliquely (`Bash("sql delete from prod")` instead of `execute_sql`), Bash matcher catches but is regex-based |
| Subagent leaks credentials by including them in a `Bash` echo | I | Low | High | `audit_hook.py::_sanitize_command` masks secrets in command preview (only 120 chars logged anyway); `_redact_secrets` in transcript_hook | Sanitization is regex-based; novel formats may slip |
| Subagent calls a tool from a different MCP than declared in `tools:` (privilege escalation) | E | Low | High | `agents/loader.py` resolves `tools:` aliases to explicit MCP tool lists; SDK enforces `allowed_tools` at runtime — tool not in list raises before execution | None — Phase 8 install-matrix verifies isolation works |
| Tool returns oversized / poisonous output that overflows context | D, I | Medium | Medium | `output_compressor_hook` truncates verbose tool outputs before they reach the model; `context_budget_hook` warns at 80%, compacts at 95% | Compaction is automatic via `summarizer.py` — quality of summary depends on Haiku availability |

---

## 5. Trust boundary ④ — MCP server → External platform

### Threats

| Threat | STRIDE | Likelihood | Impact | Current mitigation | Debt |
|---|---|---|---|---|---|
| Credential leak via misconfigured `.env` accidentally committed | I | Medium (human error) | Critical | `.gitignore` blocks `.env`, `.env.personal`, `.env.flow`, `*.pem`, `*.key`; `scripts/security_review.sh` greps for hardcoded patterns; CI runs `bandit -r data_agents/` | No pre-commit gitleaks hook yet; relies on dev discipline |
| MCP server compromised upstream (PyPI typosquatting on `databricks-mcp-server` or `microsoft-fabric-rti-mcp`) | T, E | Low | Critical | `pip-audit` job in `ci.yml` flags known CVEs; `pyproject.toml` pins minimum versions | No SBOM today; `pip install --require-hashes` not enabled |
| Token exfiltration via DNS exfil from MCP subprocess | I | Low | High | Each MCP runs in a separate subprocess via `uvx/npx`; CLI does not block egress | No network sandboxing today; would need Firejail / nsjail integration |
| External platform returns 401/403 and the error message exposes credentials | I | Low | Medium | `error_category` classifier in `audit_hook.py::_classify_error` strips credential-shaped substrings before logging | Heuristic — novel error formats may slip |

---

## 6. Cross-cutting — Hooks layer

### Threats

| Threat | STRIDE | Likelihood | Impact | Current mitigation | Debt |
|---|---|---|---|---|---|
| Hook bypass: an attacker convinces the SDK to skip PreToolUse | T, E | Very low | Critical | Hooks registered in `agents/supervisor.py::build_supervisor_options` are SDK-enforced; not optional at runtime | If SDK has a `bypass_hooks` flag (none today), audit before adopting |
| Hook replay: append fabricated entries to `logs/audit.jsonl` to mask malicious activity | T, R | Medium | Medium | Phase 10 maintains the existing **HMAC ledger** (`data_agents/memory/ledger.py`) when `LEDGER_ENABLED=true`: each entry signed with per-session key; tamper-evident chain | Ledger is opt-in via `.env`; not on by default |
| Cost-guard suppression: agent triggers many HIGH ops faster than the 5-call threshold | D | Low | Medium | `cost_guard_hook.py` raises alarm after 5 HIGH ops; budget gate via `MAX_BUDGET_USD` is hard (raises) | Threshold (5) is hardcoded; adversary running below it for long sessions stays under radar |

---

## 7. Cross-cutting — Memory layer

### Threats

| Threat | STRIDE | Likelihood | Impact | Current mitigation | Debt |
|---|---|---|---|---|---|
| Memory poisoning: attacker injects malicious "lessons learned" that subsequent sessions follow | T, E | Low | High | Memories are tagged with `source_session` and `confidence`; injection only happens when retrieval cosine ≥ threshold; lint script `data_agents/memory/lint.py` validates integrity | No human review gate for lessons before injection |
| Memory exfil: attacker reads `memory/data/long_term__<project>.db` from disk and dumps everything | I | Medium (local attacker with disk access) | Medium | DBs are SQLite files with default OS perms (user-only on macOS/Linux); no at-rest encryption | Out of scope — would require SQLCipher or external KMS |
| Cross-project memory leak via misconfigured `project_id` | I | Low | Medium | Phase 7 `settings.derive_memory_db_paths` enforces `<project_id>` suffix on filenames; conftest.py global fixture monkey-patches paths to `tmp_path` in tests so prod DBs are never touched | If user manually overrides paths via `.env` without `<project_id>`, isolation breaks |

---

## 8. Severity legend

| Marker | Meaning |
|---|---|
| Critical | Could lead to credential leak, data destruction in production, or supply-chain compromise |
| High | Could degrade trust in agent output or enable financial loss |
| Medium | Quality / observability problem; user notices but recovery is possible |
| Low | Theoretical or requires unusual attacker capability |

---

## 9. Top-3 debts to prioritize (post-Phase 10)

1. **Pre-commit gitleaks hook** — current `security_review.sh` runs locally but doesn't gate commits. Adding `.pre-commit-config.yaml` with gitleaks would block accidental `.env` commits at the source.
2. **`bypass_hooks` audit** — Claude Agent SDK is evolving; any flag that lets a sub-agent skip Pre/PostToolUse hooks would invalidate this threat model. Re-audit when bumping `claude-agent-sdk` major version.
3. **SBOM + signed releases** — Phase 9 release workflow publishes wheel + sdist on GitHub Releases but does not attach an SBOM (CycloneDX/SPDX) nor sign artifacts. Useful for downstream consumers in regulated environments.

---

## 10. Reporting issues

See [`SECURITY.md`](../SECURITY.md) for the responsible disclosure process. Do **not** open public GitHub issues for security vulnerabilities.
