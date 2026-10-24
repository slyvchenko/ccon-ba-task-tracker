import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from layered_evidence import analyze_zip_bytes, analyze_zip, classify, inspect_payload
from supplier_logs import supplier_hint


def build_zip(items):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, data in items:
            z.writestr(name, data)
    return out.getvalue()


class LayeredEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.supplier = supplier_hint("AF/KL. retrievePNR. Error")

    def test_only_selected_supplier_plus_rest_and_errors(self):
        zip_bytes = build_zip([
            ("supplier/AirFranceKLM/1-Booking-doOrder-1-request-body.xml",
             b"<RQ><cconFlowId>12345678-1234-4234-8234-123456789012</cconFlowId><Fare>100</Fare></RQ>"),
            ("supplier/AirFranceKLM/1-Booking-doOrder-1-response-body.xml",
             b"<RS><StatusCode>CANCELLED</StatusCode><Error><Code>AF_ERROR</Code></Error></RS>"),
            ("supplier/FinnAir/10-Book-doOther-1-response-body.xml",
             b"<RS><private>DO_NOT_READ</private></RS>"),
            ("rest/12-request.json",
             b'{"cconFlowId":"12345678-1234-4234-8234-123456789012","fare":100}'),
            ("rest/13-response.json", b'{"status":"FAILED","errorCode":"AF_ERROR"}'),
            ("rest/errors/14-error.json", b'{"errorCode":"AF_ERROR","message":"missing segment"}'),
            ("readme.txt", b"not relevant"),
        ])
        result = analyze_zip_bytes(zip_bytes, self.supplier)
        self.assertEqual(result["counts"], {"supplier": 2, "rest": 2, "errors": 1})
        self.assertEqual(result["totalMatchingFiles"], 5)
        self.assertEqual(result["ignoredOtherSupplierAndUnrelatedFiles"], 2)
        self.assertEqual(result["supplier"], "AirFranceKLM")
        self.assertTrue(any(x["code"] == "AF_ERROR" for x in result["errorCodes"]))
        self.assertFalse(any("FinnAir" in x["file"] for x in result["samples"]))
        self.assertTrue(all(x["layer"] in ("rest", "errors", "supplier") for x in result["samples"]))

    def test_no_supplier_match_is_partial_not_cross_supplier_contamination(self):
        data = build_zip([
            ("supplier/FinnAir/1-other-1.xml", b"<Data>SECRET</Data>"),
            ("rest/request.json", b'{"bookingId":"123"}'),
        ])
        result = analyze_zip_bytes(data, self.supplier)
        self.assertEqual(result["counts"], {"rest": 1})
        self.assertEqual(result["status"], "PARTIAL")
        self.assertTrue(any("No selected supplier" in x["reason"] for x in result["warnings"]))

    def test_missing_correlation_gives_explicit_question_not_guessed_mapping(self):
        data = build_zip([
            ("supplier/AirFranceKLM/request.xml", b"<Req><Fare>25</Fare></Req>"),
            ("rest/request.json", b'{"price":25}'),
        ])
        result = analyze_zip_bytes(data, self.supplier)
        self.assertEqual(result["correlationCandidates"], [])
        self.assertTrue(any("correlation" in q for q in result["questionsUk"]))

    def test_pairing_only_same_real_correlation_hash(self):
        cid = "12345678-1234-4234-8234-123456789012"
        data = build_zip([
            ("supplier/AirFranceKLM/request.xml", ('<Req correlationId="' + cid + '"/>').encode()),
            ("rest/request.json", ('{"correlationId":"' + cid + '"}').encode()),
        ])
        result = analyze_zip_bytes(data, self.supplier)
        self.assertEqual(len(result["correlationCandidates"]), 1)
        self.assertEqual(result["correlationCandidates"][0]["confidence"], "CANDIDATE_ONLY")

    def test_xml_is_not_parsed_when_dtd_present(self):
        value = inspect_payload(b"<!DOCTYPE data><root/>", ".xml")
        self.assertIn("DTD", value["parseWarning"])
        self.assertEqual(value["fields"], [])

    def test_reject_zip_slip_and_excessive_zip(self):
        data = build_zip([("../outside.xml", b"<Root/>")])
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            analyze_zip_bytes(data, self.supplier)
        with self.assertRaises(ValueError):
            analyze_zip_bytes(b"not a zip", self.supplier)

    def test_analyze_persists_manifest_without_xml_values(self):
        data = build_zip([
            ("supplier/AirFranceKLM/data.xml", b"<Root><Surname>VeryPrivateSurname</Surname></Root>"),
            ("rest/request.json", b'{"fare":2,"surname":"VeryPrivateSurname"}'),
        ])
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "full.zip"
            source.write_bytes(data)
            result = analyze_zip(source, "AF/KL", d, "CCON-123")
            path = next((Path(d) / "data/evidence/CCON-123").glob("*.json"))
            saved = path.read_text()
            self.assertNotIn("VeryPrivateSurname", saved)
            self.assertEqual(result["issueKey"], "CCON-123")
            self.assertEqual(result["totalMatchingFiles"], 2)


if __name__ == "__main__":
    unittest.main()
