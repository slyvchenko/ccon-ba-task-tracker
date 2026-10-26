"""Pure synthetic backlog reconciliation tests; never read personal data files."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import backlog_audit as audit


class AuditTest(unittest.TestCase):
    def test_canonical_inventory_is_stable_and_all_rows_are_traceable(self):
        report = audit.produce()
        self.assertEqual(report["counts"]["total"], 129)
        self.assertEqual(report["counts"]["reported_statuses"], {
            "DEFERRED": 4, "GATE": 3, "IMPLEMENTED": 40,
            "PARTIAL": 65, "PLANNED": 17})
        items = report["items"]
        self.assertEqual(len(items), len({x["id"] for x in items}))
        self.assertTrue(all(x["suggested_batch"] and x["acceptance_criteria"] for x in items))
        self.assertTrue(all(x["human_acceptance"] == "NOT_RECORDED" for x in items))
        self.assertTrue(all(x["disposition"] != "DONE" for x in items))

    def test_post_v2481_reconciliation_is_code_only_not_human_signoff(self):
        rows = {item["id"]: item for item in audit.produce()["items"]}
        code_reported = {"QUICK-06", "QA-09", "OPS-01"}
        newly_partial = {"QUICK-04", "QUICK-07", "FOCUS-04", "PRIOR-06",
                         "UI-05", "UI-09", "A11Y-06", "REL-06", "SEC-02", "SEC-03"}
        self.assertTrue(all(rows[key]["category"] == "IMPLEMENTED" for key in code_reported))
        self.assertTrue(all(rows[key]["category"] == "PARTIAL" for key in newly_partial))
        self.assertTrue(all(rows[key]["code_locator"] for key in code_reported | newly_partial))
        self.assertTrue(all(rows[key]["human_acceptance"] == "NOT_RECORDED"
                            for key in rows))
        self.assertEqual(len(rows), 129)
        self.assertEqual(audit.produce()["counts"]["code_plus_test_locators"], 49)
        self.assertEqual(audit.produce()["counts"]["no_direct_locator"], 74)
        for key in ("QA-02", "QA-03", "QA-10", "QA-13"):
            self.assertNotEqual(rows[key]["human_acceptance"], "PASSED")

    def test_perf_08_is_source_backed_but_device_acceptance_is_open(self):
        row = next(r for r in audit.produce()["items"] if r["id"] == "PERF-08")
        self.assertEqual(row["category"], "PARTIAL")
        self.assertEqual(row["code_locator"], "assets/detail-refresh-policy.mjs")
        self.assertEqual(row["test_locator"], "tests/detail-refresh-policy.test.mjs")
        self.assertEqual(row["human_acceptance"], "NOT_RECORDED")

    def test_queue_performance_and_sticky_action_are_partial_without_native_uat(self):
        rows = {item["id"]: item for item in audit.produce()["items"]}
        for key in ("PERF-05", "FOCUS-05"):
            self.assertEqual(rows[key]["category"], "PARTIAL")
            self.assertIsNotNone(rows[key]["code_locator"])
            self.assertIsNotNone(rows[key]["test_locator"])
            self.assertEqual(rows[key]["human_acceptance"], "NOT_RECORDED")

    def test_p0_business_gates_cannot_become_done_by_code_only(self):
        rows = {x["id"]: x for x in audit.produce()["items"]}
        for key in ("QA-02", "QA-03", "QA-10"):
            self.assertEqual(rows[key]["disposition"], "BLOCKED_PENDING_HUMAN_UAT")
            self.assertEqual(rows[key]["human_acceptance"], "NOT_RECORDED")
            self.assertIn("HUMAN_UAT", rows[key]["suggested_batch"])
        for key in ("BA-01", "BA-02", "EVD-03", "EVD-06", "OUT-01", "OUT-02"):
            self.assertNotEqual(rows[key]["disposition"], "CODE_REPORTED_HUMAN_ACCEPTANCE_OPEN")
            self.assertIn(rows[key]["suggested_batch"], ("#40", "#41"))

    def test_all_deferred_cloud_items_are_outside_local_pr_count(self):
        report = audit.produce()
        deferred = [r for r in report["items"] if r["disposition"] == "DEFERRED_PRODUCT_DECISION"]
        self.assertEqual({r["id"] for r in deferred}, {"INF-01", "INF-02", "INF-03", "INF-04"})
        self.assertTrue(all(r["suggested_batch"] == "OPTIONAL_CLOUD_SCOPE" for r in deferred))

    def test_overlap_detection_never_silently_deletes_or_merges_actions(self):
        rows = {x["id"]: x for x in audit.produce()["items"]}
        self.assertIn("VIS-15", rows["PERF-09"]["possible_overlaps"])
        self.assertIn("VIS-10", rows["UI-09"]["possible_overlaps"])
        self.assertIn("QA-12", rows["QA-09"]["possible_overlaps"])
        self.assertEqual(rows["QUICK-04"]["disposition"], "REVIEW_POSSIBLE_ACCEPTANCE_OVERLAP")
        self.assertIn("QUICK-04", rows)  # Still a distinct requirement.

    def test_no_evidence_locator_can_be_mistaken_for_semantic_proof(self):
        report = audit.produce()
        self.assertGreater(report["counts"]["code_plus_test_locators"], 20)
        self.assertGreater(report["counts"]["no_direct_locator"], 0)
        for row in report["items"]:
            self.assertIn(row["evidence_level"], ("CODE_AND_TEST_LOCATORS_ONLY", "CODE_LOCATOR_ONLY", "UNMAPPED_NEEDS_INSPECTION"))
            self.assertNotEqual(row["human_acceptance"], "PASSED")
            if row["code_locator"]:
                self.assertTrue((audit.ROOT / row["code_locator"]).is_file())
            if row["test_locator"]:
                self.assertTrue((audit.ROOT / row["test_locator"]).is_file())

    def test_parser_rejects_duplicate_or_invalid_priorities(self):
        header = "## 2. Повний функціональний backlog\n"
        tail = "\n## 2B. Visual audit"
        item = "| BA-01 | P0 | PARTIAL | Synthetic business requirement | Synthetic manual proof |\n"
        self.assertEqual(len(audit.parse_rows(header + item + tail)), 1)
        with self.assertRaisesRegex(ValueError, "Duplicate backlog ID"):
            audit.parse_rows(header + item + item + tail)
        with self.assertRaisesRegex(ValueError, "Invalid priority"):
            audit.parse_rows(header + item.replace("P0", "P9") + tail)
        with self.assertRaisesRegex(ValueError, "Unrecognized backlog status"):
            audit.parse_rows(header + item.replace("PARTIAL", "DONE") + tail)

    def test_output_is_deterministic_and_no_private_values_exist(self):
        first = audit.serialized(audit.produce())
        second = audit.serialized(audit.produce())
        self.assertEqual(first, second)
        self.assertNotIn("apiToken", first)
        self.assertNotIn("password", first.lower())
        self.assertIn("NOT_RECORDED", first)
        self.assertEqual(len(json.loads(first)["items"]),129)
        self.assertTrue(first.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
