import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import build_opener, ProxyHandler

from apply_analysis import apply
from desk_store import Desk
from server import handler


class ReportIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ccon-review-"))
        (self.root / "data").mkdir()
        self.desk = Desk(self.root)
        self.snapshot_file = self.root / "inbox" / "CCON_BA_Snapshot.json"
        self.snapshot_file.write_text(json.dumps({
            "generatedAt": "2026-10-07T08:00:00+00:00",
            "tasks": [{"key": "CCON-1", "summary": "Integration",
                       "contextFingerprint": "f1"}]
        }), encoding="utf-8")
        self.desk.import_snapshot()
        (self.root / "data" / "jira_context.json").write_text(
            json.dumps({"complete": True, "issues": {"CCON-1": {"fingerprint": "f1"}}}),
            encoding="utf-8")
        self.analysis_file = self.root / "data" / "daily_analysis.json"
        self.analysis = {
            "signal": "READY",
            "reasonUk": "Є нова задача.",
            "nextActionUk": "Перевірити мапінг.",
            "missingInfo": ["Яке очікуване поле?"],
            "waitingRequired": False,
            "waitingOnUk": "",
            "needsEmail": False,
            "queueScore": 80,
            "evidence": [{"text": "Jira", "url": "https://example.com/CCON-1"}],
            "standardDescription": "",
            "emailDraft": {"to": "", "subject": "", "body": ""},
            "contextFingerprint": "f1",
        }

    def tearDown(self):
        assert self.root.name.startswith("ccon-review-")
        shutil.rmtree(self.root)

    def apply_current(self):
        self.analysis_file.write_text(
            json.dumps({"analyses": {"CCON-1": self.analysis}}), encoding="utf-8")
        apply(self.analysis_file, self.root)

    def test_successful_import_creates_delta_report_and_preserves_manual_state(self):
        self.desk.save("CCON-1", {"manualStatus": "IN PROGRESS", "note": "Keep"})
        self.apply_current()
        report = json.loads((self.root / "data" / "daily_review_report.json").read_text())
        self.assertEqual(report["summary"]["total"], 1)
        self.assertEqual(report["summary"]["NEW"], 1)
        self.assertEqual(report["summary"]["questionsAdded"], 1)
        self.assertEqual([item["code"] for item in report["warnings"]], ["BRIEF_MISSING"])
        task = self.desk.view()["tasks"][0]
        self.assertEqual(task["manualStatus"], "IN PROGRESS")
        self.assertEqual(task["note"], "Keep")

    def test_invalid_score_preserves_last_report_and_snapshot(self):
        self.apply_current()
        report_path = self.root / "data" / "daily_review_report.json"
        original_report = report_path.read_bytes()
        original_snapshot = self.snapshot_file.read_bytes()
        self.analysis["queueScore"] = 101
        with self.assertRaisesRegex(ValueError, "0 to 100"):
            self.apply_current()
        self.assertEqual(report_path.read_bytes(), original_report)
        self.assertEqual(self.snapshot_file.read_bytes(), original_snapshot)

    def test_http_report_endpoints_and_missing_report(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.desk))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        root_url = "http://127.0.0.1:" + str(server.server_port)
        opener = build_opener(ProxyHandler({}))
        try:
            with opener.open(root_url + "/api/daily-report") as result:
                missing = json.load(result)
                self.assertFalse(missing["available"])
            self.apply_current()
            with opener.open(root_url + "/api/daily-report") as result:
                report = json.load(result)
                self.assertEqual(report["summary"]["NEW"], 1)
            with opener.open(root_url + "/api/daily-report.md") as result:
                self.assertIn("CCON-1", result.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
