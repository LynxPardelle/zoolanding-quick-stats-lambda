# Developer Guide — Zoolanding Quick Stats Lambda

This guide dives deeper into the implementation details for the Quick Stats Lambda.

## Endpoints and Event Shape

This Lambda expects an API Gateway proxy integration event. Only `body` and `isBase64Encoded` are used. `headers` are ignored by core logic.

Body fields:

- `appName`: string (required)
- `ops`: array of operation objects (required, can be empty for read-only fetch)
- `createIfMissing`: boolean (optional, default `true`)
- `dryRun`: boolean (optional, default `false`)
- `ifMatchEtag`: string (optional, optimistic concurrency)

## Operations

Each op is an object with at least `op` and `path` fields. Supported ops:

- `set`: set arbitrary value
  - `{ "op": "set", "path": "a.b.c", "value": 123 }`
- `inc`: increment numeric value by `by` (default `1`)
  - `{ "op": "inc", "path": "totals.visits", "by": 2 }`
- `delete`: remove a key or array item
  - `{ "op": "delete", "path": "a.b.c" }`
- `merge`: deep merge an object into a target object
  - `{ "op": "merge", "path": "flags", "value": { "beta": true } }`
- `append`: push a value to an array (creates array if missing)
  - `{ "op": "append", "path": "events", "value": { "name": "page_view" } }`

Path format uses dot-notation and supports numeric segments as array indices (e.g., `items.0.name`). Intermediate objects/lists are created automatically where reasonable.

## Concurrency

S3 is last-writer-wins for this use case. If you require optimistic concurrency, pass `ifMatchEtag`. The Lambda will compare against the current ETag and reject when mismatched.

## Local Testing

Use `local_test.py` to run a quick smoke test. By default, local S3 writes are disabled (`DRY_RUN=1`).

```powershell
$env:DRY_RUN = "1"
python ..\local_test.py
```

To test against a real bucket, set credentials and `STATS_BUCKET_NAME`:

```powershell
$env:DRY_RUN = "0"
$env:STATS_BUCKET_NAME = "zoolanding-quick-stats"
python ..\local_test.py
```

## Error Handling

- 400 — validation problems (invalid JSON, missing `appName`, invalid `ops`, bad op types)
- 500 — unexpected S3 or internal errors

All logs are JSON-structured and include request and S3 context.
