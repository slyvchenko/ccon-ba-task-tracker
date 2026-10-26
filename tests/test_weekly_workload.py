"""Synthetic weekly work-state tests. No real Jira or BA database access."""
import json
import os
from contextlib import closing
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from weekly_workload import weekly_report, _window


class WeeklyWorkloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-weekly-ba-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "ba_state.db"
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("""CREATE TABLE task_history(
                id INTEGER PRIMARY KEY,task_key TEXT NOT NULL,
                recorded_at TEXT NOT NULL,snapshot_json TEXT NOT NULL)""")
            conn.commit()
        self.append("CCON-11", "2026-10-18T10:00:00+00:00", "IN PROGRESS")
        self.append("CCON-12", "2026-10-18T10:00:00+00:00", "DONE")
        self.append("CCON-13", "2026-10-18T10:00:00+00:00", "WAITING INPUT")
        self.append("CCON-14", "2026-10-18T10:00:00+00:00", "IN PROGRESS")
        self.append("CCON-11", "2026-10-20T10:00:00+00:00", "DONE")
        self.append("CCON-12", "2026-10-21T10:00:00+00:00", "IN PROGRESS")
        self.append("CCON-13", "2026-10-22T10:00:00+00:00", "WAITING DEPENDENCY")
        self.append("CCON-14", "2026-10-22T10:00:00+00:00", "IN PROGRESS", False)
        self.append("CCON-15", "2026-10-23T10:00:00+00:00", "DONE")
        self.append("CCON-16", "2026-10-24T10:00:00+00:00", "AUTO")

    def append(self, key, timestamp, status, active=True, signal=None):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("INSERT INTO task_history(task_key,recorded_at,snapshot_json) "
                         "VALUES(?,?,?)", (
                             key, timestamp, json.dumps({
                                 "active": active, "manualStatus": status,
                                 "jiraStatus": "OPEN", "signal": signal,
                                 "note": "SYNTHETIC-PRIVATE-SUPPLIER-NOTE"})))
            conn.commit()

    def test_weekly_counts_include_blockers_and_rework_not_just_done(self):
        before = self.db.read_bytes()
        result = weekly_report(self.root, "2026-W43", today=date(2026,10,26))
        self.assertEqual(result["asOfWeekEnd"], {
            "workInProgress": 2, "blocked": 1, "completedState": 2})
        self.assertEqual(result["weeklyTransitions"]["completed"], 1)
        self.assertEqual(result["weeklyTransitions"]["reopened"], 1)
        self.assertEqual(result["weeklyTransitions"]["taskChanges"], 6)
        self.assertEqual(result["weeklyTransitions"]["historyEvents"], 6)
        self.assertEqual(result["blockerShareOfOpenPct"], 33.3)
        self.assertFalse(result["weekMayBeIncomplete"])
        self.assertTrue(result["metricsAreNotAgentPerformance"])
        self.assertEqual(self.db.read_bytes(), before)
        output = json.dumps(result)
        for secret in ("CCON-11", "SYNTHETIC-PRIVATE",str(self.root),
                       "task_key","snapshot_json"):
            self.assertNotIn(secret, output)

    def test_auto_signal_controls_blockers_and_completed_transitions(self):
        self.append("CCON-90", "2026-10-18T14:00:00+00:00",
                    "AUTO", signal="READY")
        self.append("CCON-90", "2026-10-23T14:00:00+00:00",
                    "AUTO", signal="DONE")
        self.append("CCON-91", "2026-10-23T15:00:00+00:00",
                    "AUTO", signal="WAIT")
        result=weekly_report(self.root,"2026-W43",today=date(2026,10,26))
        self.assertEqual(result["asOfWeekEnd"]["blocked"],2)
        self.assertEqual(result["asOfWeekEnd"]["completedState"],3)
        self.assertEqual(result["weeklyTransitions"]["completed"],2)

    def test_relative_path_and_sunday_week_are_supported(self):
        relative=Path(os.path.relpath(self.root,Path.cwd()))
        report=weekly_report(relative,"2026-W43",today=date(2026,10,25))
        self.assertTrue(report["weekMayBeIncomplete"])
        monday=weekly_report(relative,"2026-W43",today=date(2026,10,26))
        self.assertFalse(monday["weekMayBeIncomplete"])
        self.assertEqual(report["asOfWeekEnd"],monday["asOfWeekEnd"])

    def test_archived_task_return_can_complete_known_prior_work(self):
        self.append("CCON-92", "2026-10-18T14:00:00+00:00",
                    "AUTO", signal="READY")
        self.append("CCON-92", "2026-10-18T15:00:00+00:00",
                    "AUTO", active=False, signal="READY")
        self.append("CCON-92", "2026-10-23T16:00:00+00:00",
                    "AUTO", active=True, signal="DONE")
        metrics=weekly_report(self.root,"2026-W43",today=date(2026,10,26))
        self.assertEqual(metrics["weeklyTransitions"]["completed"],2)
        self.assertEqual(metrics["asOfWeekEnd"]["completedState"],3)

    def test_no_state_created_and_bad_week_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                weekly_report(directory, "2026-W43")
            self.assertFalse((Path(directory)/"ba_state.db").exists())
        for week in ("2026-W00","2026-W54","tomorrow","2026-43","2026-W3"):
            with self.subTest(week=week), self.assertRaises(ValueError):
                weekly_report(self.root,week)
        self.assertEqual(_window("2026-W43")[0].isoformat(),
                         "2026-10-19T00:00:00+00:00")

    def test_future_week_is_explicitly_incomplete_and_does_not_invent_data(self):
        result = weekly_report(self.root,"2026-W48",today=date(2026,10,26))
        self.assertTrue(result["weekMayBeIncomplete"])
        self.assertEqual(result["weeklyTransitions"]["completed"],0)


if __name__=="__main__":
    unittest.main()
