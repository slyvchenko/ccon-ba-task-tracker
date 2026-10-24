import io
import json
import unittest
import tempfile
from pathlib import Path
from zipfile import ZipFile

from layered_evidence import analyze_zip_bytes
from supplier_logs import supplier_hint
from value_mapping import leaf_values, compare_zip_bytes
from draft_output import make_ready_draft


def zip_bytes(entries):
    memory = io.BytesIO()
    with ZipFile(memory, "w") as output:
        for path, data in entries:
            output.writestr(path, data)
    return memory.getvalue()


AF = supplier_hint("AF/KL. RetrievePNR")


class ValueMappingTests(unittest.TestCase):
    def test_rest_supplier_requests_and_responses_are_compared_both_ways(self):
        flow = "12345678-1234-4234-8234-123456789012"
        raw = zip_bytes([
            ("rest/01-request.json", json.dumps({
                "correlationId": flow, "StatusCode": "CANCELLED",
                "Amount": "139.95", "LastName": "ConfidentialName"
            }).encode()),
            ("supplier/AirFranceKLM/01-request-body.xml", (
                '<Req><correlationId>' + flow + '</correlationId>'
                '<StatusCode>CANCELLED</StatusCode><Price>139.95</Price>'
                '<LastName>DifferentName</LastName></Req>'
            ).encode()),
            ("supplier/AirFranceKLM/01-response-body.xml", (
                '<Response><correlationId>' + flow + '</correlationId>'
                '<DeliveryStatusCode>REMOVED</DeliveryStatusCode>'
                '<Fare>CHF-12345</Fare></Response>'
            ).encode()),
            ("rest/01-response.json", json.dumps({
                "correlationId": flow, "DeliveryStatusCode": "REMOVED",
                "Fare": "CHANGED"
            }).encode()),
            ("supplier/FinnAir/01-request-body.xml",
             b"<Request><LastName>DO_NOT_PROCESS</LastName></Request>"),
        ])
        result = compare_zip_bytes(raw, AF["aliases"])
        self.assertEqual(len(result["comparisons"]), 2)
        req = next(x for x in result["comparisons"]
                   if x["direction"] == "REST_REQUEST_TO_SUPPLIER_REQUEST")
        self.assertEqual(req["pairingBasis"], "SHARED_CORRELATION_ID")
        self.assertIn({"restField": "Amount", "supplierField": "Req.Price",
                       "classification": "EXACT_SCALAR_EQUALITY_CANDIDATE"},
                      req["exactValueCandidates"])
        self.assertTrue(any("LastName" in x["restField"] for x in req["sameNamedDifferentValues"]))
        rep = next(x for x in result["comparisons"] if x["direction"] ==
                   "SUPPLIER_RESPONSE_TO_REST_RESPONSE")
        self.assertTrue(any(x["restField"] == "Fare" for x in rep["sameNamedDifferentValues"]))
        dumped = json.dumps(result)
        self.assertNotIn("ConfidentialName", dumped)
        self.assertNotIn("DifferentName", dumped)
        self.assertNotIn("CHF-12345", dumped)
        self.assertNotIn("DO_NOT_PROCESS", dumped)

    def test_ambiguous_multiple_provider_exchanges_do_not_get_invented_pairs(self):
        raw = zip_bytes([
            ("rest/01-request.json", b'{"price":"ABCD1234"}'),
            ("rest/02-request.json", b'{"price":"ABCD1234"}'),
            ("supplier/AirFranceKLM/01-request-body.xml",
             b'<Req><Value>ABCD1234</Value></Req>'),
            ("supplier/AirFranceKLM/02-request-body.xml",
             b'<Req><Value>ABCD1234</Value></Req>'),
        ])
        result = compare_zip_bytes(raw, AF["aliases"])
        self.assertEqual(result["comparisons"], [])
        self.assertIn("AMBIGUOUS_PAIRING", result["issues"])

    def test_single_unambiguous_pair_is_explicitly_candidate_only(self):
        raw = zip_bytes([
            ("rest/12-request.json", b'{"total":"200.99"}'),
            ("supplier/AirFranceKLM/12-request-body.xml",
             b'<RQ><Amount>200.99</Amount></RQ>'),
        ])
        result = compare_zip_bytes(raw, AF["aliases"])
        self.assertEqual(result["comparisons"][0]["pairingBasis"], "UNIQUE_SINGLE_EXCHANGE")
        self.assertEqual(result["comparisons"][0]["mappingStatus"], "CANDIDATE_ONLY")

    def test_schema_parsing_rejects_external_xml_entities(self):
        values, warning = leaf_values(b'<!DOCTYPE x [<!ENTITY leak SYSTEM "file:///etc/passwd">]><x>&leak;</x>', ".xml")
        self.assertFalse(values)
        self.assertEqual(warning, "XML_ENTITIES_DISALLOWED")

    def test_structural_evidence_also_includes_value_review(self):
        raw = zip_bytes([
            ("rest/12-request.json", b'{"status":"CANCELLED"}'),
            ("supplier/AirFranceKLM/12-request-body.xml",
             b'<Request><Status>CANCELLED</Status></Request>'),
        ])
        result = analyze_zip_bytes(raw, AF)
        self.assertIn("valueReview", result)
        self.assertEqual(len(result["valueReview"]["comparisons"]), 1)
        self.assertFalse(any("CANCELLED" in json.dumps(x)
                             for x in result["valueReview"]["comparisons"]))

    def test_optional_draft_is_available_even_without_email_signal_or_logs(self):
        analysis = {
            "signal": "READY", "needsEmail": False,
            "standardDescription": "When StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED, omit the segment from REST.",
            "emailDraft": {"to": "", "subject": "", "body": ""},
        }
        result = make_ready_draft("CCON-15340", analysis, attachment_ready=False)
        self.assertIn("Dear Team,", result["body"])
        self.assertIn("StatusCode=CANCELLED", result["body"])
        self.assertNotIn("Logs are attached", result["body"])
        self.assertEqual(result["to"], "")
        self.assertIn("[15340]", result["subject"])
        with_logs = make_ready_draft("CCON-15340", analysis, attachment_ready=True)
        self.assertIn("Logs are attached for your reference.", with_logs["body"])

    def test_existing_agent_email_preserved_and_no_false_attachment_claim(self):
        draft = make_ready_draft("CCON-15340", {
            "emailDraft": {"to": "", "subject": "AER. retrievePNR. Invalid response [15340]",
                           "body": "Dear Team,\n\nCould you clarify the error handling?"}
        }, attachment_ready=False)
        self.assertIn("Could you clarify the error handling?", draft["body"])
        self.assertNotIn("Logs are attached for your reference.", draft["body"])


if __name__ == "__main__":
    unittest.main()
