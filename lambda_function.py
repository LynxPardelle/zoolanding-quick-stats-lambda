import os
import json
import base64
import traceback
from typing import Any, Dict, List, Tuple, Union

try:
    import boto3  # Provided in AWS Lambda runtime
    from botocore.exceptions import ClientError
except Exception:  # If not available locally
    boto3 = None
    ClientError = Exception  # type: ignore


# Globals / Config
S3 = None  # Lazy initialized
STATS_BUCKET_NAME = os.getenv("STATS_BUCKET_NAME", "zoolanding-quick-stats")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
DRY_RUN = os.getenv("DRY_RUN", "0") in {"1", "true", "TRUE", "yes", "YES"}


# -------- Logging & Responses -------- #
def _should_log(level: str) -> bool:
    order = {"DEBUG": 10, "INFO": 20, "ERROR": 40}
    return order.get(level, 20) >= order.get(LOG_LEVEL, 20)


def _log(level: str, message: str, **fields: Any) -> None:
    if not _should_log(level):
        return
    record = {"level": level, "message": message, **fields}
    try:
        print(json.dumps(record, ensure_ascii=False))
    except Exception:
        print({"level": level, "message": message, "_text": str(fields)})


def _json_response(status: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    }


def _bad_request(msg: str) -> Dict[str, Any]:
    return _json_response(400, {"ok": False, "error": msg})


def _server_error() -> Dict[str, Any]:
    return _json_response(500, {"ok": False, "error": "Internal error"})


def _get_request_id(context: Any) -> str:
    try:
        rid = getattr(context, "aws_request_id", None)
        if isinstance(rid, str) and rid:
            return rid
    except Exception:
        pass
    return "-"


# -------- Event parsing -------- #
def _decode_body(event: Dict[str, Any]) -> str:
    body = event.get("body")
    if body is None or body == "":
        raise ValueError("Missing body")
    if event.get("isBase64Encoded", False):
        if not isinstance(body, str):
            raise ValueError("Body is base64Encoded but not a string")
        return base64.b64decode(body).decode("utf-8")
    if isinstance(body, (bytes, bytearray)):
        return body.decode("utf-8")
    if isinstance(body, str):
        return body
    # Accept dict or other by re-serializing
    return json.dumps(body, ensure_ascii=False)


# -------- S3 helpers -------- #
def _get_s3_client():
    global S3
    if S3 is not None:
        return S3
    if DRY_RUN:
        _log("DEBUG", "DRY_RUN enabled; skipping S3 client init")
        return None
    if boto3 is None:
        _log("ERROR", "boto3 not available; cannot access S3 when DRY_RUN=0")
        raise RuntimeError("boto3 not available")
    S3 = boto3.client("s3")
    _log("DEBUG", "Initialized S3 client")
    return S3


def _s3_head(bucket: str, key: str) -> Tuple[Union[str, None], Dict[str, Any]]:
    if DRY_RUN:
        return None, {}
    s3 = _get_s3_client()
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
        return head.get("ETag"), head
    except ClientError as e:  # type: ignore
        code = str(getattr(e, "response", {}).get("Error", {}).get("Code"))
        if code in ("404", "NoSuchKey", "NotFound"):
            return None, {}
        raise


def _s3_get_json(bucket: str, key: str) -> Tuple[Dict[str, Any], Union[str, None]]:
    if DRY_RUN:
        return {}, None
    s3 = _get_s3_client()
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        raw = obj["Body"].read().decode("utf-8")
        if not raw.strip():
            return {}, obj.get("ETag")
        return json.loads(raw), obj.get("ETag")
    except ClientError as e:  # type: ignore
        code = str(getattr(e, "response", {}).get("Error", {}).get("Code"))
        if code in ("404", "NoSuchKey", "NotFound"):
            return {}, None
        raise


