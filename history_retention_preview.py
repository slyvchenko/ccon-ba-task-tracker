"""Read-only retention eligibility preview. No task IDs, note, email or history JSON exported.

This intentionally does NOT archive/delete history. Human approval and a
verified restore path are prerequisites to any future retention mutation.
"""
import argparse
from contextlib import closing
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app_config import ROOT


def preview(root=ROOT, days=365, *, now=None):
    if type(days) is not int or not 30 <= days <= 3650:
        raise ValueError("Retention horizon must be 30..3650 days")
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Existing nonsymlink workspace required")
    # URI paths must be absolute, including caller-supplied relative roots.
    root = root.resolve(strict=True)
    path = root / "ba_state.db"
    if not path.is_file() or path.is_symlink():
        raise ValueError("Existing local SQLite database required")
    # SQLite read-only URI prevents accidental DB initialization/DDL.
    # Do not emit paths in output; only aggregate counts.
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        raise ValueError("Cutoff time must have timezone")
    cutoff = (stamp.astimezone(timezone.utc)-timedelta(days=days)).isoformat()
    # sqlite3 connection context only commits/rolls back; Windows needs an
    # explicit close before temporary folders or restored files are removed.
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro", uri=True)) as conn:
        # sqlite3 connection context does not begin read transactions for SELECT.
        # Anchor every aggregate to the same SQLite snapshot across imports.
        conn.execute("BEGIN")
        total = conn.execute("SELECT COUNT(*) FROM task_history").fetchone()[0]
        # Always retain the latest history record per task, even if old.
        # A preview is not approval to delete anything.
        candidate = conn.execute("""
            SELECT origin,COUNT(*) FROM task_history
            WHERE recorded_at < ?
              AND id NOT IN (SELECT MAX(id) FROM task_history GROUP BY task_key)
            GROUP BY origin
        """, (cutoff,)).fetchall()
        imports = conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0]
        task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    by_origin = {name: count for name, count in candidate if name in ("MANUAL", "IMPORT")}
    return {
        "schemaVersion": 1, "readOnly": True, "deleted": 0,
        "archived": 0, "eligibleOlderRevisions": sum(by_origin.values()),
        "eligibleByOrigin": {"MANUAL": by_origin.get("MANUAL", 0),
                             "IMPORT": by_origin.get("IMPORT", 0)},
        "totalHistoryRevisions": total, "taskCount": task_count,
        "importAuditEntriesPreserved": imports, "cutoffDays": days,
        "approval": "REQUIRED_BEFORE_ANY_ARCHIVE_OR_DELETION",
        "policy": "ALWAYS_PRESERVE_LATEST_PER_TASK",
        "scope": "Private local SQLite counts only; no notes, issue keys, filenames, emails, PNR or log contents.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=365)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(preview(days=args.days), indent=2))
    except (OSError, ValueError, sqlite3.Error):
        # Never echo local path or raw SQLite errors into terminal logs.
        parser.exit(1, "Retention preview unavailable; check local database and horizon.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
