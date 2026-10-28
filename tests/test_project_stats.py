"""Synthetic-only dashboard statistics regression and HTTP privacy test."""
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from desk_store import Desk
from project_stats import statistics_report, task_signal
from server import handler


class ProjectStatsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ccon-stats-")
        self.addCleanup(self.tmp.cleanup)
        self.desk = Desk(self.tmp.name)
        self.source = Path(self.tmp.name) / "inbox/CCON_BA_Snapshot.json"

    def import_tasks(self, date, tasks):
        self.source.write_text(json.dumps({"generatedAt": date,
                                           "tasks": tasks}), encoding="utf-8")
        self.desk.import_snapshot()

    def test_missing_snapshot_is_explicit_not_fake_zero_success(self):
        report = statistics_report(self.desk)
        self.assertFalse(report["tasks"]["snapshotAvailable"])
        self.assertEqual(report["tasks"]["active"], 0)
        self.assertEqual(report["project"]["requirements"], 129)
        self.assertFalse(report["project"]["releaseApproved"])
        self.assertFalse(report["project"]["humanAcceptanceVerifiableHere"])
        self.assertEqual(report["project"]["goldCasesVerifiedHere"], 0)
        self.assertGreater(report["project"]["externalGateCount"], 0)

    def test_active_archive_manual_done_and_action_lanes_are_disjoint(self):
        self.import_tasks("2026-10-27T12:00:00Z", [
            {"key":"CCON-1","summary":"PRIVATE TEST ONLY one",
             "activeSprintStatus":"VERIFIED","activeSprint":True,
             "analysis":{"signal":"WRITE"}},
            {"key":"CCON-2","summary":"PRIVATE TEST ONLY two",
             "analysis":{"signal":"READY"}},
            {"key":"CCON-3","summary":"PRIVATE TEST ONLY three",
             "analysis":{"signal":"DECIDE"}},
            {"key":"CCON-4","summary":"PRIVATE TEST ONLY four"},
            {"key":"CCON-5","summary":"PRIVATE TEST ONLY archive later"}
        ])
        self.desk.save("CCON-2", {"manualStatus": "WAITING INPUT", "note": "private note",
                                  "expectedManualRevision": 0})
        self.desk.save("CCON-3", {"manualStatus": "DONE", "note": "private done",
                                  "expectedManualRevision": 0})
        self.import_tasks("2026-10-28T12:00:00Z", [
            {"key":"CCON-1","summary":"PRIVATE TEST ONLY one",
             "activeSprintStatus":"VERIFIED","activeSprint":True,
             "analysis":{"signal":"WRITE"}},
            {"key":"CCON-2","summary":"PRIVATE TEST ONLY two",
             "analysis":{"signal":"READY"}},
            {"key":"CCON-3","summary":"PRIVATE TEST ONLY three",
             "analysis":{"signal":"DECIDE"}},
            {"key":"CCON-4","summary":"PRIVATE TEST ONLY four"}
        ])
        result = statistics_report(self.desk)
        tasks = result["tasks"]
        self.assertEqual((tasks["loaded"], tasks["active"], tasks["archived"]), (5, 4, 1))
        self.assertEqual((tasks["unfinished"], tasks["done"]), (3, 1))
        self.assertEqual(tasks["signalCounts"]["WRITE"], 1)
        self.assertEqual(tasks["signalCounts"]["WAIT"], 1)
        self.assertEqual(tasks["signalCounts"]["OTHER"], 1)
        self.assertEqual(sum(tasks["signalCounts"].values()), 3)
        self.assertEqual(tasks["activeVerifiedSprint"], 1)
        self.assertEqual(tasks["manualStatusCounts"]["WAITING INPUT"], 1)
        self.assertEqual(tasks["manualStatusCounts"]["DONE"], 1)
        self.assertEqual(tasks["snapshotGeneratedAt"], "2026-10-28T12:00:00Z")
        self.assertEqual(tasks["withoutAnalysis"], 1)
        self.assertNotIn("CCON-1", json.dumps(result))
        self.assertNotIn("PRIVATE TEST", json.dumps(result))
        self.assertNotIn("private note", json.dumps(result))

    def test_http_stats_returns_aggregate_and_no_remote_host_access(self):
        self.import_tasks("2026-10-28T09:00:00Z", [
            {"key":"CCON-999","summary":"NEVER RETURN SOURCE NAME",
             "analysis":{"signal":"READY"}}])
        http = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.desk))
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            base = "http://127.0.0.1:" + str(http.server_port)
            opener = build_opener(ProxyHandler({}))
            with opener.open(base + "/api/stats") as response:
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                raw = response.read().decode()
                self.assertNotIn("CCON-999", raw)
                self.assertNotIn("NEVER RETURN", raw)
                self.assertEqual(json.loads(raw)["tasks"]["active"], 1)
            with self.assertRaises(HTTPError) as denied:
                opener.open(Request(base + "/api/stats",
                                    headers={"Host": "evil.example"}))
            self.assertEqual(denied.exception.code, 403)
        finally:
            http.shutdown()
            http.server_close()
            thread.join()

    def test_waiting_manual_status_takes_precedence_over_AI_signal(self):
        self.assertEqual(task_signal({"manualStatus": "WAITING DEPENDENCY",
                                      "analysis": {"signal": "WRITE"}}), "WAIT")


if __name__ == "__main__":
    unittest.main()
