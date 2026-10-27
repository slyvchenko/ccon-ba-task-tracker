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
            "PARTIAL": 82})
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
        self.assertEqual(audit.produce()["counts"]["code_plus_test_locators"], 106)
        self.assertEqual(audit.produce()["counts"]["no_direct_locator"], 17)
        for key in ("QA-02", "QA-03", "QA-10", "QA-13"):
            self.assertNotEqual(rows[key]["human_acceptance"], "PASSED")

    def test_p0_legacy_source_pointers_are_locations_not_human_approval(self):
        rows = {row["id"]: row for row in audit.produce()["items"]}
        inspected = {
            "CORE-04": ("priority_score.py", "tests/test_priority_score.py"),
            "BA-03": ("ba_briefing.py", "tests/test_ba_briefing.py"),
            "UX-01": ("assets/dashboard.mjs", "browser_e2e.py"),
            "QUICK-01": ("assets/fast-handoff.mjs", "tests/fast-handoff.test.mjs"),
            "FOCUS-01": ("assets/queue-performance.mjs", "tests/queue-performance.test.mjs"),
            "PRIOR-01": ("assets/effort-planning.mjs", "tests/effort-planning.test.mjs"),
            "PRIOR-02": ("assets/task-rules.mjs", "tests/priority-hard-lanes.test.mjs"),
            "PERF-01": ("desk_store.py", "tests/test_json_response_cache.py"),
            "PERF-02": ("assets/revision-policy.mjs", "browser_e2e.py"),
            "PERF-03": ("assets/queue-performance.mjs", "tests/queue-performance.test.mjs"),
            "REL-01": ("desk_store.py", "tests/test_manual_edit_cas.py"),
            "QA-11": ("desk_store.py", "tests/test_manual_edit_cas.py"),
        }
        self.assertEqual(len(inspected), 12)
        for key, (source, test) in inspected.items():
            with self.subTest(id=key):
                self.assertEqual(rows[key]["priority"], "P0")
                self.assertEqual(rows[key]["code_locator"], source)
                self.assertEqual(rows[key]["test_locator"], test)
                self.assertEqual(rows[key]["evidence_level"],
                                 "CODE_AND_TEST_LOCATORS_ONLY")
                self.assertEqual(rows[key]["human_acceptance"], "NOT_RECORDED")
        # Do not invent implementation/test evidence for independent gates or
        # ambiguous authorized ZIP acquisition. They need actual UAT/scope.
        for key in ("EVD-05", "QA-02", "QA-10"):
            self.assertIsNone(rows[key]["code_locator"])

    def test_p1_evidence_pointers_are_limited_to_checked_source_test_paths(self):
        pairs = {
            "CORE-07": ("task_history.py", "tests/test_action_history.py"),
            "BA-06": ("question_candidates.py", "tests/test_question_decisions.py"),
            "BA-08": ("one_task_review.py", "tests/test_one_task_review.py"),
            "BA-10": ("ba_decisions.py", "tests/test_question_decisions.py"),
            "EVD-10": ("evidence_health.py", "tests/test_evidence_health.py"),
            "EVD-11": ("flow_diagnostics.py", "tests/test_flow_diagnostics.py"),
            "EVD-12": ("evidence_health.py", "tests/test_evidence_health.py"),
            "QA-04": ("ba_quality_gate.py", "tests/test_ba_quality_gate.py"),
            "QA-05": ("prompt_calibration.py", "tests/test_prompt_calibration.py"),
            "QA-06": ("prompt_experiments.py", "tests/test_prompt_experiments.py"),
            "FOCUS-03": ("assets/focus-navigation.mjs", "tests/focus-navigation.test.mjs"),
            "PRIOR-04": ("assets/effort-planning.mjs", "tests/effort-planning.test.mjs"),
            "UI-06": ("assets/manual-edit-policy.mjs", "tests/manual-edit-policy.test.mjs"),
            "PERF-04": ("assets/queue-performance.mjs", "tests/queue-performance.test.mjs"),
            "PERF-06": ("desk_store.py", "tests/test_json_response_cache.py"),
            "A11Y-01": ("assets/focus-navigation.mjs", "tests/focus-navigation.test.mjs"),
        }
        rows = {entry["id"]: entry for entry in audit.produce()["items"]}
        self.assertEqual(len(pairs), 16)
        for id_, (source, test_file) in pairs.items():
            with self.subTest(id=id_):
                entry = rows[id_]
                self.assertEqual(entry["priority"], "P1")
                self.assertEqual(entry["code_locator"], source)
                self.assertEqual(entry["test_locator"], test_file)
                self.assertEqual(entry["evidence_level"], "CODE_AND_TEST_LOCATORS_ONLY")
                self.assertEqual(entry["human_acceptance"], "NOT_RECORDED")
                self.assertTrue((audit.ROOT / source).is_file())
                self.assertTrue((audit.ROOT / test_file).is_file())

    def test_secondary_p1_p2_traceable_locators_do_not_grant_human_signoff(self):
        expected = {
            "CORE-08": ("ba_actions.py", "tests/test_action_history.py"),
            "CORE-09": ("assets/queue-performance.mjs", "tests/queue-performance.test.mjs"),
            "CORE-10": ("priority_consistency.py", "tests/test_priority_consistency.py"),
            "BA-11": ("approved_draft.py", "tests/test_approved_draft.py"),
            "EVD-09": ("value_mapping.py", "tests/test_value_mapping.py"),
            "EVD-14": ("evidence_trends.py", "tests/test_evidence_trends.py"),
            "UX-03": ("assets/dashboard.css", "tests/css-cleanup.test.mjs"),
            "UX-04": ("assets/dashboard.mjs", "browser_e2e.py"),
            "QA-07": ("supplier_logs.py", "tests/test_evidence_regression_matrix.py"),
            "PERF-07": ("performance_smoke.py", "tests/test_local_performance.py"),
            "A11Y-05": ("assets/dashboard.css", "tests/css-cleanup.test.mjs"),
            "SEC-04": ("assets/draft-recovery.mjs", "tests/draft-recovery.test.mjs"),
        }
        rows = {entry["id"]: entry for entry in audit.produce()["items"]}
        self.assertEqual(len(expected), 12)
        for key, (source, test_file) in expected.items():
            with self.subTest(key=key):
                row = rows[key]
                self.assertIn(row["priority"], ("P1", "P2"))
                self.assertEqual(row["code_locator"], source)
                self.assertEqual(row["test_locator"], test_file)
                self.assertEqual(row["evidence_level"], "CODE_AND_TEST_LOCATORS_ONLY")
                self.assertEqual(row["human_acceptance"], "NOT_RECORDED")
                self.assertTrue((audit.ROOT / source).is_file())
                self.assertTrue((audit.ROOT / test_file).is_file())

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

    def test_visual_and_technical_formatting_remain_partial_until_native_uat(self):
        rows = {item["id"]: item for item in audit.produce()["items"]}
        for key in ("UI-08", "UI-10"):
            self.assertEqual(rows[key]["category"], "PARTIAL")
            self.assertEqual(rows[key]["test_locator"], "browser_e2e.py")
            self.assertEqual(rows[key]["human_acceptance"], "NOT_RECORDED")

    def test_local_diagnostics_permissions_are_partial_without_real_windows_uat(self):
        rows={entry["id"]:entry for entry in audit.produce()["items"]}
        for key in ("REL-08", "OPS-02"):
            self.assertEqual(rows[key]["category"], "PARTIAL")
            self.assertEqual(rows[key]["code_locator"], "local_diagnostics.py")
            self.assertEqual(rows[key]["test_locator"], "tests/test_local_diagnostics.py")
            self.assertEqual(rows[key]["human_acceptance"], "NOT_RECORDED")

    def test_crash_consistency_is_test_located_but_windows_uat_remains_open(self):
        rows={x["id"]:x for x in audit.produce()["items"]}
        for item_id in ("REL-02","REL-03","REL-05"):
            self.assertEqual(rows[item_id]["category"],"PARTIAL")
            self.assertEqual(rows[item_id]["human_acceptance"],"NOT_RECORDED")
        self.assertEqual(rows["REL-05"]["test_locator"],"tests/test_crash_consistency.py")

    def test_original_thirteen_requirements_remain_partial_not_human_accepted(self):
        ids={"PERF-09","PERF-10","REL-09","REL-10","PRIOR-05",
             "PRIOR-07","PRIOR-08","PRIOR-09","QA-13","OPS-04",
             "QUICK-08","FOCUS-07","FOCUS-08"}
        rows={entry["id"]:entry for entry in audit.produce()["items"]}
        self.assertEqual(len(ids),13)
        for key in ids:
            self.assertEqual(rows[key]["category"],"PARTIAL")
            self.assertEqual(rows[key]["human_acceptance"],"NOT_RECORDED")
        self.assertEqual(rows["QA-13"]["test_locator"],"tests/test_private_gold_review.py")
        self.assertEqual(rows["PERF-09"]["test_locator"],"tests/css-cleanup.test.mjs")

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
