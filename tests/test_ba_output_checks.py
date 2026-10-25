"""Synthetic output-gate checks for BA-01, BA-02, OUT-01 and QA-04."""
import copy
import unittest

from ba_output_checks import dossier_checks, email_checks, technical_literals
from ba_quality_gate import description_review, quality_gate
from test_ba_quality_gate import analysis, issue


class BAOutputChecksTests(unittest.TestCase):
    def test_exact_field_values_from_confirmed_rule_never_silently_disappear(self):
        result = analysis()
        description = (
            "#### Objective\nOnly a matching private fare is selected.\n"
            "#### To Do\nIF TypeCode = TO THEN retain the segment.\n"
            "#### QA\nCheck the matching code returns the expected segment."
        )
        confirmed = {"rules": [{
            "id": "R1", "certainty": "CONFIRMED",
            "whenUk": "IF TypeCode = no_code",
            "thenUk": "THEN set TypeCode = TO, DeliveryStatusCode=REMOVED",
        }]}
        codes = {item["code"] for item in description_review(description, confirmed)}
        self.assertIn("CONFIRMED_LITERAL_OMITTED", codes)
        self.assertIn("CONFIRMED_FIELD_OMITTED", codes)
        self.assertEqual(technical_literals("TypeCode = no_code", "TypeCode = TO"),
                         {"no_code", "TO"})
        complete = description.replace(
            "TypeCode = TO THEN", "TypeCode = no_code THEN"
        ).replace("retain the segment.", "retain the segment with DeliveryStatusCode=REMOVED and TypeCode=TO.")
        complete_codes = {item["code"] for item in description_review(complete, confirmed)}
        self.assertNotIn("CONFIRMED_LITERAL_OMITTED", complete_codes)
        self.assertNotIn("CONFIRMED_FIELD_OMITTED", complete_codes)

    def test_compound_or_condition_not_changed_into_and(self):
        rule = {"rules": [{"id": "R1", "certainty": "CONFIRMED",
                           "whenUk": "StatusCode=CANCELLED OR DeliveryStatusCode=REMOVED",
                           "thenUk": "Omit segment from REST"}]}
        description = ("#### To Do\nIF StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED "
                       "THEN omit the segment.\n#### QA\nCheck omission for both statuses.")
        findings = description_review(description, rule)
        self.assertIn("COMPOUND_OPERATOR_OMITTED", {x["code"] for x in findings})
        corrected = description.replace("CANCELLED AND", "CANCELLED OR")
        self.assertNotIn("COMPOUND_OPERATOR_OMITTED",
                         {x["code"] for x in description_review(corrected, rule)})

    def test_generic_qa_is_review_only_not_semantic_acceptance(self):
        brief = {"rules": []}
        desc = "#### Objective\nImplement condition.\n#### QA\nCheck that everything works."
        self.assertIn("DESCRIPTION_QA_GENERIC",
                      {x["code"] for x in description_review(desc, brief)})

    def test_ready_dossier_with_open_questions_is_blocked(self):
        data = analysis()
        data["missingInfo"] = ["Яка умова fallback?"]
        self.assertIn("OPEN_REQUIREMENTS_PENDING",
                      {x["code"] for x in dossier_checks(data)})
        result = quality_gate(data, issue())
        self.assertEqual(result["state"], "BLOCKED")
        self.assertFalse(result["isReadyForReview"])
        self.assertIn("OPEN_REQUIREMENTS_PENDING",
                      {x["code"] for x in result["findings"]})

    def test_ready_dossier_with_open_rule_is_blocked(self):
        data = analysis()
        data["briefing"]["rules"].append({
            "id": "R2", "certainty": "OPEN", "whenUk": "Unknown condition",
            "thenUk": "Unknown result",
        })
        self.assertIn("OPEN_RULES_PENDING",
                      {x["code"] for x in dossier_checks(data)})
        data["briefing"]["readiness"] = "NEEDS_CONFIRMATION"
        self.assertEqual(dossier_checks(data), [])

    def test_unverified_attachment_claim_is_blocked_but_not_mutated(self):
        data = analysis()
        claim = "Please find the supplier XML logs attached for your reference."
        data["emailDraft"] = {"to": "", "subject": "AER. Clarification [123]",
                              "body": "Dear Team,\n\n" + claim}
        before = copy.deepcopy(data)
        gate = quality_gate(data, issue(), attachment_ready=False)
        self.assertEqual(gate["state"], "BLOCKED")
        self.assertIn("EMAIL_UNVERIFIED_ATTACHMENT_CLAIM",
                      {x["code"] for x in gate["findings"]})
        self.assertEqual(data, before)
        with_valid_log = quality_gate(data, issue(), attachment_ready=True)
        self.assertNotIn("EMAIL_UNVERIFIED_ATTACHMENT_CLAIM",
                         {x["code"] for x in with_valid_log["findings"]})

    def test_negative_or_future_attachment_claim_not_falsely_blocked(self):
        texts = ["Logs are not attached.", "ZIP will be attached after review.",
                 "Could you attach the XML logs?", "We can provide logs later."]
        for body in texts:
            with self.subTest(body=body):
                self.assertNotIn("EMAIL_UNVERIFIED_ATTACHMENT_CLAIM",
                                 {x["code"] for x in email_checks(
                                     {"body": body}, attachment_ready=False)})

    def test_supplier_method_mismatch_is_flagged_without_guessing_rest_method(self):
        draft = {"body": "We have recently received an error during doVerifyFare:"}
        findings = email_checks(draft, verified_supplier_method="doByLocatorPullPnr")
        self.assertIn("EMAIL_METHOD_CONFLICT", {x["code"] for x in findings})
        self.assertEqual(email_checks({"body": "REST retrievePNR failed."},
                                      verified_supplier_method="doByLocatorPullPnr"), [])

    def test_legacy_missing_brief_and_unverified_method_remain_compatible(self):
        self.assertEqual(dossier_checks({"emailDraft": {}}), [])
        self.assertEqual(email_checks({"body": "Dear Team"}, attachment_ready=None), [])
        self.assertEqual(technical_literals("StatusCode=AND", ""), set())


if __name__ == "__main__":
    unittest.main()
