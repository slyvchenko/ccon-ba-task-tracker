"""Synthetic 20-case private QA-13 preflight: never claims real business acceptance."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from evaluation import RUBRIC
from qa13_gold_preflight import check, main


class PrivateGoldPreflightTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="ccon-qa13-gold-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.directory=self.root/"data"/"evaluation"
        self.directory.mkdir(parents=True)
        self.keys=[f"SYNTHETIC-{i:02d}" for i in range(20)]
        self.write("selected_cases.json",{
            "cases":[{"key":key,"contextFingerprint":"freeze-"+key} for key in self.keys]})
        reviews=[]
        gold=[]
        for key in self.keys:
            item=lambda grade,minutes: {
                "scores":{field:grade for field in RUBRIC},
                "criticalFalseClaims":[],
                "minutesSpent":minutes,
                "reviewed":True}
            reviews.append({"key":key,"reviewer":"CHECKER-B",
                            "baseline":item(2,10),"candidate":item(4,3)})
            gold.append({"key":key,"referenceAuthorCode":"AUTHOR-A",
                         "independentReviewerCode":"CHECKER-B",
                         "referenceFrozenAt":"2026-10-20T09:00:00Z",
                         "candidateFirstSeenAt":"2026-10-20T10:00:00Z",
                         "independentSourceReview":True,"goldExpectedWritten":True,
                         "sourceFingerprint":"freeze-"+key})
        self.write("reviews.json",{"reviews":reviews})
        self.write("gold_attestations.json",{"cases":gold})
        for variant in ("baseline","candidate"):
            self.write(variant+"_predictions.json",
                {"variant":variant,"analyses":{
                    key:{"contextFingerprint":"freeze-"+key}
                    for key in self.keys}})

    def write(self,name,payload):
        (self.directory/name).write_text(json.dumps(payload),encoding="utf-8")

    def get(self,name):
        return json.loads((self.directory/name).read_text(encoding="utf-8"))

    def test_complete_synthetic_case_attestation_never_claims_business_acceptance(self):
        before={p.name:p.read_bytes() for p in self.directory.iterdir()}
        report=check(self.root)
        self.assertEqual(report["caseCount"],20)
        self.assertEqual(report["independentGoldCases"],20)
        self.assertEqual(report["reviewedCases"],20)
        self.assertTrue(report["rubricTargetsFromHumanScores"])
        self.assertEqual(report["status"],"READY_FOR_PRIVATE_HUMAN_SIGNOFF")
        self.assertEqual(report["humanAcceptance"],"NOT_RECORDED")
        self.assertTrue(report["baselineFrozen"])
        self.assertTrue(report["candidateFrozen"])
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.directory.iterdir()})
        output=json.dumps(report)
        for secret in ("SYNTHETIC-01","AUTHOR-A","CHECKER-B",str(self.root)):
            self.assertNotIn(secret,output)
        self.assertFalse(report["externalAccess"])

    def test_independence_and_freeze_order_required(self):
        gold=self.get("gold_attestations.json")
        gold["cases"][0]["independentReviewerCode"]="AUTHOR-A"
        gold["cases"][0]["referenceFrozenAt"]="2026-10-20T12:00:00Z"
        self.write("gold_attestations.json",gold)
        result=check(self.root)
        self.assertEqual(result["independentGoldCases"],19)
        self.assertEqual(result["status"],"INCOMPLETE_PRIVATE_GOLD_STUDY")
        self.assertNotIn("SYNTHETIC-01",json.dumps(result))

    def test_mismatched_frozen_prediction_fails_closed(self):
        baseline=self.get("baseline_predictions.json")
        baseline["analyses"][self.keys[3]]["contextFingerprint"]="OUTDATED"
        self.write("baseline_predictions.json",baseline)
        result=check(self.root)
        self.assertFalse(result["baselineFrozen"])
        self.assertEqual(result["status"],"INCOMPLETE_PRIVATE_GOLD_STUDY")

    def test_critical_false_claim_fails_human_rubric_even_with_gold_attestation(self):
        reviews=self.get("reviews.json")
        reviews["reviews"][2]["candidate"]["criticalFalseClaims"]=["SYNTHETIC PRIVATE ERROR"]
        self.write("reviews.json",reviews)
        result=check(self.root)
        self.assertEqual(result["status"],"RUBRIC_TARGETS_NOT_MET")
        self.assertFalse(result["rubricTargetsFromHumanScores"])
        self.assertEqual(result["humanCriticalFalseClaims"],1)
        self.assertNotIn("SYNTHETIC PRIVATE ERROR",json.dumps(result))

    def test_no_real_case_or_missing_attestation_is_never_pass(self):
        (self.directory/"gold_attestations.json").unlink()
        result=check(self.root)
        self.assertEqual(result["independentGoldCases"],0)
        self.assertIn("gold",result["missingFiles"])
        self.assertEqual(result["humanAcceptance"],"NOT_RECORDED")
        with tempfile.TemporaryDirectory(prefix="ccon-no-gold-") as folder:
            missing=check(folder)
            self.assertEqual(missing["status"],"INCOMPLETE_PRIVATE_GOLD_STUDY")
            self.assertEqual(missing["caseCount"],0)

    def test_cli_rejects_invalid_json_without_leaking_contents(self):
        (self.directory/"gold_attestations.json").write_text("SYNTHETIC PRIVATE BAD JSON",encoding="utf-8")
        out,err=io.StringIO(),io.StringIO()
        with redirect_stdout(out),redirect_stderr(err),self.assertRaises(SystemExit) as thrown:
            main(["--root",str(self.root)])
        self.assertEqual(thrown.exception.code,1)
        self.assertNotIn("SYNTHETIC PRIVATE",out.getvalue()+err.getvalue())
        self.assertNotIn(str(self.root),out.getvalue()+err.getvalue())


if __name__=="__main__":
    unittest.main()
