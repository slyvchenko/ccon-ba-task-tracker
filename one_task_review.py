"""Re-analyze exactly one of MY cached Jira tasks with the approved BA model.

This CLI does not browse Jira/Kibana, modify Jira, send email, or silently
refresh stale unrelated tasks. It preserves analyst manual notes and drafts
through the existing transactional snapshot import. For a browser-triggered
workflow the local Codex must invoke the CLI explicitly; there is no remote
code-execution API in the dashboard.
"""
import argparse
import json
import re
from pathlib import Path

from app_config import ROOT
from model_analysis import analyze_all, request_analysis
from apply_analysis import apply


def review_one(root=ROOT, issue_key=None, model_call=request_analysis):
    if not isinstance(issue_key, str) or not re.fullmatch(r"CCON-\d+", issue_key):
        raise ValueError("A valid CCON issue key is required.")
    root = Path(root)
    generated = analyze_all(root, model_call=model_call, issue_key=issue_key)
    if generated.get("generated") != 1 or generated.get("focusIssue") != issue_key:
        raise ValueError("Focused model analysis did not produce exactly one review.")
    # Existing import validates every analysis and preserves all manual edits.
    apply(Path(generated["path"]), root)
    return {"issueKey": issue_key, "generated": 1,
            "preservedOtherAnalyses": generated["reused"],
            "status": "LOCAL_ANALYSIS_IMPORTED_NOT_JIRA_UPDATED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = review_one(args.root, args.issue)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, "Focused BA review failed: " + str(error) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
