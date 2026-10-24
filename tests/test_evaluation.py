import json
import tempfile
import unittest
from pathlib import Path

from evaluation import RUBRIC, prepare, score_pack, select_cases, evaluate, attach_predictions


def issue(i):
    return {
        "key": f"CCON-{i}",
        "fingerprint": str(i),
        "summary": "NDC refund issue" if i % 2 else "FareComponent rebooking",
        "description": ("Description of NDC order " * ((i % 9) + 1)),
        "comments": [{"id": str(j), "body": "Test"} for j in range(i % 7)],
        "links": [{"linkedKey": "CCON-1"}] if i % 3 == 0 else [],
        "url": f"https://jira.example/CCON-{i}",
    }


class EvaluationTests(unittest.TestCase):
    def dataset(self, n=40):
        return {f"CCON-{i}": issue(i) for i in range(1, n + 1)}

    def test_diverse_case_selection_is_repeatable_without_faking_examples(self):
        cases = self.dataset()
        a = select_cases(cases, 30)
        self.assertEqual(a, select_cases(cases, 30))
        self.assertEqual(len(a), 30)
        self.assertEqual(len(set(a)), 30)
        self.assertGreater(len({i % 3 for i in range(1, 31) if f"CCON-{i}" in a}), 1)

    def test_too_few_cases_and_invalid_limits_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "required"):
            select_cases(self.dataset(19), 20)
        with self.assertRaisesRegex(ValueError, "between 20 and 30"):
            select_cases(self.dataset(), 31)

    def test_prepare_never_overwrites_human_labels(self):
        with tempfile.TemporaryDirectory(prefix="ccon-eval-") as folder:
            root = Path(folder)
            path = root / "data" / "jira_context.json"
            path.parent.mkdir()
            path.write_text(json.dumps({"complete": True, "issues": self.dataset()}))
            result = prepare(root, 30)
            self.assertEqual(result["cases"], 30)
            self.assertTrue(Path(result["reviews"]).exists())
            with self.assertRaisesRegex(ValueError, "already exists"):
                prepare(root, 30)
            scored = evaluate(root)
            self.assertEqual(scored["status"], "INCOMPLETE")
            self.assertEqual(scored["completed"], 0)
            self.assertNotIn("metrics", scored)

    def test_human_a_b_evaluation_and_quality_targets(self):
        cases = {"cases": [{"key": f"CCON-{i}"} for i in range(1, 21)]}
        rows = []
        for i in range(1, 21):
            score = {k: 3 for k in RUBRIC}
            rows.append({
                "key": f"CCON-{i}",
                "reviewer": "human-qa",
                "baseline": {"reviewed": True, "scores": {k: 2 for k in RUBRIC},
                             "criticalFalseClaims": ["Unverified claim"],
                             "minutesSpent": 10},
                "candidate": {"reviewed": True, "scores": score,
                              "criticalFalseClaims": [], "minutesSpent": 5},
            })
        result = score_pack(cases, {"reviews": rows})
        self.assertEqual(result["status"], "REVIEWED")
        self.assertTrue(result["candidateMeetsTargets"])
        self.assertEqual(result["medianTimeSavedPercent"], 50)
        rows[0]["candidate"]["criticalFalseClaims"] = ["Invented field mapping"]
        result = score_pack(cases, {"reviews": rows})
        self.assertFalse(result["candidateMeetsTargets"])

    def test_attach_requires_exact_frozen_context_and_never_overwrites(self):
        with tempfile.TemporaryDirectory(prefix="ccon-eval-") as folder:
            root = Path(folder)
            path = root / "data" / "jira_context.json"
            path.parent.mkdir()
            path.write_text(json.dumps({"complete": True, "issues": self.dataset()}))
            prepare(root, 20)
            cases = json.loads((root / "data/evaluation/selected_cases.json").read_text())["cases"]
            predictions = {"analyses": {c["key"]: {"signal": "REVIEW",
                            "contextFingerprint": c["contextFingerprint"]} for c in cases}}
            sample = root / "data" / "candidate.json"
            sample.write_text(json.dumps(predictions))
            result = attach_predictions(root, "candidate", sample)
            self.assertEqual(result["count"], 20)
            with self.assertRaisesRegex(ValueError, "already frozen"):
                attach_predictions(root, "candidate", sample)
            predictions["analyses"][cases[0]["key"]]["contextFingerprint"] = "stale"
            sample.write_text(json.dumps(predictions))
            with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
                attach_predictions(root, "baseline", sample)
            self.assertFalse((root / "data/evaluation/baseline_predictions.json").exists())
    def test_partial_reviews_are_not_sold_as_passed(self):
        cases = {"cases": [{"key": f"CCON-{i}"} for i in range(1, 21)]}
        reviews = [{"key": f"CCON-{i}", "reviewer": "", "baseline": {}, "candidate": {}}
                   for i in range(1, 21)]
        result = score_pack(cases, {"reviews": reviews})
        self.assertEqual(result["completed"], 0)
        self.assertEqual(result["status"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
