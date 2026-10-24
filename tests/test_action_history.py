import json
import shutil
import tempfile
import unittest
from pathlib import Path

from desk_store import Desk
from storage import write_json, read_json
from ba_actions import edit_action, display_actions, all_actions
from task_history import history_page


def snapshot(date, *, summary="Task A", state="OPEN", key="CCON-123"):
    return {"generatedAt": date, "tasks": [{
        "key": key, "summary": summary, "jiraStatus": state,
        "activeSprintStatus": "VERIFIED", "activeSprint": True,
        "analysis": {
            "signal": "WRITE", "needsEmail": True,
            "reasonUk": "Необхідна перевірка.", "nextActionUk": "Перевірити supplier response.",
            "standardDescription": "IF status CANCELLED THEN omit segment.",
            "emailDraft": {"to": "", "subject": "Question", "body": "Please clarify"},
        },
    }]}


class TaskHistoryAndActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.desk = Desk(self.root)
        self.root.joinpath("data").mkdir(exist_ok=True)
        write_json(self.root / "data/jira_context.json", {
            "complete": True, "issues": {"CCON-123": {"key": "CCON-123", "fingerprint": "fp"}}
        })

    def import_doc(self, doc):
        write_json(self.desk.inbox / "CCON_BA_Snapshot.json", doc)
        return self.desk.import_snapshot()

    def test_import_changes_persist_and_duplicate_does_not_create_revision(self):
        self.import_doc(snapshot("2026-10-24T10:00:00Z"))
        self.assertEqual(self.desk.history("CCON-123")["total"], 1)
        self.import_doc(snapshot("2026-10-24T10:00:00Z"))
        self.assertEqual(self.desk.history("CCON-123")["total"], 1)
        self.import_doc(snapshot("2026-10-24T11:00:00Z", summary="Task A edited"))
        h = Desk(self.root).history("CCON-123")
        self.assertEqual(h["total"], 2)
        self.assertIn("summary", h["revisions"][0]["changed"])
        self.assertEqual(h["revisions"][1]["state"]["summary"], "Task A")

    def test_note_status_and_draft_history_survive_refresh(self):
        self.import_doc(snapshot("2026-10-24T10:00:00Z"))
        self.desk.save("CCON-123", {
            "manualStatus": "IN PROGRESS", "note": "Asked supplier",
            "emailDraft": {"to": "supplier@example.com", "subject": "New",
                           "body": "My manual draft"}
        })
        self.assertEqual(self.desk.history("CCON-123")["total"], 2)
        self.import_doc(snapshot("2026-10-24T11:00:00Z", state="IN PROGRESS"))
        h = Desk(self.root).history("CCON-123")
        self.assertEqual(h["total"], 3)
        self.assertEqual(h["revisions"][0]["state"]["note"], "Asked supplier")
        self.assertEqual(h["revisions"][0]["state"]["savedEmailDraft"]["body"], "My manual draft")
        self.assertEqual(self.desk.view()["tasks"][0]["savedEmailDraft"]["body"], "My manual draft")
        # Saving identical manual fields does not duplicate history.
        self.desk.save("CCON-123", {
            "manualStatus": "IN PROGRESS", "note": "Asked supplier",
            "emailDraft": {"to": "supplier@example.com", "subject": "New",
                           "body": "My manual draft"}
        })
        self.assertEqual(self.desk.history("CCON-123")["total"], 3)

    def test_departed_and_returned_task_are_tracked(self):
        self.import_doc(snapshot("2026-10-24T10:00:00Z"))
        self.import_doc({"generatedAt": "2026-10-24T11:00:00Z", "tasks": [{
            "key": "CCON-456", "summary": "Other task"
        }]})
        left = self.desk.history("CCON-123")
        self.assertFalse(left["revisions"][0]["state"]["active"])
        self.import_doc(snapshot("2026-10-24T12:00:00Z"))
        arrived = self.desk.history("CCON-123")
        self.assertTrue(arrived["revisions"][0]["state"]["active"])
        self.assertEqual(arrived["total"], 3)

    def test_paginated_history_and_invalid_key(self):
        for i in range(45):
            self.import_doc(snapshot(f"2026-10-24T{i % 24:02d}:00:00Z",
                                     summary=f"Version {i}"))
            # import rejects old time across midnight; use valid monotonic days below
            break
        self.assertEqual(self.desk.history("CCON-123", limit=1)["total"], 1)
        with self.assertRaises(ValueError):
            self.desk.history("CCON-123", limit=999)
        with self.assertRaises(ValueError):
            self.desk.history("../evil")

    def test_manual_plan_with_overdue_followup_and_no_ai_auto_save(self):
        self.import_doc(snapshot("2026-10-24T10:00:00Z"))
        self.assertEqual(display_actions(self.root, "CCON-123", today="2026-10-24")["actions"], [])
        created = edit_action(self.root, "CCON-123",
            description="Check AF/KL response", owner="BA",
            due_date="2026-10-30", next_review_date="2026-10-23", waiting_on="Supplier")
        item = created["actions"][0]
        self.assertEqual(item["status"], "OPEN")
        item_id = item["id"]
        # A follow-up earlier than due date must be indicated as overdue.
        self.assertEqual(display_actions(self.root, "CCON-123", today="2026-10-24")["overdueCount"], 1)
        queue = all_actions(self.root, self.desk.view()["tasks"], today="2026-10-24")
        self.assertEqual(queue["total"], 1)
        self.assertTrue(queue["actions"][0]["inSprint"])
        self.assertTrue(queue["actions"][0]["needsEmail"])
        edit_action(self.root, "CCON-123", action="update", identifier=item_id,
            description="Check AF/KL response", status="DONE",
            due_date="2026-10-30", next_review_date="2026-10-23")
        self.assertEqual(all_actions(self.root, self.desk.view()["tasks"], today="2026-10-24")["total"], 0)
        self.assertEqual(display_actions(self.root, "CCON-123")["actions"][0]["status"], "DONE")

    def test_action_scope_and_dates_are_validated(self):
        self.import_doc(snapshot("2026-10-24T10:00:00Z"))
        for due in ("2026-02-30", "tomorrow", "2026-13-01"):
            with self.subTest(due=due), self.assertRaises(ValueError):
                edit_action(self.root, "CCON-123", description="Test", due_date=due)
        with self.assertRaises(ValueError):
            edit_action(self.root, "CCON-999", description="Other person's task")
        with self.assertRaises(ValueError):
            edit_action(self.root, "CCON-123", description="")
        with self.assertRaises(ValueError):
            edit_action(self.root, "CCON-123", description="Other", source="AI")
        self.assertEqual(display_actions(self.root, "CCON-123")["actions"], [])

    def test_plan_survives_snapshot_refresh_and_is_private(self):
        self.import_doc(snapshot("2026-10-24T10:00:00Z"))
        edit_action(self.root, "CCON-123", description="Send supplier question", due_date="2026-10-27")
        self.import_doc(snapshot("2026-10-24T11:00:00Z", state="IN PROGRESS"))
        self.assertEqual(display_actions(self.root, "CCON-123")["openCount"], 1)
        self.assertTrue((self.root / "data/actions/CCON-123.json").is_file())


if __name__ == "__main__":
    unittest.main()
