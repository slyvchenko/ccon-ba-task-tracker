"""Synthetic weekly work-state tests. No real Jira or BA database access."""
import io
import json
from contextlib import redirect_stderr, redirect_stdout
import os
import shutil
from contextlib import closing
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from weekly_workload import weekly_report, _window, main


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

    def append(self, key, timestamp, status, active=True, signal=None, fresh=True, jira_status="OPEN"):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("INSERT INTO task_history(task_key,recorded_at,snapshot_json) "
                         "VALUES(?,?,?)", (
                             key, timestamp, json.dumps({
                                 "active": active, "manualStatus": status,
                                 "jiraStatus": jira_status, "signal": signal,
                                  "analysisVerified": bool(signal) and fresh,
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
        # Windows runner workspace may be on D: while temp DB is on C:.
        # Create a separate synthetic relative fixture on the current drive.
        with tempfile.TemporaryDirectory(prefix="tmp-week-relative-", dir=Path.cwd() / "tests") as folder:
            shutil.copyfile(self.db, Path(folder) / "ba_state.db")
            relative=Path(os.path.relpath(folder,Path.cwd()))
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

    def test_stale_auto_done_is_reopened_not_counted_as_completed(self):
        self.append("CCON-93", "2026-10-18T13:00:00+00:00",
                    "AUTO", signal="DONE", fresh=True)
        self.append("CCON-93", "2026-10-23T13:00:00+00:00",
                    "AUTO", signal="DONE", fresh=False)
        values=weekly_report(self.root,"2026-W43",today=date(2026,10,26))
        self.assertEqual(values["weeklyTransitions"]["reopened"],2)
        self.assertEqual(values["asOfWeekEnd"]["workInProgress"],3)
        self.assertEqual(values["asOfWeekEnd"]["completedState"],2)

    def test_historical_freshness_matches_real_history_contract(self):
        from task_history import view_state
        task={"contextFingerprint":"new","analysis":{
            "signal":"WAIT", "reasonUk":"Synthetic BA analysis",
            "nextActionUk":"Investigate synthetic REST source",
            "contextFingerprint":"old"}}
        self.assertFalse(view_state(task)["analysisVerified"])
        task["analysis"]["contextFingerprint"]="new"
        self.assertTrue(view_state(task)["analysisVerified"])
        task["analysis"]["stale"]=True
        self.assertFalse(view_state(task)["analysisVerified"])

    def test_legacy_history_metadata_upgrade_is_not_a_fake_completion(self):
        self.append("CCON-94", "2026-10-18T13:00:00+00:00",
                    "AUTO", signal="DONE", fresh=True)
        # Simulate pre-v2.50.7 history that stored the signal, but did not
        # contain the analysisVerified freshness marker.
        with closing(sqlite3.connect(self.db)) as conn:
            ident, raw = conn.execute(
                "SELECT id,snapshot_json FROM task_history ORDER BY id DESC LIMIT 1"
            ).fetchone()
            value=json.loads(raw)
            del value["analysisVerified"]
            conn.execute("UPDATE task_history SET snapshot_json=? WHERE id=?",
                         (json.dumps(value),ident))
            conn.commit()
        self.append("CCON-94", "2026-10-23T13:00:00+00:00",
                    "AUTO", signal="DONE", fresh=True)
        state=weekly_report(self.root,"2026-W43",today=date(2026,10,26))
        self.assertEqual(state["weeklyTransitions"]["completed"],1)
        self.assertEqual(state["asOfWeekEnd"]["completedState"],3)

    def test_legacy_freshness_upgrade_does_not_hide_jira_completion(self):
        # A real Jira transition must not be discarded as a schema upgrade.
        self.append("CCON-95", "2026-10-18T13:00:00+00:00",
                    "AUTO", signal="DONE", jira_status="OPEN")
        with closing(sqlite3.connect(self.db)) as conn:
            ident, raw = conn.execute(
                "SELECT id,snapshot_json FROM task_history ORDER BY id DESC LIMIT 1"
            ).fetchone()
            state = json.loads(raw)
            del state["analysisVerified"]
            conn.execute("UPDATE task_history SET snapshot_json=? WHERE id=?",
                         (json.dumps(state), ident))
            conn.commit()
        self.append("CCON-95", "2026-10-23T13:00:00+00:00",
                    "AUTO", signal="DONE", jira_status="DONE")
        weekly = weekly_report(self.root, "2026-W43", today=date(2026, 10, 26))
        self.assertEqual(weekly["weeklyTransitions"]["completed"], 2)
        self.assertEqual(weekly["asOfWeekEnd"]["completedState"], 3)

    def test_invalid_cli_arguments_never_echo_private_paths_or_identifiers(self):
        for args in (
            ["--private-SYNTHETIC-PNR987", "SYNTHETIC-SECRET"],
            ["--root", str(self.root), "SYNTHETIC-SECRET-PNR"],
            ["--week", "2026-W43", "--unexpected", "/private/SYNTHETIC-SECRET"],
        ):
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = main(args)
            self.assertEqual(status, 1)
            output = stdout.getvalue() + stderr.getvalue()
            for secret in ("SYNTHETIC-SECRET", "SYNTHETIC-PNR987",
                           str(self.root), "/private/"):
                self.assertNotIn(secret, output)

    def test_wal_without_sidecars_fails_closed_before_read_only_connection(self):
        import shutil
        copy=self.root / "synthetic-wal-without-sidecars.db"
        shutil.copyfile(self.db,copy)
        # Snapshot tests only: mark the copied SQLite header as WAL without
        # creating any sidecar. The preview must not open it to create files.
        with copy.open("r+b") as stream:
            stream.seek(18)
            stream.write(bytes([2,2]))
        self.assertFalse(Path(str(copy)+"-shm").exists())
        original=self.root/"ba_state.db"
        alternate=self.root/"synthetic-normal-original.db"
        original.rename(alternate)
        copy.rename(original)
        try:
            with self.assertRaisesRegex(ValueError,"Read-only WAL sidecars unavailable"):
                weekly_report(self.root,"2026-W43",today=date(2026,10,27))
            self.assertFalse(Path(str(original)+"-shm").exists())
            self.assertFalse(Path(str(original)+"-wal").exists())
        finally:
            original.rename(copy)
            alternate.rename(original)

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
