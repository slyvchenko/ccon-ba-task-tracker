"""Synthetic-only human review form checks, never publish real case data."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from private_gold_review import summarize, main

DISTRIBUTION = ["READY"]*4 + ["WRITE"]*5 + ["WAIT"]*4 + ["DECIDE"]*4 + ["DEEP"]*5 + ["ERROR"]*4


def cohort():
    return {
        "schemaVersion": 1,
        "cases": [{
            "id": f"GOLD-{i:02d}",
            "archetype": kind,
            "referenceFrozenBeforeAI": True,
            "independentReview": True,
            "sourceAccessVerified": True,
            "facts": "PASS", "rules": "PASS", "handoff": "PASS",
            "criticalFalseReady": False, "unapprovedExternalAction": False,
            "falseSourceOrRecipient": False,
            "result": "PASSED",
            "ttnaSeconds": 4 + i, "ttshSeconds": 9 + i,
        } for i,kind in enumerate(DISTRIBUTION,1)],
    }


class PrivateGoldReviewTests(unittest.TestCase):
    def test_synthetic_complete_form_never_claims_human_or_release_acceptance(self):
        out=summarize(cohort())
        self.assertEqual(out["caseCount"],26)
        self.assertTrue(out["criteriaReadyForHumanDecision"])
        self.assertEqual(out["humanAcceptance"],"NOT_RECORDED")
        self.assertFalse(out["releaseApproved"])
        self.assertEqual(out["results"]["PASSED"],26)
        self.assertEqual(out["verifiedSourceAccessCount"],26)
        self.assertEqual(out["timedCases"],{"ttna":26,"ttsh":26})
        self.assertEqual(out["archetypeCounts"]["DEEP"],5)
        self.assertNotIn("GOLD-01",json.dumps(out))

    def test_critical_violation_or_missing_independent_review_blocks_readiness(self):
        for column,value in [
            ("criticalFalseReady",True),("unapprovedExternalAction",True),
            ("falseSourceOrRecipient",True),("independentReview",False),
            ("referenceFrozenBeforeAI",False),("sourceAccessVerified",False),
            ("facts","INCONCLUSIVE"),("rules","FAIL"),
            ("handoff","FAIL"),("result","BLOCKED"),
            ("ttnaSeconds",None),("ttshSeconds",None),
        ]:
            pack=cohort()
            pack["cases"][0][column]=value
            with self.subTest(column=column):
                result=summarize(pack)
                self.assertFalse(result["criteriaReadyForHumanDecision"])
                self.assertFalse(result["releaseApproved"])

    def test_id_validation_rejects_real_jira_pnr_and_unknown_private_fields(self):
        for bad in ("CCON-12345","ZX97YJ","GOLD-31","GOLD-00"):
            data=cohort()
            data["cases"][0]["id"]=bad
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                summarize(data)
        data=cohort()
        data["cases"][0]["emailAddress"]="private@example.invalid"
        with self.assertRaises(ValueError):
            summarize(data)
        data=cohort()
        data["cases"][0]["id"]=data["cases"][1]["id"]
        with self.assertRaises(ValueError):
            summarize(data)

    def test_cohort_limits_and_explicit_types(self):
        for count in (0,19,31):
            pack=cohort()
            pack["cases"]=pack["cases"][:count] if count<26 else pack["cases"]+[pack["cases"][-1]]*5
            with self.subTest(count=count),self.assertRaises(ValueError):
                summarize(pack)
        data=cohort()
        data["cases"][0]["independentReview"]=1
        with self.assertRaises(ValueError):
            summarize(data)
        data=cohort()
        data["cases"][0]["ttnaSeconds"]=True
        with self.assertRaises(ValueError):
            summarize(data)

    def test_local_cli_prints_only_aggregates_not_private_source_data(self):
        with tempfile.TemporaryDirectory(prefix="gold-private-synthetic-") as folder:
            path=Path(folder)/"private-review.json"
            path.write_text(json.dumps(cohort()),encoding="utf-8")
            out=io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["--input",str(path)]),0)
            self.assertIn("NOT_RECORDED",out.getvalue())
            self.assertNotIn("GOLD-01",out.getvalue())
            self.assertNotIn(str(path),out.getvalue())
            bad=cohort()
            bad["cases"][0]["description"]="PRIVATE REST ZX97YJ"
            path.write_text(json.dumps(bad),encoding="utf-8")
            stdout,stderr=io.StringIO(),io.StringIO()
            with redirect_stdout(stdout),redirect_stderr(stderr):
                self.assertEqual(main(["--input",str(path)]),1)
            self.assertEqual(stdout.getvalue(),"")
            self.assertNotIn("ZX97YJ",stderr.getvalue())
            self.assertNotIn(str(path),stderr.getvalue())


if __name__=="__main__":
    unittest.main()
