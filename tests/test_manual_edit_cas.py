"""Synthetic cross-tab CAS regressions for manual status, notes, and email drafts."""
import json
import sqlite3
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from desk_store import Desk, SaveConflict
from server import handler


class ManualEditCASTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ccon-cas-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.desk = Desk(self.root)
        self.source = self.desk.inbox / "CCON_BA_Snapshot.json"
        self.snapshot()
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.desk))
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.base = f"http://127.0.0.1:{self.http.server_port}"
        self.opener = build_opener(ProxyHandler({}))

    def close(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()

    def snapshot(self, timestamp="2026-10-25T09:00:00+00:00"):
        self.source.write_text(json.dumps({
            "generatedAt": timestamp, "tasks": [
                {"key": "CCON-1", "summary": "Synthetic NDC rebooking"},
                {"key": "CCON-2", "summary": "Independent synthetic issue"},
            ]}), encoding="utf-8")
        return self.desk.import_snapshot()

    def post(self, key, value):
        req = Request(self.base + "/api/tasks/" + key, method="POST",
                      data=json.dumps(value).encode(), headers={
                          "Origin": self.base, "Content-Type": "application/json"})
        with self.opener.open(req) as reply:
            return json.load(reply)

    def initial(self):
        return next(x for x in self.desk.view()["tasks"] if x["key"] == "CCON-1")

    def test_initial_revision_successful_CAS_and_preserved_draft(self):
        self.assertEqual(self.initial()["manualRevision"], 0)
        draft = {"to": "synthetic@example.invalid", "subject": "Test", "body": "First"}
        ack = self.post("CCON-1", {"manualStatus": "IN PROGRESS", "note": "reviewed",
            "emailDraft": draft, "expectedManualRevision": 0})
        self.assertEqual(ack["manualRevision"], 1)
        self.assertEqual(self.initial()["savedEmailDraft"], draft)
        self.assertEqual(self.initial()["manualRevision"], 1)

    def test_second_tab_stale_409_does_not_overwrite_or_increment_global_version(self):
        self.post("CCON-1", {"manualStatus": "IN PROGRESS", "note": "First tab",
                           "expectedManualRevision": 0})
        before = self.desk.revision()["revision"]
        with self.assertRaises(HTTPError) as caught:
            self.post("CCON-1", {"manualStatus": "DONE", "note": "Second tab",
                               "expectedManualRevision": 0})
        self.assertEqual(caught.exception.code, 409)
        detail = json.loads(caught.exception.read())
        self.assertEqual(detail["code"], "TASK_REVISION_CONFLICT")
        self.assertEqual(detail["currentManualRevision"], 1)
        self.assertNotIn("First tab", json.dumps(detail))
        self.assertEqual(self.initial()["note"], "First tab")
        self.assertEqual(self.initial()["manualStatus"], "IN PROGRESS")
        self.assertEqual(self.desk.revision()["revision"], before)

    def test_explicit_retry_after_reading_current_version_succeeds(self):
        self.post("CCON-1", {"manualStatus": "IN PROGRESS", "note": "First",
                           "expectedManualRevision": 0})
        latest = self.initial()
        ack = self.post("CCON-1", {"manualStatus": "WAITING INPUT",
                           "note": "My reviewed override",
                           "expectedManualRevision": latest["manualRevision"]})
        self.assertEqual(ack["manualRevision"], 2)
        self.assertEqual(self.initial()["note"], "My reviewed override")

    def test_missing_and_invalid_tokens_keep_legacy_backward_compatibility(self):
        for invalid in (None, -1, True, False, 1.0, "0"):
            with self.subTest(invalid=invalid), self.assertRaises(HTTPError) as caught:
                self.post("CCON-1", {"manualStatus": "DONE", "note": "",
                                    "expectedManualRevision": invalid})
            self.assertEqual(caught.exception.code, 400)
            self.assertEqual(self.initial()["manualRevision"], 0)
        result = self.post("CCON-1", {"manualStatus": "IN PROGRESS", "note": "legacy"})
        self.assertEqual(result["manualRevision"], 1)

    def test_snapshot_reimport_preserves_manual_revision(self):
        self.post("CCON-1", {"manualStatus": "IN PROGRESS", "note": "Private",
                           "expectedManualRevision": 0})
        self.snapshot("2026-10-25T10:00:00+00:00")
        task = self.initial()
        self.assertEqual(task["manualRevision"], 1)
        self.assertEqual(task["note"], "Private")
        self.assertEqual(task["manualStatus"], "IN PROGRESS")
        self.post("CCON-1", {"manualStatus": "WAITING DEPENDENCY", "note": "Private",
                           "expectedManualRevision": 1})
        self.assertEqual(self.initial()["manualRevision"], 2)

    def test_independent_tasks_do_not_conflict(self):
        self.post("CCON-2", {"manualStatus": "DONE", "note": "other task",
                           "expectedManualRevision": 0})
        ack = self.post("CCON-1", {"manualStatus": "IN PROGRESS", "note": "own task",
                                 "expectedManualRevision": 0})
        self.assertEqual(ack["manualRevision"], 1)

    def test_status_only_save_keeps_draft_and_revision_consistency(self):
        draft = {"to": "", "subject": "not sent", "body": "Private synthetic"}
        self.post("CCON-1", {"manualStatus": "IN PROGRESS", "note": "First",
                           "emailDraft": draft, "expectedManualRevision": 0})
        self.post("CCON-1", {"manualStatus": "WAITING INPUT", "note": "First",
                           "expectedManualRevision": 1})
        self.assertEqual(self.initial()["savedEmailDraft"], draft)
        self.assertEqual(self.initial()["manualRevision"], 2)

    def test_two_independent_desk_instances_cannot_both_succeed_with_same_token(self):
        instance_a = Desk(self.root)
        instance_b = Desk(self.root)
        barrier = threading.Barrier(2)
        results = []
        def write(store, note):
            barrier.wait()
            try:
                store.save("CCON-1", {"manualStatus": "IN PROGRESS", "note": note,
                                     "expectedManualRevision": 0})
                results.append("SAVED")
            except SaveConflict:
                results.append("CONFLICT")
        threads = [threading.Thread(target=write, args=(instance_a, "A")),
                   threading.Thread(target=write, args=(instance_b, "B"))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertCountEqual(results, ["SAVED", "CONFLICT"])
        self.assertEqual(self.initial()["manualRevision"], 1)

    def test_restart_keeps_cas_revision_and_private_manual_data(self):
        self.post("CCON-1", {"manualStatus": "NEEDS DECISION", "note": "Saved",
                           "expectedManualRevision": 0})
        restart = Desk(self.root)
        state = next(t for t in restart.view()["tasks"] if t["key"] == "CCON-1")
        self.assertEqual(state["manualRevision"], 1)
        self.assertEqual(state["note"], "Saved")
        with self.assertRaises(SaveConflict):
            restart.save("CCON-1", {"manualStatus": "DONE", "note": "Wrong",
                                   "expectedManualRevision": 0})

    def test_additive_migration_retains_legacy_table_rows(self):
        with tempfile.TemporaryDirectory(prefix="ccon-legacy-db-") as folder:
            database = Path(folder) / "ba_state.db"
            with sqlite3.connect(database) as con:
                con.executescript("""
                    CREATE TABLE tasks (
                    key TEXT PRIMARY KEY, snapshot TEXT NOT NULL,
                    manual_status TEXT NOT NULL DEFAULT 'AUTO',
                    note TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1,
                    position INTEGER NOT NULL DEFAULT 0,
                    imported_at TEXT NOT NULL, modified_at TEXT, email_draft TEXT);
                """)
                con.execute("INSERT INTO tasks(key,snapshot,manual_status,note,imported_at) "
                            "VALUES(?,?,?,?,?)",
                            ("CCON-1", '{"key":"CCON-1","summary":"Old issue"}',
                             "IN PROGRESS", "Old note", "2026-10-25T09:00:00Z"))
            desk = Desk(folder)
            task = desk.view()["tasks"][0]
            self.assertEqual(task["note"], "Old note")
            self.assertEqual(task["manualRevision"], 0)
            desk.save("CCON-1", {"manualStatus": "DONE", "note": "Old note",
                                "expectedManualRevision": 0})
            self.assertEqual(desk.view()["tasks"][0]["manualRevision"], 1)


if __name__ == "__main__":
    unittest.main()
