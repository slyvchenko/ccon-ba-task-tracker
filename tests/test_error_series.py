import json
import tempfile
import unittest
from pathlib import Path

from error_series import (_make_case, investigate_cases, build_investigation,
                          MAX_CASES)
from storage import write_json
from ba_questions import all_evidence


FLOW = "12345678-1234-4234-8234-123456789012"
AF = "AirFranceKLM"
CODE = "AF_REJECTED"


def flow_id(i):
    return f"12345678-1234-4234-8234-{i:012d}"


def manifest(i, code=CODE, supplier=AF, include_supplier=True,
             rest=True, errors=True, diff=False):
    layers = {}
    if rest:
        layers["rest"] = 2
    if include_supplier:
        layers["supplier"] = 2
    if errors:
        layers["errors"] = 1
    samples = []
    if rest:
        samples.append({"layer": "rest", "kind": "response",
                        "file": "rest/1-response.json",
                        "errors": [code] if code else []})
    if include_supplier:
        samples.append({"layer": "supplier", "kind": "response",
                        "file": "supplier/AirFranceKLM/1-Retrieve-doByLocator-1-response-body.xml",
                        "errors": [code] if code else []})
    if errors:
        samples.append({"layer": "errors", "kind": "unknown",
                        "file": "rest/errors/1-error.json",
                        "errors": [code] if code else []})
    return {"issueKey": "CCON-123", "supplier": supplier,
            "sourceSha256": f"{i:064x}", "flowId": flow_id(i),
            "createdAt": f"2026-10-24T12:{i % 60:02d}:00+00:00",
            "counts": layers,
            "samples": samples,
            "errorCodes": [{"code": code, "count": 1}] if code else [],
            "valueReview": {"comparisons": [{
                "mappingStatus": "CANDIDATE_ONLY",
                "sameNamedDifferentValues": (
                    [{"restField": "Fare", "supplierField": "Price"}] if diff else []),
            }], "issues": []}}


class ErrorSeriesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.context = self.root / "data/jira_context.json"
        write_json(self.context, {"complete": True, "issues": {
            "CCON-123": {"summary": "AF/KL. retrievePNR", "key": "CCON-123"},
        }})
        self.evidence = self.root / "data/evidence/CCON-123"
        self.evidence.mkdir(parents=True)

    def write(self, i, value=None):
        write_json(self.evidence / f"{i}.json", value or manifest(i))

    def test_thirty_cases_dedup_and_hypotheses_never_confirm_root_cause(self):
        for i in range(1, 34):
            self.write(i, manifest(i, diff=i % 3 == 0))
        self.write(99, dict(manifest(1), createdAt="2026-10-24T22:00:00+00:00"))
        result = build_investigation(self.root, "CCON-123",
                                     code=CODE, max_cases=30)
        self.assertEqual(result["availableUniqueFlows"], 33)
        self.assertEqual(result["analyzedCases"], 30)
        self.assertEqual(result["causality"], "ROOT_CAUSE_UNCONFIRMED")
        self.assertEqual(result["coverage"]["withSupplier"], 30)
        self.assertEqual(result["coverage"]["withRest"], 30)
        self.assertTrue(any("ліміт" in q for q in result["questionsUk"]))
        self.assertTrue(all(h["classification"] == "HYPOTHESIS_NOT_CONFIRMED"
                            for h in result["hypotheses"]))
        self.assertTrue(any("трансформація" in h["titleUk"]
                            for h in result["hypotheses"]))
        self.assertEqual(len(set(case["flowId"] for case in result["cases"])), 30)
        self.assertEqual(result["groups"][0]["supplierMethod"], "doByLocator")
        self.assertTrue((self.root / "data/investigations/CCON-123.json").exists())
        self.assertFalse(any("CONFIRMED_CAUSE" == h.get("classification")
                             for h in result["hypotheses"]))

    def test_only_requested_code_kept_not_mixed_with_other_errors(self):
        rows = [_make_case(manifest(1), "CCON-123", AF),
                _make_case(manifest(2, code="OTHER_ERROR"), "CCON-123", AF)]
        report = investigate_cases(rows, "CCON-123", AF, code=CODE)
        self.assertEqual(report["availableUniqueFlows"], 1)
        self.assertEqual(report["analyzedCases"], 1)
        self.assertEqual(report["groups"][0]["errorCode"], CODE)

    def test_foreign_supplier_and_unrelated_issue_never_enter_series(self):
        self.write(1, manifest(1))
        self.write(2, manifest(2, supplier="FinnAir"))
        self.write(3, dict(manifest(3), issueKey="CCON-999"))
        report = build_investigation(self.root, "CCON-123", code=CODE)
        self.assertEqual(report["analyzedCases"], 1)
        self.assertEqual(report["sourceManifestCount"], 1)

    def test_incomplete_layers_mark_missing_proof(self):
        self.write(1, manifest(1, include_supplier=False, diff=True))
        report = build_investigation(self.root, "CCON-123", code=CODE)
        self.assertEqual(report["coverage"]["withSupplier"], 0)
        self.assertTrue(any("supplier layer" in q for q in report["questionsUk"]))
        self.assertEqual(report["causality"], "ROOT_CAUSE_UNCONFIRMED")

    def test_unavailable_source_is_not_silently_treated_as_complete(self):
        report = build_investigation(self.root, "CCON-123", code=CODE)
        self.assertEqual(report["analyzedCases"], 0)
        self.assertIn("Немає валідних локально", report["questionsUk"][0])
        self.assertEqual(report["browserAccess"], "NOT_PERFORMED_BY_THIS_SCRIPT")

    def test_personal_scope_and_limits(self):
        with self.assertRaisesRegex(ValueError, "personal Jira scope"):
            build_investigation(self.root, "CCON-456", code=CODE)
        with self.assertRaisesRegex(ValueError, "30"):
            build_investigation(self.root, "CCON-123", max_cases=31)
        with self.assertRaisesRegex(ValueError, "error code"):
            build_investigation(self.root, "CCON-123", code="<secret>")
        with self.assertRaisesRegex(ValueError, "error code"):
            investigate_cases([], "CCON-123", AF, code="../BAD")

    def test_empty_error_code_no_hidden_merging(self):
        for i in range(1, 4):
            self.write(i, manifest(i, code="ERR_A" if i % 2 else "ERR_B"))
        r = build_investigation(self.root, "CCON-123")
        self.assertEqual(len(r["groups"]), 2)
        self.assertIsNone(r["requestedErrorCode"])
        self.assertTrue(any("Не задано конкретний error code" in q
                            for q in r["questionsUk"]))

    def test_question_tracker_receives_investigation_gaps(self):
        self.write(1, manifest(1, include_supplier=False))
        build_investigation(self.root, "CCON-123", CODE)
        content = all_evidence(self.root, "CCON-123")
        self.assertTrue(any("supplier layer" in q
                            for row in content for q in row.get("questionsUk", [])))

    def test_no_raw_payloads_in_multi_case_reports(self):
        secret = "REAL_PASSENGER_SURNAME_DONT_COPY"
        item = manifest(1)
        item["samples"].append({"layer": "rest", "kind": "request",
                                "file": "rest/private-request.json",
                                "fields": ["CustomerName"], "secret": secret})
        self.write(1, item)
        result = build_investigation(self.root, "CCON-123", CODE)
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(secret, (self.root / "data/investigations/CCON-123.json").read_text())


if __name__ == "__main__":
    unittest.main()
