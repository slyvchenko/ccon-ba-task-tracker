"""Local performance protocol and durable monotonic SQLite revision tests."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import build_opener, ProxyHandler, Request
from urllib.error import HTTPError

from desk_store import Desk
from performance_smoke import synthetic_document, measure
from server import handler


class RevisionProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ccon-revision-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.desk = Desk(self.root)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.desk))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.opener = build_opener(ProxyHandler({}))

    def shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(self.base + path, data=data,
                          headers={"Origin": self.base, "Content-Type": "application/json"})
        with self.opener.open(request) as response:
            return json.load(response)

    def import_demo(self, count=3, when="2026-10-25T09:00:00+00:00"):
        payload = synthetic_document(count)
        payload["generatedAt"] = when
        (self.root / "inbox/CCON_BA_Snapshot.json").write_text(json.dumps(payload), encoding="utf-8")
        return self.request("/api/import", {})

    def test_revision_initial_small_and_persists_after_restart(self):
        self.assertEqual(self.request("/api/tasks/revision"), {"revision": 0, "error": ""})
        self.import_demo()
        full = self.request("/api/tasks")
        self.assertEqual(full["revision"], 1)
        token = self.request("/api/tasks/revision")
        self.assertEqual(token, {"revision": 1, "error": ""})
        self.assertEqual(len(full["tasks"]), 3)
        self.assertEqual(Desk(self.root).revision()["revision"], 1)
        self.request("/api/tasks/CCON-1", {"manualStatus": "IN PROGRESS", "note": "Manual"})
        self.assertEqual(self.request("/api/tasks/revision")["revision"], 2)
        self.assertEqual(Desk(self.root).revision()["revision"], 2)
        self.assertEqual(Desk(self.root).view()["tasks"][0]["note"], "Manual")

    def test_duplicate_snapshot_does_not_invalidate_cache_but_new_import_does(self):
        self.import_demo()
        self.import_demo()
        self.assertEqual(self.desk.revision()["revision"], 1)
        self.import_demo(when="2026-10-25T10:00:00+00:00")
        self.assertEqual(self.desk.revision()["revision"], 2)

    def test_failed_import_and_unknown_save_never_commit_partial_revision(self):
        self.import_demo()
        source = self.root / "inbox/CCON_BA_Snapshot.json"
        source.write_text("{broken-json", encoding="utf-8")
        with self.assertRaises(HTTPError) as caught:
            self.request("/api/import", {})
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.desk.revision()["revision"], 1)
        self.assertTrue(self.desk.revision()["error"])
        with self.assertRaises(HTTPError) as caught:
            self.request("/api/tasks/CCON-999", {"manualStatus": "DONE", "note": ""})
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.desk.revision()["revision"], 1)
        self.assertEqual(len(self.desk.view()["tasks"]), 3)

    def test_every_acknowledged_manual_save_advances_revision_without_draft_loss(self):
        self.import_demo()
        for index in range(5):
            self.request("/api/tasks/CCON-1", {
                "manualStatus": "IN PROGRESS", "note": f"note-{index}",
                "emailDraft": {"to": "", "subject": "", "body": f"draft-{index}"}})
        self.assertEqual(self.desk.revision()["revision"], 6)
        task = self.desk.view()["tasks"][0]
        self.assertEqual(task["note"], "note-4")
        self.assertEqual(task["savedEmailDraft"]["body"], "draft-4")
        self.request("/api/tasks/CCON-1", {"manualStatus": "WAITING INPUT", "note": "note-4"})
        task = self.desk.view()["tasks"][0]
        self.assertEqual(task["savedEmailDraft"]["body"], "draft-4")
        self.assertEqual(self.desk.revision()["revision"], 7)

    def test_concurrent_saves_are_serialized_and_monotonic(self):
        self.import_demo()
        errors = []
        def write(i):
            try:
                self.desk.save("CCON-1", {"manualStatus": "IN PROGRESS", "note": str(i)})
            except Exception as exc:
                errors.append(type(exc).__name__)
        threads = [threading.Thread(target=write, args=(i,)) for i in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(self.desk.revision()["revision"], 13)

    def test_revision_response_never_returns_full_issue_text_and_is_small(self):
        self.import_demo(count=250)
        revision = self.request("/api/tasks/revision")
        full = self.request("/api/tasks")
        payload = json.dumps(revision)
        self.assertNotIn("FAKE Supplier", payload)
        self.assertGreater(len(json.dumps(full)), len(payload) * 100)
        self.assertEqual(revision["revision"], full["revision"])

    def test_synthetic_only_benchmark_has_no_shared_runner_latency_gate(self):
        report = measure(20, iterations=3)
        self.assertEqual(report["syntheticTasks"], 20)
        self.assertGreater(report["full"]["responseBytes"], report["revision"]["responseBytes"])
        self.assertIn("p95Ms", report["full"])
        self.assertNotIn("pass", report)


if __name__ == "__main__":
    unittest.main()
