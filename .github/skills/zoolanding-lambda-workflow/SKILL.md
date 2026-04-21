---
name: zoolanding-lambda-workflow
description: 'Zoolanding Lambda workflow for quick stats updates in S3. Use when changing request validation, operation application, optimistic concurrency, tests, local harness behavior, or SAM deployment for zoolanding-quick-stats-lambda.'
user-invocable: true
---

# Zoolanding Lambda Workflow

Use this skill for work in the quick-stats Lambda.

## Repo Focus

- The contract is operation-driven: `set`, `inc`, `delete`, `merge`, `append`.
- The persisted object is `appName/stats.json` in S3.
- This repo owns the Lambda behavior; the frontend repo owns cross-platform integration context.

## Workflow

1. Read the contract first.
   - Start with `README.md` and `instructions.md`.

2. Keep operation semantics stable.
   - Unknown ops and invalid payload shapes should fail clearly.
   - `dryRun`, `createIfMissing`, and `ifMatchEtag` should stay behaviorally explicit.
   - Preserve ordering of `ops` application.

3. Prefer focused changes.
   - Modify `apply_op` or handler flow only where the requested behavior requires it.
   - Avoid broad rewrites that blur operation semantics.

4. Verify with tests first when practical.
   - Run the unit tests under `tests/` for operation behavior.
   - Use `python .\\local_test.py` for a handler-level local harness when needed.

5. Keep deployment and docs aligned.
   - If env vars, response shape, or API behavior changes, update the docs with the code.

## Resources

- [Validation Checklist](./references/validation-checklist.md)