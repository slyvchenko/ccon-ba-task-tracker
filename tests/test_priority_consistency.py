"""Synthetic review tests: no real Jira data or corporate source text."""
import unittest

from review_report import build_report, render_markdown
from priority_consistency import inspect_priority


def item(key="CCON-42", *, score=60, fingerprint="same", sprint=True,
         factors=None):
    analysis = {
        "signal": "READY", "queueScore": score,
        "contextFingerprint": fingerprint,
        "nextActionUk": "Check evidence", "missingInfo": [],
        "emailDraft": {"to": "", "subject": "", "body": ""},
        "evidence": [{"text": "Jira", "url": "https://jira.example/browse/CCON-42"}],
    }
    if factors is not None:
        analysis["priorityFactors"] = factors
    return {
        "key": key, "summary": "Synthetic priority fixture",
        "contextFingerprint": fingerprint,
        "activeSprint": sprint, "analysis": analysis,
    }


class PriorityConsistencyTests(unittest.TestCase):
    def report(self, old, new):
        return build_report({old["key"]: old} if old else {}, [new],
                            "2026-10-25T07:00:00+00:00")

    def test_score_change_updates_daily_report_even_when_text_same(self):
        before = item(score=40)
        after = item(score=70)
        report = self.report(before, after)
        self.assertEqual(report["summary"]["UPDATED"], 1)
        change = report["changes"][0]
        self.assertIn("queueScore", change["changedFields"])
        self.assertEqual(change["priorityChange"],
                         {"before": 40, "after": 70, "delta": 30})
        codes = {w["code"] for w in report["warnings"]}
        self.assertIn("PRIORITY_DRIFT_REVIEW", codes)
        self.assertIn("Пріоритет: 40 → 70", render_markdown(report))

    def test_changed_jira_source_does_not_trigger_unsupported_drift_claim(self):
        report = self.report(item(score=20, fingerprint="prior"),
                             item(score=90, fingerprint="current"))
        codes = {w["code"] for w in report["warnings"]}
        self.assertNotIn("PRIORITY_DRIFT_REVIEW", codes)
        self.assertTrue(report["changes"][0]["sourceChanged"])

    def test_sprint_change_does_not_trigger_drift_flag(self):
        report = self.report(item(score=30, sprint=False),
                             item(score=90, sprint=True))
        codes = {w["code"] for w in report["warnings"]}
        self.assertNotIn("PRIORITY_DRIFT_REVIEW", codes)
        self.assertTrue(report["changes"][0]["sprintChanged"])

    def test_threshold_and_missing_factors_are_review_only(self):
        before, after = item(score=50), item(score=69)
        report = self.report(before, after)
        codes = [w["code"] for w in report["warnings"]]
        self.assertIn("PRIORITY_FACTORS_MISSING", codes)
        self.assertNotIn("PRIORITY_DRIFT_REVIEW", codes)
        self.assertEqual(after["analysis"]["queueScore"], 69)

    def test_factors_only_change_is_reported_without_score_drift(self):
        a = {"businessImpact": 15, "urgency": 15, "dependencies": 10,
             "baDecision": 10, "actionability": 10}
        b = {"businessImpact": 20, "urgency": 10, "dependencies": 10,
             "baDecision": 10, "actionability": 10}
        report = self.report(item(factors=a), item(factors=b))
        self.assertEqual(report["summary"]["UPDATED"], 1)
        self.assertEqual(report["changes"][0]["changedFields"], ["priorityFactors"])
        self.assertIsNone(report["changes"][0]["priorityChange"])
        self.assertNotIn("PRIORITY_FACTORS_MISSING",
                         {w["code"] for w in report["warnings"]})

    def test_identical_score_and_factors_do_not_trigger_change(self):
        factors = {"businessImpact": 15, "urgency": 15, "dependencies": 10,
                   "baDecision": 10, "actionability": 10}
        report = self.report(item(factors=factors), item(factors=factors))
        self.assertEqual(report["summary"]["UNCHANGED"], 1)
        self.assertIsNone(report["changes"][0]["priorityChange"])

    def test_legacy_missing_fingerprint_and_boolean_are_not_false_drifts(self):
        check = inspect_priority("CCON-42",
                                 {"queueScore": 10, "contextFingerprint": ""},
                                 {"queueScore": 80, "contextFingerprint": ""},
                                 source_changed=False, sprint_changed=False)
        self.assertEqual(check["change"]["delta"], 70)
        self.assertNotIn("PRIORITY_DRIFT_REVIEW",
                         {w["code"] for w in check["warnings"]})
        check = inspect_priority("CCON-42", {"queueScore": True},
                                 {"queueScore": 90}, source_changed=False,
                                 sprint_changed=False)
        self.assertIsNone(check["change"])


if __name__ == "__main__":
    unittest.main()
