"""Private-only independent BA gold case UAT summary, never a CI acceptance claim.

Reads ONLY a local anonymous scoring JSON file. No Jira/API access, logging,
persistent state, raw source text or public output of case/reviewer identifiers.
The tool can prove that a review form is complete, not that it is truthful.
"""
import argparse
import json
import math
import statistics
import re
import sys
from collections import Counter
from pathlib import Path

ARCHETYPES = ("READY", "WRITE", "WAIT", "DECIDE", "DEEP", "ERROR")
GRADES = ("PASS", "FAIL", "INCONCLUSIVE")
RESULTS = ("PASSED", "FAILED", "BLOCKED")
ALLOWED = {"id", "archetype", "referenceFrozenBeforeAI",
           "independentReview", "sourceAccessVerified", "facts", "rules",
           "handoff", "criticalFalseReady", "unapprovedExternalAction",
           "falseSourceOrRecipient", "result", "ttnaSeconds", "ttshSeconds"}


def _boolean(value):
    if type(value) is not bool:
        raise ValueError("All review flags must be explicit booleans")
    return value


def _duration(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 <= value <= 86400:
        raise ValueError("Invalid private review timing")
    return round(float(value), 2)


def timing_distribution(values):
    """Anonymous self-reported timing statistics, not a Windows measurement."""
    if not values:
        return {"p50": None, "p95": None}
    ordered = sorted(values)
    return {"p50": round(statistics.median(ordered), 2),
            "p95": round(ordered[math.ceil(0.95 * len(ordered)) - 1], 2)}


def summarize(pack):
    if (not isinstance(pack, dict) or set(pack) != {"schemaVersion", "cases"} or
            type(pack["schemaVersion"]) is not int or pack["schemaVersion"] != 1):
        raise ValueError("Use the anonymous gold review schemaVersion 1")
    rows = pack["cases"]
    if not isinstance(rows, list) or not 20 <= len(rows) <= 30:
        raise ValueError("20 to 30 private case records required")
    seen = set()
    archetypes = Counter()
    outcomes = Counter()
    grades = {name: Counter() for name in ("facts", "rules", "handoff")}
    unsafe = {name: 0 for name in ("criticalFalseReady", "unapprovedExternalAction",
                                  "falseSourceOrRecipient")}
    reviewed = 0
    frozen = 0
    verified = 0
    ttnas = []
    ttshs = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != ALLOWED:
            raise ValueError("Review entries must contain only anonymous schema fields")
        case_id = row["id"]
        if not isinstance(case_id, str) or not re.fullmatch(r"GOLD-(?:0[1-9]|[12][0-9]|30)", case_id):
            raise ValueError("Use generic GOLD-01..GOLD-30 labels, not Jira/PNR IDs")
        if case_id in seen:
            raise ValueError("Duplicate private review pseudonym")
        seen.add(case_id)
        kind = row["archetype"]
        if kind not in ARCHETYPES:
            raise ValueError("Unknown BA work archetype")
        archetypes[kind] += 1
        result = row["result"]
        if result not in RESULTS:
            raise ValueError("Incomplete private reviewer result")
        outcomes[result] += 1
        for field in grades:
            value = row[field]
            if value not in GRADES:
                raise ValueError("Incomplete independent gold rating")
            grades[field][value] += 1
        for field in unsafe:
            if _boolean(row[field]):
                unsafe[field] += 1
        reviewed += int(_boolean(row["independentReview"]))
        frozen += int(_boolean(row["referenceFrozenBeforeAI"]))
        verified += int(_boolean(row["sourceAccessVerified"]))
        a = _duration(row["ttnaSeconds"])
        b = _duration(row["ttshSeconds"])
        # A PASSED result without verified input, passing grades, safe conduct
        # and timings is a contradictory record, not an acceptance result.
        if result == "PASSED" and (
                any(row[flag] is not True for flag in (
                    "referenceFrozenBeforeAI", "independentReview", "sourceAccessVerified")) or
                any(row[field] != "PASS" for field in grades) or
                any(row[field] for field in unsafe) or
                a is None or b is None):
            raise ValueError("PASSED case has missing or failing review fields")
        if a is not None:
            ttnas.append(a)
        if b is not None:
            ttshs.append(b)
    # A reviewer must cover all six archetypes, with case sources frozen
    # before generating the candidate response. No invented PASS if blocked.
    missing = [item for item in ARCHETYPES if not archetypes[item]]
    complete = (not missing and reviewed == len(rows) and frozen == len(rows)
                and verified == len(rows) and not any(unsafe.values())
                and not outcomes["FAILED"] and not outcomes["BLOCKED"]
                and all(grades[key]["PASS"] == len(rows) for key in grades)
                and len(ttnas) == len(rows) and len(ttshs) == len(rows))
    return {
        "schemaVersion": 1,
        "privateOnly": True,
        "caseCount": len(rows),
        "archetypeCounts": dict(sorted(archetypes.items())),
        "missingArchetypes": missing,
        "results": {key: outcomes[key] for key in RESULTS},
        "independentReviewCount": reviewed,
        "frozenBeforeAiCount": frozen,
        "verifiedSourceAccessCount": verified,
        "ratings": {key: {grade: grades[key][grade] for grade in GRADES}
                    for key in sorted(grades)},
        "criticalSafetyCounts": unsafe,
        "timedCases": {"ttna": len(ttnas), "ttsh": len(ttshs)},
        "ttnaSecondsMean": round(sum(ttnas)/len(ttnas), 2) if ttnas else None,
        "ttshSecondsMean": round(sum(ttshs)/len(ttshs), 2) if ttshs else None,
        "ttnaSecondsP50": timing_distribution(ttnas)["p50"],
        "ttnaSecondsP95": timing_distribution(ttnas)["p95"],
        "ttshSecondsP50": timing_distribution(ttshs)["p50"],
        "ttshSecondsP95": timing_distribution(ttshs)["p95"],
        "criteriaReadyForHumanDecision": complete,
        "humanAcceptance": "NOT_RECORDED",
        "releaseApproved": False,
        "limitations": ("Anonymous self-reported review results are NOT independently "
                        "verified; source evidence, reviewer identity, signed UAT and "
                        "Windows acceptance must be checked in private."),
    }


class _PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("Invalid private review CLI arguments")


def main(argv=None):
    parser = _PrivateParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    try:
        args = parser.parse_args(argv)
        with args.input.open("r", encoding="utf-8") as stream:
            result = summarize(json.load(stream))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        print("Private gold-case preflight unavailable or invalid; no case data printed.",
              file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
