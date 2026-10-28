"""Read-only local project + task statistics. Return no issue keys or source content.

The product counts are based on the tracked public backlog ledger. Live task
statistics come only from the currently loaded local SQLite snapshot.
This endpoint never evaluates independent human acceptance or CI status.
"""
import json
from collections import Counter

from release_readiness import LEDGER, release_report

SIGNALS = ("WRITE", "READY", "DECIDE", "REVIEW", "WAIT", "OTHER")
STATUS_LABELS = ("AUTO", "IN PROGRESS", "WAITING INPUT",
                 "WAITING DEPENDENCY", "NEEDS DECISION", "DONE")


def analysis_is_stale(task):
    analysis = task.get("analysis")
    if not isinstance(analysis, dict):
        return False
    return (analysis.get("stale") is True or
            bool(analysis.get("contextFingerprint") and
                 task.get("contextFingerprint") and
                 analysis["contextFingerprint"] != task["contextFingerprint"]))


def task_signal(task):
    """Match the UI queue's effectiveSignal: never count stale AI as READY."""
    manual = task.get("manualStatus")
    if manual in ("WAITING INPUT", "WAITING DEPENDENCY"):
        return "WAIT"
    if manual == "IN PROGRESS":
        return "READY"  # Explicit human status, not an AI recommendation.
    if manual == "NEEDS DECISION":
        return "DECIDE"
    if manual not in ("AUTO", None, ""):
        return "REVIEW"
    analysis = task.get("analysis")
    if (isinstance(analysis, dict) and not analysis_is_stale(task) and
            analysis.get("reasonUk") and analysis.get("nextActionUk") and
            analysis.get("signal") in SIGNALS[:-1]):
        return analysis["signal"]
    # aiStatus alone is not sufficient proof that a recommendation is current.
    return "REVIEW"


def statistics_report(desk):
    """Aggregate only fixed enumerated categories and integer counts."""
    with LEDGER.open("r", encoding="utf-8") as source:
        ledger = json.load(source)
    release = release_report(ledger)
    view = desk.view()  # One transaction: statuses and counts match a revision.
    tasks = view["tasks"]
    active = [row for row in tasks if row.get("active")]
    unfinished = [row for row in active if row.get("manualStatus") != "DONE"]
    lanes = Counter(task_signal(task) for task in unfinished)
    manual = Counter(task.get("manualStatus") for task in active)
    p0 = Counter(row["category"] for row in ledger["items"]
                 if row["priority"] == "P0")
    unanalyzed = sum(not isinstance(row.get("analysis"), dict)
                     for row in unfinished)
    stale = sum(analysis_is_stale(row) for row in unfinished)
    # Sprint membership is independent of the local manual DONE state.
    sprint = sum(row.get("activeSprintStatus") == "VERIFIED"
                 and row.get("activeSprint") is True for row in active)
    latest = view.get("latest")
    return {
        "schemaVersion": 1,
        "source": "LOCAL_SQLITE_AND_TRACKED_LEDGER",
        "privacy": "AGGREGATE_ONLY_NO_ISSUE_CONTENT",
        "project": {
            "requirements": release["totalRequirements"],
            "reportedStatuses": release["reportedStatusCounts"],
            "priorityCounts": release["priorityCounts"],
            "p0ReportedStatuses": dict(sorted(p0.items())),
            "codeAndTestPointers": ledger["counts"]["code_plus_test_locators"],
            "readiness": release["readiness"],
            "releaseApproved": False,
            "humanAcceptanceVerifiableHere": False,
            "goldCaseTarget": 26,
            "goldCasesVerifiedHere": 0,
            "externalGateCount": len(release["externalGates"]),
            "externalGatesVerifiedHere": 0,
        },
        "tasks": {
            "loaded": len(tasks),
            "active": len(active),
            "archived": len(tasks) - len(active),
            "done": manual["DONE"],
            "unfinished": len(unfinished),
            "signalCounts": {lane: lanes[lane] for lane in SIGNALS},
            "manualStatusCounts": {
                status: manual[status] for status in STATUS_LABELS
            },
            "activeVerifiedSprint": sprint,
            "withoutAnalysis": unanalyzed,
            "staleAnalysis": stale,
            "snapshotAvailable": latest is not None,
            "snapshotGeneratedAt": latest["generated_at"] if latest else None,
        },
    }
