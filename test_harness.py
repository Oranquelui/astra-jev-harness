import copy
import unittest
from unittest.mock import patch
import urllib.error

import harness as h
from fixtures import CASES


def reply(values):
    return {"model": "jev-1.13.0", "usage": {"input_tokens": 123, "output_tokens": 4},
            "answers": {f"f{i}": {"type": "noul", "noul": v} for i, v in enumerate(values)}}


class SelectionTests(unittest.TestCase):
    def test_selects_relevant_files_without_using_answer_key(self):
        files = {"a.py": "a", "b.py": "b", "c.py": "c"}
        result = h.select_context(files, reply([.95, .05, .9]))
        self.assertEqual(result["paths"], ["a.py", "c.py"])
        request = h.jev_request(CASES[0])
        self.assertNotIn("tests", request["state"])
        self.assertNotIn("required", request["state"])
        self.assertNotIn("solution", request["state"])

    def test_uncertainty_preserves_all_context(self):
        files = {"a.py": "a", "b.py": "b"}
        for values in [[.95, .5], [.05, .05]]:
            self.assertEqual(h.select_context(files, reply(values))["paths"], list(files))

    def test_invalid_or_incomplete_answers_are_rejected(self):
        for values in [[1.1, 0], [float("nan"), 0], [True, 0], [.9]]:
            with self.assertRaises(h.ProtocolError):
                h.select_context({"a.py": "a", "b.py": "b"}, reply(values))

    def test_malformed_containers_are_rejected(self):
        for response in [[], {"answers": []}, {"answers": {"f0": None}}]:
            with self.assertRaises(h.ProtocolError):
                h.select_context({"a.py": "a"}, response)

    def test_auth_failure_does_not_leak_key_or_retry(self):
        with patch.dict(h.os.environ, {"TYPESAFE_API_KEY": "fixture-secret"}), patch.object(h.urllib.request, "build_opener") as make:
            make.return_value.open.side_effect = urllib.error.HTTPError("https://api.typesafe.ai", 401, "fixture-secret", {}, None)
            with self.assertRaises(h.ProtocolError) as raised:
                h.call_jev(CASES[0])
            self.assertNotIn("fixture-secret", str(raised.exception))
            self.assertIn("401", str(raised.exception))
            self.assertEqual(make.return_value.open.call_count, 1)

    def test_redirect_is_refused(self):
        with self.assertRaises(h.ProtocolError):
            h.NoRedirect().redirect_request(None, None, 302, "", {}, "https://another.example")


class CodingTests(unittest.TestCase):
    def test_originals_fail_and_reference_fixes_pass(self):
        for case in CASES:
            with self.subTest(case=case["id"]):
                self.assertFalse(h.evaluate(case, {"files": []})["passed"])
                fixed = {"files": [{"path": k, "content": v} for k, v in case["solution"].items()]}
                self.assertTrue(h.evaluate(case, fixed)["passed"])

    def test_patch_cannot_escape_or_add_unknown_files(self):
        for path in ["../secret.py", "/tmp/secret.py", "new.py"]:
            with self.assertRaises(h.ProtocolError):
                h.validate_patch({"files": [{"path": path, "content": ""}]}, CASES[0]["files"])

    def test_generated_code_cannot_import_or_access_runtime(self):
        for source in ["import os", "x = open('x')", "x = ().__class__", "while True: pass"]:
            with self.assertRaises(h.ProtocolError):
                h.check_pure_source(source)


class AccountingTests(unittest.TestCase):
    def test_missing_usage_is_unknown_not_zero(self):
        self.assertIsNone(h.parse_codex_events('{"type":"thread.started"}')["usage"])

    def test_failed_run_and_tool_use_are_detected(self):
        result = h.parse_codex_events('\n'.join([
            '{"type":"item.completed","item":{"type":"command_execution"}}',
            '{"type":"turn.failed","error":{"message":"failure"}}']))
        self.assertTrue(result["contaminated"])
        self.assertTrue(result["failed"])

    def test_nonzero_usage_survives_event_parse(self):
        usage = {"input_tokens": 100, "cached_input_tokens": 60, "output_tokens": 10}
        import json
        result = h.parse_codex_events(json.dumps({"type": "turn.completed", "usage": usage}))
        self.assertEqual(result["usage"], usage)

    def test_context_warning_is_preserved_without_claiming_generation_failed(self):
        result = h.parse_codex_events('{"type":"item.completed","item":{"type":"error","message":"context budget"}}')
        self.assertEqual(result["runtime_warnings"], ["context budget"])
        self.assertFalse(result["failed"])


if __name__ == "__main__":
    unittest.main()