def _s3_put_json(bucket: str, key: str, data: Dict[str, Any]) -> Tuple[Union[str, None], Union[str, None]]:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if DRY_RUN:
        _log("INFO", "Dry-run: would PUT stats", bucket=bucket, key=key, size=len(payload))
        return None, None
    s3 = _get_s3_client()
    res = s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=payload,
        ContentType="application/json",
        CacheControl="no-cache",
    )
    return res.get("ETag"), res.get("VersionId")


# -------- Path utilities -------- #
def _split_path(path: str) -> List[str]:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Missing or invalid path")
    return [seg for seg in path.strip().split(".") if seg != ""]


def _is_int_like(s: str) -> bool:
    try:
        int(s)
        return True
    except Exception:
        return False


def _get_parent_and_key(root: Any, segments: List[str], create: bool = True) -> Tuple[Any, Union[str, int]]:
    """Traverse to the parent container of the final segment.
    Returns (parent, last_key_or_index). Creates intermediate dicts/lists when create=True.
    """
    if not segments:
        raise ValueError("Path cannot be empty")
    curr = root
    for i, seg in enumerate(segments[:-1]):
        next_is_index = _is_int_like(segments[i + 1])
        # Decide container we need for this segment: dict key or list index
        if _is_int_like(seg):
            idx = int(seg)
            if not isinstance(curr, list):
                if not create:
                    raise KeyError("Parent is not a list")
                # Convert non-list into list (wrap if has value)
                curr_list = []
                # If prior was dict with this seg as numeric key, treat as list anyway
                curr = curr_list
            # Ensure list large enough
            while len(curr) <= idx:
                curr.append({} if next_is_index or not create else None)
            if curr[idx] is None and create:
                curr[idx] = {} if next_is_index else {}
            curr = curr[idx]
        else:
            # seg is dict key
            if not isinstance(curr, dict):
                if not create:
                    raise KeyError("Parent is not an object")
                # Convert non-dict into dict
                curr = {}
            if seg not in curr or curr[seg] is None:
                if create:
                    curr[seg] = [] if next_is_index else {}
                else:
                    raise KeyError("Path segment not found")
            curr = curr[seg]

    last = segments[-1]
    return curr, int(last) if _is_int_like(last) else last


