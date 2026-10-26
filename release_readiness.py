"""Fail-closed local BA Desk release readiness inventory.

This is NOT human acceptance, supplier validation, a signed approval, or a
deployment action. Only outputs aggregate counts and fixed gate identifiers.
The public Jira/backlog locator ledger does not contain private signoff proof.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "docs/BACKLOG_ACCEPTANCE_LEDGER.json"
HUMAN_GATES = ("QA-02", "QA-03", "QA-10", "QA-13")
WINDOWS_GATES = ("WINDOWS_SQLITE_CRASH_RESTORE", "WINDOWS_EDGE_NVDA_ZOOM",
                 "WINDOWS_EIGHT_HOUR_SOAK")
CATEGORIES = frozenset(("IMPLEMENTED", "PARTIAL", "GATE", "PLANNED", "NEXT", "DEFERRED"))
PRIORITIES = frozenset(("P0", "P1", "P2", "P3"))


def release_report(ledger):
    """Validate the source-controlled ledger, then refuse to infer UAT from code.

    A human changing a reported status to PASSED in this public ledger is not
    independent evidence: no automated tool can inspect the private real BA
    corpus, verified supplier contracts or native Windows accessibility.
    """
    if not isinstance(ledger, dict) or ledger.get("schema_version") != 1:
        raise ValueError("Unsupported acceptance ledger schema.")
    rows = ledger.get("items")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Acceptance ledger is empty.")
    totals = ledger.get("counts")
    if not isinstance(totals, dict) or totals.get("total") != len(rows):
        raise ValueError("Backlog total does not match the acceptance ledger.")
    ids, category_counts, priority_counts = set(), Counter(), Counter()
    p0_pending = 0
    stated_human_acceptance = 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid backlog row.")
        ident = row.get("id")
        category = row.get("category")
        priority = row.get("priority")
        if not isinstance(ident, str) or not ident or ident in ids:
            raise ValueError("Duplicate or invalid acceptance identifier.")
        if category not in CATEGORIES or priority not in PRIORITIES:
            raise ValueError("Unexpected status or priority in acceptance ledger.")
        ids.add(ident)
        category_counts[category] += 1
        priority_counts[priority] += 1
        state = row.get("human_acceptance")
        if state not in ("NOT_RECORDED", "PASSED", "FAILED", "BLOCKED"):
            raise ValueError("Invalid human acceptance claim.")
        if state != "NOT_RECORDED":
            stated_human_acceptance += 1
        if priority == "P0" and state != "PASSED":
            p0_pending += 1
    if dict(category_counts) != totals.get("reported_statuses"):
        raise ValueError("Backlog category counts have drifted from ledger.")
    missing = [ident for ident in HUMAN_GATES if ident not in ids]
    if missing:
        raise ValueError("Required human acceptance gate missing from inventory.")
    # Real signoff cannot be validated from GitHub-local synthetic fixtures.
    # Thus even 129 manually edited PASSED strings cannot return READY.
    external = [{"id":ident, "state":"NOT_VERIFIED_IN_PUBLIC_REPO"}
                for ident in (*HUMAN_GATES, *WINDOWS_GATES)]
    return {
        "schemaVersion": 1,
        "scope": "LOCAL_SINGLE_BA_DESK",
        "readiness": "BLOCKED_INDEPENDENT_UAT",
        "releaseApproved": False,
        "totalRequirements": len(rows),
        "reportedStatusCounts": dict(sorted(category_counts.items())),
        "priorityCounts": dict(sorted(priority_counts.items())),
        "p0WithoutReportedAcceptance": p0_pending,
        "humanAcceptanceClaimsInLedger": stated_human_acceptance,
        "externalGates": external,
        "reason": ("GitHub source/test locators and synthetic CI cannot verify "
                   "live supplier/Jira/Kibana facts, signed BA gold cases, "
                   "native Windows crash recovery, Edge/NVDA or long-session UAT."),
        "nextStep": "Complete and independently review private BA and Windows signoff before local deployment.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="Validate inventory consistency without asserting release is ready")
    parser.add_argument("--require-ready", action="store_true",
                        help="Fail closed if independent human signoff is unavailable")
    parser.add_argument("--json", action="store_true", help="Print sanitized aggregate report")
    args = parser.parse_args(argv)
    try:
        report = release_report(json.loads(LEDGER.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("Release inventory validation failed: " + str(error), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("Release inventory valid: " + str(report["totalRequirements"]) +
              " items; release=" + report["readiness"] +
              "; independent external UAT unverified.")
    return 2 if args.require_ready else 0


if __name__ == "__main__":
    raise SystemExit(main())
