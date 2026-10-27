"""Read-only ISO-week BA workload metrics from private local history.

Only aggregate counts leave this process. Never emit task IDs, drafts,
notes, history payloads or person names. No network, no background scheduler.
"""
import argparse
from contextlib import closing
import json
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app_config import ROOT

DONE = {"DONE", "CLOSED", "RESOLVED", "COMPLETED"}
BLOCKED = {"WAITING INPUT", "WAITING DEPENDENCY"}
WEEK = re.compile(r"^(\d{4})-W(\d{2})$")


def _window(week, today=None):
    if not isinstance(week, str):
        raise ValueError("ISO week is required")
    match = WEEK.fullmatch(week)
    if not match:
        raise ValueError("Invalid ISO week")
    start = date.fromisocalendar(int(match[1]), int(match[2]), 1)
    end = start + timedelta(days=7)
    return (datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc),
            datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc))


def _status(state):
    manual = state.get("manualStatus", "AUTO")
    # Explicit manual action always overrides the automatic BA signal.
    if manual != "AUTO":
        if manual == "DONE":
            return "DONE"
        return "BLOCKED" if manual in BLOCKED else "WIP"
    # Older history has no verified freshness marker; treat it conservatively.
    signal = state.get("signal") if state.get("analysisVerified") is True else None
    if signal == "DONE":
        return "DONE"
    if signal == "WAIT":
        return "BLOCKED"
    if signal in ("READY", "WRITE", "DECIDE", "REVIEW"):
        return "WIP"
    return "DONE" if str(state.get("jiraStatus") or "").upper() in DONE else "WIP"


def weekly_report(root=ROOT, week=None, *, today=None):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Local workspace must exist")
    # sqlite3 URI paths require an absolute canonical workspace path.
    root = root.resolve(strict=True)
    today = today or datetime.now(timezone.utc).date()
    if week is None:
        last_monday = today - timedelta(days=today.weekday() + 7)
        iso = last_monday.isocalendar()
        week = f"{iso.year}-W{iso.week:02d}"
    start, end = _window(week)
    db = root / "ba_state.db"
    if not db.is_file() or db.is_symlink():
        raise ValueError("Read-only local history database required")
    latest = {}
    completed, reopened, touched = set(), set(), set()
    total_events = 0
    # A read-only WAL open may CREATE missing -wal/-shm sidecars; refuse to
    # open that unverified state rather than silently writing into a workspace.
    with db.open("rb") as header_file:
        header = header_file.read(20)
    if len(header) < 20 or header[:16] != b"SQLite format 3\\x00":
        raise ValueError("Invalid SQLite database header")
    if header[18] == 2:
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(db) + suffix)
            if not sidecar.is_file() or sidecar.is_symlink():
                raise ValueError("Read-only WAL sidecars unavailable")
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as conn:
        # Historical revisions are append-only. Do not expose keys or content.
        for key, stamp, raw in conn.execute(
                "SELECT task_key,recorded_at,snapshot_json "
                "FROM task_history ORDER BY id"):
            try:
                when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                if when.tzinfo is None:
                    continue
                when = when.astimezone(timezone.utc)
            except (ValueError, AttributeError, TypeError):
                continue
            if when >= end:
                continue
            state = json.loads(raw)
            if not isinstance(state, dict):
                raise ValueError("Unexpected history state")
            previous = latest.get(key)
            if start <= when < end:
                total_events += 1
                touched.add(key)
                # Archived tasks keep known previous revisions. Their later
                # return may legitimately complete or reopen an older task.
                if previous:
                    # Upgrading the old history schema from an unverified
                    # signal to a verified marker is not evidence of a newly
                    # completed BA task. Preserve the as-of state, but do not
                    # count metadata-only changes as work transitions.
                    metadata_upgrade = (
                        "analysisVerified" not in previous and
                        state.get("analysisVerified") is True and
                        previous.get("manualStatus", "AUTO") == "AUTO" and
                        state.get("manualStatus", "AUTO") == "AUTO" and
                        previous.get("signal") == state.get("signal") and
                        previous.get("jiraStatus") == state.get("jiraStatus") and
                        previous.get("active") == state.get("active"))
                    if not metadata_upgrade:
                        prior = _status(previous)
                        current = _status(state)
                        if prior != "DONE" and current == "DONE":
                            completed.add(key)
                        if prior == "DONE" and current != "DONE":
                            reopened.add(key)
            latest[key] = state
    active_states = [x for x in latest.values() if x.get("active", False)]
    wip = sum(_status(x) == "WIP" for x in active_states)
    blockers = sum(_status(x) == "BLOCKED" for x in active_states)
    done = sum(_status(x) == "DONE" for x in active_states)
    return {
        "schemaVersion": 1, "isoWeek": week,
        "timeBoundary": "UTC", "readOnly": True, "cloudTelemetry": False,
        "source": "APPEND_ONLY_LOCAL_HISTORY",
        "metricsAreNotAgentPerformance": True,
        "asOfWeekEnd": {"workInProgress": wip, "blocked": blockers,
                        "completedState": done},
        "weeklyTransitions": {"completed": len(completed), "reopened": len(reopened),
                              "taskChanges": len(touched), "historyEvents": total_events},
        "blockerShareOfOpenPct": (round(100*blockers/(wip+blockers),1)
                                  if wip+blockers else None),
        # Even Sunday at 23:59 has not completed the current ISO week.
        "weekMayBeIncomplete": end > datetime.combine(
            today, datetime.min.time(),tzinfo=timezone.utc),
        "limitations": ("As-of snapshot comes from recorded BA task history; "
                        "no agent ranking, no time spent measurement, no inference "
                        "about work before the first imported snapshot."),
    }


class _SanitizedParser(argparse.ArgumentParser):
    def error(self, message):
        # Default argparse echoes the rejected argument, which may contain
        # private filesystem paths, supplier references or PNRs.
        raise ValueError("Invalid weekly metrics arguments.")


def main(argv=None):
    parser = _SanitizedParser(description=__doc__)
    parser.add_argument("--week", default=None)
    parser.add_argument("--root", type=Path, default=ROOT)
    try:
        args = parser.parse_args(argv)
        print(json.dumps(weekly_report(args.root, args.week), sort_keys=True))
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError):
        print("Weekly local metrics unavailable. Check the week and local database.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
