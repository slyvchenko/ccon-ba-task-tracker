import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sprint_priority import active_sprint_snapshot, sprint_fields, validate_board_id, load_board_id
from jira_sync import sync
from test_jira_sync import FakeJira


class FakeSprintClient:
    def __init__(self):
        self.calls = []
        self.sprint_pages = [
            {"startAt": 0, "isLast": True,
             "values": [{"id": 101, "name": "CCON Sprint 25", "state": "active"},
                        {"id": 102, "name": "Parallel Sprint", "state": "active"}]}
        ]

    def get(self, path, params=None):
        self.calls.append((path, copy.deepcopy(params)))
        if path.endswith("/sprint"):
            return self.sprint_pages[0]
        if path.endswith("/101/issue"):
            if params.get("nextPageToken") == "next":
                return {"issues": [{"key": "CCON-2"}], "isLast": True}
            return {"issues": [{"key": "CCON-1"}], "isLast": False,
                    "nextPageToken": "next"}
        if path.endswith("/102/issue"):
            return {"issues": [{"key": "CCON-2"}], "isLast": True}
        raise AssertionError("Unexpected " + path)


class SprintTests(unittest.TestCase):
    def test_validates_explicit_board_id(self):
        self.assertIsNone(validate_board_id(None))
        self.assertEqual(validate_board_id("345"), 345)
        for wrong in ("-1", "abc", 0, True):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                validate_board_id(wrong)

    def test_board_config_survives_process_restart_without_env(self):
        import json
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            (root / '.jira-board.json').write_text(json.dumps({'boardId': 12}))
            with patch.dict(os.environ, {'CCON_JIRA_BOARD_ID': ''}):
                self.assertIsNone(load_board_id(root))
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(load_board_id(root), 12)
            with patch.dict(os.environ, {'CCON_JIRA_BOARD_ID': '55'}):
                self.assertEqual(load_board_id(root), 55)
    def test_unconfigured_board_never_guesses_membership(self):
        client = FakeSprintClient()
        result = active_sprint_snapshot(client, None)
        self.assertEqual(result["status"], "NOT_CONFIGURED")
        self.assertIsNone(sprint_fields(result, "CCON-1")["activeSprint"])
        self.assertEqual(client.calls, [])

    def test_board_sprints_and_issue_pagination(self):
        client = FakeSprintClient()
        result = active_sprint_snapshot(client, 12)
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["boardId"], 12)
        self.assertEqual(sprint_fields(result, "CCON-1")["activeSprintIds"], [101])
        self.assertEqual(sprint_fields(result, "CCON-2")["activeSprintIds"], [101, 102])
        self.assertFalse(sprint_fields(result, "CCON-3")["activeSprint"])

    def test_incomplete_sprint_issue_pagination_fails_closed(self):
        class Broken(FakeSprintClient):
            def get(self, path, params=None):
                if path.endswith("/101/issue"):
                    return {"issues": [{"key": "CCON-1"}], "isLast": False}
                return super().get(path, params)
        with self.assertRaisesRegex(ValueError, "pagination"):
            active_sprint_snapshot(Broken(), 12)

    def test_no_active_sprint_is_verified_empty(self):
        client = FakeSprintClient()
        client.sprint_pages = [{"startAt": 0, "isLast": True, "values": []}]
        result = active_sprint_snapshot(client, 12)
        self.assertEqual(result["status"], "VERIFIED")
        self.assertFalse(sprint_fields(result, "CCON-1")["activeSprint"])

    def test_sync_adds_verified_membership_without_analysing_out_of_scope_issues(self):
        class JiraAndSprint(FakeJira):
            def get(self, path, params=None):
                if path.startswith("/rest/agile/") or path.startswith("/rest/software/"):
                    if path.endswith("/sprint"):
                        return {"startAt": 0, "isLast": True,
                                "values": [{"id": 101, "name": "Sprint priority", "state": "active"}]}
                    return {"issues": [{"key": "CCON-2"}, {"key": "CCON-999"}], "isLast": True}
                return super().get(path, params)
        with tempfile.TemporaryDirectory() as dirname:
            with patch.dict(os.environ, {"CCON_JIRA_BOARD_ID": "12"}):
                result = sync(Path(dirname), JiraAndSprint())
            self.assertEqual(result["activeSprintStatus"], "VERIFIED")
            self.assertEqual(result["activeSprintTaskCount"], 1)
            import json
            snap = json.loads((Path(dirname) / "inbox/CCON_BA_Snapshot.json").read_text())
            tasks = {task["key"]: task for task in snap["tasks"]}
            self.assertFalse(tasks["CCON-1"]["activeSprint"])
            self.assertTrue(tasks["CCON-2"]["activeSprint"])
            self.assertEqual(len(tasks), 2)


if __name__ == "__main__":
    unittest.main()
