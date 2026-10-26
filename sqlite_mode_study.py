"""Bounded synthetic SQLite mode evaluation. NEVER touches a user's BA DB.

All database files are created under TemporaryDirectory; no PRAGMA mode change
is made to the installed application. Outputs aggregate latency/plan labels.
"""
import argparse
import json
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path

from desk_store import Desk
from performance_smoke import synthetic_document


def _p95(values):
    return round(sorted(values)[min(len(values)-1, round((len(values)-1)*.95))], 3)


def evaluate(count=100, iterations=5):
    if type(count) is not int or not 10 <= count <= 1000:
        raise ValueError("Synthetic task count must be 10..1000")
    if type(iterations) is not int or not 3 <= iterations <= 20:
        raise ValueError("Iterations must be 3..20")
    results = []
    for journal in ("DELETE", "WAL"):
        for indexed in (False, True):
            with tempfile.TemporaryDirectory(prefix="ccon-synthetic-sqlite-mode-") as folder:
                root = Path(folder)
                desk = Desk(root)
                source = desk.inbox / "CCON_BA_Snapshot.json"
                source.write_text(json.dumps(synthetic_document(count)), encoding="utf-8")
                desk.import_snapshot()
                with desk.connect() as connection:
                    actual = connection.execute("PRAGMA journal_mode=" + journal).fetchone()[0]
                    if actual.upper() != journal:
                        raise RuntimeError("SQLite mode was not applied in synthetic DB")
                    if indexed:
                        connection.execute(
                            "CREATE INDEX idx_synthetic_json_priority "
                            "ON tasks(json_extract(snapshot,'$.priority'))")
                    query = ("SELECT COUNT(*) FROM tasks WHERE "
                             "json_extract(snapshot,'$.priority')=?")
                    plan = " ".join(row[3] for row in connection.execute(
                        "EXPLAIN QUERY PLAN " + query, ("High",)).fetchall())
                    durations = []
                    for _ in range(iterations):
                        started = time.perf_counter()
                        connection.execute(query, ("High",)).fetchone()
                        durations.append((time.perf_counter()-started)*1000)
                    # sqlite3 backup() works with a WAL source; verify integrity
                    # without ever touching the installed user's DB.
                    backup_path = root / "synthetic-copy.db"
                    with sqlite3.connect(backup_path) as target:
                        connection.backup(target)
                        integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
                    # Read current busy timeout rather than silently enabling a
                    # different one on the user's real application.
                    timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
                results.append({
                    "journal": journal, "syntheticJsonIndex": indexed,
                    "p95QueryMs": _p95(durations),
                    "queryUsesIndex": "USING INDEX idx_synthetic_json_priority" in plan,
                    "busyTimeoutMs": timeout,
                    "backupIntegrity": integrity,
                    "liveConfigurationChanged": False,
                })
    return {"syntheticOnly": True, "taskCount": count,
            "iterations": iterations, "results": results,
            "recommendation": "EVALUATE_ONLY_NO_PRODUCTION_SWITCH",
            "limits": "Synthetic JSON filter not used in normal queue; device and Windows WAL/backup UAT required."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=int, default=100)
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args(argv)
    print(json.dumps(evaluate(args.tasks, args.iterations), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
