"""Shared application constants and UTC timestamps."""
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = '2.2.0'
LIMIT = SNAPSHOT_LIMIT = 5 * 1024 * 1024
CONTEXT_LIMIT = 50 * 1024 * 1024
STATUSES = ['AUTO', 'IN PROGRESS', 'WAITING INPUT', 'WAITING DEPENDENCY', 'NEEDS DECISION', 'DONE']
SIGNALS = ('READY', 'WRITE', 'WAIT', 'DECIDE', 'REVIEW', 'DONE')

def utc_now():
    return datetime.now(timezone.utc).isoformat()
