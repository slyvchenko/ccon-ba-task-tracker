"""Quiet and observable local snapshot watcher with bounded retry."""
import time
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class SnapshotMonitor:
    def __init__(self, desk, *, clock=time.monotonic, retry_seconds=30):
        self.desk = desk
        self.path = Path(desk.inbox) / 'CCON_BA_Snapshot.json'
        self.clock = clock
        self.retry_seconds = retry_seconds
        self.signature = None
        self.next_retry = 0
        self.status = {"state": "WAITING", "attempts": 0, "failures": 0,
                       "lastSuccessAt": None, "lastFailureAt": None}

    def check(self):
        try:
            metadata = self.path.stat()
            signature = (metadata.st_mtime_ns, metadata.st_size)
        except FileNotFoundError:
            self.status["state"] = "NO_SNAPSHOT"
            self.signature = None
            return False
        except OSError:
            signature = None

        now = self.clock()
        if signature == self.signature and now < self.next_retry:
            return False
        if signature == self.signature and self.status["state"] == "OK":
            return False
        self.signature = signature
        self.status["attempts"] += 1
        stamp = datetime.now(timezone.utc).isoformat()
        try:
            self.desk.import_snapshot()
        except (OSError, ValueError, sqlite3.Error):
            self.status["state"] = "FAILED"
            self.status["failures"] += 1
            self.status["lastFailureAt"] = stamp
            # Do not show raw Jira data or paths. desk.error remains available
            # through existing revision source-error handling.
            self.next_retry = now + self.retry_seconds
            return False
        self.status["state"] = "OK"
        self.status["lastSuccessAt"] = stamp
        self.next_retry = 0
        return True

    def public_status(self):
        return dict(self.status)
