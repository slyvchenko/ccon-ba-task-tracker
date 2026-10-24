"""Local-to-cloud pilot scheduler at 08:00 Europe/Warsaw.

Persistent once-per-local-calendar-day successful-run receipt. Built for a
single worker replica; use a managed cloud job scheduler for HA/multi-replica
production. Does not rely on the owner's Windows laptop.
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app_config import ROOT, utc_now
from storage import write_json
from run_daily import run

WARSAW = ZoneInfo("Europe/Warsaw")


def eligible(now, receipt):
    date = now.astimezone(WARSAW)
    return (date.hour >= 8 and receipt.get("successfulLocalDate") != date.date().isoformat())


def scheduler_iteration(root=ROOT, clock=None, worker=run):
    root = Path(root)
    clock = clock or datetime.now(WARSAW)
    path = root / "data/last_daily_success.json"
    receipt = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not eligible(clock, receipt):
        return {"executed": False, "localDate": clock.astimezone(WARSAW).date().isoformat()}
    attempt = root / "data/last_daily_attempt.json"
    try:
        result = worker(root)
    except Exception as error:
        # Do not persist potentially sensitive provider/Jira response text.
        write_json(attempt, {"status": "FAILED", "attemptedAtUtc": utc_now(),
                             "localDate": clock.astimezone(WARSAW).date().isoformat(),
                             "errorType": type(error).__name__})
        raise
    write_json(attempt, {"status": "SUCCESS", "attemptedAtUtc": utc_now(),
                         "localDate": clock.astimezone(WARSAW).date().isoformat()})
    # Record success only after full sync+analysis+import.
    write_json(path, {
        "successfulLocalDate": clock.astimezone(WARSAW).date().isoformat(),
        "completedAtUtc": utc_now(),
        "promptVersion": result.get("analysis", {}).get("promptVersion"),
        "taskCount": result.get("analysis", {}).get("total", 0),
    })
    return {"executed": True, "localDate": clock.astimezone(WARSAW).date().isoformat()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    while True:
        try:
            output = scheduler_iteration(args.root)
            if output["executed"] or args.once:
                print(json.dumps(output, ensure_ascii=False), flush=True)
        except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError) as error:
            print("Daily scheduler failed: " + str(error), file=sys.stderr, flush=True)
            if args.once:
                return 1
        if args.once:
            return 0
        # Simple single-worker pilot. Failed runs are retried later.
        time.sleep(3600)


if __name__ == "__main__":
    raise SystemExit(main())
