"""Synthetic, local-only effort estimate persistence and conflict regression tests."""
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from desk_store import Desk, SaveConflict


class EffortPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ccon-effort-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Desk(self.root)
        self.snapshot("2026-10-25T10:00:00Z")

    def snapshot(self, when):
        value = {"generatedAt": when,
            "tasks": [{"key":"CCON-100", "summary":"Synthetic issue"},
                      {"key":"CCON-200", "summary":"Synthetic second issue"}]}
        (self.store.inbox / "CCON_BA_Snapshot.json").write_text(
            json.dumps(value), encoding="utf-8")
        return self.store.import_snapshot()

    def current(self, key="CCON-100"):
        return next(x for x in self.store.view()["tasks"] if x["key"] == key)

    def test_manual_band_persists_save_reload_and_independent_second_task(self):
        self.assertEqual(self.current()["manualEffort"], "UNKNOWN")
        for index, band in enumerate(("XS","S","M","L","XL","UNKNOWN")):
            ack = self.store.save("CCON-100", {
                "manualStatus":"IN PROGRESS", "note":"Synthetic note",
                "manualEffort":band, "expectedManualRevision":index})
            self.assertEqual(ack["manualRevision"], index+1)
            self.assertEqual(self.current()["manualEffort"], band)
            self.assertEqual(self.current()["note"], "Synthetic note")
            self.assertEqual(Desk(self.root).view()["tasks"][0]["manualEffort"], band)
        self.assertEqual(self.current("CCON-200")["manualEffort"], "UNKNOWN")

    def test_changing_status_only_keeps_prior_effort_and_saved_mail(self):
        draft={"to":"fake@example.invalid","subject":"Demo","body":"Synthetic note"}
        self.store.save("CCON-100",{"manualStatus":"IN PROGRESS", "note":"",
              "manualEffort":"L", "emailDraft":draft, "expectedManualRevision":0})
        self.store.save("CCON-100",{"manualStatus":"WAITING INPUT","note":"",
              "expectedManualRevision":1})
        self.assertEqual(self.current()["manualEffort"],"L")
        self.assertEqual(self.current()["savedEmailDraft"],draft)

    def test_import_does_not_overwrite_manual_effort_or_trigger_cas(self):
        self.store.save("CCON-100",{"manualStatus":"IN PROGRESS","note":"Manual",
              "manualEffort":"XL","expectedManualRevision":0})
        self.snapshot("2026-10-25T11:00:00Z")
        self.assertEqual(self.current()["manualEffort"],"XL")
        self.assertEqual(self.current()["manualRevision"],1)
        self.store.save("CCON-100",{"manualStatus":"DONE","note":"Manual",
              "expectedManualRevision":1})
        self.assertEqual(self.current()["manualEffort"],"XL")

    def test_invalid_effort_input_is_atomic(self):
        before=self.store.view()
        for value in (None,True,0,"", "two days", "xs",["S"],{}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.save("CCON-100",{"manualStatus":"DONE","note":"Bad",
                            "manualEffort":value,"expectedManualRevision":0})
            self.assertEqual(self.store.view(),before)

    def test_stale_second_editor_cannot_overwrite_effort(self):
        first=Desk(self.root)
        second=Desk(self.root)
        first.save("CCON-100",{"manualStatus":"IN PROGRESS","note":"Saved",
                   "manualEffort":"M","expectedManualRevision":0})
        with self.assertRaises(SaveConflict):
            second.save("CCON-100",{"manualStatus":"DONE","note":"Stale",
                         "manualEffort":"XS","expectedManualRevision":0})
        self.assertEqual(self.current()["manualEffort"],"M")
        self.assertEqual(self.current()["manualRevision"],1)

    def test_legacy_db_migration_is_additive_and_preserves_existing_edits(self):
        with tempfile.TemporaryDirectory(prefix="ccon-effort-old-") as folder:
            location=Path(folder)/"ba_state.db"
            with closing(sqlite3.connect(location)) as con, con:
                con.executescript("""
                CREATE TABLE tasks (
                    key TEXT PRIMARY KEY, snapshot TEXT NOT NULL,
                    manual_status TEXT NOT NULL DEFAULT 'AUTO', note TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1, position INTEGER NOT NULL DEFAULT 0,
                    imported_at TEXT NOT NULL, modified_at TEXT, email_draft TEXT,
                    manual_revision INTEGER NOT NULL DEFAULT 0);
                """)
                con.execute("INSERT INTO tasks (key,snapshot,manual_status,note,imported_at) "
                           "VALUES (?,?,?,?,?)",("CCON-555",
                           '{"key":"CCON-555","summary":"Old synthetic"}',
                           "WAITING INPUT","Past note","2026-10-20T12:00:00Z"))
            migrated=Desk(folder)
            restored=migrated.view()["tasks"][0]
            self.assertEqual(restored["note"],"Past note")
            self.assertEqual(restored["manualEffort"],"UNKNOWN")
            migrated.save("CCON-555",{"manualStatus":"IN PROGRESS", "note":"Past note",
                                     "manualEffort":"S","expectedManualRevision":0})
            self.assertEqual(migrated.view()["tasks"][0]["manualEffort"],"S")


if __name__ == "__main__":
    unittest.main()
