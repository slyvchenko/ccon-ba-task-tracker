import io
import json
import unittest
from zipfile import ZipFile

from flow_diagnostics import diagnose_zip, shape_and_times, event_timestamp
from layered_evidence import analyze_zip_bytes
from supplier_logs import supplier_hint


AF = supplier_hint("AF/KL. RetrievePNR")


def zip_bytes(entries):
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        for filename, content in entries:
            archive.writestr(filename, content)
    return stream.getvalue()


class FlowDiagnosticsTests(unittest.TestCase):
    def test_method_shape_and_explicit_timeline(self):
        raw = zip_bytes([
            ("rest/01-request.json", json.dumps({
                "timestamp": "2026-10-24T10:00:00+02:00",
                "StatusCode": "CANCELLED",
                "Extra": None, "Segments": [{"StatusCode": "CANCELLED"},
                                             {"StatusCode": "REMOVED"}],
                "PassengerSurname": "PRIVATE_SURNAME",
            }).encode()),
            ("supplier/AirFranceKLM/1-Booking-doOrder-1-request-body.xml",
             b'<RQ><eventTime>2026-10-24T08:00:02Z</eventTime><StatusCode>CANCELLED</StatusCode>'
             b'<Items><Item>one</Item><Item>two</Item></Items></RQ>'),
            ("supplier/AirFranceKLM/1-Booking-doOrder-1-response-body.xml",
             b'<RS xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
             b'<eventTime>2026-10-24T08:00:04Z</eventTime>'
             b'<Missing xsi:nil="true"/></RS>'),
            ("rest/01-response.json", b'{"timestamp":"2026-10-24T08:00:05+00:00","StatusCode":"REMOVED"}'),
            ("supplier/FinnAir/9-Other-doOther-1-response-body.xml",
             b'<SECRET><eventTime>2026-10-22T00:00:00Z</eventTime></SECRET>'),
        ])
        manifest = analyze_zip_bytes(raw, AF)
        report = manifest["flowDiagnostics"]
        self.assertEqual(report["entriesExamined"], 4)
        self.assertEqual(report["timestampedEntries"], 4)
        self.assertEqual(report["timeStatus"], "ALL_EXPLICIT_TIMESTAMPS")
        self.assertEqual(report["timeline"][0]["eventTimeUtc"], "2026-10-24T08:00:00+00:00")
        self.assertEqual(report["timeline"][-1]["eventTimeUtc"], "2026-10-24T08:00:05+00:00")
        self.assertEqual(report["timeline"][1]["method"], "doOrder")
        text = json.dumps(report)
        self.assertNotIn("PRIVATE_SURNAME", text)
        self.assertNotIn("FinnAir", text)
        self.assertNotIn("doOther", text)
        self.assertNotIn("one", text)
        self.assertTrue(any("Segments" in name for item in report["timeline"]
                            for name in item["shape"]["repeatedFields"]))
        self.assertTrue(any("Extra" in name for item in report["timeline"]
                            for name in item["shape"]["nullFields"]))
        self.assertTrue(any("Missing" in name for item in report["timeline"]
                            for name in item["shape"]["nullFields"]))
        self.assertTrue(any(x.get("supplierMethod") == "doOrder" for x in report["contractCandidates"]))
        self.assertTrue(all(x["mappingStatus"] == "CANDIDATE_NOT_CONFIRMED_CONTRACT"
                            for x in report["contractCandidates"]))

    def test_zip_order_and_supplier_sequence_never_prove_event_order(self):
        raw = zip_bytes([
            ("supplier/AirFranceKLM/5-Booking-doOrder-22-request-body.xml", b"<RQ><Value>A</Value></RQ>"),
            ("rest/01-request.json", b'{"Value":"A"}'),
            ("supplier/AirFranceKLM/5-Booking-doOrder-2-request-body.xml", b"<RQ><Value>B</Value></RQ>"),
            ("rest/01-response.json", b'{"ok":true}'),
        ])
        result = analyze_zip_bytes(raw, AF)["flowDiagnostics"]
        self.assertEqual(result["timestampedEntries"], 0)
        self.assertEqual(result["timeStatus"], "NO_EXPLICIT_EVENT_TIMESTAMPS")
        self.assertIn("INCOMPLETE_EVENT_TIMESTAMPS_NO_GLOBAL_CHRONOLOGY", result["warnings"])
        self.assertEqual(result["repeatedMethodCandidates"][0]["interpretation"],
                         "REPEATED_METHOD_RETRY_NOT_PROVEN")
        self.assertEqual([e["zipOrder"] for e in result["timeline"]], sorted(e["zipOrder"] for e in result["timeline"]))
        self.assertTrue(all(e["eventTimeUtc"] is None for e in result["timeline"]))

    def test_never_infer_time_from_naive_or_filename(self):
        self.assertIsNone(event_timestamp("2026-10-24T10:00:00"))
        self.assertIsNone(event_timestamp("2026-10-24"))
        self.assertIsNone(event_timestamp("2026-10-24T10:00:00Zprivate"))
        payload = shape_and_times(b'{"createdAt":"2026-10-24T10:00:00","duration":5}', ".json")
        self.assertEqual(payload["eventTimes"], [])

    def test_multiple_explicit_times_are_ambiguous_not_fabricated(self):
        raw = zip_bytes([("rest/01-request.json",
                          b'{"createdAt":"2026-10-24T08:00:00Z","receivedAt":"2026-10-24T08:00:10Z"}')])
        report = analyze_zip_bytes(raw, AF)["flowDiagnostics"]
        self.assertEqual(report["timestampedEntries"], 0)
        self.assertEqual(report["timeline"][0]["timeEvidence"], "MULTIPLE_TIMES_AMBIGUOUS")

    def test_xml_dtd_rejected_and_no_fields_leak(self):
        result = shape_and_times(
            b'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><x>&secret;</x>', ".xml")
        self.assertEqual(result["parseStatus"], "XML_ENTITY_REJECTED")
        self.assertEqual(result["fields"], [])

    def test_nested_repeating_xml_fields_with_no_provider_blame(self):
        payload = b'<RS><Items><Item/><Item/></Items><StatusCode>FAILED</StatusCode></RS>'
        result = shape_and_times(payload, ".xml")
        self.assertIn("RS.Items.Item", result["repeatedFields"])
        self.assertEqual(result["eventTimes"], [])


if __name__ == "__main__":
    unittest.main()
