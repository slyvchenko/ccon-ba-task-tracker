import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from model_analysis import (model_settings, request_analysis, approved_prompts,
                            sanitize_source, extract_adf_links, sprint_cache_version,
                            analyze_all)
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
    def test_named_adf_hyperlinks_are_available_without_raw_adf(self):
        value = {
            "description": "Read Supplier spec",
            "descriptionAdf": {"type": "doc", "content": [
                {"type": "text", "text": "Supplier spec",
                 "marks": [{"type": "link", "attrs": {
                     "href": "https://supplier.example/spec?token=SECRET999#fragment"}}]},
                {"type": "inlineCard", "attrs": {"url": "https://jira.example/browse/CCON-123"}},
            ]},
            "comments": [{"body": "Refer to policy",
                          "bodyAdf": {"type": "doc", "content": [
                              {"type": "text", "text": "Policy",
                               "marks": [{"type": "link", "attrs": {
                                   "href": "https://policy.example/guide"}}]}]}}],
        }
        result = sanitize_source(value)
        encoded = json.dumps(result)
        self.assertNotIn("descriptionAdf\"", encoded)
        self.assertNotIn("bodyAdf\"", encoded)
        self.assertNotIn("SECRET999", encoded)
        self.assertIn("https://supplier.example/spec", encoded)
        self.assertIn("https://jira.example/browse/CCON-123", encoded)
        self.assertIn("https://policy.example/guide", encoded)
        self.assertEqual(result["descriptionAdfLinks"][0]["label"], "Supplier spec")
        self.assertEqual(extract_adf_links({"type": "doc", "content": []}), [])

    def test_json_quoted_and_escaped_secrets_are_redacted(self):
        samples = [
            '{"password": "superSecret123", "api_key": "veryPrivateKey456"}',
            r'{\"password\": \"superSecret123\", \"token\": \"anotherPrivate789\"}',
            "password=unquotedCredential01234",
        ]
        for sample in samples:
            with self.subTest(sample=sample[:15]):
                safe = sanitize_source({"description": sample})["description"]
                self.assertNotIn("superSecret123", safe)
                self.assertNotIn("veryPrivateKey456", safe)
                self.assertNotIn("anotherPrivate789", safe)
                self.assertNotIn("unquotedCredential01234", safe)
                self.assertIn("[REDACTED_CREDENTIAL]", safe)

    def test_sprint_membership_change_invalidates_cached_analysis(self):
        from desk_store import Desk
        from test_ba_briefing import briefing
        import hashlib
        with tempfile.TemporaryDirectory(prefix="ccon-sprint-cache-") as folder:
            root = Path(folder)
            (root / "data").mkdir()
            (root / "data/jira_context.json").write_text(json.dumps({
                "complete": True, "issues": {
                    "CCON-1": {"key": "CCON-1", "fingerprint": "fp1",
                               "comments": [], "links": []}}}))
            _, prompt_version = approved_prompts(root)
            sprint = {"active": True, "verification": "VERIFIED",
                      "names": ["Sprint A"]}
            analysis = {
                "signal": "READY", "queueScore": 0,
                "priorityFactors": {"businessImpact": 0, "urgency": 0,
                                    "dependencies": 0, "baDecision": 0,
                                    "actionability": 0},
                "briefing": briefing(), "contextFingerprint": "fp1",
                "promptVersion": prompt_version,
                "manualNoteVersion": hashlib.sha256(b"").hexdigest()[:16],
                "sprintVersion": sprint_cache_version({"sprint": sprint}),
            }
            snapshot_path = root / "inbox/CCON_BA_Snapshot.json"
            snapshot_path.parent.mkdir()
            task = {"key": "CCON-1", "summary": "Sample",
                    "contextFingerprint": "fp1", "analysis": analysis,
                    "activeSprint": True, "activeSprintStatus": "VERIFIED",
                    "activeSprintNames": ["Sprint A"]}
            document = {"generatedAt": "2026-10-24T09:00:00+00:00",
                        "complete": True, "tasks": [task]}
            snapshot_path.write_text(json.dumps(document))
            Desk(root).import_snapshot()
            calls = []
            def fake_model(*args):
                calls.append(True)
                return {"signal": "READY", "queueScore": 0,
                        "priorityFactors": analysis["priorityFactors"].copy(),
                        "briefing": briefing()}
            with patch("model_analysis.model_settings", return_value={"model": "fake"}):
                same = analyze_all(root, fake_model)
                self.assertEqual(same["reused"], 1)
                self.assertEqual(len(calls), 0)
                document["generatedAt"] = "2026-10-24T10:00:00+00:00"
                task["activeSprint"] = False
                task["activeSprintNames"] = []
                snapshot_path.write_text(json.dumps(document))
                Desk(root).import_snapshot()
                refreshed = analyze_all(root, fake_model)
            self.assertEqual(refreshed["generated"], 1)
            self.assertEqual(len(calls), 1)
            self.assertNotEqual(
                analysis["sprintVersion"], sprint_cache_version({
                    "sprint": {"active": False, "verification": "VERIFIED",
                               "names": []}}))

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
