# Zoolanding Quick Stats Lambda — Implementation Guide

This document specifies a Lambda function that reads and updates an application-level `stats.json` stored in S3. The Lambda is invoked via API Gateway with a JSON body describing one or more operations to apply to the stats document. After applying the operations, the function persists the updated document and returns it.

## Overview

- Language/runtime: Python 3.13 (no external dependencies; `boto3` is available in AWS runtime)
- Trigger: API Gateway (HTTP/REST) or any invoker providing an API Gateway–like `event`
- Target bucket: `zoolanding-quick-stats` (configurable via env var `STATS_BUCKET_NAME`)
- Object to read/write: `appName/stats.json`
- Behavior: Load current stats (or initialize if missing), apply operations (add/update/delete/merge/append/inc), save, and return the full stats JSON

Rationale: A simple S3-backed JSON document per application provides a lightweight, cost-effective store for aggregate counters and simple stats without provisioning a database. This lambda orchestrates safe read-modify-write cycles and validates inputs.

## Data Contract

Incoming event matches API Gateway proxy integration shape:

- `event.body`: stringified JSON payload (may be base64-encoded when `event.isBase64Encoded` is true)
- `event.headers` (optional): not required for core logic
- `context.aws_request_id` (from Lambda context): used in logs

Payload (JSON) must contain:

- `appName` (string): application identifier; used as the top-level S3 prefix
- `ops` (array): ordered list of operations to apply

Optional fields:

- `createIfMissing` (boolean, default `true`): if `stats.json` does not exist, start from `{}`
- `dryRun` (boolean, default `false`): apply operations in-memory and return result without writing to S3
- `ifMatchEtag` (string, optional): optimistic concurrency control; if provided and differs from current ETag, abort

Example request body:

```json
{
  "appName": "zoo_landing_page",
  "ops": [
    { "op": "inc", "path": "totals.pageViews", "by": 1 },
    { "op": "set", "path": "lastVisit.timestamp", "value": 1725148800000 },
    { "op": "merge", "path": "countries", "value": { "MX": 10, "US": 3 } },
    { "op": "append", "path": "recentEvents", "value": { "name": "page_view", "t": 1725148800000 } }
  ]
}
```

Notes:

- Paths use dot-notation, e.g., `a.b.c` to refer to nested objects. Array indices are supported for numeric segments (e.g., `items.0`).
- If a parent path does not exist for `set`, `merge`, or `inc`, intermediate objects are created automatically.
- `inc` will treat a missing target as `0` and then add the specified `by` amount (defaults to `1`).

## Operations Spec

Supported operation objects inside `ops`:

- `{"op": "set", "path": "a.b.c", "value": any}`
  - Sets the value at `path` to `value` (creates parents as needed)
- `{"op": "inc", "path": "a.b.counter", "by": number}`
  - Increments numeric value at `path` by `by` (default `1`). If missing, initializes to `0` first
- `{"op": "delete", "path": "a.b.c"}`
  - Deletes the key or array element at `path` (no-op if path missing)
- `{"op": "merge", "path": "a.b", "value": object}`
  - Deep-merges `value` object into the object at `path` (creates object if missing). Non-object at target will be replaced by `value`
- `{"op": "append", "path": "a.list", "value": any}`
  - Appends `value` to an array at `path`. If missing, initializes `[]`. If target is not an array, it becomes `[oldValue, value]`

Rejected operations (400): unknown `op`, missing `path` (except where noted), invalid types for specific ops (e.g., `by` must be numeric for `inc`, `value` must be object for `merge`).

## S3 Object Layout

- Bucket: `zoolanding-quick-stats` (configurable via env var `STATS_BUCKET_NAME`)
- Key: `appName/stats.json`
  - Example: `zoo_landing_page/stats.json`

## Validation Rules

Reject the request with HTTP 400 if any is true:

- `event.body` is missing or empty
- JSON parse fails (invalid JSON)
- `appName` missing or not a non-empty string
- `ops` missing or not an array (can be empty; empty means no change/read-only fetch)
- At least one op is invalid (unknown `op`, missing required fields, invalid types)

Edge handling:

- If `stats.json` is missing and `createIfMissing !== false`, start from `{}`. If `createIfMissing` is `false`, return 404-like error (use 400 with message `Stats file not found`)
- If `dryRun` is `true`, do not write to S3; return the would-be result

