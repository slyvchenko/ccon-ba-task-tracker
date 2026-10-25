"""Synthetic EVD-14 recurrence tests with explicit event-time uncertainty."""
import json
import unittest
from evidence_health import analyze_health
from evidence_trends import event_window, parse_utc, recurrence_window

FLOW1 = "12345678-1234-4234-8234-123456789012"
FLOW2 = "12345678-1234-4234-8234-123456789013"
FLOW3 = "12345678-1234-4234-8234-123456789014"
ISSUE = {"summary": "AF/KL. retrievePNR", "description": "", "comments": []}


def row(flow, day, *, supplier="AirFranceKLM", code="AF_TIMEOUT", date=True):
    return {
        "issueKey": "CCON-1", "flowId": flow,
        "supplier": supplier,
        "createdAt": f"2026-10-{day}T22:00:00+00:00",
        "counts": {"rest": 1, "supplier": 1, "errors": 1},
        "errorCodes": [{"code": code, "count": 1}],
        "flowDiagnostics": {"timeline": [
            {"eventTimeUtc": (f"2026-10-{day}T07:00:00+02:00"
                              if date else None), "timeEvidence": "PAYLOAD_TIMESTAMP"}
        ]},
    }


class EvidenceTrendsTests(unittest.TestCase):
    def test_repeated_error_across_explicit_days_is_flow_window_only(self):
        result = analyze_health(ISSUE, [row(FLOW1, "23"), row(FLOW2, "24")])
        repeated = result["recurrence"][0]
        self.assertEqual(repeated["caseCount"], 2)
        window = repeated["temporalEvidence"]
        self.assertEqual(window["distinctFlowCount"], 2)
        self.assertEqual(window["flowsWithExplicitEventTimes"], 2)
        self.assertEqual(window["observedFlowEventDaysUtc"], ["2026-10-23", "2026-10-24"])
        self.assertEqual(window["firstFlowEventUtc"], "2026-10-23T05:00:00+00:00")
        self.assertEqual(window["crossDaySignal"], "OBSERVED_IN_DISTINCT_DOWNLOADED_FLOW_WINDOWS")
        self.assertEqual(window["timeBasis"], "EXPLICIT_PAYLOAD_FLOW_EVENTS_NOT_ERROR_TIMESTAMPS")
        self.assertIn("not prevalence", window["limits"])
        self.assertNotIn("productionRate", json.dumps(result))

    def test_naive_timestamp_and_manifest_creation_are_not_event_evidence(self):
        first = row(FLOW1, "23", date=False)
        second = row(FLOW2, "24", date=False)
        result = analyze_health(ISSUE, [first, second])
        evidence = result["recurrence"][0]["temporalEvidence"]
        self.assertEqual(evidence["flowsWithExplicitEventTimes"], 0)
        self.assertIsNone(evidence["firstFlowEventUtc"])
        self.assertEqual(evidence["observedFlowEventDaysUtc"], [])
        self.assertEqual(evidence["crossDaySignal"], "TIME_EVIDENCE_INSUFFICIENT")
        self.assertIsNone(parse_utc("2026-10-24T04:00:00"))
        self.assertIsNone(parse_utc("2026-13-24T04:00:00Z"))

    def test_same_flow_multiple_exports_and_wrong_supplier_not_frequency(self):
        first = row(FLOW1, "23")
        latest = row(FLOW1, "24")
        other = row(FLOW2, "24", supplier="FinnAir")
        result = analyze_health(ISSUE, [first, latest, other])
        self.assertEqual(result["availableEvidenceFlowCount"], 1)
        self.assertEqual(result["recurrence"], [])

    def test_ambiguous_mixed_days_are_not_claimed_as_error_onset(self):
        a = row(FLOW1, "24")
        b = row(FLOW2, "24")
        a["flowDiagnostics"]["timeline"].append(
            {"eventTimeUtc": "2026-10-22T22:55:00Z"})
        result = analyze_health(ISSUE, [a, b])
        evidence = result["recurrence"][0]["temporalEvidence"]
        self.assertEqual(evidence["observedFlowEventDaysUtc"],
                         ["2026-10-22", "2026-10-24"])
        self.assertEqual(evidence["timeBasis"],
                         "EXPLICIT_PAYLOAD_FLOW_EVENTS_NOT_ERROR_TIMESTAMPS")
        self.assertTrue(all(key not in evidence for key in ("errorStartedAt", "cause")))
        self.assertIsNotNone(event_window(a))


if __name__ == "__main__":
    unittest.main()
