"""Create an explicitly requested, incomplete and private 26-case BA UAT form.

Never fills evaluation PASS values, never accesses Jira, never sends data.
The template is intentionally BLOCKED until real independent human review.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from app_config import ROOT
from private_gold_review import ARCHETYPES, summarize

CONFIRM = "CREATE EMPTY PRIVATE GOLD COHORT"
DISTRIBUTION = (("READY", 4), ("WRITE", 5), ("WAIT", 4),
                ("DECIDE", 4), ("DEEP", 5), ("ERROR", 4))


def blank_cohort():
    """Twenty-six anonymous, explicitly unreviewed records, no case contents."""
    rows = []
    for archetype, amount in DISTRIBUTION:
        for _ in range(amount):
            rows.append({
                "id": f"GOLD-{len(rows) + 1:02d}",
                "archetype": archetype,
                "referenceFrozenBeforeAI": False,
                "independentReview": False,
                "sourceAccessVerified": False,
                "facts": "INCONCLUSIVE",
                "rules": "INCONCLUSIVE",
                "handoff": "INCONCLUSIVE",
                # False here is a placeholder, NOT a verified absence.
                "criticalFalseReady": False,
                "unapprovedExternalAction": False,
                "falseSourceOrRecipient": False,
                "result": "BLOCKED",
                "ttnaSeconds": None,
                "ttshSeconds": None,
            })
    pack = {"schemaVersion": 1, "cases": rows}
    result = summarize(pack)
    assert result["caseCount"] == 26
    assert not result["criteriaReadyForHumanDecision"]
    assert result["humanAcceptance"] == "NOT_RECORDED"
    assert not result["releaseApproved"]
    return pack


def create_template(destination, confirm):
    if confirm != CONFIRM:
        raise ValueError("Explicit private template confirmation required")
    target = Path(destination)
    parent = target.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("Use a private existing nonsymlink directory")
    actual_parent = parent.resolve(strict=True)
    # Reject symlinked ancestors as well as the direct parent. This protects
    # against accidentally writing via a redirected folder.
    if os.path.normcase(os.path.abspath(parent)) != os.path.normcase(str(actual_parent)):
        raise ValueError("Private template destination has a redirected parent")
    if actual_parent == ROOT or ROOT in actual_parent.parents:
        raise ValueError("Do not write private UAT artifacts inside the repository")
    if target.exists() or target.is_symlink():
        raise ValueError("Refusing to overwrite the local private review form")
    data = json.dumps(blank_cohort(), ensure_ascii=False, indent=2) + "\n"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return {"created": True, "caseCount": 26,
            "realCasesIncluded": False, "independentReviewCompleted": False,
            "releaseApproved": False, "externalSends": False}


class _PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("Invalid private template arguments")


def main(argv=None):
    parser = _PrivateParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm", default="")
    try:
        args = parser.parse_args(argv)
        result = create_template(args.output, args.confirm)
    except (ValueError, OSError):
        print("Private gold template was not created; check consent and output location.",
              file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
