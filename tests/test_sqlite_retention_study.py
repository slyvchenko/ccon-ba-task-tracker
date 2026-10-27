"""Synthetic SQLite study and history retention preview regression."""
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from desk_store import Desk
from history_retention_preview import preview
from sqlite_mode_study import evaluate


class SqliteModeStudyTests(unittest.TestCase):
    def test_four_synthetic_scenarios_are_integrity_checked_without_live_switch(self):
        result = evaluate(10, 3)
        self.assertTrue(result["syntheticOnly"])
        self.assertEqual(result["recommendation"], "EVALUATE_ONLY_NO_PRODUCTION_SWITCH")
        self.assertEqual(len(result["results"]), 4)
        self.assertEqual({x["journal"] for x in result["results"]}, {"DELETE", "WAL"})
        self.assertEqual({x["syntheticJsonIndex"] for x in result["results"]},
                         {True, False})
        self.assertTrue(all(x["backupIntegrity"] == "ok" for x in result["results"]))
        self.assertTrue(all(x["matchingSyntheticRows"] == 3 for x in result["results"]))
        self.assertTrue(all(not x["liveConfigurationChanged"] for x in result["results"]))
        self.assertTrue(all(x["busyTimeoutMs"] == 10000 for x in result["results"]))
        self.assertTrue(all(x["p95QueryMs"] >= 0 for x in result["results"]))
        self.assertTrue(all(x["queryUsesIndex"] for x in result["results"]
                            if x["syntheticJsonIndex"]))
        self.assertTrue(all(not x["queryUsesIndex"] for x in result["results"]
                            if not x["syntheticJsonIndex"]))

    def test_input_bounds_prevent_accidental_large_study(self):
        for count, iterations in [(0,3),(1001,3),(10,2),(10,21),(True,3)]:
            with self.subTest(count=count,iterations=iterations), self.assertRaises(ValueError):
                evaluate(count,iterations)


class RetentionPreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ccon-synthetic-retention-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.desk = Desk(self.root)
        source = self.desk.inbox / "CCON_BA_Snapshot.json"
        source.write_text(json.dumps({
            "generatedAt": "2026-10-20T12:00:00Z",
            "tasks": [{"key":"CCON-1","summary":"SECRET-SYNTHETIC-TICKET"},
                      {"key":"CCON-2","summary":"Synthetic second"}]
        }),encoding="utf-8")
        self.desk.import_snapshot()
        self.desk.save("CCON-1",{
            "manualStatus":"IN PROGRESS",
            "note":"PRIVATE-SYNTHETIC-NOTE",
            "expectedManualRevision":0})
        self.desk.save("CCON-1",{
            "manualStatus":"WAITING INPUT",
            "note":"PRIVATE-SYNTHETIC-SECOND",
            "expectedManualRevision":1})
        # Deliberately age every revision; last per-task must remain protected.
        with self.desk.connect() as conn:
            conn.execute("UPDATE task_history SET recorded_at=?",
                         ("2020-01-01T00:00:00+00:00",))

    def test_preview_preserves_latest_per_task_and_never_mutates(self):
        before = hashlib.sha256(self.desk.db.read_bytes()).hexdigest()
        result = preview(self.root,365,now=datetime(2026,10,26,tzinfo=timezone.utc))
        after = hashlib.sha256(self.desk.db.read_bytes()).hexdigest()
        self.assertEqual(before,after)
        self.assertEqual(result["totalHistoryRevisions"],4)
        self.assertEqual(result["eligibleOlderRevisions"],2)
        self.assertEqual(result["eligibleByOrigin"]["MANUAL"],1)
        self.assertEqual(result["eligibleByOrigin"]["IMPORT"],1)
        self.assertEqual(result["importAuditEntriesPreserved"],1)
        self.assertEqual(result["deleted"],0)
        self.assertEqual(result["archived"],0)
        self.assertEqual(result["policy"],"ALWAYS_PRESERVE_LATEST_PER_TASK")
        text=json.dumps(result)
        for secret in ("CCON-1","SECRET-SYNTHETIC","PRIVATE-SYNTHETIC",
                       str(self.root),"example.invalid"):
            self.assertNotIn(secret,text)
        with self.desk.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM task_history").fetchone()[0],4)

    def test_relative_root_accepted_and_read_counts_use_single_snapshot(self):
        from unittest.mock import patch
        from history_retention_preview import preview
        actual_connect=sqlite3.connect
        observed=[]
        class ProbeConnection(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                if sql.strip().upper().startswith("SELECT"):
                    observed.append(("SELECT",self.in_transaction))
                elif sql.strip().upper()=="BEGIN":
                    observed.append(("BEGIN",self.in_transaction))
                return super().execute(sql,parameters)
        def connection(*args,**kwargs):
            return actual_connect(*args,**{**kwargs,"factory":ProbeConnection})
        prior=Path.cwd()
        try:
            os.chdir(self.root.parent)
            with patch("history_retention_preview.sqlite3.connect",side_effect=connection):
                result=preview(self.root.name,365,now=datetime(2026,10,26,tzinfo=timezone.utc))
        finally:
            os.chdir(prior)
        self.assertEqual(result["totalHistoryRevisions"],4)
        self.assertTrue(observed and observed[0][0]=="BEGIN")
        self.assertTrue(all(inside for operation,inside in observed if operation=="SELECT"))

    def test_preview_does_not_write_or_create_db(self):
        with tempfile.TemporaryDirectory(prefix="ccon-empty-preview-") as folder:
            with self.assertRaises(ValueError):
                preview(folder)
            self.assertFalse((Path(folder)/"ba_state.db").exists())
        for days in (0,29,3651,True):
            with self.assertRaises(ValueError):
                preview(self.root,days)

    def test_unknown_timezones_are_rejected(self):
        with self.assertRaises(ValueError):
            preview(self.root,365,now=datetime(2026,10,26))


if __name__=="__main__":
    unittest.main()
