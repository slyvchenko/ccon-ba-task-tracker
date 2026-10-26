"""Synthetic privacy-bounded evidence provenance and source cache tests."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from kibana_evidence import discover_links, plan_for_issue
from model_analysis import linked_document_version, evidence_for_issue, task_source
from error_series import _observations
from storage import write_json

class EvidenceProvenanceTests(unittest.TestCase):
    def test_source_version_changes_with_local_verified_document_and_not_with_order(self):
        src={"linkedDocumentAudit":{
            "eligibleLinkedSourceCount":2, "verifiedLocalSourceCount":1,
            "notVerifiedCount":1,
            "attachments":[{"attachmentId":"1001","sourceSha256":"a"*64,
                            "state":"LOCAL_TEXT_VERIFIED"}],
            "wikiPages":[{"pageId":"500","state":"NOT_READ"}],
            "variantCandidates":[]}}
        first=linked_document_version(src)
        self.assertEqual(first,linked_document_version(json.loads(json.dumps(src))))
        changed=json.loads(json.dumps(src))
        changed["linkedDocumentAudit"]["wikiPages"][0]["state"]="LOCAL_TEXT_VERIFIED"
        changed["linkedDocumentAudit"]["verifiedLocalSourceCount"]=2
        changed["linkedDocumentAudit"]["notVerifiedCount"]=0
        self.assertNotEqual(first,linked_document_version(changed))
        changed["linkedDocumentAudit"]["wikiPages"][0]["sourceSha256"]="b"*64
        self.assertNotEqual(first,linked_document_version(changed))
        # Digest is not a substitute for semantic business approval.
        self.assertEqual(len(first),16)

    def test_evidence_report_exposes_counts_not_sensitive_correlations(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            report={"issueKey":"CCON-1","sourceSha256":"a"*64,
                    "schemaVersion":1,"valueReview":{
                       "comparisons":[],
                       "coverage":[{"direction":"REST_REQUEST_TO_SUPPLIER_REQUEST",
                                    "restExchanges":2,"supplierExchanges":1,
                                    "unpairedRest":2,"unpairedSupplier":1,
                                    "state":"INCOMPLETE_OR_AMBIGUOUS"}],
                       "issues":["AMBIGUOUS_PAIRING"],
                       "disclaimer":"Synthetic evidence only"},
                    "supplier":"AF/KL"}
            write_json(root/"data/evidence/CCON-1/test.json",report)
            result,version=evidence_for_issue(root,"CCON-1")
            self.assertEqual(len(result),1)
            self.assertEqual(result[0]["valueReview"]["coverage"][0]["unpairedRest"],2)
            self.assertIn("AMBIGUOUS_PAIRING",result[0]["valueReview"]["issues"])
            self.assertEqual(len(version),16)
            self.assertNotIn("source text",json.dumps(result).lower())

    def test_unauthorized_kibana_link_never_becomes_read_evidence(self):
        issue={"key":"CCON-1","summary":"AF/KL RetrievePNR",
               "description":("See https://evil.test/app/discover "
                              "and https://kibana.example.org/app/discover#_a=errorlog"),
               "comments":[]}
        links=discover_links(issue)
        self.assertTrue(all("evil.test" not in x["url"] for x in links))
        plan=plan_for_issue(issue)
        self.assertTrue(plan["kibana"])
        self.assertTrue(all(x["readOnly"] is True for x in plan["kibana"]))
        self.assertTrue(all(x["kind"] in ("SEARCH","ERROR_SEARCH") for x in plan["kibana"]))
        self.assertNotIn("CONFIRMED",json.dumps(plan))

    def test_rca_flags_every_new_correlational_gap_as_ambiguous(self):
        for gap in ("AMBIGUOUS_PAIRING","CORRELATION_MISMATCH",
                    "UNCORRELATED_EXCHANGE","INCOMPLETE_EXCHANGE"):
            with self.subTest(gap=gap):
                result = _observations({"valueReview":{"issues":[gap]}})
                self.assertTrue(result["hasAmbiguousMapping"])
        result = _observations({"valueReview":{"issues":[]}})
        self.assertFalse(result["hasAmbiguousMapping"])

    def test_no_browser_access_cannot_make_source_confirmed(self):
        ctx={"issues":{"CCON-1":{"key":"CCON-1","fingerprint":"f1",
                                 "description":"Synthetic rule","links":[],
                                 "attachments":[],"comments":[]}}}
        result=task_source(ctx,{"key":"CCON-1","activeSprintStatus":"UNVERIFIED"},"",root=None)
        self.assertEqual(result["linkedDocumentAudit"]["unreadSourceStatus"],"NO_LOCAL_VERIFICATION")
        self.assertEqual(result["evidenceReports"],[])

if __name__=="__main__":
    unittest.main()
