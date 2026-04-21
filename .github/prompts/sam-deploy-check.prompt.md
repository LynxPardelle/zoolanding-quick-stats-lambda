---
name: "SAM Deploy Check"
description: "Review this quick-stats Lambda for AWS SAM deploy readiness. Use when preparing to deploy changes that may affect POST /quick-stats, operation semantics, tests, env vars, IAM, or documentation in zoolanding-quick-stats-lambda."
argument-hint: "Changed files, diff, or deploy concern"
agent: "agent"
---

Review this repository for deploy readiness after the current change.

Follow [Zoolanding Lambda Workflow](../skills/zoolanding-lambda-workflow/SKILL.md) and inspect the contract files:

- [README](../../README.md)
- [Implementation Guide](../../instructions.md)
- [SAM Template](../../template.yaml)
- [SAM Config](../../samconfig.toml)

Use the user's arguments plus the current diff or changed files.

Check specifically for:

- handler and template wiring for `POST /quick-stats`
- drift in `set`, `inc`, `delete`, `merge`, or `append` semantics
- `dryRun`, `createIfMissing`, and `ifMatchEtag` behavior changes
- missing or outdated tests for the critical path under `tests/`
- env var, IAM, or parameter-override mismatches
- docs drift between code, README, instructions, tests, and SAM template

Return:

1. findings first, ordered by severity
2. the deploy command to use, or a note that plain `sam deploy` is sufficient
3. the smallest post-deploy smoke test
4. test or doc updates still required