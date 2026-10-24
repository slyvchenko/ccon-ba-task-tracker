import unittest

from review_report import build_report, diagnostics, render_markdown


def task(key="CCON-1", signal="READY", questions=None, fingerprint="f1", action="Перевірити дані"):
    analysis = {
        "signal": signal, "missingInfo": questions or [], "nextActionUk": action,
        "contextFingerprint": fingerprint, "standardDescription": "",
        "waitingRequired": signal == "WAIT", "needsEmail": signal == "WRITE",
        "waitingOnUk": "", "evidence": [{"text": "Коментар", "url": "https://jira.example/1"}],
        "emailDraft": {"to": "", "subject": "", "body": ""},
    }
    return {"key": key, "summary": "Test issue", "contextFingerprint": fingerprint,
            "analysis": analysis}


class DailyReportTests(unittest.TestCase):
    def report(self, old, fresh):
        return build_report(old, fresh, "2026-10-24T12:00:00+00:00")

    def test_new_tasks_have_initial_questions(self):
        current = task(questions=["Який метод?", "Який результат?"])
        result = self.report({}, [current])
        self.assertEqual(result["summary"]["NEW"], 1)
        self.assertEqual(result["summary"]["questionsAdded"], 2)
        self.assertEqual(result["changes"][0]["category"], "NEW")

    def test_unchanged_reanalysis_ignores_whitespace_and_question_order(self):
        old = task(questions=["Перше питання", "Друге питання"])
        current = task(questions=["  друге   питання ", "ПЕРШЕ ПИТАННЯ"])
        current["analysis"]["nextActionUk"] = "  перевірити  дані "
        result = self.report({"CCON-1": old}, [current])
        self.assertEqual(result["summary"]["UNCHANGED"], 1)
        self.assertEqual(result["summary"]["questionsAdded"], 0)
        self.assertEqual(result["summary"]["questionsRemoved"], 0)

    def test_removed_question_is_not_claimed_answered(self):
        old = task(questions=["Є питання про TypeCode?", "Який scope?"])
        current = task(questions=["Який scope?", "Чи потрібний fallback?"])
        result = self.report({"CCON-1": old}, [current])
        self.assertEqual(result["summary"]["UPDATED"], 1)
        item = result["changes"][0]
        self.assertEqual(item["questionsRemoved"], ["Є питання про TypeCode?"])
        self.assertEqual(item["questionsAdded"], ["Чи потрібний fallback?"])
        self.assertIn("не обов'язково отримало відповідь", render_markdown(result))

    def test_source_change_is_visible_even_if_summary_same(self):
        old = task(fingerprint="old")
        current = task(fingerprint="new")
        result = self.report({"CCON-1": old}, [current])
        self.assertEqual(result["changes"][0]["category"], "UPDATED")
        self.assertTrue(result["changes"][0]["sourceChanged"])

    def test_signals_track_completion_and_reopening_without_changing_manual_status(self):
        old = task(signal="READY")
        old["manualStatus"] = "IN PROGRESS"
        done = task(signal="DONE")
        result = self.report({"CCON-1": old}, [done])
        self.assertEqual(result["changes"][0]["category"], "COMPLETED")
        self.assertEqual(result["changes"][0]["manualStatus"], "IN PROGRESS")
        result2 = self.report({"CCON-1": done}, [task(signal="WAIT")])
        self.assertEqual(result2["changes"][0]["category"], "REOPENED")

    def test_quality_warnings_are_non_blocking_and_explicit(self):
        wait = task(signal="WAIT")
        wait["analysis"]["waitingRequired"] = None
        wait["analysis"]["evidence"] = []
        write = task(key="CCON-2", signal="WRITE")
        write["analysis"]["needsEmail"] = False
        write["analysis"]["evidence"] = []
        done = task(key="CCON-3", signal="DONE", questions=["Не вирішено"])
        done["analysis"]["standardDescription"] = "Unstructured"
        result = self.report({}, [wait, write, done])
        codes = {finding["code"] for finding in result["warnings"]}
        self.assertEqual(codes, {"WAIT_NOT_VERIFIED", "WRITE_EMAIL_CONFLICT",
                                 "ACTION_WITHOUT_EVIDENCE", "DONE_HAS_QUESTIONS",
                                 "DESCRIPTION_WITHOUT_QA", "BRIEF_MISSING"})
        self.assertEqual(result["summary"]["warnings"], 8)


if __name__ == "__main__":
    unittest.main()
