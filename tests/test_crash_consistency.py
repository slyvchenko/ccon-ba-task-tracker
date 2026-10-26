"""Crash-boundary drills on synthetic local SQLite only.

Child processes are explicitly terminated at a known transaction boundary.
No real BA records, browser profiles, supplier logs or network calls.
"""
import json
import queue
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from app_config import ROOT
from desk_store import Desk
from local_backup import CONFIRM, backup_status, create_backup, restore_backup, verify_backup
import local_backup

WORKER = r'''
import sys, time
from unittest.mock import patch
from desk_store import Desk

root, mode = sys.argv[1:]
desk = Desk(root)
def before_commit(*_args, **_kwargs):
    print("BEFORE_COMMIT", flush=True)
    while True:
        time.sleep(0.1)

if mode == "save-before":
    with patch("desk_store.history_append", before_commit):
        desk.save("CCON-1", {
            "manualStatus": "WAITING INPUT", "note": "UNCOMMITTED SYNTHETIC NOTE",
            "emailDraft": {"to": "demo@example.invalid",
                           "subject": "Synthetic", "body": "UNCOMMITTED DRAFT"},
            "expectedManualRevision": 1})
elif mode == "import-before":
    with patch("desk_store.history_append", before_commit):
        desk.import_snapshot()
elif mode == "save-after":
    result = desk.save("CCON-1", {
        "manualStatus": "NEEDS DECISION", "note": "ACKNOWLEDGED SYNTHETIC NOTE",
        "emailDraft": {"to": "demo@example.invalid",
                       "subject": "Synthetic", "body": "ACKNOWLEDGED DRAFT"},
        "expectedManualRevision": 1})
    assert result["manualRevision"] == 2
    print("COMMITTED", flush=True)
    while True:
        time.sleep(0.1)
else:
    raise ValueError("Unsupported synthetic stage")
'''


class CrashConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ccon-transaction-crash-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.desk = Desk(self.root)
        self.snapshot = self.root / "inbox" / "CCON_BA_Snapshot.json"
        self.snapshot.write_text(json.dumps({
            "generatedAt": "2026-10-26T11:00:00Z",
            "tasks": [{"key": "CCON-1", "summary": "Baseline synthetic ticket"},
                      {"key": "CCON-2", "summary": "Independent ticket"}]
        }), encoding="utf-8")
        self.desk.import_snapshot()
        self.desk.save("CCON-1", {
            "manualStatus": "IN PROGRESS", "note": "CONFIRMED SYNTHETIC NOTE",
            "emailDraft": {"to": "verified@example.invalid",
                           "subject": "Verified", "body": "Confirmed draft"},
            "expectedManualRevision": 0
        })

    def state(self):
        restarted = Desk(self.root)
        with restarted.connect() as conn:
            self.assertEqual(conn.execute("PRAGMA quick_check").fetchone()[0], "ok")
            self.assertEqual(conn.execute("PRAGMA synchronous").fetchone()[0], 2)
            history = conn.execute(
                "SELECT COUNT(*) FROM task_history").fetchone()[0]
            imports = conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0]
        task = next(x for x in restarted.view()["tasks"] if x["key"] == "CCON-1")
        return task, restarted.revision()["revision"], history, imports

    def interrupt(self, mode, expect):
        # Use an independent subprocess so sqlite rollback journals are
        # recovered exactly as after an unexpected native process termination.
        process = subprocess.Popen(
            [sys.executable, "-u", "-c", WORKER, str(self.root), mode],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=str(ROOT))
        notice = queue.Queue(maxsize=1)
        reader = threading.Thread(target=lambda: notice.put(process.stdout.readline()),
                                  daemon=True)
        reader.start()
        try:
            try:
                announcement = notice.get(timeout=12).strip()
            except queue.Empty:
                self.fail(f"Synthetic worker did not reach {mode} crash boundary")
            self.assertEqual(announcement, expect)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            reader.join(timeout=2)
            process.stdout.close()
            process.stderr.close()

    def test_uncommitted_save_is_rolled_back_after_process_termination(self):
        before = self.state()
        self.interrupt("save-before", "BEFORE_COMMIT")
        after = self.state()
        self.assertEqual(after, before)
        self.assertEqual(after[0]["note"], "CONFIRMED SYNTHETIC NOTE")
        self.assertEqual(after[0]["savedEmailDraft"]["body"], "Confirmed draft")

    def test_uncommitted_import_rolls_back_all_rows_and_history(self):
        before = self.state()
        self.snapshot.write_text(json.dumps({
            "generatedAt": "2026-10-26T12:00:00Z",
            "tasks": [{"key": "CCON-1", "summary": "NEW UNCOMMITTED SNAPSHOT"},
                      {"key": "CCON-3", "summary": "Should never materialize"}]
        }), encoding="utf-8")
        self.interrupt("import-before", "BEFORE_COMMIT")
        after = self.state()
        self.assertEqual(after, before)
        self.assertEqual(len(Desk(self.root).view()["tasks"]), 2)

    def test_acknowledged_save_survives_abrupt_termination_and_restart(self):
        self.interrupt("save-after", "COMMITTED")
        task, version, history, imports = self.state()
        self.assertEqual(task["note"], "ACKNOWLEDGED SYNTHETIC NOTE")
        self.assertEqual(task["savedEmailDraft"]["body"], "ACKNOWLEDGED DRAFT")
        self.assertEqual(task["manualRevision"], 2)
        self.assertEqual(version, 3)
        self.assertEqual(history, 4)
        self.assertEqual(imports, 1)

    def test_database_publish_without_eligibility_manifest_is_not_restorable(self):
        good = create_backup(self.root, force=True, keep=0)
        original = local_backup._publish
        calls = []
        def interrupted(source, target):
            calls.append(Path(target).name)
            if str(target).endswith(".json"):
                raise OSError("synthetic interruption before manifest publication")
            return original(source, target)
        with patch("local_backup._publish", side_effect=interrupted):
            with self.assertRaises(OSError):
                create_backup(self.root, force=True, keep=0)
        self.assertEqual(len(calls), 2)
        self.assertTrue(verify_backup(self.root, good["filename"])["verified"])
        self.assertTrue(backup_status(self.root)["available"])
        self.assertEqual(len(list((self.root/"backups").glob("backup-*.sqlite3.json"))), 1)
        self.assertEqual(len(list((self.root/"backups").glob("backup-*.sqlite3"))), 2)
        later = create_backup(self.root, force=True, keep=0)
        self.assertTrue(verify_backup(self.root, later["filename"])["verified"])

    def test_restore_failure_before_atomic_replace_preserves_current_db(self):
        good = create_backup(self.root, force=True, keep=0)
        before = self.state()
        original = local_backup._publish
        def interrupted(source, target):
            if Path(target).name == "ba_state.db":
                raise OSError("synthetic interrupted final restore rename")
            return original(source, target)
        with patch("local_backup._publish", side_effect=interrupted):
            with self.assertRaises(OSError):
                restore_backup(self.root, good["filename"], CONFIRM)
        self.assertEqual(self.state(), before)
        self.assertFalse(list(self.root.glob("ba_state.db.*.pending")))
        self.assertTrue(verify_backup(self.root, good["filename"])["verified"])


if __name__ == "__main__":
    unittest.main()