## Response Contract

- Success (200):

  ```json
  {
    "ok": true,
    "bucket": "zoolanding-quick-stats",
    "key": "zoo_landing_page/stats.json",
    "stats": { },
    "etag": "\"abc123...\"",
    "versionId": "null-or-version-id-if-enabled",
    "dryRun": false
  }
  ```

- Client error (400):

  ```json
  { "ok": false, "error": "<message>" }
  ```

- Server error (500):

  ```json
  { "ok": false, "error": "Internal error" }
  ```

## IAM Requirements

Lambda execution role must allow:

- `s3:GetObject`, `s3:PutObject` on `arn:aws:s3:::zoolanding-quick-stats/*`
- If bucket enforces KMS encryption: `kms:Encrypt`, `kms:Decrypt`, `kms:GenerateDataKey` for the bucket’s CMK

No other AWS services required.

## Configuration

- Env vars:
	- `STATS_BUCKET_NAME` (optional): defaults to `zoolanding-quick-stats`
	- `LOG_LEVEL` (optional): `INFO` (default), `DEBUG`, or `ERROR`
	- `JSON_INDENT` (optional): integer or empty; when set, pretty-prints output JSON for readability (defaults to compact)
	- `MAX_RETRIES` (optional): number of times to retry read-modify-write on transient S3 errors (default 2)
	- `ALLOW_EMPTY_OPS` (optional): when true, returning the current stats without changes is allowed (default true)
- Timeout: 10 seconds is plenty
- Memory: 128–256 MB

## Logging

Use JSON-structured logs to CloudWatch with at least:

- `level`, `message`, `requestId`, `appName`, `bucket`, `key`, number of `ops`, `dryRun`, and error details on failure

## Concurrency Notes

S3 does not provide atomic read-modify-write for a single object without additional services. This implementation uses a simple last-writer-wins strategy with small retries. For stronger guarantees, consider enabling S3 Versioning and adding an optional optimistic concurrency field in requests (e.g., `ifMatchEtag`) to abort when the server-side ETag changed between read and write.

Behavior when `ifMatchEtag` is provided:

- If the current `HEAD` ETag of `stats.json` differs from `ifMatchEtag`, return 409-like conflict (use 400 with message `ETag mismatch, please retry`)

## Pseudocode

```text
def lambda_handler(event, context):
    request_id = (context.aws_request_id if context and getattr(context, 'aws_request_id', None) else '-')
    bucket = os.getenv('STATS_BUCKET_NAME', 'zoolanding-quick-stats')

    # 1) Get body (handle base64)
    body_str = event.get('body')
    if not body_str:
        return http_400('Missing body')
    if event.get('isBase64Encoded'):
        body_str = base64.b64decode(body_str).decode('utf-8')

    # 2) Parse JSON
    try:
        payload = json.loads(body_str)
    except Exception:
        return http_400('Body is not valid JSON')

    # 3) Validate
    app = payload.get('appName')
    ops = payload.get('ops', [])
    create_if_missing = payload.get('createIfMissing', True)
    dry_run = bool(payload.get('dryRun', False))
    if not isinstance(app, str) or not app.strip():
        return http_400('Missing or invalid appName')
    if not isinstance(ops, list):
        return http_400('Missing or invalid ops (must be array)')

    key = f"{app}/stats.json"

    # 4) Load existing stats (or initialize)
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
        etag = head.get('ETag')
        obj = s3.get_object(Bucket=bucket, Key=key)
        raw = obj['Body'].read().decode('utf-8')
        stats = json.loads(raw) if raw.strip() else {}
    except NoSuchKey:
        if not create_if_missing:
            return http_400('Stats file not found')
        stats, etag = {}, None
    except Exception as e:
        # if 404, treat as missing
        code = getattr(e, 'response', {}).get('Error', {}).get('Code')
        if code in ('404', 'NoSuchKey'):
            if not create_if_missing:
                return http_400('Stats file not found')
            stats, etag = {}, None
        else:
            return http_500()

    # 5) Optional optimistic concurrency
    if 'ifMatchEtag' in payload:
        if etag and payload['ifMatchEtag'] != etag:
            return http_400('ETag mismatch, please retry')

    # 6) Validate and apply ops in order
    try:
        for op in ops:
            apply_op(stats, op)  # handles set/inc/delete/merge/append and validation
    except ValidationError as ve:
        return http_400(str(ve))
    except Exception:
        return http_500()

    # 7) Write back unless dryRun
    if dry_run:
        return http_200({ 'ok': True, 'bucket': bucket, 'key': key, 'stats': stats, 'etag': etag, 'dryRun': True })

    payload_bytes = json.dumps(stats, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    put = s3.put_object(Bucket=bucket, Key=key, Body=payload_bytes, ContentType='application/json', CacheControl='no-cache')
    return http_200({ 'ok': True, 'bucket': bucket, 'key': key, 'stats': stats, 'etag': put.get('ETag'), 'versionId': put.get('VersionId'), 'dryRun': False })
```

