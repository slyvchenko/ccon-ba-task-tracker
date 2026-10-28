import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from ba_questions import (sync_questions, read_questions, update_question,
                          question_id, proposed_questions, question_write_lock,
                          QuestionConflict, STATES)
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
        self.assertFalse(answer["answerVerified"])
        self.assertTrue(answer["sourceLinkProvided"])
        self.assertEqual(read_questions(self.root, "CCON-123")["questions"][0]["status"], "ANSWERED")
        sync_questions(self.root, "CCON-123", {"missingInfo": ["Чи потрібен код?"]})
        self.assertEqual(read_questions(self.root, "CCON-123")["questions"][0]["status"], "ANSWERED")

    def test_legacy_true_verified_flag_is_downgraded_on_read_and_sync(self):
        first = sync_questions(self.root, "CCON-123", {
            "missingInfo": ["Confirm supplier evidence"]})
        identifier = first["questions"][0]["id"]
        path = self.root / "data/questions/CCON-123.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["questions"][0].update({
            "status": "ANSWERED", "answer": "Manually entered",
            "evidenceUrl": "https://unrelated.example.invalid/unverified",
            "answerVerified": True})
        path.write_text(json.dumps(value), encoding="utf-8")
        loaded = read_questions(self.root, "CCON-123")["questions"][0]
        self.assertFalse(loaded["answerVerified"])
        self.assertTrue(loaded["sourceLinkProvided"])
        self.assertEqual(loaded["answer"], "Manually entered")
        again = sync_questions(self.root, "CCON-123", {"missingInfo": []})
        preserved = next(q for q in again["questions"] if q["id"] == identifier)
        self.assertFalse(preserved["answerVerified"])
        self.assertTrue(preserved["sourceLinkProvided"])
        self.assertEqual(preserved["status"], "ANSWERED")
        self.assertEqual(preserved["answer"], "Manually entered")
        self.assertFalse(json.loads(path.read_text())["questions"][0]["answerVerified"])

    def test_legacy_invalid_source_cannot_be_painted_as_linked_evidence(self):
        first = sync_questions(self.root, "CCON-123", {
            "missingInfo": ["Confirm source"]})
        path = self.root / "data/questions/CCON-123.json"
        for url in ("javascript:alert(1)", "https://user:pass@example.invalid",
                    "https://example.invalid:bad/path", "https://[broken",
                    "https://example.invalid:0/path", "https://bad host/path",
                    "https://bad..host/path", "https://bad%20host/path",
                    "https://host.example/path with spaces"):
            with self.subTest(url=url):
                value = json.loads(path.read_text(encoding="utf-8"))
                value["questions"][0].update({
                    "status": "ANSWERED", "answer": "Human text",
                    "evidenceUrl": url, "answerVerified": True})
                path.write_text(json.dumps(value), encoding="utf-8")
                result = read_questions(self.root, "CCON-123")["questions"][0]
                self.assertFalse(result["answerVerified"])
                self.assertFalse(result["sourceLinkProvided"])
                self.assertEqual(result["answer"], "Human text")
                self.assertEqual(result["evidenceUrl"], url)

    def test_valid_http_hostnames_remain_source_pointers_only(self):
        first = sync_questions(self.root, "CCON-123", {"missingInfo": ["Check"]})
        identifier = first["questions"][0]["id"]
        for valid in ("https://jira.example.invalid/browse/CCON-123",
                      "http://127.0.0.1:5601/app/discover",
                      "http://[::1]:5601/app/discover"):
            with self.subTest(valid=valid):
                result = update_question(self.root, "CCON-123", identifier,
                    status="ANSWERED", answer="Human statement",
                    evidence_url=valid)
                self.assertTrue(result["sourceLinkProvided"])
                self.assertFalse(result["answerVerified"])

    def test_answer_without_source_stays_unverified_and_source_flag_clears(self):
        first = sync_questions(self.root, "CCON-123", {
            "missingInfo": ["Confirm mapping rule"]})
        identifier = first["questions"][0]["id"]
        answered = update_question(self.root, "CCON-123", identifier,
            status="ANSWERED", answer="Human answer without URL")
        self.assertFalse(answered["answerVerified"])
        self.assertFalse(answered["sourceLinkProvided"])
        with_link = update_question(self.root, "CCON-123", identifier,
            status="ANSWERED", answer="Human answer with source pointer",
            evidence_url="https://jira.example.invalid/browse/CCON-123")
        self.assertFalse(with_link["answerVerified"])
        self.assertTrue(with_link["sourceLinkProvided"])
        reopened = update_question(self.root, "CCON-123", identifier,
            status="OPEN", answer="", evidence_url="")
        self.assertFalse(reopened["answerVerified"])
        self.assertFalse(reopened["sourceLinkProvided"])

    def test_two_question_editors_cannot_silently_overwrite_a_manual_answer(self):
        source = sync_questions(self.root, "CCON-123", {
            "missingInfo": ["Which supplier rule applies?"]})
        identifier = source["questions"][0]["id"]
        self.assertEqual(source["questions"][0]["manualRevision"], 0)
        first = update_question(self.root, "CCON-123", identifier,
            status="ANSWERED", answer="First analyst decision",
            expected_manual_revision=0)
        self.assertEqual(first["manualRevision"], 1)
        with self.assertRaises(QuestionConflict) as caught:
            update_question(self.root, "CCON-123", identifier,
                status="ANSWERED", answer="Stale second tab",
                expected_manual_revision=0)
        self.assertEqual(caught.exception.current_revision, 1)
        saved = read_questions(self.root, "CCON-123")["questions"][0]
        self.assertEqual(saved["answer"], "First analyst decision")
        self.assertEqual(saved["manualRevision"], 1)
        # AI refreshes only metadata; they must never invalidate a human CAS
        # token or overwrite the analyst's answer.
        synced = sync_questions(self.root, "CCON-123", {
            "missingInfo": ["Which supplier rule applies?"]})["questions"][0]
        self.assertEqual(synced["manualRevision"], 1)
        self.assertEqual(synced["answer"], "First analyst decision")
        second = update_question(self.root, "CCON-123", identifier,
            status="ANSWERED", answer="Explicitly reviewed second decision",
            expected_manual_revision=1)
        self.assertEqual(second["manualRevision"], 2)

    def test_question_revision_validation_and_legacy_normalization(self):
        source = sync_questions(self.root, "CCON-123", {
            "missingInfo": ["One missing rule"]})
        identifier = source["questions"][0]["id"]
        path = self.root / "data/questions/CCON-123.json"
        old = json.loads(path.read_text(encoding="utf-8"))
        old["questions"][0].pop("manualRevision")
        path.write_text(json.dumps(old), encoding="utf-8")
        self.assertEqual(read_questions(self.root, "CCON-123")["questions"][0]["manualRevision"], 0)
        for invalid in (None, True, -1, "0", 1.5):
            with self.subTest(value=invalid), self.assertRaisesRegex(ValueError, "expectedManualRevision"):
                update_question(self.root, "CCON-123", identifier, status="OPEN",
                                expected_manual_revision=invalid)
        self.assertEqual(read_questions(self.root, "CCON-123")["questions"][0]["manualRevision"], 0)

    def test_question_updates_are_restricted_to_personal_scope(self):
        with self.assertRaisesRegex(ValueError, "personal"):
            sync_questions(self.root, "CCON-999", {"missingInfo": ["Unknown"]})
        with self.assertRaisesRegex(ValueError, "Invalid task key"):
            read_questions(self.root, "../evil")
        with self.assertRaisesRegex(ValueError, "Invalid question state"):
            update_question(self.root, "CCON-123", "Q-notfound", status="CLOSED")

    def test_manual_question_update_and_ai_sync_share_one_issue_lock(self):
        first = sync_questions(self.root, "CCON-123", {
            "missingInfo": ["Clarify supplier behavior"]})
        identifier = first["questions"][0]["id"]
        with question_write_lock(self.root, "CCON-123"):
            with self.assertRaisesRegex(ValueError, "Another question update"):
                sync_questions(self.root, "CCON-123", {
                    "missingInfo": ["AI-added conflicting question"]})
            with self.assertRaisesRegex(ValueError, "Another question update"):
                update_question(self.root, "CCON-123", identifier,
                                status="ANSWERED", answer="Confirmed by analyst",
                                evidence_url="https://jira.example/CCON-123")
        self.assertEqual(len(read_questions(self.root, "CCON-123")["questions"]), 1)
        self.assertEqual(read_questions(self.root, "CCON-123")["questions"][0]["status"], "OPEN")
        answer = update_question(self.root, "CCON-123", identifier,
                                 status="ANSWERED", answer="Confirmed by analyst",
                                 evidence_url="https://jira.example/CCON-123")
        self.assertFalse(answer["answerVerified"])
        self.assertTrue(answer["sourceLinkProvided"])
        sync_questions(self.root, "CCON-123", {
            "missingInfo": ["AI-added conflicting question"]})
        questions = read_questions(self.root, "CCON-123")["questions"]
        self.assertEqual(len(questions), 2)
        self.assertEqual(next(q for q in questions if q["id"] == identifier)["status"],
                         "ANSWERED")
        self.assertEqual(next(q for q in questions if q["id"] == identifier)["answer"],
                         "Confirmed by analyst")

    def test_question_lock_validates_issue_key_before_creating_paths(self):
        with self.assertRaisesRegex(ValueError, "Invalid task key"):
            question_write_lock(self.root, "../escape")

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
            "https://kibana.example.com/app/discover;api",
            "https://kibana.example.com/app/kibana;management#/discover",
            "https://kibana.example.com/app/kibana#/management",
            "https://kibana.example.com/app/kibana#/dev_tools/console",
            "https://kibana.example.com/app/kibana",
            "https://kibana.example.com/app/kibana#/discover-extra",
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
