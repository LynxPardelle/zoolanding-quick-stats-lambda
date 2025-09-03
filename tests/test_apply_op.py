import os
import sys
import unittest

# Ensure no S3 calls are made
os.environ.setdefault("DRY_RUN", "1")

# Ensure project root is on sys.path
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import lambda_function as lf


class TestApplyOp(unittest.TestCase):
    def setUp(self):
        self.doc = {}

    def test_set_creates_parents(self):
        lf._apply_op(self.doc, {"op": "set", "path": "a.b.c", "value": 123})
        self.assertEqual(self.doc["a"]["b"]["c"], 123)

    def test_inc_default_and_by(self):
        lf._apply_op(self.doc, {"op": "inc", "path": "totals.visits"})
        self.assertEqual(self.doc["totals"]["visits"], 1)
        lf._apply_op(self.doc, {"op": "inc", "path": "totals.visits", "by": 3})
        self.assertEqual(self.doc["totals"]["visits"], 4)

    def test_inc_non_numeric_raises(self):
        lf._apply_op(self.doc, {"op": "set", "path": "x", "value": "not-a-number"})
        with self.assertRaises(lf.ValidationError):
            lf._apply_op(self.doc, {"op": "inc", "path": "x"})

    def test_delete_key_and_index(self):
        lf._apply_op(self.doc, {"op": "set", "path": "k1", "value": 1})
        lf._apply_op(self.doc, {"op": "delete", "path": "k1"})
        self.assertNotIn("k1", self.doc)

        # delete index in list
        lf._apply_op(self.doc, {"op": "append", "path": "arr", "value": 10})
        lf._apply_op(self.doc, {"op": "append", "path": "arr", "value": 20})
        lf._apply_op(self.doc, {"op": "delete", "path": "arr.0"})
        self.assertEqual(self.doc["arr"], [20])

    def test_merge_deep(self):
        lf._apply_op(self.doc, {"op": "set", "path": "obj", "value": {"a": {"x": 1}}})
        lf._apply_op(self.doc, {"op": "merge", "path": "obj", "value": {"a": {"y": 2}, "b": 3}})
        self.assertEqual(self.doc["obj"], {"a": {"x": 1, "y": 2}, "b": 3})

    def test_append_initializes_array(self):
        lf._apply_op(self.doc, {"op": "append", "path": "items", "value": "a"})
        lf._apply_op(self.doc, {"op": "append", "path": "items", "value": "b"})
        self.assertEqual(self.doc["items"], ["a", "b"])

    def test_numeric_path_builds_arrays(self):
        lf._apply_op(self.doc, {"op": "set", "path": "list.0.value", "value": 42})
        self.assertIsInstance(self.doc["list"], list)
        self.assertEqual(self.doc["list"][0]["value"], 42)


if __name__ == "__main__":
    unittest.main()
