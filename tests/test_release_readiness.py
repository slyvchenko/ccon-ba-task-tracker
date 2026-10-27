"""Synthetic release gate contract, never evidence of live BA/Windows acceptance."""
import copy
import json
import unittest

from release_readiness import HUMAN_GATES, WINDOWS_GATES, closeout_matrix, release_report, main
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

    def test_full_closeout_matrix_has_every_requirement_and_no_fake_pass(self):
        result=closeout_matrix(self.ledger)
        self.assertEqual(result["totalRequirements"],129)
        self.assertEqual(len(result["items"]),129)
        self.assertEqual(len(set(x["id"] for x in result["items"])),129)
        self.assertEqual(result["sourceTestPointerCoverage"],78)
        self.assertFalse(result["releaseApproved"])
        self.assertEqual(result["readiness"],"BLOCKED_INDEPENDENT_UAT")
        self.assertEqual(result["privateAcceptanceVerified"],0)
        self.assertTrue(all(not x["verifiedHumanAcceptance"] for x in result["items"]))
        self.assertEqual(len(result["externalRequiredChecks"]),
                         len(HUMAN_GATES)+len(WINDOWS_GATES))
        self.assertEqual(sum(result["nextActionCounts"].values()),129)
        self.assertEqual(len([x for x in result["items"]
                              if x["nextAction"]=="EXPLICIT_PRODUCT_SCOPE_DECISION"]),4)
        self.assertEqual(len([x for x in result["items"]
                              if x["nextAction"]=="INDEPENDENT_HUMAN_UAT"]),3)
        self.assertEqual(len([x for x in result["items"]
                              if x["reportedCategory"] in ("PLANNED","NEXT")]),0)
        self.assertEqual([x["priority"] for x in result["items"]][:44],["P0"]*44)

    def test_closeout_uses_only_public_ids_and_status_codes(self):
        data=copy.deepcopy(self.ledger)
        secret="SYNTHETIC-SUPPLIER-PNR-EXAMPLE"
        data["items"][0]["requirement"]=secret
        data["items"][0]["acceptance_criteria"]=secret
        data["items"][0]["code_locator"]=secret
        data["items"][0]["test_locator"]=secret
        result=closeout_matrix(data)
        self.assertNotIn(secret,json.dumps(result))
        self.assertEqual(result["sourceTestPointerCoverage"],78)
        data["items"][0]["id"]="PRIVATE-PNR-12345"
        with self.assertRaisesRegex(ValueError,"identifier"):
            closeout_matrix(data)

    def test_fake_human_pass_claims_do_not_influence_closeout(self):
        data=copy.deepcopy(self.ledger)
        for row in data["items"]:
            row["human_acceptance"]="PASSED"
        result=closeout_matrix(data)
        self.assertFalse(result["releaseApproved"])
        self.assertEqual(result["privateAcceptanceVerified"],0)
        self.assertTrue(all(not r["verifiedHumanAcceptance"] for r in result["items"]))

    def test_closeout_cli_is_read_only_and_require_ready_fails_closed(self):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        report=io.StringIO()
        with redirect_stdout(report):
            self.assertEqual(main(["--closeout"]),0)
        result=json.loads(report.getvalue())
        self.assertEqual(result["totalRequirements"],129)
        self.assertEqual(result["privateAcceptanceVerified"],0)
        with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--closeout","--require-ready"]),2)

    def test_optional_cloud_is_not_treated_as_completed_or_approved(self):
        report=release_report(self.ledger)
        self.assertEqual(report["reportedStatusCounts"]["DEFERRED"],4)
        self.assertFalse(report["releaseApproved"])


if __name__=="__main__":
    unittest.main()
