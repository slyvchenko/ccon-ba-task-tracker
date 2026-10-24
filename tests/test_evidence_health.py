import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidence_health import classify_error, analyze_health, health_for_issue
from storage import write_json

KEY = "CCON-123"
A = "12345678-1234-4234-8234-123456789012"
B = "12345678-1234-4234-8234-123456789013"
C = "12345678-1234-4234-8234-123456789014"
AF = {"key": KEY, "summary": "AF/KL retrievePNR",
      "description": "No live links", "comments": []}


def manifest(flow, code="AF_TIMEOUT", supplier="AirFranceKLM", rest=1, provider=1, errors=1, created="2026-10-24T10:00:00+00:00"):
    return {"issueKey": KEY, "flowId": flow, "supplier": supplier,
            "createdAt": created, "counts": {"rest": rest, "supplier": provider, "errors": errors},
            "valueReview": {"comparisons": [{"mappingStatus": "CANDIDATE_ONLY"}] if provider and rest else []},
            "errorCodes": [{"code": code, "count": 1}]}


class EvidenceHealthTests(unittest.TestCase):
    def test_taxonomy_is_explicitly_uncertain(self):
        self.assertEqual(classify_error("SUPPLIER_TIMEOUT"), "TIMEOUT_OR_CONNECTIVITY_CANDIDATE")
        self.assertEqual(classify_error("FareComponent_NOT_FOUND"), "MAPPING_OR_CONTRACT_CANDIDATE")
        self.assertEqual(classify_error("HTTP_500"), "CCON_PROCESSING_CANDIDATE")
        self.assertEqual(classify_error("REJECTED"), "PROVIDER_REJECTION_CANDIDATE")
        self.assertEqual(classify_error("<script>alert"), "UNCLASSIFIED")

    def test_expected_flows_coverage_and_missing_layers(self):
        records = [manifest(A), manifest(B, provider=0, errors=0)]
        with patch("evidence_health.flow_references", return_value=[
            {"flowId": A}, {"flowId": B}, {"flowId": C}
        ]):
            result = analyze_health(AF, records)
        self.assertEqual(result["expectedFlowCount"], 3)
        self.assertEqual(result["analyzedExpectedFlowCount"], 2)
        self.assertEqual(result["restSupplierCoverage"], 0.333)
        gap = next(x for x in result["flows"] if x["flowId"] == C)
        self.assertIn("ZIP_NOT_ANALYZED", gap["gaps"])
        missing = next(x for x in result["flows"] if x["flowId"] == B)
        self.assertIn("SELECTED_SUPPLIER_MISSING", missing["gaps"])
        self.assertIn("ERROR_LAYER_MISSING_OR_NOT_EXPORTED", missing["gaps"])
        self.assertEqual(result["taxonomy"][0]["status"], "HEURISTIC_NOT_CONFIRMED_CAUSE")

    def test_repeat_exports_and_foreign_supplier_never_inflate_count(self):
        records = [
            manifest(A), manifest(A, created="2026-10-24T11:00:00+00:00"),
            manifest(B), manifest(C, supplier="FinnAir"),
        ]
        with patch("evidence_health.flow_references", return_value=[]):
            result = analyze_health(AF, records)
        self.assertIsNone(result["expectedFlowCount"])
        self.assertIsNone(result["restSupplierCoverage"])
        self.assertEqual(result["availableEvidenceFlowCount"], 2)
        self.assertEqual(result["recurrence"][0]["caseCount"], 2)
        self.assertEqual(result["recurrence"][0]["repeatSignal"], "REPEATED_ONLY_IN_DOWNLOADED_FLOWS")

    def test_missing_error_folder_is_not_claimed_no_errors(self):
        with patch("evidence_health.flow_references", return_value=[{"flowId": A}]):
            result = analyze_health(AF, [manifest(A, errors=0)])
        self.assertIn("ERROR_LAYER_MISSING_OR_NOT_EXPORTED", result["flows"][0]["gaps"])
        self.assertIn("does not prove absence", result["uncertainty"])

    def test_personal_issue_scope_and_local_json_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root / "data/jira_context.json", {"complete": True, "issues": {KEY: AF}})
            write_json(root / ("data/evidence/" + KEY + "/a.json"), manifest(A))
            with patch("evidence_health.flow_references", return_value=[{"flowId": A}]):
                r = health_for_issue(root, KEY)
            self.assertEqual(r["availableEvidenceFlowCount"], 1)
            self.assertNotIn("passenger", json.dumps(r))
            with self.assertRaisesRegex(ValueError, "personal Jira"):
                health_for_issue(root, "CCON-999")


if __name__ == "__main__":
    unittest.main()
