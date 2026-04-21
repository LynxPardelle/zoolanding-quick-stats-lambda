# Validation Checklist

## Contract

- `appName` must be a non-empty string.
- `ops` must be an array and remain ordered.
- Invalid operations should fail clearly with a client error.
- `dryRun` must not write to S3.
- `ifMatchEtag` behavior must remain explicit when present.

## Local Verification

- Run the unit tests under `tests/` for operation semantics.
- Use `python .\\local_test.py` when you need handler-level validation.
- Verify both read-only fetches with empty `ops` and mutating requests.

## Change Discipline

- Do not change operation semantics without matching contract documentation.
- Keep frontend integration context in the main `zoolandingpage` repo.
