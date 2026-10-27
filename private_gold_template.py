"""Create an explicitly requested, incomplete and private 26-case BA UAT form.

Never fills evaluation PASS values, never accesses Jira, never sends data.
The template is intentionally BLOCKED until real independent human review.
"""
import argparse
import json
import os
import stat
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


def _has_reparse_attribute(details):
    """Detect NTFS junction/reparse points on Python 3.10+, not only 3.12+."""
    return bool(getattr(details, "st_file_attributes", 0) &
                getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def create_template(destination, confirm):
    if confirm != CONFIRM:
        raise ValueError("Explicit private template confirmation required")
    target = Path(destination)
    # A symlink followed by '..' resolves differently from abspath():
    # lexical normalization collapses '..' *before* checking symlinks.
    # Refuse parent traversal at the raw path level instead of guessing.
    if ".." in target.parts:
        raise ValueError("Private template destination must not contain parent traversal")
    parent = target.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("Use a private existing nonsymlink directory")
    # Windows Path.resolve() may change drive/path spelling on an ordinary
    # folder. Do not equate string inequality with symlink traversal.
    # Inspect actual filesystem entries (including NTFS junctions) instead.
    lexical_parent = Path(os.path.abspath(parent))
    for component in (lexical_parent, *lexical_parent.parents):
        # lstat observes the link itself, not its target. st_file_attributes
        # has been available on Windows since well before Path.is_junction().
        # Reject every reparse-point type conservatively, including junctions.
        try:
            details = component.lstat()
        except OSError as exc:
            raise ValueError("Cannot verify private destination ancestry") from exc
        if component.is_symlink() or _has_reparse_attribute(details) or (
            hasattr(component, "is_junction") and component.is_junction()
        ):
            raise ValueError("Private template destination has a redirected parent")
    actual_parent = lexical_parent.resolve(strict=True)
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
