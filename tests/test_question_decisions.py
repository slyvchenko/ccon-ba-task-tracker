import tempfile
import unittest
from pathlib import Path

from ba_questions import sync_questions, read_questions
from question_candidates import question_candidates, questions_with_candidates
from ba_decisions import sync_decision_proposals, apply_decision, read_decisions
from storage import write_json


KEY = "CCON-123"
BASE = "https://aerticket.atlassian.net/browse/CCON-123"
def issue():
    return {
        "key": KEY, "url": BASE,
        "comments": [
            {"id": "100", "created": "2026-10-19T10:00:00.000+0000",
             "body": "For StatusCode=CANCELLED and DeliveryStatusCode=REMOVED we will omit segment."},
            {"id": "101", "created": "2026-10-22T10:00:00.000+0000",
             "body": "Confirmed: StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED; omit the REST segment."},
            {"id": "102", "created": "2026-10-23T10:00:00.000+0000",
             "body": "Reminder about unrelated parking next week, no relevant technical field."},
        ]
    }


class QuestionDecisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        write_json(self.root / "data/jira_context.json", {
            "complete": True, "issues": {KEY: issue()}})

    def _question(self):
        q = sync_questions(self.root, KEY,
                           {"missingInfo": ["Чи StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED означає omission?"]})
        # Mimic a previously opened question, created before the later comment.
        q["questions"][0]["firstSeenAt"] = "2026-10-20T12:00:00+00:00"
        write_json(self.root / "data/questions/CCON-123.json", q)
        return q["questions"][0]

    def test_only_new_relevant_comment_suggested_without_answering(self):
        question = self._question()
        matches = question_candidates(question, issue())
        self.assertEqual([m["commentId"] for m in matches], ["101"])
        self.assertEqual(matches[0]["label"], "POSSIBLE_RELEVANT_COMMENT_NOT_VERIFIED_ANSWER")
        self.assertIn("focusedCommentId=101", matches[0]["sourceUrl"])
        stored = questions_with_candidates(self.root, KEY)["questions"][0]
        self.assertEqual(stored["status"], "OPEN")
        self.assertEqual(stored["answer"], "")
        self.assertEqual(stored["answerCandidates"][0]["commentId"], "101")
        self.assertEqual(read_questions(self.root, KEY)["questions"][0]["status"], "OPEN")

    def test_edited_old_comment_not_treated_as_new_answer(self):
        q = self._question()
        old = issue()
        old["comments"] = [{**old["comments"][0], "updated": "2026-10-23T16:00:00+0000"}]
        self.assertEqual(question_candidates(q, old), [])

    def test_no_generic_keyword_false_positives(self):
        q = self._question()
        data = issue()
        data["comments"] = [{"id": "103", "created": "2026-10-22T12:00:00+0000",
                             "body": "We have reviewed your question and will reply shortly."}]
        self.assertEqual(question_candidates(q, data), [])

    def test_closed_questions_do_not_receive_candidates(self):
        q = self._question()
        q["status"] = "ANSWERED"
        self.assertEqual(question_candidates(q, issue()), [])

    def test_decision_timeline_is_never_auto_confirmed(self):
        item = {"briefing": {"timeline": [
            {"date": "2026-10-22", "status": "CONFIRMED",
             "sourceUrl": BASE, "eventUk": "Не повертати скасований сегмент"},
        ]}}
        first = sync_decision_proposals(self.root, KEY, item)
        self.assertEqual(first["decisions"][0]["status"], "PROPOSED")
        self.assertEqual(first["decisions"][0]["origin"], "AI_TIMELINE_PROPOSAL")
        self.assertEqual(len(first["events"]), 1)
        second = sync_decision_proposals(self.root, KEY, item)
        self.assertEqual(len(second["decisions"]), 1)
        self.assertEqual(len(second["events"]), 1)

    def test_confirm_dispute_supersede_preserve_history(self):
        first = apply_decision(self.root, KEY, action="propose",
                               text="Omit the CANCELLED segment", source_url=BASE,
                               impact="REST response changes")
        oldid = first["decisions"][0]["id"]
        confirmed = apply_decision(self.root, KEY, action="confirm", identifier=oldid,
                                   source_url=BASE, impact="Needs 3 regression tests")
        self.assertEqual(confirmed["decisions"][0]["status"], "CONFIRMED")
        changed = apply_decision(self.root, KEY, action="supersede", identifier=oldid,
                                 text="Omit only when both statuses match", source_url=BASE,
                                 impact="Revisit AND condition", reason="New supplier clarification")
        new = next(d for d in changed["decisions"] if d["id"] != oldid)
        prior = next(d for d in changed["decisions"] if d["id"] == oldid)
        self.assertEqual(prior["status"], "SUPERSEDED")
        self.assertEqual(new["status"], "CONFIRMED")
        self.assertEqual(new["supersedes"], oldid)
        self.assertEqual(prior["supersededBy"], new["id"])
        self.assertEqual(len(changed["events"]), 4)
        disputed = apply_decision(self.root, KEY, action="dispute",
                                  identifier=new["id"], reason="Counterexample in logs")
        self.assertEqual(next(d for d in disputed["decisions"] if d["id"] == new["id"])["status"], "DISPUTED")
        self.assertEqual(len(disputed["events"]), 5)
        self.assertEqual(read_decisions(self.root, KEY)["events"][0]["to"], "PROPOSED")

    def test_automatic_sync_does_not_revert_manual_confirmed(self):
        timeline = {"briefing": {"timeline": [
            {"date": "2026-10-23", "status": "CONFIRMED",
             "sourceUrl": BASE, "eventUk": "Do not return removed segment"}]}}
        first = sync_decision_proposals(self.root, KEY, timeline)
        key = first["decisions"][0]["id"]
        apply_decision(self.root, KEY, action="confirm", identifier=key)
        again = sync_decision_proposals(self.root, KEY, timeline)
        self.assertEqual(again["decisions"][0]["status"], "CONFIRMED")
        self.assertEqual(len(again["events"]), 2)

    def test_must_be_manual_and_in_scope(self):
        with self.assertRaisesRegex(ValueError, "personal Jira scope"):
            apply_decision(self.root, "CCON-999", action="propose",
                           text="Something", source_url=BASE)
        proposal = apply_decision(self.root, KEY, action="propose", text="Check condition",
                                  source_url=BASE)
        did = proposal["decisions"][0]["id"]
        with self.assertRaises(ValueError):
            apply_decision(self.root, KEY, action="supersede", identifier=did,
                           text="Replacement", source_url=BASE)
        with self.assertRaises(ValueError):
            apply_decision(self.root, KEY, action="dispute", identifier=did)
        with self.assertRaises(ValueError):
            apply_decision(self.root, KEY, action="propose", text="Bad", source_url="file:///secret")

    def test_ai_proposals_never_rewrite_human_decision(self):
        proposal = apply_decision(self.root, KEY, action="propose",
                                  text="Human rule", source_url=BASE)
        did = proposal["decisions"][0]["id"]
        apply_decision(self.root, KEY, action="confirm", identifier=did)
        sync_decision_proposals(self.root, KEY, {"briefing": {"timeline": [
            {"date": "2026-10-24", "status": "SUPERSEDED",
             "sourceUrl": BASE, "eventUk": "Conflicting draft"}]}})
        records = read_decisions(self.root, KEY)["decisions"]
        self.assertEqual(next(x for x in records if x["id"] == did)["status"], "CONFIRMED")
        self.assertEqual(len([x for x in records if x["status"] == "PROPOSED"]), 1)


if __name__ == "__main__":
    unittest.main()
