# Zoolanding Quick Stats Lambda

An AWS Lambda that reads and updates a per-app `stats.json` file in S3 based on a sequence of operations sent via API Gateway.

- Runtime: Python 3.13 (or 3.11+). In AWS, `boto3` is available by default.
- Handler: `lambda_function.lambda_handler`
- Target bucket: `zoolanding-quick-stats` (configurable via env var `STATS_BUCKET_NAME`)

## Where this fits in Zoolanding

This Lambda is the lightweight stats backend for the Zoolanding frontend platform.

- The Angular app sends `POST` requests to `environment.apiUrl + /quick-stats`.
- The frontend service boundary lives in `../zoolandingpage/src/app/shared/services/quick-stats.service.ts`.
- Runtime analytics and event ownership are configured from the frontend payload/runtime layer, not from this repo.
- Platform architecture and frontend integration context are documented in `../zoolandingpage/docs/02-architecture.md` and `../zoolandingpage/docs/09-quick-stats-lambda.md`.

This repository documents the Lambda itself. The main frontend repo is the source of truth for cross-platform behavior.

## How it works

- Expects an API Gateway–like event with a JSON string in `event.body`:
  - Required: `appName` (string), `ops` (array of operation objects)
  - Optional: `createIfMissing` (default `true`), `dryRun` (default `false`), `ifMatchEtag` (optimistic concurrency)
- Loads `appName/stats.json` from S3 (or `{}` if missing and `createIfMissing` is true)
- Applies operations in order:
  - `set`, `inc`, `delete`, `merge`, `append`
- Writes the updated document back to S3 (unless `dryRun`)
- Returns the full updated `stats` object and metadata

See `instructions.md` for the complete contract and acceptance criteria.

## Quick start (local)

- Optional: install boto3 locally if you want to actually hit S3.

```powershell
# Optionally create a venv
python -m venv .venv
. .venv/Scripts/Activate.ps1

# Optional: install boto3 for local S3 testing
pip install boto3 botocore
```

- Run the local harness with a sample event. By default, uploads are disabled via `DRY_RUN=1`.

```powershell
$env:DRY_RUN = "1"
python .\local_test.py
```

- To perform a real update locally (requires configured AWS credentials), set your bucket name explicitly:

```powershell
$env:DRY_RUN = "0"
$env:STATS_BUCKET_NAME = "zoolanding-quick-stats"
python .\local_test.py
```

## Deploy

- Zip and upload (no external deps needed), or use your preferred IaC (SAM/Serverless/Terraform).
- AWS console settings:
  - Runtime: Python 3.13 (or 3.11)
  - Handler: `lambda_function.lambda_handler`
  - Env vars (optional): `STATS_BUCKET_NAME`, `LOG_LEVEL`
  - Role policy must include `s3:GetObject` and `s3:PutObject` on `arn:aws:s3:::<bucket>/*`

### Deploy with AWS SAM (recommended)

For repeatable deployments from this repository:

```bash
sam deploy
```

The checked-in `samconfig.toml` already targets `us-east-1` with the correct stack name and parameter overrides.

The equivalent first non-interactive deployment command is:

```bash
sam deploy --stack-name zoolanding-quick-stats --region us-east-1 --capabilities CAPABILITY_IAM --resolve-s3 --no-confirm-changeset --no-fail-on-empty-changeset --parameter-overrides StatsBucketName=zoolanding-quick-stats LogLevel=INFO
```

This template now exposes:

- `POST /quick-stats`
- CORS preflight for `POST,OPTIONS`
- output `ApiUrl` for the deployed endpoint

## Environment variables

- `STATS_BUCKET_NAME` (default: `zoolanding-quick-stats`)
- `LOG_LEVEL` = `DEBUG` | `INFO` | `ERROR` (default: `INFO`)
- `DRY_RUN` = `1` to skip actual S3 writes (handy for local dev; ignored in production requests with `dryRun=false`)

## Troubleshooting

- ImportError: boto3 could not be resolved
  - In AWS: safe to ignore during deployment.
  - Locally: `pip install boto3 botocore` or keep `DRY_RUN=1` to avoid S3 calls.
- 400 responses:
  - Ensure `event.body` is a valid JSON string and contains `appName` (string) and `ops` (array).
- Optimistic concurrency failures:
  - If you pass `ifMatchEtag` and the server’s current ETag differs, you’ll get `ETag mismatch, please retry`.
- Read-only fetches:
  - An empty `ops` array is valid and returns the current `stats` document without changing it.

## CI

GitHub Actions workflow `.github/workflows/ci.yml` runs unit tests on push/PR to `main` using Python 3.12 with `DRY_RUN=1`.

---

All specs live in `instructions.md`.
