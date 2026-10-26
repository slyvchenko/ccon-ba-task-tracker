"""Synthetic release gate contract, never evidence of live BA/Windows acceptance."""
import copy
import json
import unittest

from release_readiness import HUMAN_GATES, WINDOWS_GATES, release_report
from backlog_audit import produce


class ReleaseReadinessTests(unittest.TestCase):
    def setUp(self):
        self.ledger = produce()

    def test_current_source_ledger_is_structurally_consistent_but_not_approved(self):
        result=release_report(self.ledger)
        self.assertEqual(result["totalRequirements"],129)
        self.assertEqual(result["priorityCounts"]["P0"],44)
        self.assertEqual(result["p0WithoutReportedAcceptance"],44)
        self.assertEqual(result["readiness"],"BLOCKED_INDEPENDENT_UAT")
        self.assertFalse(result["releaseApproved"])
        self.assertEqual(result["humanAcceptanceClaimsInLedger"],0)
        self.assertEqual(len(result["externalGates"]),len(HUMAN_GATES)+len(WINDOWS_GATES))

    def test_fake_human_pass_claims_cannot_auto_approve_release(self):
        forged=copy.deepcopy(self.ledger)
        for item in forged["items"]:
            item["human_acceptance"]="PASSED"
        result=release_report(forged)
        self.assertEqual(result["p0WithoutReportedAcceptance"],0)
        self.assertEqual(result["humanAcceptanceClaimsInLedger"],129)
        self.assertFalse(result["releaseApproved"])
        self.assertEqual(result["readiness"],"BLOCKED_INDEPENDENT_UAT")
        self.assertTrue(all(x["state"]=="NOT_VERIFIED_IN_PUBLIC_REPO"
                            for x in result["externalGates"]))

    def test_missing_qa_gate_invalid_counts_and_duplicate_rows_fail_closed(self):
        missing=copy.deepcopy(self.ledger)
        missing["items"]=[x for x in missing["items"] if x["id"]!="QA-02"]
        missing["counts"]["total"]-=1
        missing["counts"]["reported_statuses"]["GATE"]-=1
        with self.assertRaisesRegex(ValueError,"Required human acceptance"):
            release_report(missing)
        broken=copy.deepcopy(self.ledger)
        broken["counts"]["total"]=1
        with self.assertRaisesRegex(ValueError,"total"):
            release_report(broken)
        duplicated=copy.deepcopy(self.ledger)
        duplicated["items"][1]["id"]=duplicated["items"][0]["id"]
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            release_report(duplicated)

    def test_external_report_only_contains_aggregate_no_user_or_supplier_text(self):
        data=copy.deepcopy(self.ledger)
        secret="SECRET_SYNTHETIC_PNR_123"
        data["items"][0]["requirement"]=secret
        result=release_report(data)
        encoded=json.dumps(result)
        self.assertNotIn(secret,encoded)
        self.assertNotIn("https://",encoded)
        self.assertIn("BLOCKED_INDEPENDENT_UAT",encoded)

    def test_optional_cloud_is_not_treated_as_completed_or_approved(self):
        report=release_report(self.ledger)
        self.assertEqual(report["reportedStatusCounts"]["DEFERRED"],4)
        self.assertFalse(report["releaseApproved"])


if __name__=="__main__":
    unittest.main()
