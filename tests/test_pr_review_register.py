"""In-repository factual consistency check for original GitHub review metadata."""
import json
import unittest
from pathlib import Path

REGISTER = Path(__file__).resolve().parents[1] / "docs/PR_REVIEW_COMMENT_REGISTER.json"

class HistoricalReviewRegisterTests(unittest.TestCase):
    def test_counts_are_derived_from_the_original_findings(self):
        data=json.loads(REGISTER.read_text(encoding="utf-8"))
        rows=data["findings"]
        self.assertEqual(len(rows), data["counts"]["original_review_findings"])
        self.assertEqual(len(rows), data["counts"]["github_threads_assessed"])
        self.assertEqual(len({r["id"] for r in rows}), len(rows))
        self.assertEqual(len({r["thread_id"] for r in rows}), len(rows))
        opened=[r for r in rows if not r["thread_resolved"]]
        resolved=[r for r in rows if r["thread_resolved"]]
        self.assertEqual(len(opened), data["counts"]["open_review_threads"])
        self.assertEqual(len(resolved), data["counts"]["resolved_review_threads"])
        self.assertEqual(sum(bool(r["thread_outdated"]) for r in opened),
                         data["counts"]["outdated_open_threads"])
        for severity, count in data["counts"]["open_severity"].items():
            self.assertEqual(sum(r["severity"]==severity for r in opened),count)
        self.assertEqual(sum(r["severity"]=="P1" for r in opened),0)
        for row in opened:
            self.assertEqual(row["outcome"],"SOURCE_LEVEL_TRIAGE_REQUIRED")
            self.assertTrue(row["url"].startswith("https://github.com/"))
        self.assertEqual(data["counts"]["newly_source_verified_in_followup"],26)
