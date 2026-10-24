import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from model_analysis import model_settings, request_analysis, approved_prompts, sanitize_source
from run_daily import run
from cloud_scheduler import eligible, scheduler_iteration, WARSAW


class ModelAndSchedulerTests(unittest.TestCase):
    def test_provider_requires_explicit_company_approval(self):
        data = {
            "CCON_LLM_ENDPOINT": "https://llm.example.org/v1/chat/completions",
            "CCON_LLM_APPROVED_HOST": "llm.example.org",
            "CCON_LLM_MODEL": "approved-model",
            "CCON_LLM_API_KEY": "test-only-not-a-real-key",
        }
        with self.assertRaisesRegex(ValueError, "approval"):
            model_settings(data)
        data["CCON_ALLOW_CORPORATE_AI_UPLOAD"] = "YES"
        self.assertEqual(model_settings(data)["host"], "llm.example.org")
        for invalid in ("http://llm.example.org/v1/chat/completions",
                        "https://evil.example.org/v1/chat/completions",
                        "https://llm.example.org@evil.example.org/v1/chat/completions"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                model_settings({**data, "CCON_LLM_ENDPOINT": invalid})

    def test_invalid_model_response_rejected_without_import(self):
        settings = {
            "endpoint": "https://llm.example.org/v1/chat/completions",
            "model": "test", "key": "testing",
        }
        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, n):
                return json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode()
        calls = []
        def opener(req, timeout):
            calls.append(req)
            return FakeResponse()
        with self.assertRaisesRegex(ValueError, "analysis object|invalid JSON|missing required"):
            request_analysis(settings, "rules", {"issue": {"key": "CCON-1"}},
                             opener=opener)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].get_method(), "POST")

    def test_model_source_strips_common_credentials_and_duplicate_raw_adf(self):
        original = {
            'issue': {'summary': 'NDC workflow', 'description':
                      'Authorization: Bearer abcdefghijklmnop and password=abcdef123456',
                      'descriptionAdf': {'secret': 'should-not-be-sent'},
                      'reporter': {'emailAddress': 'person@example.test'},
                      'comments': [{'body': 'API_KEY: testsecret12345678'}],
                      'attachments': [{'content': 'https://jira/private_attachment'}]},
        }
        filtered = sanitize_source(original)
        dump = json.dumps(filtered)
        self.assertNotIn('abcdefghijklmnop', dump)
        self.assertNotIn('abcdef123456', dump)
        self.assertNotIn('testsecret12345678', dump)
        self.assertNotIn('person@example.test', dump)
        self.assertNotIn('descriptionAdf', dump)
        self.assertNotIn('private_attachment', dump)
        self.assertEqual(filtered['issue']['summary'], 'NDC workflow')
    def test_cloud_runner_fails_before_network_for_missing_analyst(self):
        with patch.dict(os.environ, {"CCON_CLOUD_MODE": "1",
                                     "CCON_JIRA_ASSIGNEE_ACCOUNT_ID": "",
                                     "CCON_ALLOW_CORPORATE_AI_UPLOAD": "YES"}):
            calls = []
            def fake_sync(root):
                calls.append("jira")
            with self.assertRaisesRegex(ValueError, "ASSIGNEE_ACCOUNT_ID"):
                run(Path("/tmp/unused"), jira_sync=fake_sync)
            self.assertEqual(calls, [])

    def test_daily_schedule_uses_warsaw_calendar_and_success_receipts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clock = datetime(2026, 10, 25, 8, 4, tzinfo=WARSAW)
            completed = []
            def fake_worker(root):
                completed.append("run")
                return {"analysis": {"promptVersion": "x1", "total": 4}}
            result = scheduler_iteration(root, clock, fake_worker)
            self.assertTrue(result["executed"])
            self.assertFalse(scheduler_iteration(root, clock, fake_worker)["executed"])
            self.assertEqual(completed, ["run"])
            self.assertFalse(eligible(datetime(2026, 10, 26, 7, 59, tzinfo=WARSAW),
                                      json.loads((root / "data/last_daily_success.json").read_text())))
            self.assertTrue(eligible(datetime(2026, 10, 26, 8, 0, tzinfo=WARSAW),
                                     json.loads((root / "data/last_daily_success.json").read_text())))

    def test_failed_daily_run_does_not_claim_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def fail(root):
                raise ValueError("provider missing")
            with self.assertRaises(ValueError):
                scheduler_iteration(root, datetime(2026, 10, 25, 8, 0, tzinfo=WARSAW), fail)
            self.assertFalse((root / "data/last_daily_success.json").exists())
            attempt = json.loads((root / "data/last_daily_attempt.json").read_text())
            self.assertEqual(attempt["status"], "FAILED")
            self.assertEqual(attempt["errorType"], "ValueError")
            self.assertNotIn("provider missing", json.dumps(attempt))


if __name__ == "__main__":
    unittest.main()
