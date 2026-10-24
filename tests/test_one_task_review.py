import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desk_store import Desk
from one_task_review import review_one
from model_analysis import analyze_all
from storage import write_json


def analysis(key, number):
    from test_ba_briefing import briefing
    return {"signal": "READY", "queueScore": 45 + number,
            "reasonUk": "Потрібно перевірити технічну умову.",
            "nextActionUk": "Перевірити відповідь постачальника.",
            "missingInfo": [], "waitingRequired": False, "waitingOnUk": "",
            "needsEmail": False, "evidence": [],
            "standardDescription": "#### To Do\nCheck " + key + "\n#### QA\n- Check expected REST response.",
            "emailDraft": {"to": "", "subject": "", "body": ""},
            "priorityFactors": {"businessImpact": 10, "urgency": 10,
                                "dependencies": 10, "baDecision": 10,
                                "actionability": 5 + number},
            "briefing": briefing(), "contextFingerprint": f"fp-{key}"}


class FocusedReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.joinpath("data").mkdir()
        tasks = []
        issues = {}
        for i in (1, 2):
            key = f"CCON-{i}"
            value = analysis(key, i)
            tasks.append({"key": key, "summary": f"Sample {i}",
                          "contextFingerprint": f"fp-{key}", "analysis": value})
            issues[key] = {"key": key, "fingerprint": f"fp-{key}",
                           "summary": f"Sample {i}", "description": "Simple task",
                           "comments": [], "links": []}
        write_json(self.root / "data/jira_context.json",
                   {"complete": True, "issues": issues})
        write_json(self.root / "inbox/CCON_BA_Snapshot.json",
                   {"complete": True, "generatedAt": "2026-10-24T09:00:00+00:00",
                    "tasks": tasks})
        self.desk = Desk(self.root)
        self.desk.import_snapshot()
        self.desk.save("CCON-1", {"manualStatus": "IN PROGRESS", "note": "Keep this note",
                   "emailDraft": {"to": "", "subject": "MY SUBJECT", "body": "My edited email"}})

    def fake_model(self, settings, instructions, source, note):
        self.calls.append(source["issue"]["key"])
        result = analysis(source["issue"]["key"], 2)
        result["reasonUk"] = "Оновлений цільовий аналіз задачі."
        return result

    def test_only_target_invoked_and_manual_edits_kept(self):
        self.calls = []
        old = {t["key"]: t["analysis"] for t in self.desk.view()["tasks"]}
        with patch("model_analysis.model_settings", return_value={"model": "fake"}):
            result = review_one(self.root, "CCON-1", model_call=self.fake_model)
        self.assertEqual(result["generated"], 1)
        self.assertEqual(result["preservedOtherAnalyses"], 1)
        self.assertEqual(self.calls, ["CCON-1"])
        tasks = {t["key"]: t for t in self.desk.view()["tasks"]}
        self.assertEqual(tasks["CCON-2"]["analysis"], old["CCON-2"])
        self.assertEqual(tasks["CCON-1"]["note"], "Keep this note")
        self.assertEqual(tasks["CCON-1"]["manualStatus"], "IN PROGRESS")
        self.assertEqual(tasks["CCON-1"]["savedEmailDraft"]["body"], "My edited email")

    def test_non_target_stale_analysis_blocks_target_review(self):
        context = json.loads((self.root / "data/jira_context.json").read_text())
        context["issues"]["CCON-2"]["fingerprint"] = "changed"
        write_json(self.root / "data/jira_context.json", context)
        self.calls = []
        with patch("model_analysis.model_settings", return_value={"model": "fake"}):
            with self.assertRaisesRegex(ValueError, "stale/missing"):
                review_one(self.root, "CCON-1", model_call=self.fake_model)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.desk.view()["tasks"][0]["note"], "Keep this note")

    def test_bad_issue_never_calls_model(self):
        self.calls = []
        with patch("model_analysis.model_settings", return_value={"model": "fake"}):
            with self.assertRaisesRegex(ValueError, "personal Jira"):
                review_one(self.root, "CCON-999", model_call=self.fake_model)
        self.assertEqual(self.calls, [])

    def test_denied_provider_blocks_target_review(self):
        self.calls = []
        with patch("model_analysis.model_settings", side_effect=ValueError("Company approval missing")):
            with self.assertRaisesRegex(ValueError, "approval"):
                review_one(self.root, "CCON-1", model_call=self.fake_model)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
