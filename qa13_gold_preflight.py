"""QA-13 independent gold handoff preflight for private real Jira cases.

This CLI never visits Jira, infers factual truth, saves reports, or publishes
case text. It checks that the existing human-scored 20-30-case pack has frozen
source fingerprints, two variant snapshots and a separately authored gold
reference attestation. Human release acceptance always remains separate.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from app_config import ROOT
from evaluation import score_pack

MIN_CASES, MAX_CASES = 20, 30
FILES = {
    "cohort": "selected_cases.json",
    "reviews": "reviews.json",
    "gold": "gold_attestations.json",
    "baseline": "baseline_predictions.json",
    "candidate": "candidate_predictions.json",
}


def _read_private(directory, filename, limit=32 * 1024 * 1024):
    path = directory / filename
    if not path.is_file():
        return None
    if path.is_symlink() or path.stat().st_size > limit:
        raise ValueError("Private evaluation file refused (symlink or size).")
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _date(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (ValueError, AttributeError, TypeError):
        return None


def _frozen_prediction(pack, data, variant):
    if not isinstance(data, dict) or data.get("variant") != variant:
        return False
    analyses = data.get("analyses")
    if not isinstance(analyses, dict):
        return False
    cases = pack["cases"]
    if set(analyses) != {x["key"] for x in cases}:
        return False
    return all(isinstance(analyses.get(x["key"]), dict) and
               analyses[x["key"]].get("contextFingerprint") == x["contextFingerprint"]
               for x in cases)


def check(root=ROOT):
    directory = Path(root) / "data" / "evaluation"
    if directory.is_symlink():
        raise ValueError("Symlinked private evaluation directory refused.")
    payload = {key: _read_private(directory, name) for key, name in FILES.items()}
    result = {
        "schemaVersion": 1, "requirement": "QA-13",
        "readOnly": True, "externalAccess": False,
        "rawCaseDataExported": False, "humanAcceptance": "NOT_RECORDED",
        "status": "INCOMPLETE_PRIVATE_GOLD_STUDY",
        "caseCount": 0, "independentGoldCases": 0,
        "missingFiles": [key for key, value in payload.items() if value is None],
        "baselineFrozen": False, "candidateFrozen": False,
        "rubricTargetsFromHumanScores": None,
        "limitations": "Self-attested metadata cannot verify real Jira source truth or substitute for independent human signoff.",
    }
    if payload["cohort"] is None:
        return result
    pack = payload["cohort"]
    cases = pack.get("cases") if isinstance(pack, dict) else None
    if not isinstance(cases, list) or not MIN_CASES <= len(cases) <= MAX_CASES:
        raise ValueError("Frozen 20-30 case cohort required.")
    if not all(isinstance(x, dict) and isinstance(x.get("key"), str) and x["key"] and
               isinstance(x.get("contextFingerprint"), str) and x["contextFingerprint"]
               for x in cases):
        raise ValueError("Incomplete frozen case provenance.")
    keys = [x["key"] for x in cases]
    if len(set(keys)) != len(keys):
        raise ValueError("Repeated private case identities.")
    result["caseCount"] = len(cases)
    for label in ("baseline", "candidate"):
        result[label + "Frozen"] = _frozen_prediction(pack, payload[label], label)
    if payload["reviews"] is not None:
        score = score_pack(pack, payload["reviews"])
        result["reviewedCases"] = score["completed"]
        result["rubricTargetsFromHumanScores"] = score.get("candidateMeetsTargets", False)
        result["humanCriticalFalseClaims"] = (score.get("metrics") or {}).get(
            "candidate", {}).get("criticalFalseClaims")
    else:
        result["reviewedCases"] = 0
    gold = payload["gold"]
    if isinstance(gold, dict) and isinstance(gold.get("cases"), list):
        rows = gold["cases"]
        by_key = {x.get("key"): x for x in rows if isinstance(x, dict)}
        reviews = {x["key"]: x for x in (payload["reviews"] or {}).get("reviews", [])
                   if isinstance(x, dict) and isinstance(x.get("key"), str)}
        if len(by_key) == len(rows) and set(by_key) == set(keys):
            good = 0
            for case in cases:
                row = by_key[case["key"]]
                reviewer = reviews.get(case["key"], {}).get("reviewer")
                author = row.get("referenceAuthorCode")
                checker = row.get("independentReviewerCode")
                frozen = _date(row.get("referenceFrozenAt"))
                first_seen = _date(row.get("candidateFirstSeenAt"))
                if (isinstance(author, str) and bool(author.strip()) and
                        isinstance(checker, str) and bool(checker.strip()) and
                        author != checker and checker == reviewer and
                        frozen is not None and first_seen is not None and frozen < first_seen and
                        row.get("sourceFingerprint") == case["contextFingerprint"] and
                        row.get("independentSourceReview") is True and
                        row.get("goldExpectedWritten") is True):
                    good += 1
            result["independentGoldCases"] = good
    if (result["independentGoldCases"] == result["caseCount"]
            and result["reviewedCases"] == result["caseCount"]
            and result["baselineFrozen"] and result["candidateFrozen"]):
        result["status"] = (
            "READY_FOR_PRIVATE_HUMAN_SIGNOFF" if result["rubricTargetsFromHumanScores"]
            else "RUBRIC_TARGETS_NOT_MET"
        )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local-only independent BA gold attestation preflight.")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        result = check(args.root)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        # Never print private Jira case IDs, filesystem paths or JSON fields.
        parser.exit(1, "Private BA gold preflight invalid; check local files and cohort.\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
