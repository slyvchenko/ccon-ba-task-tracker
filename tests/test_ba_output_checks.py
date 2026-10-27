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

    def test_unknown_zip_readiness_is_not_permission_to_claim_attached(self):
        claim = {"body":"Dear Team,\n\nLogs are attached for your reference."}
        for ready in (None, False):
            with self.subTest(ready=ready):
                found = email_checks(claim, attachment_ready=ready)
                self.assertIn("EMAIL_UNVERIFIED_ATTACHMENT_CLAIM",
                              {x["code"] for x in found})
        self.assertNotIn("EMAIL_UNVERIFIED_ATTACHMENT_CLAIM",
                         {x["code"] for x in email_checks(claim,attachment_ready=True)})

    def test_negative_or_future_attachment_claim_not_falsely_blocked(self):
        texts = ["Logs are not attached.", "ZIP will be attached after review.",
                 "Could you attach the XML logs?", "We can provide logs later."]
        for body in texts:
            with self.subTest(body=body):
                self.assertNotIn("EMAIL_UNVERIFIED_ATTACHMENT_CLAIM",
                                 {x["code"] for x in email_checks(
                                     {"body": body}, attachment_ready=False)})

    def test_positive_attachment_claim_not_hidden_by_later_negative_sentence(self):
        for body in (
            "Please find the request logs attached. The response is not attached.",
            "Please find the request logs attached, but response is not attached."
        ):
            warnings=email_checks({"body":body},attachment_ready=False)
            self.assertIn("EMAIL_UNVERIFIED_ATTACHMENT_CLAIM",
                          {w["code"] for w in warnings})

    def test_supplier_method_mismatch_is_flagged_without_guessing_rest_method(self):
        draft = {"body": "We have recently received an error during doVerifyFare:"}
        findings = email_checks(draft, verified_supplier_method="doByLocatorPullPnr")
        self.assertIn("EMAIL_METHOD_CONFLICT", {x["code"] for x in findings})
        self.assertEqual(email_checks({"body": "REST retrievePNR failed."},
                                      verified_supplier_method="doByLocatorPullPnr"), [])

    def test_normalized_email_cannot_erase_original_false_attachment_claim(self):
        data = analysis()
        data["emailDraft"] = {"subject": "AER. Clarification [123]",
                              "body": "Dear Team, could you investigate?"}
        original = {"subject": "AER. Clarification [123]",
                    "body": "Dear Team, please find the supplier logs attached."}
        for ready in (False, None):
            with self.subTest(ready=ready):
                result = quality_gate(data, issue(), attachment_ready=ready,
                                      original_email_draft=original)
                self.assertEqual(result["state"], "BLOCKED")
                self.assertIn("EMAIL_UNVERIFIED_ATTACHMENT_CLAIM",
                              {f["code"] for f in result["findings"]})
                self.assertNotIn("supplier logs attached", str(result["findings"]))
        verified = quality_gate(data, issue(), attachment_ready=True,
                                original_email_draft=original)
        self.assertNotIn("EMAIL_UNVERIFIED_ATTACHMENT_CLAIM",
                         {f["code"] for f in verified["findings"]})

    def test_unverified_attachment_subject_and_mixed_assertions_are_blocked(self):
        for draft in (
            {"subject": "AER. Supplier ZIP is attached [123]", "body": ""},
            {"subject": "AER. Clarification [123]",
             "body": "Logs are attached and the response is not attached."},
            {"subject": "AER. Clarification [123]",
             "body": "Please find the request logs attached although the reply is not attached."},
        ):
            with self.subTest(draft=draft):
                findings = email_checks(draft, attachment_ready=False)
                self.assertIn("EMAIL_UNVERIFIED_ATTACHMENT_CLAIM",
                              {f["code"] for f in findings})
        safe = {"subject": "ZIP will be attached after manual review",
                "body": "Logs are not attached. Could you provide the XML?"}
        self.assertNotIn("EMAIL_UNVERIFIED_ATTACHMENT_CLAIM",
                         {f["code"] for f in email_checks(safe, attachment_ready=False)})
        for body in (
            "No logs are attached.",
            "We have not attached logs.",
            "We haven't attached the logs.",
            "The ZIP will be attached with the logs after review.",
            "We can attach the logs later.",
            "The XML response is not attached but the ZIP will be attached.",
        ):
            with self.subTest(safe_body=body):
                self.assertNotIn("EMAIL_UNVERIFIED_ATTACHMENT_CLAIM",
                                 {f["code"] for f in email_checks(
                                     {"body": body}, attachment_ready=None)})


    def test_original_method_conflict_is_not_erased_by_normalization(self):
        data=analysis()
        data["emailDraft"]={"body":"Error during doByLocatorPullPnr"}
        result=quality_gate(data,issue(),supplier_method="doByLocatorPullPnr",
                            original_email_draft={"body":"Error during doVerifyFare:"})
        self.assertIn("EMAIL_METHOD_CONFLICT",
                      {f["code"] for f in result["findings"]})
        self.assertEqual(result["state"],"BLOCKED")

    def test_original_subject_method_conflict_is_audit_finding(self):
        data=analysis()
        data["emailDraft"]={"subject":"AER. doByLocatorPullPnr. Corrected [1]","body":"Dear Team"}
        gate=quality_gate(data,issue(),supplier_method="doByLocatorPullPnr",
                          original_email_draft={
                              "subject":"AER. doVerifyFare. Wrong [1]",
                              "body":"Dear Team"})
        self.assertIn("EMAIL_METHOD_CONFLICT",
                      {f["code"] for f in gate["findings"]})

    def test_plain_word_double_is_not_a_supplier_method(self):
        from ba_output_checks import email_checks
        draft={"subject":"AER. Double booking detected [123]",
               "body":"Dear Team, booking problem"}
        self.assertNotIn("EMAIL_METHOD_CONFLICT",
                         {x["code"] for x in email_checks(
                             draft, verified_supplier_method="doBooking")})

    def test_persisted_open_question_still_blocks_ready(self):
        data=analysis()
        data["missingInfo"]=[]
        gate=quality_gate(data,issue(),persisted_questions=[
            {"status":"OPEN","presentInLatestAnalysis":False}])
        self.assertIn("OPEN_REQUIREMENTS_PENDING",
                      {f["code"] for f in gate["findings"]})
        self.assertEqual(gate["state"],"BLOCKED")

    def test_legacy_missing_brief_and_unverified_method_remain_compatible(self):
        self.assertEqual(dossier_checks({"emailDraft": {}}), [])
        self.assertEqual(email_checks({"body": "Dear Team"}, attachment_ready=None), [])
        self.assertEqual(technical_literals("StatusCode=AND", ""), set())


if __name__ == "__main__":
    unittest.main()