def _deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in src.items():
        if k in dst and isinstance(dst[k], dict) and isinstance(v, dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


class ValidationError(Exception):
    pass


def _apply_op(doc: Dict[str, Any], op: Dict[str, Any]) -> None:
    if not isinstance(op, dict):
        raise ValidationError("Each op must be an object")
    kind = op.get("op")
    path = op.get("path")
    if kind not in {"set", "inc", "delete", "merge", "append"}:
        raise ValidationError(f"Unknown op: {kind}")
    if kind != "append" and (not isinstance(path, str) or not path.strip()):
        # append still needs a path
        if not isinstance(path, str) or not path.strip():
            raise ValidationError("Missing or invalid path")

    segments = _split_path(path)
    parent, last = _get_parent_and_key(doc, segments, create=True)

    # Helpers to read/write at final location
    def get_current():
        if isinstance(parent, dict):
            return parent.get(last)  # type: ignore[index]
        elif isinstance(parent, list):
            idx = int(last)  # type: ignore[arg-type]
            return parent[idx] if 0 <= idx < len(parent) else None
        else:
            return None

    def set_current(value):
        if isinstance(parent, dict):
            parent[last] = value  # type: ignore[index]
        elif isinstance(parent, list):
            idx = int(last)  # type: ignore[arg-type]
            while len(parent) <= idx:
                parent.append(None)
            parent[idx] = value
        else:
            raise ValidationError("Cannot set value at path; parent is not a container")

    if kind == "set":
        if "value" not in op:
            raise ValidationError("set op requires 'value'")
        set_current(op.get("value"))
        return

    if kind == "inc":
        by = op.get("by", 1)
        if not isinstance(by, (int, float)):
            raise ValidationError("inc 'by' must be a number")
        curr = get_current()
        if curr is None:
            curr = 0
        if not isinstance(curr, (int, float)):
            raise ValidationError("inc target is not numeric")
        set_current(curr + by)
        return

    if kind == "delete":
        if isinstance(parent, dict):
            parent.pop(last, None)  # type: ignore[index]
        elif isinstance(parent, list):
            idx = int(last)  # type: ignore[arg-type]
            if 0 <= idx < len(parent):
                parent.pop(idx)
        return

    if kind == "merge":
        value = op.get("value")
        if not isinstance(value, dict):
            raise ValidationError("merge 'value' must be an object")
        curr = get_current()
        if not isinstance(curr, dict):
            curr = {}
        set_current(_deep_merge(curr, value))
        return

    if kind == "append":
        value = op.get("value")
        curr = get_current()
        if curr is None:
            curr = []
        if not isinstance(curr, list):
            curr = [curr]
        curr.append(value)
        set_current(curr)
        return


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    request_id = _get_request_id(context)
    try:
        body_str = _decode_body(event)
        _log("DEBUG", "Decoded body", requestId=request_id, decodedLen=len(body_str))
    except Exception as e:
        _log("ERROR", "Failed to decode body", requestId=request_id, error=str(e))
        return _bad_request(str(e))

    # Parse JSON
    try:
        payload = json.loads(body_str)
    except Exception as e:
        _log("ERROR", "Body is not valid JSON", requestId=request_id, error=str(e))
        return _bad_request("Body is not valid JSON")

    app = payload.get("appName")
    ops = payload.get("ops", [])
    create_if_missing = payload.get("createIfMissing", True)
    dry_run = bool(payload.get("dryRun", False))
    if not isinstance(app, str) or not app.strip():
        return _bad_request("Missing or invalid appName")
    if not isinstance(ops, list):
        return _bad_request("Missing or invalid ops (must be array)")

    key = f"{app}/stats.json"

    # Read current stats
    try:
        current_etag, _ = _s3_head(STATS_BUCKET_NAME, key)
        stats, etag_from_get = _s3_get_json(STATS_BUCKET_NAME, key)
        # Prefer explicit head etag; otherwise use get etag
        etag = current_etag or etag_from_get
    except Exception as e:
        _log("ERROR", "Failed to read stats", requestId=request_id, bucket=STATS_BUCKET_NAME, key=key, error=str(e), stack=traceback.format_exc())
        # If truly not found, s3 helpers return empty {}
        stats, etag = {}, None

    if not stats and not create_if_missing:
        return _bad_request("Stats file not found")

    # Optional optimistic concurrency
    if "ifMatchEtag" in payload:
        req_etag = payload.get("ifMatchEtag")
        if etag and req_etag != etag:
            return _bad_request("ETag mismatch, please retry")

    # Apply operations in order
    try:
        for op in ops:
            _apply_op(stats, op)
    except ValidationError as ve:
        return _bad_request(str(ve))
    except Exception as ex:
        _log("ERROR", "Failed while applying ops", requestId=request_id, error=str(ex), stack=traceback.format_exc())
        return _server_error()

    # Write back unless dryRun or DRY_RUN env
    if dry_run or DRY_RUN:
        _log("INFO", "Dry run result", requestId=request_id, appName=app, bucket=STATS_BUCKET_NAME, key=key, ops=len(ops), dryRun=True)
        return _json_response(200, {
            "ok": True,
            "bucket": STATS_BUCKET_NAME,
            "key": key,
            "stats": stats,
            "etag": etag,
            "dryRun": True
        })

    try:
        new_etag, version_id = _s3_put_json(STATS_BUCKET_NAME, key, stats)
    except Exception as e:
        _log("ERROR", "Failed to write stats", requestId=request_id, bucket=STATS_BUCKET_NAME, key=key, error=str(e), stack=traceback.format_exc())
        return _server_error()

    _log("INFO", "Updated stats", requestId=request_id, appName=app, bucket=STATS_BUCKET_NAME, key=key, etag=new_etag, ops=len(ops))
    return _json_response(200, {
        "ok": True,
        "bucket": STATS_BUCKET_NAME,
        "key": key,
        "stats": stats,
        "etag": new_etag,
        "versionId": version_id,
        "dryRun": False,
    })
