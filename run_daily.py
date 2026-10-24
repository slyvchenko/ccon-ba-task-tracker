"""One read-only corporate Jira + approved-AI daily cycle.

Fails closed without an authorized model provider / one analyst account ID.
External side effects are only GET Jira and an explicitly approved model POST;
Jira, Confluence, and email remain unmodified.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from app_config import ROOT
from jira_sync import sync, query_for_owner
from model_analysis import analyze_all, model_settings
from apply_analysis import apply
from pipeline_lock import pipeline_lock


def run(root=ROOT, jira_sync=sync, analyze=analyze_all, importer=apply):
    root = Path(root)
    if os.environ.get("CCON_CLOUD_MODE") != "1":
        raise ValueError("Cloud cycle requires CCON_CLOUD_MODE=1.")
    # Validate *before* making any Jira request or modifying any local file.
    query_for_owner(cloud_mode=True)
    model_settings()
    with pipeline_lock(root / ".daily"):
        pulled = jira_sync(root)
        analyzed = analyze(root)
        importer(Path(analyzed["path"]), root)
        # A successful snapshot alone is insufficient: the daily delta report
        # must belong to this exact completed import.
        report = json.loads((root / "data/daily_review_report.json").read_text(encoding="utf-8"))
        snapshot = json.loads((root / "inbox/CCON_BA_Snapshot.json").read_text(encoding="utf-8"))
        if report.get("generatedAt") != snapshot.get("generatedAt"):
            raise ValueError("Daily report is missing or stale after import.")
    return {
        "sync": pulled,
        "analysis": analyzed,
        "mode": "READ_ONLY_JIRA_AND_EXPLICITLY_APPROVED_AI",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = run(args.root)
    except (ValueError, OSError, KeyError, TypeError) as error:
        # Exception messages are owned by validated app code, never raw provider responses.
        print("Daily cloud BA cycle failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
