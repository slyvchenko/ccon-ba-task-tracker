"""Deterministic, read-only audit of the canonical BA Desk product backlog.

Writes no Jira data, cookies, task descriptions, or local BA state. Source/test
paths are discovery pointers, NEVER proof of semantic correctness or BA signoff.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKLOG = ROOT / "docs" / "PRODUCT_BACKLOG.md"
OUTPUT = ROOT / "docs" / "BACKLOG_ACCEPTANCE_LEDGER.json"
ID_PATTERN = re.compile(r"^(CORE|BA|EVD|OUT|UX|QA|INF|QUICK|FOCUS|PRIOR|UI|PERF|REL|A11Y|OPS|SEC)-\d{2}$")
ALLOWED = {"IMPLEMENTED", "PARTIAL", "GATE", "PLANNED", "NEXT", "DEFERRED"}
# Evidence pointers are verified to exist, not asserted to demonstrate a PASS.
POINTERS = {
    "CORE-01": ("jira_sync.py", "tests/test_jira_sync.py"),
    "CORE-02": ("sprint_priority.py", "tests/test_sprint_priority.py"),
    "CORE-03": ("priority_score.py", "tests/test_priority_score.py"),
    "CORE-05": ("desk_store.py", "tests/test_desk.py"),
    "CORE-06": ("task_history.py", "tests/test_action_history.py"),
    "BA-01": ("ba_output_checks.py", "tests/test_ba_output_checks.py"),
    "BA-02": ("email_rules.py", "tests/test_email_rules.py"),
    "BA-04": ("ba_quality_gate.py", "tests/test_ba_quality_gate.py"),
    "BA-05": ("ba_questions.py", "tests/test_ba_questions.py"),
    "BA-07": ("ba_quality_gate.py", "tests/test_quality_regression_pack.py"),
    "BA-09": ("confluence_local.py", "tests/test_local_source_crosscheck.py"),
    "EVD-01": ("supplier_logs.py", "tests/test_supplier_logs.py"),
    "EVD-02": ("flow_diagnostics.py", "tests/test_flow_diagnostics.py"),
    "EVD-03": ("value_mapping.py", "tests/test_value_mapping.py"),
    "EVD-04": ("log_attachments.py", "tests/test_log_attachments.py"),
    "EVD-06": ("kibana_evidence.py", None),
    "EVD-07": ("error_series.py", "tests/test_error_series.py"),
    "EVD-08": ("layered_evidence.py", "tests/test_layered_evidence.py"),
    "EVD-13": ("jira_attachments.py", "tests/test_jira_attachments.py"),
    "EVD-15": ("evidence_retention.py", "tests/test_evidence_retention.py"),
    "OUT-01": ("ba_briefing.py", "tests/test_ba_briefing.py"),
    "OUT-02": ("draft_output.py", "tests/test_ba_output_checks.py"),
    "OUT-04": ("local_source_audit.py", "tests/test_local_source_crosscheck.py"),
    "QA-01": ("check_project.py", "tests/test_static_release.py"),
    "QA-03": ("quality_evaluation.py", "tests/test_quality_regression_pack.py"),
    "QA-08": ("prompt_safety.py", "tests/test_prompt_safety.py"),
    "QA-12": ("browser_e2e.py", None),
    "QUICK-02": ("assets/handoff-ui-policy.mjs", "tests/handoff-ui-policy.test.mjs"),
    "QUICK-03": ("ba_actions.py", "tests/test_action_history.py"),
    "FOCUS-02": ("assets/draft-recovery.mjs", "tests/draft-recovery.test.mjs"),
    "PRIOR-03": ("sprint_priority.py", "tests/test_sprint_priority.py"),
    "UI-08": ("assets/dashboard.mjs", "browser_e2e.py"),
    "UI-09": ("assets/progressive-layout.mjs", "tests/progressive-layout.test.mjs"),
    "UI-10": ("assets/dashboard.css", "browser_e2e.py"),
    "FOCUS-05": ("assets/dashboard.mjs", "browser_e2e.py"),
    "PERF-05": ("assets/queue-dom.mjs", "tests/queue-dom.test.mjs"),
    "PERF-08": ("assets/detail-refresh-policy.mjs", "tests/detail-refresh-policy.test.mjs"),
    "PERF-09": ("assets/dashboard.css", "tests/css-cleanup.test.mjs"),
    "REL-02": ("desk_store.py", "tests/test_manual_edit_cas.py"),
    "REL-03": ("local_backup.py", "tests/test_local_backup.py"),
    "REL-07": ("assets/reconnect-policy.mjs", "tests/reconnect-policy.test.mjs"),
    "SEC-01": ("desk_store.py", "tests/test_manual_edit_cas.py"),
    "A11Y-02": ("assets/dashboard.css", "tests/css-cleanup.test.mjs"),
    "UI-07": ("assets/visual-clarity.mjs", "tests/visual-clarity.test.mjs"),
    "QA-14": (".github/workflows/quality.yml", None),
    "QUICK-04": ("email_rules.py", "tests/test_email_rules.py"),
    "QUICK-06": ("assets/manual-done-undo.mjs", "tests/manual-done-undo.test.mjs"),
    "QUICK-07": ("assets/fast-handoff.mjs", "tests/fast-handoff.test.mjs"),
    "FOCUS-04": ("assets/progressive-layout.mjs", "tests/progressive-layout.test.mjs"),
    "PRIOR-06": ("ba_actions.py", "tests/test_action_history.py"),
    "UI-05": ("assets/dashboard.css", "tests/css-cleanup.test.mjs"),
    "A11Y-06": ("assets/dashboard.mjs", None),
    "QA-09": ("browser_e2e.py", None),
    "OPS-01": ("performance_smoke.py", None),
    "REL-06": ("desk_store.py", "tests/test_local_backup.py"),
    "SEC-02": ("server.py", "tests/test_cloud_security.py"),
    "SEC-03": (".github/workflows/quality.yml", "tests/test_static_release.py"),
}
# These are *possible overlapping acceptance criteria*, not verified duplicates.
OVERLAPS = {
    "QUICK-07": ("VIS-01", "VIS-04"),
    "UI-05": ("VIS-04", "VIS-15"),
    "UI-09": ("VIS-06", "VIS-10"),
    "UI-10": ("VIS-15",),
    "PERF-09": ("VIS-15",),
    "A11Y-06": ("VIS-14",),
    "QA-09": ("QA-12",),
    "OPS-01": ("QA-09", "PERF-05"),
    "QUICK-04": ("BA-02", "OUT-02"),
}
PR39_GATES = {"QA-02", "QA-03", "QA-10", "QA-13"}
ROUTES = {
    "#40": set("EVD-03 EVD-06 EVD-13 BA-09 OUT-04 QA-08".split()),
    "#41": set("BA-01 BA-02 BA-05 OUT-01 OUT-02 QUICK-02 QUICK-03 QUICK-04".split()),
    "#42": set("QUICK-05 QUICK-06 QUICK-07 QUICK-08 FOCUS-04 FOCUS-05 FOCUS-06 FOCUS-07 FOCUS-08".split()),
    "#43": set("CORE-10 OPS-01 QA-10".split()) | {"PRIOR-%02d" % n for n in range(1, 10)},
    "#44": set("EVD-10 EVD-14 EVD-15 QA-04 QA-05 QA-07".split()),
    "#45": {"REL-%02d" % n for n in range(1, 11)} |
           {"SEC-%02d" % n for n in range(1, 5)} |
           set("OPS-02 OPS-03 OPS-05".split()),
    "#46": {"PERF-%02d" % n for n in range(1, 11)} |
           set("QA-09 QA-11 QA-12 QA-14 QA-15 OPS-04".split()),
    "#47": {"UI-%02d" % n for n in range(1, 11)} |
           {"UX-%02d" % n for n in range(1, 5)} |
           {"A11Y-%02d" % n for n in range(1, 7)} |
           set("FOCUS-01 FOCUS-02 FOCUS-03 QUICK-01".split()),
}
def classify(value):
    kind = value.split(None, 1)[0]
    if kind not in ALLOWED:
        raise ValueError(f"Unrecognized backlog status: {value!r}")
    return kind

def parse_rows(text):
    begin = text.find("## 2. Повний функціональний backlog")
    end = text.find("## 2B.", begin)
    if begin < 0 or end < 0:
        raise ValueError("Canonical backlog tables or section boundaries missing")
    rows = []
    seen = set()
    for line in text[begin:end].splitlines():
        if not line.startswith("|"):
            continue
        cells = [piece.strip() for piece in line.split("|")[1:-1]]
        if len(cells) != 5 or not ID_PATTERN.fullmatch(cells[0]):
            continue
        item_id, priority, raw_status, description, acceptance = cells
        if item_id in seen:
            raise ValueError(f"Duplicate backlog ID: {item_id}")
        if priority not in {"P0", "P1", "P2", "P3"}:
            raise ValueError(f"Invalid priority for {item_id}: {priority}")
        if not description or not acceptance:
            raise ValueError(f"Incomplete backlog row: {item_id}")
        rows.append({"id": item_id, "priority": priority,
                     "reported_status": raw_status, "category": classify(raw_status),
                     "requirement": description, "acceptance_criteria": acceptance})
        seen.add(item_id)
    if not rows:
        raise ValueError("No recognized backlog rows")
    return rows

def route(row):
    item_id = row["id"]
    if row["category"] == "DEFERRED":
        return "OPTIONAL_CLOUD_SCOPE"
    if item_id in PR39_GATES:
        return "#39/#48 HUMAN_UAT"
    if row["category"] == "IMPLEMENTED":
        return "#48 ACCEPTANCE_RECHECK"
    for batch, members in ROUTES.items():
        if item_id in members:
            return batch
    # Existing unassigned work is not silently dropped.
    return "#48 TRIAGE"

def disposition(row):
    if row["category"] == "DEFERRED":
        return "DEFERRED_PRODUCT_DECISION"
    if row["category"] == "GATE":
        return "BLOCKED_PENDING_HUMAN_UAT"
    if row["id"] in OVERLAPS:
        return "REVIEW_POSSIBLE_ACCEPTANCE_OVERLAP"
    if row["category"] == "IMPLEMENTED":
        return "CODE_REPORTED_HUMAN_ACCEPTANCE_OPEN"
    if row["priority"] == "P2" and row["category"] in ("PLANNED", "NEXT"):
        return "OPTIONAL_SCOPE_REVIEW"
    return "REQUIRES_IMPLEMENTATION_OR_EVIDENCE"

def produce(root=ROOT, backlog_text=None):
    source = backlog_text if backlog_text is not None else (root / "docs/PRODUCT_BACKLOG.md").read_text(encoding="utf-8")
    rows = parse_rows(source)
    output = []
    for row in rows:
        path, test = POINTERS.get(row["id"], (None, None))
        if path is not None and not (root / path).is_file():
            raise ValueError(f"Evidence locator source missing for {row['id']}: {path}")
        if test is not None and not (root / test).is_file():
            raise ValueError(f"Evidence locator test missing for {row['id']}: {test}")
        output.append({
            **row,
            "suggested_batch": route(row),
            "disposition": disposition(row),
            "code_locator": path,
            "test_locator": test,
            "evidence_level": ("CODE_AND_TEST_LOCATORS_ONLY" if path and test else
                               "CODE_LOCATOR_ONLY" if path else "UNMAPPED_NEEDS_INSPECTION"),
            "possible_overlaps": list(OVERLAPS.get(row["id"], ())),
            "human_acceptance": "NOT_RECORDED",
        })
    counts = dict(sorted(Counter(row["category"] for row in output).items()))
    batched = dict(sorted(Counter(row["suggested_batch"] for row in output).items()))
    return {
        "schema_version": 1,
        "scope": "LOCAL_SINGLE_BA_DESK",
        "canonical_source": "docs/PRODUCT_BACKLOG.md",
        "evidence_caveat": "Source/test file existence is a navigation aid, not successful business UAT or verified code coverage.",
        "acceptance_policy": "No row automatically becomes DONE; signed human evidence must be recorded separately.",
        "counts": {"total": len(output), "reported_statuses": counts, "suggested_batches": batched,
                   "code_plus_test_locators": sum(x["test_locator"] is not None for x in output),
                   "no_direct_locator": sum(x["code_locator"] is None for x in output)},
        "items": output,
    }

def serialized(result):
    return json.dumps(result, ensure_ascii=False, indent=2) + "\n"

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if committed acceptance ledger is stale")
    args = parser.parse_args(argv)
    try:
        text = serialized(produce())
        if args.check:
            if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != text:
                print("Backlog ledger stale. Run python backlog_audit.py and review diff.", file=sys.stderr)
                return 1
            print("Backlog audit ledger is synchronized (no semantic UAT claimed).")
        else:
            OUTPUT.write_text(text, encoding="utf-8")
            print("Updated " + str(OUTPUT.relative_to(ROOT)))
    except (OSError, ValueError) as exc:
        print("Backlog audit failed: " + str(exc), file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
