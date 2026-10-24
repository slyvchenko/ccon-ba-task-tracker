"""Regression coverage for actionable PR #2–#5 review comments."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from ba_briefing import validate_briefing
from desk_store import Desk
from evaluation import prepare
from jira_sync import sync
from model_analysis import approved_prompts
from prompt_calibration import update_daily
from review_report import (
    build_report, diagnostics, validate_report, write_report, REPORT_LIMIT,
)
from test_jira_sync import FakeJira
from zoneinfo import ZoneInfoNotFoundError


def analyzed(key, desc, signal="READY", **fields):
    analysis = {
        "signal": signal,
        "nextActionUk": "Перевірити TypeCode",
        "contextFingerprint": "fp1",
        "evidence": [{"text": "Jira evidence", "url": "https://jira.example/CCON-1"}],
        "missingInfo": [],
        "waitingRequired": signal == "WAIT",
        "needsEmail": signal == "WRITE",
        "standardDescription": desc,
        "emailDraft": {"to": "", "subject": "", "body": ""},
    }
    analysis.update(fields)
    return {"key": key, "summary": "Sample", "active": True,
            "contextFingerprint": "fp1", "analysis": analysis}


class ReviewFeedbackRegressions(unittest.TestCase):
    def test_case_sensitive_api_and_mail_changes_are_not_hidden(self):
        previous = analyzed("CCON-1", "Use TypeCode")
        current = analyzed("CCON-1", "Use typeCode")
        result = build_report({"CCON-1": previous}, [current], "2026-10-24T17:30:00Z")
        self.assertEqual(result["summary"]["UPDATED"], 1)
        self.assertIn("standardDescription", result["changes"][0]["changedFields"])
        current = analyzed("CCON-1", "Use TypeCode")
        current["analysis"]["emailDraft"]["body"] = "Pass TypeCode to GET API"
        old = analyzed("CCON-1", "Use TypeCode")
        old["analysis"]["emailDraft"]["body"] = "Pass typeCode to GET API"
        result = build_report({"CCON-1": old}, [current], "2026-10-24T17:30:00Z")
        self.assertIn("emailDraft", result["changes"][0]["changedFields"])

    def test_blank_or_unusable_evidence_does_not_claim_proof(self):
        for proof in ([{"text": "", "url": ""}], [{"text": "a", "url": "javascript:alert(1)"}], []):
            with self.subTest(proof=proof):
                issue = analyzed("CCON-1", "", "WAIT", evidence=proof)
                self.assertIn("WAIT_NOT_VERIFIED",
                              {x["code"] for x in diagnostics("CCON-1", issue["analysis"])})
                issue["analysis"]["signal"] = "READY"
                self.assertIn("ACTION_WITHOUT_EVIDENCE",
                              {x["code"] for x in diagnostics("CCON-1", issue["analysis"])})

    def test_report_rejects_empty_summary_and_malformed_changes(self):
        with self.assertRaisesRegex(ValueError, "timestamp"):
            validate_report({"summary": {}})
        with self.assertRaisesRegex(ValueError, "incomplete"):
            validate_report({"generatedAt": "2026-10-24", "summary": {},
                             "changes": [], "warnings": []})
        good = build_report({}, [analyzed("CCON-1", "")], "2026-10-24T17:30:00Z")
        validate_report(good)
        good["changes"][0].pop("nextActionUk")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            validate_report(good)

    def test_briefing_warns_about_timeline_with_actual_comments(self):
        briefing = {
            "overviewUk": "", "currentUk": "", "targetUk": "No change",
            "businessImpactUk": "", "technicalScopeUk": "",
            "readiness": "NEEDS_CONFIRMATION", "readinessReasonUk": "Supplier input",
            "risksUk": [], "unknownsUk": ["Need confirmation"],
            "confirmedFacts": [], "timeline": [],
            "rules": [], "verification": [],
        }
        validate_briefing(briefing)
        issue = analyzed("CCON-1", "")
        issue["analysis"]["briefing"] = briefing
        result = build_report({}, [issue], "2026-10-24T17:30:00Z",
                              issue_contexts={"CCON-1": {"comments": [{"id": "123"}]}})
        self.assertIn("TIMELINE_MISSING", {x["code"] for x in result["warnings"]})

    def test_report_larger_than_5mb_stays_accessible_through_report_limit(self):
        issue = analyzed("CCON-1", "")
        report = build_report({}, [issue], "2026-10-24T17:30:00Z")
        question = "long_question_" + ("x" * 1100000)
        report["changes"][0]["questionsAdded"] = [question] * 6
        with tempfile.TemporaryDirectory() as folder:
            path = write_report(report, folder)
            self.assertGreater(path.stat().st_size, 5 * 1024 * 1024)
            self.assertLess(path.stat().st_size, REPORT_LIMIT)
            validate_report(json.loads(path.read_text()))

    def test_evaluation_preserves_adf_link_in_main_and_linked_context(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "data").mkdir()
            issues = {}
            for i in range(1, 21):
                key = f"CCON-{i}"
                issues[key] = {
                    "key": key, "summary": key, "fingerprint": f"f-{i}",
                    "description": "Read the supplier instructions",
                    "descriptionAdf": {"content": [{"type": "text",
                                        "text": "Supplier instructions",
                                        "marks": [{"type": "link",
                                                   "attrs": {"href": "https://supplier.example/spec"}}]}]},
                    "comments": [{"body": "Supplier update", "bodyAdf": {"content": [
                        {"type": "text", "text": "Update",
                         "marks": [{"type": "link", "attrs": {"href": "https://example.com/update"}}]}]}}],
                    "links": [{"linkedKey": "RELATED-1"}],
                }
            (root / "data/jira_context.json").write_text(json.dumps({
                "complete": True, "issues": issues,
                "linkedIssues": {"RELATED-1": {
                    "summary": "Linked", "descriptionAdf": {
                        "content": [{"type": "text", "text": "Reference",
                                     "marks": [{"attrs": {"href": "https://linked.example"}}]}]},
                }},
            }))
            prepare(root, 20)
            cases = json.loads((root / "data/evaluation/selected_cases.json").read_text())["cases"]
            self.assertEqual(len(cases), 20)
            source = cases[0]["source"]
            self.assertEqual(source["descriptionAdf"]["content"][0]["marks"][0]["attrs"]["href"],
                             "https://supplier.example/spec")
            self.assertEqual(source["comments"][0]["bodyAdf"]["content"][0]["marks"][0]["attrs"]["href"],
                             "https://example.com/update")
            self.assertEqual(source["linkedContexts"][0]["descriptionAdf"]["content"][0]["marks"][0]["attrs"]["href"],
                             "https://linked.example")

    def test_repeated_sync_preserves_departure_until_reported(self):
        class Fixture(FakeJira):
            def get(self, path, params=None):
                if path.endswith("/issue/CCON-1"):
                    return {"key": "CCON-1", "fields": {"status": {
                        "name": "Done", "statusCategory": {"key": "done"}}}}
                return super().get(path, params)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture = Fixture()
            with patch.dict("os.environ", {"CCON_JIRA_BOARD_ID": ""}):
                sync(root, fixture)
                desk = Desk(root)
                desk.import_snapshot()
                from unittest.mock import patch as mocked
                with mocked("jira_sync.fetch_issues",
                            return_value={"CCON-2": fixture.second}):
                    first = sync(root, Fixture())
                    desk.import_snapshot()  # simulate live server auto-import
                    second = sync(root, Fixture())
                    self.assertEqual(first["leftScopeCount"], 1)
                    self.assertEqual(second["leftScopeCount"], 1)
                    context = json.loads((root / "data/jira_context.json").read_text())
                    previous = {v["key"]: v for v in desk.view()["tasks"]}
                    self.assertFalse(previous["CCON-1"]["active"])
                    fresh = [analyzed("CCON-2", "")]
                    report = build_report(previous, fresh, datetime.now(timezone.utc).isoformat(),
                                          context["leftScope"])
                    self.assertEqual(report["summary"]["JIRA_DONE"], 1)
                    write_report(report, root)
                    third = sync(root, Fixture())
                    self.assertEqual(third["leftScopeCount"], 0)
                    self.assertEqual(third["confirmedDoneSinceLastSync"], 0)

    def test_windows_missing_tzdata_does_not_block_daily_checklist(self):
        report = build_report({}, [analyzed("CCON-1", "")], "2026-10-24T17:30:00Z")
        with tempfile.TemporaryDirectory() as folder:
            with patch("prompt_calibration.ZoneInfo", side_effect=ZoneInfoNotFoundError):
                result = update_daily(report, folder)
            self.assertRegex(result["date"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertTrue((Path(folder) / "data/prompt_calibration/current.md").exists())

    def test_prompt_cache_fingerprint_ignores_calibration_date_and_count(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report = {"warnings": [{"code": "WAIT_NOT_VERIFIED"}]}
            update_daily(report, root, date="2026-10-24")
            _, earlier = approved_prompts(root)
            update_daily({"warnings": [{"code": "WAIT_NOT_VERIFIED"}] * 9},
                         root, date="2026-10-25")
            _, later = approved_prompts(root)
            self.assertEqual(earlier, later)
            update_daily({"warnings": [{"code": "ACTION_WITHOUT_EVIDENCE"}]},
                         root, date="2026-10-26")
            _, changed = approved_prompts(root)
            self.assertNotEqual(earlier, changed)


if __name__ == "__main__":
    unittest.main()
