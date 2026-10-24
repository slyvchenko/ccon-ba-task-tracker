import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from jira_sync import sync
from test_jira_sync import FakeJira
from review_report import build_report


class DepartedIssueTests(unittest.TestCase):
    def test_removed_issue_requires_verified_jira_done(self):
        previous = {
            "CCON-1": {"key": "CCON-1", "summary": "Completed ticket",
                       "manualStatus": "IN PROGRESS", "analysis": {"signal": "READY"}},
            "CCON-2": {"key": "CCON-2", "summary": "Unassigned ticket",
                       "manualStatus": "AUTO", "analysis": {"signal": "WAIT"}},
        }
        cases = [
            {"key": "CCON-1", "confirmedDone": True, "verification": "VERIFIED",
             "jiraStatus": "Done", "sourceUrl": "https://jira.example/CCON-1"},
            {"key": "CCON-2", "confirmedDone": False, "verification": "VERIFIED",
             "jiraStatus": "In Progress", "sourceUrl": "https://jira.example/CCON-2"},
        ]
        report = build_report(previous, [], "2026-10-24T12:00:00Z", cases)
        self.assertEqual(report["summary"]["JIRA_DONE"], 1)
        self.assertEqual(report["summary"]["LEFT_SCOPE"], 1)
        self.assertEqual([x["category"] for x in report["changes"]],
                         ["JIRA_DONE", "LEFT_SCOPE"])
        self.assertEqual(report["summary"]["warnings"], 1)
        self.assertEqual(report["changes"][0]["manualStatus"], "IN PROGRESS")

    def test_sync_reads_departed_issue_status_without_writing_jira(self):
        class DepartedJira(FakeJira):
            def get(self, path, params=None):
                if path.endswith("/issue/CCON-1"):
                    return {"key": "CCON-1", "fields": {
                        "status": {"name": "Done", "statusCategory": {"key": "done"}},
                        "resolution": {"name": "Fixed"},
                    }}
                return super().get(path, params)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.dict("os.environ", {"CCON_JIRA_BOARD_ID": ""}):
                first = sync(root, DepartedJira())
                self.assertEqual(first["retrievedCount"], 2)
                with patch("jira_sync.fetch_issues", return_value={
                    "CCON-2": DepartedJira().second}):
                    second = sync(root, DepartedJira())
            self.assertEqual(second["leftScopeCount"], 1)
            self.assertEqual(second["confirmedDoneSinceLastSync"], 1)
            cache = json.loads((root / "data/jira_context.json").read_text())
            self.assertEqual(cache["leftScope"][0]["key"], "CCON-1")
            self.assertTrue(cache["leftScope"][0]["confirmedDone"])
            self.assertEqual(cache["leftScope"][0]["verification"], "VERIFIED")

    def test_unavailable_status_does_not_claim_done(self):
        report = build_report({"CCON-1": {"key": "CCON-1", "summary": "Previous"}},
                              [], "2026-10-24T12:00:00Z",
                              [{"key": "CCON-1", "verification": "UNAVAILABLE",
                                "confirmedDone": False, "statusCategory": "unknown"}])
        self.assertEqual(report["summary"]["JIRA_DONE"], 0)
        self.assertEqual(report["summary"]["LEFT_SCOPE"], 1)


if __name__ == "__main__":
    unittest.main()