Helper behavior (`apply_op`):

- Resolve `path` into the nested structure using dot-notation
- For `merge`, ensure both sides are objects; perform deep, key-wise merge
- For `append`, ensure target is array; if not present, initialize `[]`
- For `inc`, ensure numeric; use `0` when missing
- For `delete`, remove key or pop array index if numeric last segment

## Example API Gateway Test Events

Increment counters and set last visit:

```json
{
  "resource": "/",
  "path": "/stats",
  "httpMethod": "POST",
  "headers": { "Content-Type": "application/json" },
  "isBase64Encoded": false,
  "body": "{\n  \"appName\": \"zoo_landing_page\",\n  \"ops\": [\n    { \"op\": \"inc\", \"path\": \"totals.pageViews\" },\n    { \"op\": \"set\", \"path\": \"lastVisit.ts\", \"value\": 1725148800000 }\n  ]\n}"
}
```

Fetch-only (no changes):

```json
{
  "isBase64Encoded": false,
  "body": "{\"appName\":\"zoo_landing_page\",\"ops\":[]}"
}
```

## Local Smoke Test (without AWS)

You can invoke the handler locally to validate parsing and operation behavior. This won’t reach S3 unless you have AWS creds and network.

Python snippet:

```python
from lambda_function import lambda_handler

event = {
  "isBase64Encoded": False,
  "body": "{\"appName\":\"zoo_landing_page\",\"ops\":[{\"op\":\"inc\",\"path\":\"totals.visits\",\"by\":2}]}"
}

class Ctx: aws_request_id = "12345678-aaaa-bbbb-cccc-1234567890ab"

print(lambda_handler(event, Ctx()))
```

## Deployment Notes

- Zip upload or IaC (SAM/Serverless/Terraform); no third-party libs needed
- Runtime: Python 3.13
- Handler: `lambda_function.lambda_handler`
- Env var (optional): set `STATS_BUCKET_NAME=zoolanding-quick-stats` to be explicit
- S3 Versioning is optional but recommended for recovery/auditing

## Acceptance Criteria (Definition of Done)

- [ ] Valid requests return 200 with `{ ok: true, bucket, key, stats, etag }` (include `versionId` when available)
- [ ] Invalid requests return 400 with a clear error message
- [ ] Key layout is exactly `appName/stats.json`
- [ ] When file is missing and `createIfMissing` is true (default), initialize from `{}`
- [ ] Supported ops work as specified: set, inc, delete, merge, append
- [ ] `dryRun` returns computed result without writing to S3
- [ ] Logs include requestId, appName, bucket, key, ops count, and outcome
- [ ] No external dependencies beyond AWS SDK included in runtime

## Nice-to-haves (Optional)

- Optimistic concurrency: allow client to pass `ifMatchEtag` to detect concurrent updates (returns 409-like error)
- Audit trail: write a compact diff or append-only log to `appName/audit/YYYY/MM/DD/...` alongside the primary `stats.json`
- Schema hints: allow a `schema` object to validate and coerce certain fields (numbers, arrays)
- Compression: set `ContentEncoding: gzip` if you decide to store a compressed `stats.json`
- Partial reads: allow a `select` list of paths to return only parts of the document for bandwidth savings

---

Implement the function in `lambda_function.py` according to this guide. If anything is unclear, prefer explicit validation and returning 400 rather than guessing.
