"""Synthetic-only HTTP question CAS regressions; never use private source payloads."""
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener

from ba_questions import read_questions, sync_questions
from desk_store import Desk
from server import handler


class QuestionHTTPCASTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ccon-question-cas-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        (self.root / "data/jira_context.json").write_text(json.dumps({
            "complete": True,
            "issues": {"CCON-123": {"key": "CCON-123",
                                    "summary": "Synthetic supplier rule",
                                    "comments": []}}
        }), encoding="utf-8")
        self.key = sync_questions(self.root, "CCON-123", {
            "missingInfo": ["Confirm error response rule"]})["questions"][0]["id"]
        self.desk = Desk(self.root)
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.desk))
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.shutdown)
        self.base = "http://127.0.0.1:" + str(self.http.server_port)
        self.opener = build_opener(ProxyHandler({}))

    def shutdown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()

    def save(self, data):
        request = Request(self.base + "/api/questions/CCON-123/" + self.key,
                          data=json.dumps(data).encode("utf-8"), method="POST",
                          headers={"Origin": self.base, "Content-Type": "application/json"})
        with self.opener.open(request) as response:
            return json.load(response)

    def test_http_stale_edit_must_return_409_without_answer_leak(self):
        original = self.save({"status": "ANSWERED",
                              "answer": "First tab private synthetic answer",
                              "expectedManualRevision": 0})
        self.assertEqual(original["question"]["manualRevision"], 1)
        with self.assertRaises(HTTPError) as raised:
            self.save({"status": "ANSWERED", "answer": "Second tab stale answer",
                       "expectedManualRevision": 0})
        self.assertEqual(raised.exception.code, 409)
        payload = json.loads(raised.exception.read())
        self.assertEqual(payload["code"], "QUESTION_REVISION_CONFLICT")
        self.assertEqual(payload["currentManualRevision"], 1)
        self.assertNotIn("First tab", json.dumps(payload))
        saved = read_questions(self.root, "CCON-123")["questions"][0]
        self.assertEqual(saved["answer"], "First tab private synthetic answer")
        self.assertEqual(saved["manualRevision"], 1)
        self.assertEqual(self.save({
            "status": "ANSWERED", "answer": "Reviewed later answer",
            "expectedManualRevision": 1})["question"]["manualRevision"], 2)

    def test_missing_invalid_and_foreign_origin_fail_closed(self):
        with self.assertRaises(HTTPError) as missing:
            self.save({"status": "ANSWERED", "answer": "Unversioned stale"})
        self.assertEqual(missing.exception.code, 428)
        self.assertEqual(json.loads(missing.exception.read())["code"],
                         "QUESTION_REVISION_REQUIRED")
        for bad in (None, -1, True, "0", 1.2):
            with self.subTest(value=bad), self.assertRaises(HTTPError) as invalid:
                self.save({"status": "OPEN", "expectedManualRevision": bad})
            self.assertEqual(invalid.exception.code, 400)
        self.assertEqual(read_questions(self.root, "CCON-123")["questions"][0]["manualRevision"], 0)
        request = Request(self.base + "/api/questions/CCON-123/" + self.key,
                          data=json.dumps({"status": "OPEN",
                                           "expectedManualRevision": 0}).encode(),
                          method="POST", headers={"Origin": "https://evil.example"})
        with self.assertRaises(HTTPError) as foreign:
            self.opener.open(request)
        self.assertEqual(foreign.exception.code, 403)

    def test_get_returns_revision_but_never_semantic_verification(self):
        with self.opener.open(self.base + "/api/questions/CCON-123") as response:
            question = json.load(response)["questions"][0]
        self.assertEqual(question["manualRevision"], 0)
        self.assertFalse(question["answerVerified"])


if __name__ == "__main__":
    unittest.main()
