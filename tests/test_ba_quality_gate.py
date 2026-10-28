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

    def test_operator_must_be_in_the_relevant_if_condition_not_qa_prose(self):
        data=analysis()
        data["briefing"]["rules"][0]["whenUk"] = (
            "StatusCode=CANCELLED OR DeliveryStatusCode=REMOVED")
        data["standardDescription"] += (
            "\n- Check that missing or invalid inputs preserve the segment.")
        gate=quality_gate(data, issue())
        self.assertIn("COMPOUND_OPERATOR_OMITTED",
                      {item["code"] for item in gate["findings"]})
        self.assertEqual(gate["state"], "BLOCKED")

    def test_added_opposite_operator_in_same_confirmed_if_is_blocked(self):
        data = analysis()
        data["standardDescription"] = data["standardDescription"].replace(
            "IF StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED THEN",
            "IF StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED "
            "OR SegmentRefID=EXTRA THEN")
        result = quality_gate(data, issue())
        self.assertIn("COMPOUND_OPERATOR_CONFLICT",
                      {f["code"] for f in result["findings"]})
        self.assertEqual(result["state"], "BLOCKED")
        # Contradictory operator also blocks a declared OR with extra AND.
        data["briefing"]["rules"][0]["whenUk"] = (
            "StatusCode=CANCELLED OR DeliveryStatusCode=REMOVED")
        data["standardDescription"] = data["standardDescription"].replace(
            "StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED OR",
            "StatusCode=CANCELLED OR DeliveryStatusCode=REMOVED AND")
        result = quality_gate(data, issue())
        self.assertIn("COMPOUND_OPERATOR_CONFLICT",
                      {f["code"] for f in result["findings"]})

    def test_distinct_rules_sharing_fields_do_not_cross_match(self):
        data = analysis()
        second = copy.deepcopy(data["briefing"]["rules"][0])
        second["id"] = "R2"
        second["whenUk"] = "StatusCode=ACTIVE OR DeliveryStatusCode=PENDING"
        second["thenUk"] = "Preserve the segment"
        data["briefing"]["rules"].append(second)
        data["standardDescription"] = data["standardDescription"].replace(
            "#### QA\n",
            "IF StatusCode=ACTIVE OR DeliveryStatusCode=PENDING "
            "THEN preserve the segment.\n#### QA\n")
        findings = description_review(data["standardDescription"], data["briefing"])
        codes = {finding["code"] for finding in findings}
        self.assertNotIn("COMPOUND_OPERATOR_CONFLICT", codes)
        self.assertNotIn("COMPOUND_OPERATOR_OMITTED", codes)

    def test_unrelated_if_or_qa_operator_does_not_conflict(self):
        data = analysis()
        data["standardDescription"] += (
            "\nIF AnotherCode=OTHER OR UnknownFlag=TRUE "
            "THEN keep unrelated flow.\n"
            "- Check another condition with OR in QA prose.")
        result = quality_gate(data, issue())
        self.assertNotIn("COMPOUND_OPERATOR_CONFLICT",
                         {f["code"] for f in result["findings"]})
        self.assertEqual(result["state"], "STRUCTURALLY_VERIFIED")

    def test_free_text_confirmed_and_predicate_is_not_false_blocked(self):
        data = analysis()
        data["briefing"]["rules"][0]["whenUk"] = (
            "the booking is cancelled AND the ticket is unused")
        data["standardDescription"] = (
            "#### To Do\n"
            "IF the booking is cancelled AND the ticket is unused "
            "THEN omit the segment.\n"
            "#### QA\n"
            "- Check when both flags hold, segment is omitted.\n"
            "- Check when the ticket is used, segment is preserved.")
        findings = description_review(data["standardDescription"], data["briefing"])
        codes = {entry["code"] for entry in findings}
        self.assertNotIn("COMPOUND_OPERATOR_OMITTED", codes)
        self.assertNotIn("COMPOUND_OPERATOR_CONFLICT", codes)
        # Even free-text rules cannot silently swap AND for OR.
        data["standardDescription"] = data["standardDescription"].replace(
            "cancelled AND the ticket", "cancelled OR the ticket")
        codes = {entry["code"] for entry in
                 description_review(data["standardDescription"], data["briefing"])}
        self.assertIn("COMPOUND_OPERATOR_OMITTED", codes)
        self.assertIn("COMPOUND_OPERATOR_CONFLICT", codes)

    def test_free_text_predicate_comparison_polarity_is_not_lost(self):
        data = analysis()
        data["briefing"]["rules"][0]["whenUk"] = "fare > 100 AND seats > 0"
        description = (
            "#### To Do\n"
            "IF fare > 100 AND seats > 0 THEN apply the approved rule.\n"
            "#### QA\n"
            "- Check when fare <= 100, rule does not apply.")
        codes = {entry["code"] for entry in
                 description_review(description, data["briefing"])}
        self.assertNotIn("COMPOUND_OPERATOR_OMITTED", codes)
        # An operator-neutral signature must still preserve comparisons.
        wrong = description.replace("fare > 100 AND seats > 0",
                                    "fare < 100 AND seats < 0")
        codes = {entry["code"] for entry in
                 description_review(wrong, data["briefing"])}
        self.assertIn("COMPOUND_OPERATOR_OMITTED", codes)
        # QA polarity is not a replacement for the real declaration.
        self.assertNotIn("COMPOUND_OPERATOR_CONFLICT", codes)

    def test_mixed_boolean_operator_order_cannot_be_swapped(self):
        data = analysis()
        data["briefing"]["rules"][0]["whenUk"] = "A AND B OR C"
        data["standardDescription"] = (
            "#### To Do\nIF A AND B OR C THEN deliver the segment.\n"
            "#### QA\n- Check negative variants remain independent.")
        valid = description_review(data["standardDescription"], data["briefing"])
        self.assertNotIn("COMPOUND_OPERATOR_CONFLICT",
                         {x["code"] for x in valid})
        swapped = data["standardDescription"].replace(
            "A AND B OR C", "A OR B AND C")
        findings = description_review(swapped, data["briefing"])
        self.assertIn("COMPOUND_OPERATOR_CONFLICT",
                      {x["code"] for x in findings})
        # An unrelated QA example cannot make the invalid rule look valid.
        swapped += "\n- Check IF A AND B OR C THEN preserve a nonmatching case."
        findings = description_review(swapped, data["briefing"])
        self.assertIn("COMPOUND_OPERATOR_CONFLICT",
                      {x["code"] for x in findings})

    def test_negative_if_in_qa_does_not_contradict_positive_rule(self):
        data = analysis()
        data["standardDescription"] += (
            "\n- Check IF StatusCode != CANCELLED OR "
            "DeliveryStatusCode != REMOVED THEN preserve the segment.")
        result = quality_gate(data, issue())
        codes = {entry["code"] for entry in result["findings"]}
        self.assertNotIn("COMPOUND_OPERATOR_CONFLICT", codes)
        self.assertNotIn("COMPOUND_OPERATOR_OMITTED", codes)
        self.assertEqual(result["state"], "STRUCTURALLY_VERIFIED", result["findings"])

    def test_negative_qa_does_not_hide_wrong_to_do_operator(self):
        data = analysis()
        data["standardDescription"] = (
            data["standardDescription"].replace(
                "StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED",
                "StatusCode=CANCELLED OR DeliveryStatusCode=REMOVED") +
            "\n- Check IF StatusCode != CANCELLED AND "
            "DeliveryStatusCode != REMOVED THEN preserve the segment.")
        codes = {entry["code"] for entry in
                 description_review(data["standardDescription"], data["briefing"])}
        self.assertIn("COMPOUND_OPERATOR_OMITTED", codes)
        self.assertIn("COMPOUND_OPERATOR_CONFLICT", codes)

    def test_verified_local_excerpts_normalize_source_whitespace(self):
        data=analysis()
        link="https://aerticket.atlassian.net/wiki/spaces/SUP/pages/12345/a"
        data["briefing"]["confirmedFacts"][0]["sourceUrl"]=link
        data["briefing"]["confirmedFacts"][0]["sourceExcerpt"]="Supplier says TypeCode=TO"
        result=quality_gate(data, issue(), local_sources={
            link: "Supplier says\n\tTypeCode=TO"})
        self.assertNotIn("CLAIM_EXCERPT_NOT_FOUND",
                         {item["code"] for item in result["findings"]})

    def test_compactness_advice_does_not_downgrade_valid_ready_review(self):
        data=analysis()
        data["standardDescription"] += (
            "\nContext a: " + "a" * 420 +
            "\nContext b: " + "b" * 420)
        result=quality_gate(data, issue())
        self.assertEqual(result["state"], "STRUCTURALLY_VERIFIED", result["findings"])
        self.assertIn("DESCRIPTION_LONG_PARAGRAPHS",
                      {item["code"] for item in result["findings"]})

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
