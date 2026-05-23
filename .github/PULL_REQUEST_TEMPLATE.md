<!--
Thank you for contributing to ai-data-agents!
Please fill out this template to help reviewers understand and merge your change.
-->

## Summary

<!-- One or two sentences describing what this PR does and why. -->

## Type of change

<!-- Check all that apply with [x]. Conventional Commit type matches `<type>(scope): ...`. -->

- [ ] `feat` — new feature
- [ ] `fix` — bug fix
- [ ] `docs` — documentation only
- [ ] `refactor` — code restructuring without behavior change
- [ ] `perf` — performance improvement
- [ ] `test` — adding or fixing tests
- [ ] `build` / `ci` — build system or CI configuration
- [ ] `chore` — maintenance, no source change

## Related issue / ADR

<!-- Link issues with "Closes #123" or "Refs #456". For architectural decisions, link the ADR. -->

Closes #
Refs ADR-

## What changed

<!-- High-level list of changes. Avoid listing every file — focus on what reviewers need to know. -->

-
-
-

## Why this approach

<!-- Trade-offs considered, alternatives evaluated, links to discussions. -->

## How to test

<!--
Concrete commands a reviewer can run.
Example:
  make test
  pytest tests/unit/test_agents.py::TestDatabricksEngineer -v
  python main.py "/sql SELECT 1"
-->

```bash

```

## Breaking changes

<!-- If this changes a public API, environment variable, file path, or CLI flag, describe the migration path. -->

- [ ] **No breaking changes**
- [ ] Breaking change — described below and flagged in commit footer

<!-- If breaking, describe the migration:
- Removed: `<symbol>` → use `<new symbol>` instead.
- Renamed: `<env var>` → `<new env var>`. Setting both during transition is supported until v3.1.
-->

## Checklist

- [ ] My branch is up to date with `develop` (or `refactor/v3.0` until v3.0 ships).
- [ ] `make lint type-check test` passes locally.
- [ ] New or changed code has unit tests; coverage does not decrease.
- [ ] I added a `CHANGELOG.md` entry under `## [Unreleased]`.
- [ ] I updated documentation (README, docstrings, ADRs, KB) where applicable.
- [ ] I added/updated entries in `docs/refactor-v3/inventory.md` if I added agents/MCPs/skills/KBs.
- [ ] No secrets, tokens, or PII are in the diff or in test fixtures.
- [ ] All required CI checks pass.
- [ ] Self-review done — I read every line of my diff before requesting review.

## Screenshots / output (optional)

<!-- For UI changes or CLI output changes, paste a screenshot or terminal capture. -->

## Notes for reviewers

<!-- Anything reviewers should pay extra attention to. Known unknowns. Risk areas. -->
