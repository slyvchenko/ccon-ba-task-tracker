import copy
import unittest

from ba_quality_gate import claim_audit, quality_gate, source_registry, description_review
from ba_briefing import validate_briefing
from test_ba_briefing import briefing


URL = "https://aerticket.atlassian.net/browse/CCON-123"


def issue():
    return {
        "key": "CCON-123", "url": URL, "summary": "REST. PullPNR. cancelled segment",
        "description": "For REST PullPNR omit CANCELLED segment when DeliveryStatusCode=REMOVED.",
        "comments": [{"body": {"type": "doc", "content": [{
            "type": "paragraph", "content": [{
                "type": "text", "text": "If StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED, do not return segment."
            }]
        }]}}],
    }


def analysis():
    b = briefing()
    b["unknownsUk"] = []
    b["readiness"] = "READY_FOR_REVIEW"
    b["confirmedFacts"] = [{
        "textUk": "Сегмент не потрібен у REST.",
        "sourceUrl": URL, "sourceExcerpt": "omit CANCELLED segment when DeliveryStatusCode=REMOVED",
    }]
    b["rules"] = [{
        "id": "R1", "whenUk": "StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED",
        "thenUk": "Omit segment", "certainty": "CONFIRMED", "sourceUrl": URL,
        "sourceExcerpt": "If StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED, do not return segment.",
    }]
    b["verification"] = [
        {"scenarioUk": "Обидві умови", "expectedUk": "Сегмент не повертається", "sourceUrl": URL,
         "kind": "POSITIVE", "ruleIds": ["R1"]},
        {"scenarioUk": "Без CANCELLED", "expectedUk": "Сегмент не виключається", "sourceUrl": URL,
         "kind": "NEGATIVE", "ruleIds": ["R1"]},
        {"scenarioUk": "CANCELLED без REMOVED", "expectedUk": "Сегмент не виключається",
         "sourceUrl": URL, "kind": "EDGE", "ruleIds": ["R1"]},
    ]
    return {
        "briefing": b,
        "standardDescription": (
            "#### Objective\nExclude segments from REST PullPNR only when both confirmed conditions hold.\n"
            "#### To Do\nIF StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED "
            "THEN omit the segment from REST.\n"
            "#### QA\n- Check both conditions return no segment.\n"
            "- Check other StatusCode preserves segment.\n"
            "- Check CANCELLED without REMOVED preserves segment."
        ),
    }


class QualityGateTests(unittest.TestCase):
    def test_source_excerpt_and_full_qa_coverage_structurally_verified(self):
        data = analysis()
        validate_briefing(data["briefing"])
        check = quality_gate(data, issue())
        self.assertEqual(check["state"], "STRUCTURALLY_VERIFIED", check["findings"])
        self.assertEqual(check["summary"]["sourceExcerptsPresent"], 2)
        self.assertEqual(check["summary"]["rulesFullyCovered"], 1)
        self.assertTrue(check["isReadyForReview"])
        self.assertIn("NOT truth", check["claims"][0]["meaning"])

    def test_fabricated_url_and_excerpt_cannot_confirm_provenance(self):
        data = analysis()
        data["briefing"]["rules"][0]["sourceUrl"] = "https://supplier.example/contracts"
        result = quality_gate(data, issue())
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn("CLAIM_SOURCE_NOT_READ", {f["code"] for f in result["findings"]})
        data["briefing"]["rules"][0]["sourceUrl"] = URL
        data["briefing"]["rules"][0]["sourceExcerpt"] = "supplier approved all refunds"
        result = quality_gate(data, issue())
        self.assertIn("CLAIM_EXCERPT_NOT_FOUND", {f["code"] for f in result["findings"]})

    def test_jira_url_alone_is_not_content_proof(self):
        data = analysis()
        del data["briefing"]["confirmedFacts"][0]["sourceExcerpt"]
        result = quality_gate(data, issue())
        self.assertFalse(result["isReadyForReview"])
        self.assertIn("CLAIM_EXCERPT_MISSING", {f["code"] for f in result["findings"]})

    def test_negative_and_edge_cases_required_for_AND_condition(self):
        data = analysis()
        data["briefing"]["verification"] = data["briefing"]["verification"][:1]
        result = quality_gate(data, issue())
        self.assertEqual(result["qaCoverage"][0]["missing"], ["EDGE", "NEGATIVE"])
        self.assertIn("RULE_QA_GAP", {f["code"] for f in result["findings"]})

    def test_wrong_rule_ref_and_missing_rule_id_cannot_pass(self):
        data = analysis()
        data["briefing"]["verification"][0]["ruleIds"] = ["R999"]
        result = quality_gate(data, issue())
        self.assertIn("QA_UNKNOWN_RULE_ID", {f["code"] for f in result["findings"]})
        del data["briefing"]["rules"][0]["id"]
        result = quality_gate(data, issue())
        self.assertIn("RULE_ID_MISSING", {f["code"] for f in result["findings"]})

    def test_missing_field_case_and_qa_in_description_flagged(self):
        data = analysis()
        data["standardDescription"] = (
            "#### To Do\nIF StatusCode=CANCELLED, then omit the segment.\n"
            "#### QA\nTest expected behavior"
        )
        result = quality_gate(data, issue())
        codes = {f["code"] for f in result["findings"]}
        self.assertIn("CONFIRMED_FIELD_OMITTED", codes)
        self.assertIn("DESCRIPTION_QA_MISSING", codes)

    def test_draft_filler_and_repetition_flagged_without_sentence_limit(self):
        data = analysis()
        data["standardDescription"] += (
            "\n- Check both conditions return no segment.\n"
            "Please kindly ensure that everything works.\n"
        )
        codes = {x["code"] for x in description_review(data["standardDescription"], data["briefing"])}
        self.assertIn("DESCRIPTION_FILLER", codes)
        self.assertIn("DESCRIPTION_REPEATS", codes)
        # No rule says only two sentences are allowed.
        self.assertNotIn("TOO_MANY_SENTENCES", codes)

    def test_comment_adf_excerpt_is_read_without_exposing_payload_in_diagnostics(self):
        data = analysis()
        data["briefing"]["rules"][0]["sourceExcerpt"] = (
            "If StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED, do not return segment.")
        result = quality_gate(data, issue())
        self.assertEqual(result["claims"][1]["sourceState"], "TEXT_PRESENT_NOT_FACT_PROVEN")
        self.assertNotIn("CANCELLED", str(result["claims"]))
        self.assertNotIn("passenger", str(result["findings"]))

    def test_legacy_brief_does_not_raise_or_fake_readiness(self):
        old = {"briefing": briefing(), "standardDescription": ""}
        out = quality_gate(old, issue())
        self.assertNotEqual(out["state"], "STRUCTURALLY_VERIFIED")
        self.assertFalse(out["isReadyForReview"])

    def test_linked_source_allowed_only_if_actually_retrieved(self):
        data = analysis()
        link = "https://aerticket.atlassian.net/browse/CCON-456"
        data["briefing"]["rules"][0]["sourceUrl"] = link
        data["briefing"]["rules"][0]["sourceExcerpt"] = "Special acceptance rule for StatusCode"
        rel = {"CCON-456": {"url": link, "description": "Special acceptance rule for StatusCode"}}
        with_rel = quality_gate(data, issue(), rel)
        self.assertNotIn("CLAIM_SOURCE_NOT_READ", {x["code"] for x in with_rel["findings"]})
        no_rel = quality_gate(data, issue())
        self.assertIn("CLAIM_SOURCE_NOT_READ", {x["code"] for x in no_rel["findings"]})


if __name__ == "__main__":
    unittest.main()
