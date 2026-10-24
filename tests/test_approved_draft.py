import json
import tempfile
import unittest
from pathlib import Path

from approved_draft import approve, describe, file_path
from desk_store import Desk
from storage import write_json
from test_one_task_review import analysis

KEY = "CCON-1"


class ApprovedDraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.context = {"complete": True, "issues": {
            KEY: {"key": KEY, "fingerprint": "fp-" + KEY, "summary": "AF/KL. retrievePNR"}}}
        write_json(self.root / "data/jira_context.json", self.context)
        self.snapshot = {"complete": True, "generatedAt": "2026-10-24T09:00:00+00:00",
                         "tasks": [{"key": KEY, "summary": "AF/KL. retrievePNR",
                                    "contextFingerprint": "fp-" + KEY,
                                    "analysis": analysis(KEY, 1)}]}
        write_json(self.root / "inbox/CCON_BA_Snapshot.json", self.snapshot)
        self.desk = Desk(self.root)
        self.desk.import_snapshot()
        self.desk.save(KEY, {"manualStatus": "IN PROGRESS", "note": "Preserve expert note",
                             "emailDraft": {"to": "", "subject": "Human subject", "body": "Human body"}})

    def update_ai_description(self, text, fp="fp-CCON-1"):
        self.snapshot["tasks"][0]["analysis"]["standardDescription"] = text
        self.snapshot["tasks"][0]["contextFingerprint"] = fp
        self.snapshot["tasks"][0]["analysis"]["contextFingerprint"] = fp
        self.snapshot["generatedAt"] = "2026-10-24T10:00:00+00:00"
        write_json(self.root / "inbox/CCON_BA_Snapshot.json", self.snapshot)
        self.desk.import_snapshot()

    def test_explicit_approve_creates_local_reference_and_detects_future_delta(self):
        self.assertFalse(describe(self.root, KEY)["hasApproved"])
        first = approve(self.root, KEY)
        self.assertEqual(first["state"], "UNCHANGED")
        approved = json.loads(file_path(self.root, KEY).read_text())
        saved_text = approved["text"]
        self.update_ai_description("#### To Do\nCheck TypeCode no_code\n#### QA\n- Check mapping outcome.")
        delta = describe(self.root, KEY)
        self.assertEqual(delta["state"], "NEW_DRAFT_DIFFERS")
        self.assertTrue(delta["changed"])
        self.assertIn("+Check TypeCode", delta["diff"])
        self.assertEqual(json.loads(file_path(self.root, KEY).read_text())["text"], saved_text)
        task = self.desk.view()["tasks"][0]
        self.assertEqual(task["note"], "Preserve expert note")
        self.assertEqual(task["savedEmailDraft"]["subject"], "Human subject")

    def test_jira_context_change_requires_reapproval_and_does_not_fake_equal(self):
        approve(self.root, KEY)
        self.context["issues"][KEY]["fingerprint"] = "new"
        write_json(self.root / "data/jira_context.json", self.context)
        self.update_ai_description("#### To Do\nCheck changed contract\n#### QA\n- Check output.", fp="new")
        self.assertEqual(describe(self.root, KEY)["state"], "SOURCE_CHANGED")
        with self.assertRaisesRegex(ValueError, "stale"):
            self.update_ai_description("#### To Do\nCheck again", fp="stale")
            approve(self.root, KEY)

    def test_no_write_without_scoped_and_ready_analysis(self):
        with self.assertRaises(ValueError):
            approve(self.root, "CCON-999")
        self.update_ai_description("")
        with self.assertRaisesRegex(ValueError, "ready BA description"):
            approve(self.root, KEY)
        self.assertFalse(file_path(self.root, KEY).exists())


if __name__ == "__main__":
    unittest.main()
