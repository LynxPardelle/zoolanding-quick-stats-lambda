import os
import json

# Ensure DRY_RUN is enabled before importing the handler so local runs don't need boto3
os.environ.setdefault("DRY_RUN", "1")

from lambda_function import lambda_handler


class Ctx:
    aws_request_id = "12345678-aaaa-bbbb-cccc-1234567890ab"


def main():
    event = {
        "isBase64Encoded": False,
        "body": json.dumps({
            "appName": "zoo_landing_page",
            "ops": [
                {"op": "inc", "path": "totals.visits", "by": 1},
                {"op": "merge", "path": "countries", "value": {"MX": 1}},
                {"op": "append", "path": "recent", "value": {"name": "page_view"}},
            ],
            "createIfMissing": True,
            "dryRun": True if os.getenv("DRY_RUN", "1") in {"1", "true", "TRUE"} else False,
        })
    }

    res = lambda_handler(event, Ctx())
    print("Status:", res.get("statusCode"))
    print("Body:", res.get("body"))


if __name__ == "__main__":
    main()
