"""QA-07 realistic offline REST/supplier/error ZIP regression matrix.

Synthetic fixtures deliberately include customer-like values that must never
appear in private structural reports; they are not corporate data.
"""
import io
import json
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

from flow_diagnostics import shape_and_times
from layered_evidence import analyze_zip_bytes
from supplier_logs import inspect_bundle, supplier_hint

AF = supplier_hint("AF/KL. retrievePNR. AF_REJECTED")
AY = supplier_hint("Finnair. retrievePNR. AY_TIMEOUT")


def archive(entries):
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as bundle:
        for name, data in entries:
            bundle.writestr(name, data)
    return buffer.getvalue()


def generated_case(provider="AirFranceKLM", *, multi_error=True,
                   missing_supplier=False, nested=False, retry=False):
    fields = [
        ("rest/01-request.json",
         b'{"timestamp":"2026-10-24T09:00:00+02:00",'
         b'"cconFlowId":"12345678-1234-4234-8234-123456789012",'
         b'"passengerName":"SYNTHETIC_CUSTOMER","Fare":123}'),
        ("rest/02-response.json",
         b'{"timestamp":"2026-10-24T07:00:05Z","errorCode":"AF_REJECTED"}'),
        ("rest/errors/03-error.json",
         b'{"errorCode":"AF_REJECTED","stage":"REST"}'),
    ]
    if multi_error:
        fields.append(("rest/errors/04-error.json",
                       b'{"errorCode":"AF_TIMEOUT","stage":"REST"}'))
    if not missing_supplier:
        fields.extend([
            (f"supplier/{provider}/1-retrievePNR-doByLocator-2-request-body.xml",
             b'<RQ><eventTime>2026-10-24T07:00:01Z</eventTime><Fare>123</Fare></RQ>'),
            (f"supplier/{provider}/1-retrievePNR-doByLocator-2-response-body.xml",
             b'<RS><eventTime>2026-10-24T07:00:03Z</eventTime>'
             b'<providerError><code>AF_REJECTED</code></providerError></RS>'),
        ])
    if retry:
        fields.extend([
            (f"supplier/{provider}/1-retrievePNR-doByLocator-9-request-body.xml",
             b'<RQ><eventTime>2026-10-24T07:00:04Z</eventTime></RQ>'),
            (f"supplier/{provider}/1-retrievePNR-doByLocator-9-response-body.xml",
             b'<RS><eventTime>2026-10-24T07:00:05Z</eventTime></RS>'),
        ])
    if nested:
        fields.append(("supplier/Unrelated/embedded.zip",
                       archive([("private.json", b'{"secret":"SYNTHETIC_INNER"}')])))
    return archive(fields)


class EvidenceRegressionMatrixTests(unittest.TestCase):
    def test_selected_supplier_multilayer_multi_error_fixture(self):
        payload = generated_case(retry=True, nested=True)
        report = analyze_zip_bytes(payload, AF)
        self.assertEqual(report["counts"]["rest"], 2)
        self.assertEqual(report["counts"]["errors"], 2)
        self.assertEqual(report["counts"]["supplier"], 4)
        codes = {c["code"] for c in report["errorCodes"]}
        self.assertTrue({"AF_REJECTED", "AF_TIMEOUT"} <= codes)
        diagnostic = report["flowDiagnostics"]
        self.assertEqual(diagnostic["timestampedEntries"], 8)
        self.assertTrue(all(row.get("timeEvidence") == "PAYLOAD_TIMESTAMP"
                            for row in diagnostic["timeline"]
                            if row.get("eventTimeUtc")))
        serialized = json.dumps(report)
        self.assertNotIn("SYNTHETIC_CUSTOMER", serialized)
        self.assertNotIn("SYNTHETIC_INNER", serialized)
        self.assertNotIn("private.json", serialized)
        self.assertNotIn("Unrelated", serialized)
        self.assertTrue(diagnostic["repeatedMethodCandidates"])
        self.assertEqual(diagnostic["repeatedMethodCandidates"][0]["interpretation"],
                         "REPEATED_METHOD_RETRY_NOT_PROVEN")

    def test_incomplete_supplier_is_explicitly_partial_not_no_error(self):
        manifest = analyze_zip_bytes(generated_case(missing_supplier=True), AF)
        self.assertEqual(manifest["status"], "PARTIAL")
        self.assertFalse(manifest["counts"].get("supplier"))
        self.assertEqual(manifest["counts"]["errors"], 2)
        self.assertTrue(any("supplier" in str(w).lower() for w in manifest["warnings"]))

    def test_same_zip_never_mixes_other_provider_when_selected(self):
        payload = generated_case(provider="FinnAir")
        af = analyze_zip_bytes(payload, AF)
        ay = analyze_zip_bytes(payload, AY)
        self.assertFalse(af["counts"].get("supplier"))
        self.assertEqual(ay["counts"]["supplier"], 2)
        self.assertEqual(af["counts"]["rest"], 2)
        self.assertFalse(any("FinnAir" in str(item) for item in af["samples"]))
        self.assertTrue(all(row["layer"] in ("rest", "errors", "supplier")
                            for row in ay["samples"]))

    def test_supplier_attachment_still_xml_only_not_full_rest_zip(self):
        payload = generated_case(retry=True)
        prepared = inspect_bundle(payload, ["AirFranceKLM"], "AF/KL. retrievePNR. AF_REJECTED")
        self.assertEqual(prepared["exchangeCount"], 2)
        self.assertEqual(len(prepared["files"]), 4)
        self.assertEqual(prepared["preferredMethod"], "doByLocator")
        self.assertTrue(all(x["output"].endswith(".xml") for x in prepared["files"]))
        self.assertFalse(any("rest" in x["source"] for x in prepared["files"]))

    def test_malformed_xml_timestamp_and_invalid_nested_payload(self):
        shape = shape_and_times(
            b'<RS><eventTime>2026-10-24T07:00:00</eventTime><Item/></RS>', ".xml")
        self.assertEqual(shape["eventTimes"], [])
        entity = shape_and_times(
            b'<!DOCTYPE a [<!ENTITY ext SYSTEM "file:///etc/passwd">]><a>&ext;</a>', ".xml")
        self.assertEqual(entity["parseStatus"], "XML_ENTITY_REJECTED")
        with self.assertRaises(ValueError):
            analyze_zip_bytes(archive([("../evil.json", b'{"x":1}')]), AF)


if __name__ == "__main__":
    unittest.main()
