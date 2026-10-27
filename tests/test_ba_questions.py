import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from ba_questions import (sync_questions, read_questions, update_question,
                          question_id, proposed_questions, STATES)
from kibana_evidence import plan_for_issue, discover_links
from supplier_logs import flow_references


class QuestionsAndKibanaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()
        (self.root / "data/jira_context.json").write_text(json.dumps({
            "complete": True,
            "issues": {"CCON-123": {"key": "CCON-123", "summary": "AF/KL. retrievePNR",
                                    "fingerprint": "fp"}},
        }))

    def test_answers_not_inferred_from_disappearing_question(self):
        first = sync_questions(self.root, "CCON-123", {
            "missingInfo": ["Підтвердити стан CANCELLED"], "briefing": {"unknownsUk": ["Коли REMOVED?"]},
        })
        self.assertEqual(len(first["questions"]), 2)
        q = first["questions"][0]
        self.assertEqual(q["status"], "OPEN")
        second = sync_questions(self.root, "CCON-123", {"missingInfo": []})
        self.assertEqual(len(second["questions"]), 2)
        self.assertTrue(all(item["status"] == "OPEN" for item in second["questions"]))
        self.assertTrue(all(item["presentInLatestAnalysis"] is False for item in second["questions"]))

    def test_human_answer_updates_status_and_verification(self):
        data = sync_questions(self.root, "CCON-123", {"missingInfo": ["Чи потрібен код?"]})
        key = data["questions"][0]["id"]
        with self.assertRaisesRegex(ValueError, "written answer"):
            update_question(self.root, "CCON-123", key, status="ANSWERED")
        answer = update_question(self.root, "CCON-123", key, status="ANSWERED",
                                 owner="Supplier", answer="Так, потрібно.",
                                 evidence_url="https://jira.example/browse/CCON-123")
        self.assertTrue(answer["answerVerified"])
        self.assertEqual(read_questions(self.root, "CCON-123")["questions"][0]["status"], "ANSWERED")
        sync_questions(self.root, "CCON-123", {"missingInfo": ["Чи потрібен код?"]})
        self.assertEqual(read_questions(self.root, "CCON-123")["questions"][0]["status"], "ANSWERED")

    def test_question_updates_are_restricted_to_personal_scope(self):
        with self.assertRaisesRegex(ValueError, "personal"):
            sync_questions(self.root, "CCON-999", {"missingInfo": ["Unknown"]})
        with self.assertRaisesRegex(ValueError, "Invalid task key"):
            read_questions(self.root, "../evil")
        with self.assertRaisesRegex(ValueError, "Invalid question state"):
            update_question(self.root, "CCON-123", "Q-notfound", status="CLOSED")

    def test_evidence_questions_get_a_distinct_source(self):
        result = proposed_questions({"missingInfo": ["A"]}, [
            {"questionsUk": ["B", "A"]},
        ])
        self.assertEqual([i["text"] for i in result], ["A", "B"])
        self.assertEqual(result[1]["origin"], "LOG_EVIDENCE")

    def test_kibana_search_limits_and_known_user_flow_id(self):
        flow = "11111111-2222-4333-8444-555555555555"
        link = "http://192.168.197.246:5601/app/kibana#/discover?_a=(filters:!((meta:(key:cconFlowId,params:(query:'" + flow + "',type:phrase),value:'" + flow + "'),query:(match:(cconFlowId:(query:'" + flow + "'))))))"
        issue = {"key": "CCON-123", "summary": "AF/KL. retrievePNR",
                 "description": link,
                 "comments": [{"body": "Kibana error log: https://kibana.example.com/app/discover?error_log=yes"}]}
        with patch.dict(os.environ, {"CCON_KIBANA_ALLOWED_ORIGINS":
                                      "https://kibana.example.com"}):
            plan = plan_for_issue(issue)
            self.assertEqual(len(discover_links(issue)), 2)
        self.assertEqual(plan["supplier"]["name"], "AirFranceKLM")
        self.assertTrue(any(item["kind"] == "ERROR_SEARCH" and item["maxCases"] == 30
                            for item in plan["kibana"]))
        self.assertTrue(plan["flows"])
        with self.assertRaises(ValueError):
            plan_for_issue(issue, 31)

    def test_unapproved_lookalike_kibana_and_bad_port_are_never_actions(self):
        issue = {"key": "CCON-123", "summary": "AF/KL. retrievePNR",
                 "description": (
                     "https://kibana-victim.evil.test/app/discover "
                     "https://kibana.example.com.evil.test/app/discover "
                     "https://evil.test/kibana/app/discover "
                     "https://kibana.example.com:0/app/discover "
                     "https://kibana.example.com:invalid/app/discover "
                     "https://user:secret@kibana.example.com/app/discover "
                     "https://kibana.example.com/app/discover")}
        with patch.dict(os.environ, {"CCON_KIBANA_ALLOWED_ORIGINS":
                                      "https://kibana.example.com"}):
            links = discover_links(issue)
        self.assertEqual([x["url"] for x in links],
                         ["https://kibana.example.com/app/discover"])

    def test_unknown_kibana_origin_requires_explicit_local_configuration(self):
        issue = {"key": "CCON-123", "summary": "AF/KL. retrievePNR",
                 "description": "https://kibana.example.com/app/discover"}
        with patch.dict(os.environ, {"CCON_KIBANA_ALLOWED_ORIGINS": ""}):
            self.assertEqual(discover_links(issue), [])
        with patch.dict(os.environ, {"CCON_KIBANA_ALLOWED_ORIGINS":
                                      "https://kibana.example.com/path,"
                                      "https://kibana.example.com.evil.test"}):
            self.assertEqual(discover_links(issue), [])
        with patch.dict(os.environ, {"CCON_KIBANA_ALLOWED_ORIGINS":
                                      "https://kibana.example.com"}):
            self.assertEqual(len(discover_links(issue)), 1)

    def test_approved_origin_never_authorizes_arbitrary_kibana_get_routes(self):
        # This list is all on a locally approved origin, but only views may
        # become local browser actions. A GET URL is not inherently read-only.
        urls = [
            "https://kibana.example.com/api/saved_objects/_find",
            "https://kibana.example.com/api/actions/connector/trigger",
            "https://kibana.example.com/internal/security/session",
            "https://kibana.example.com/app/management",
            "https://kibana.example.com/login",
            "https://kibana.example.com/app/discover-extra",
            "https://kibana.example.com/app/discover/../api/delete",
            "https://kibana.example.com/app/discover",
            "https://kibana.example.com/app/kibana#/discover",
            "https://kibana.example.com/app/discover/?_a=errors",
        ]
        issue = {"description": " ".join(urls), "comments": []}
        with patch.dict(os.environ, {"CCON_KIBANA_ALLOWED_ORIGINS":
                                      "https://kibana.example.com"}):
            found = discover_links(issue)
        self.assertEqual({i["url"] for i in found}, set(urls[-3:]))
        self.assertTrue(all(i["kind"] in ("SEARCH", "ERROR_SEARCH") for i in found))

    def test_unknown_supplier_never_follows_other_provider_folder(self):
        issue = {"key": "CCON-123", "summary": "Unknown. retrieve"}
        plan = plan_for_issue(issue)
        self.assertIsNone(plan["supplier"])
        self.assertTrue(any("постачальника" in x for x in plan["questionsUk"]))


if __name__ == "__main__":
    unittest.main()
