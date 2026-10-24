import copy
import unittest
from ba_briefing import validate_briefing, audit_briefing
from schema import validate_analysis


def briefing():
    return {
        "overviewUk": "Постачальник повертає зайвий сегмент.",
        "currentUk": "REST повертає скасований сегмент.",
        "targetUk": "REST не повертає сегмент за підтвердженою умовою.",
        "businessImpactUk": "Зайва інформація для агента.",
        "technicalScopeUk": "REST PullPNR; інші методи не перевірялися.",
        "readiness": "NEEDS_CONFIRMATION",
        "readinessReasonUk": "Потрібна відповідь постачальника.",
        "confirmedFacts": [{"textUk": "У логах є CANCELLED.", "sourceUrl": "https://jira.example/1"}],
        "timeline": [{"date": "2026-10-24", "status": "CONFIRMED", "eventUk": "Показано payload.",
                      "sourceUrl": "https://jira.example/1"}],
        "rules": [{"whenUk": "StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED",
                   "thenUk": "Сегмент не повертається", "certainty": "CONFIRMED",
                   "sourceUrl": "https://jira.example/1"}],
        "verification": [{"scenarioUk": "Скасований сегмент", "expectedUk": "Сегмент відсутній",
                          "sourceUrl": "https://jira.example/1"}],
        "unknownsUk": ["Чи можливий стан без REMOVED?"],
        "risksUk": [],
    }


class BriefingTests(unittest.TestCase):
    def test_valid_source_grounded_briefing(self):
        validate_briefing(briefing())
        analysis = {"briefing": briefing()}
        validate_analysis(analysis)
        self.assertEqual(audit_briefing(analysis), [])

    def test_open_rule_without_source_is_not_misrepresented_as_confirmed(self):
        draft = briefing()
        draft["rules"][0]["sourceUrl"] = ""
        validate_briefing(draft)
        self.assertIn("RULE_WITHOUT_SOURCE",
                      {w["code"] for w in audit_briefing({"briefing": draft})})
        draft["rules"][0]["certainty"] = "OPEN"
        self.assertNotIn("RULE_WITHOUT_SOURCE",
                         {w["code"] for w in audit_briefing({"briefing": draft})})

    def test_readiness_without_acceptance_is_flagged(self):
        draft = briefing()
        draft["readiness"] = "READY_FOR_REVIEW"
        draft["verification"] = []
        codes = {w["code"] for w in audit_briefing({"briefing": draft})}
        self.assertIn("NO_ACCEPTANCE_TESTS", codes)
        self.assertIn("READY_WITH_UNKNOWNS", codes)

    def test_invalid_url_and_status_rejected(self):
        draft = briefing()
        draft["confirmedFacts"][0]["sourceUrl"] = "javascript:alert(1)"
        with self.assertRaisesRegex(ValueError, "HTTP"):
            validate_briefing(draft)
        draft = briefing()
        draft["timeline"][0]["status"] = "GUESSED"
        with self.assertRaisesRegex(ValueError, "status"):
            validate_briefing(draft)

    def test_missing_briefing_is_an_explicit_warning_for_legacy(self):
        result = audit_briefing({"signal": "REVIEW"})
        self.assertEqual([v["code"] for v in result], ["BRIEF_MISSING"])

    def test_timeline_gap_flagged_with_existing_comments(self):
        draft = briefing()
        draft["timeline"] = []
        codes = {w["code"] for w in audit_briefing(
            {"briefing": draft}, {"comments": [{"body": "Decision"}]})}
        self.assertIn("TIMELINE_MISSING", codes)


if __name__ == "__main__":
    unittest.main()
