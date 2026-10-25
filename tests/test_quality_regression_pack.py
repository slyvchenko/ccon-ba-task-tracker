"""UX-02 and QA-03/QA-04 synthetic quality tests. Never store real Jira data."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from ba_compactness import advisory_findings, compact_generated, profile
from ba_quality_gate import quality_gate
from quality_evaluation import diagnostics, compare
from evaluation import evaluate
from storage import write_json

URL = "https://aerticket.atlassian.net/browse/CCON-999"


def _draft():
    return ("#### Objective\nPreserve the confirmed REST response behavior.\n"
            "#### To Do\nIF StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED "
            "THEN omit segment in REST response.\n"
            "#### QA\nCheck CANCELLED and REMOVED excludes the segment.\n"
            "Check ACTIVE with REMOVED retains the segment.\n"
            "Check CANCELLED with ACTIVE delivery retains the segment.")


def _analysis(key, fingerprint):
    return {"contextFingerprint": fingerprint, "signal": "REVIEW",
            "standardDescription": _draft(),
            "missingInfo": [], "emailDraft": {"subject": "Check", "body": ""},
            "briefing": {"readiness": "READY_FOR_REVIEW", "unknownsUk": [],
                "confirmedFacts": [{"textUk": "Вимога", "sourceUrl": URL,
                                    "sourceExcerpt": "Omit CANCELLED segments only when REMOVED."}],
                "rules": [{"id": "R1", "certainty": "CONFIRMED", "sourceUrl": URL,
                           "sourceExcerpt": "Omit CANCELLED segments only when REMOVED.",
                           "whenUk": "StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED",
                           "thenUk": "Omit segment in REST response"}],
                "verification": [
                    {"ruleIds": ["R1"], "kind": kind, "scenarioUk": "Стан",
                     "expectedUk": "Перевірити REST", "sourceUrl": URL}
                    for kind in ("POSITIVE", "NEGATIVE", "EDGE")]},
            }


def cohort():
    cases, predictions = [], {}
    for i in range(1, 21):
        key = f"CCON-{i}"
        fingerprint = f"source-{i}"
        cases.append({"key": key, "summary": "NDC rebooking", "contextFingerprint": fingerprint,
            "source": {"url": URL, "description": "Omit CANCELLED segments only when REMOVED.",
                       "comments": [], "linkedContexts": []}})
        predictions[key] = _analysis(key, fingerprint)
    return {"cases": cases}, {"analyses": predictions}


class CompactBAQualityTests(unittest.TestCase):
    def test_compactor_keeps_technical_conditions_and_qa(self):
        source = _draft().replace("#### QA", "IF StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED "
            "THEN omit segment in REST response.\n#### QA")
        output, detail = compact_generated(source)
        self.assertEqual(detail["exactAdjacentLinesRemoved"], 1)
        self.assertEqual(output.count("StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED"), 1)
        self.assertEqual(output.count("Check "), 3)
        self.assertEqual(profile(output)["qaChecks"], 3)

    def test_nonadjacent_and_nonidentical_conditions_survive(self):
        raw = ("#### To Do\nIF StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED THEN omit.\n"
               "IF StatusCode=CANCELLED OR DeliveryStatusCode=REMOVED THEN review.\n"
               "#### QA\nCheck code case A.\n#### To Do\n"
               "IF StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED THEN omit.")
        output, detail = compact_generated(raw)
        self.assertEqual(detail["exactAdjacentLinesRemoved"], 0)
        self.assertIn(" AND ", output)
        self.assertIn(" OR ", output)
        self.assertEqual(output.count("THEN omit."), 2)
        self.assertEqual(compact_generated(output)[0], output)

    def test_long_prose_warning_does_not_block_approved_conditions(self):
        raw = _draft() + "\n" + ("Plain English " * 43) + "\n" + ("Another long paragraph " * 31)
        hints = advisory_findings(raw)
        self.assertIn("DESCRIPTION_LONG_PARAGRAPHS", {x["code"] for x in hints})
        analysis = _analysis("CCON-1", "source-1")
        analysis["standardDescription"] = raw
        issue = {"url": URL, "description": "Omit CANCELLED segments only when REMOVED."}
        gate = quality_gate(analysis, issue)
        self.assertNotEqual(gate["state"], "BLOCKED", gate["findings"])
        self.assertEqual(gate["summary"]["descriptionProfile"]["qaChecks"], 3)

    def test_frozen_cohort_diagnostics_are_counts_only(self):
        pack, base = cohort()
        candidate = copy.deepcopy(base)
        candidate["analyses"]["CCON-1"]["standardDescription"] = (
            "#### To Do\nCheck that everything works.\n#### QA\nCheck that everything works.")
        result = compare(pack, base, candidate)
        self.assertEqual(result["status"], "PREFLIGHT_ONLY_REQUIRES_HUMAN_REVIEW")
        self.assertEqual(result["baseline"]["caseCount"], 20)
        self.assertEqual(result["candidate"]["caseCount"], 20)
        self.assertEqual(result["warningDeltaCases"].get("CONFIRMED_FIELD_OMITTED"), 1)
        self.assertEqual(result["acceptance"], "NOT_DETERMINABLE_FROM_DETERMINISTIC_CHECKS")
        output = json.dumps(result)
        for phrase in ("CANCELLED", "source-1", "Omit CANCELLED segments", URL):
            self.assertNotIn(phrase, output)

    def test_missing_prediction_stale_or_extra_issue_rejected(self):
        pack, predictions = cohort()
        variants = [
            {k:v for k,v in predictions["analyses"].items() if k != "CCON-20"},
            {**predictions["analyses"], "CCON-900": _analysis("CCON-900", "wrong")},
            {**predictions["analyses"], "CCON-20": _analysis("CCON-20", "old")},
        ]
        for item in variants:
            with self.subTest(count=len(item)), self.assertRaisesRegex(ValueError, "(scope|fingerprint)"):
                diagnostics(pack, {"analyses": item})

    def test_source_excerpt_hallucination_counted_not_claimed_as_true(self):
        pack, base = cohort()
        base["analyses"]["CCON-3"]["briefing"]["rules"][0]["sourceExcerpt"] = "fabricated supplier mapping"
        report = diagnostics(pack, base)
        self.assertEqual(report["warningCaseCounts"]["CLAIM_EXCERPT_NOT_FOUND"], 1)
        self.assertNotIn("fabricated supplier", str(report))
        self.assertIn("Automated preflight only", report["limitations"][0])

    def test_evaluation_writes_preflight_only_with_both_frozen_sets(self):
        pack, baseline = cohort()
        candidate = copy.deepcopy(baseline)
        with tempfile.TemporaryDirectory(prefix="ccon-quality-metrics-") as folder:
            root = Path(folder)
            directory = root / "data/evaluation"
            directory.mkdir(parents=True)
            write_json(directory / "selected_cases.json", pack)
            write_json(directory / "reviews.json", {"reviews": [
                {"key": case["key"], "reviewer": "", "baseline": {}, "candidate": {}}
                for case in pack["cases"]]})
            report = evaluate(root)
            self.assertEqual(report["status"], "INCOMPLETE")
            self.assertNotIn("automatedPreflight", report)
            self.assertEqual(report["missingPredictionSets"], ["baseline", "candidate"])
            write_json(directory / "baseline_predictions.json",
                       {"variant": "baseline", **baseline})
            write_json(directory / "candidate_predictions.json",
                       {"variant": "candidate", **candidate})
            report = evaluate(root)
            self.assertEqual(report["status"], "INCOMPLETE")
            self.assertIn("automatedPreflight", report)
            self.assertFalse(report.get("candidateMeetsTargets", False))
            markdown = (directory / "results.md").read_text()
            self.assertIn("INCOMPLETE", markdown)
            # With incomplete human review, the Markdown summary remains
            # incomplete and automated diagnostics do not authorize release.
            candidate["analyses"]["CCON-2"]["contextFingerprint"] = "tampered"
            write_json(directory / "candidate_predictions.json",
                       {"variant": "candidate", **candidate})
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                evaluate(root)


if __name__ == "__main__":
    unittest.main()
