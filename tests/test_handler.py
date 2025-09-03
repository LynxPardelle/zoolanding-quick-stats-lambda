import os
import sys
import json
import unittest

# Ensure DRY_RUN for local
os.environ.setdefault("DRY_RUN", "1")

# Ensure project root on sys.path
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import lambda_function as lf


class Ctx:
    aws_request_id = "abcd-efgh-ijkl-mnop-qrstuvwx"


class TestHandler(unittest.TestCase):
    def test_missing_body(self):
        res = lf.lambda_handler({}, Ctx())
        self.assertEqual(res["statusCode"], 400)

    def test_invalid_json(self):
        res = lf.lambda_handler({"body": "not-json", "isBase64Encoded": False}, Ctx())
        self.assertEqual(res["statusCode"], 400)

    def test_happy_path_empty_ops(self):
        body = {"appName": "app", "ops": []}
        res = lf.lambda_handler({"body": json.dumps(body), "isBase64Encoded": False}, Ctx())
        self.assertEqual(res["statusCode"], 200)
        payload = json.loads(res["body"])
        self.assertTrue(payload["ok"])  # fetch-only is allowed


if __name__ == "__main__":
    unittest.main()
