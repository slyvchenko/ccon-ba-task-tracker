"""Append-only local history for changed Jira snapshots and manual BA decisions.

Full history stays in private SQLite; API returns bounded recent revisions.
Never sends notes, drafts, PNRs, or task details to GitHub. The history log is
updated inside the same transaction as Desk's import/save operation.
"""
import hashlib
import json
import re
from app_config import utc_now

MAX_TEXT = 22000
MAX_HISTORY_PAGE = 40


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS task_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_key TEXT NOT NULL,
        recorded_at TEXT NOT NULL,
        origin TEXT NOT NULL,
        signature TEXT NOT NULL,
        snapshot_json TEXT NOT NULL,
        change_labels TEXT NOT NULL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_history_task ON task_history(task_key,id DESC)")


def view_state(task, manual_status="AUTO", note="", draft=None, active=True):
    analysis = task.get("analysis") or {}
    email = analysis.get("emailDraft") or {}
    return {
        "summary": str(task.get("summary") or "")[:3000],
        "jiraStatus": str(task.get("jiraStatus") or "")[:200],
        "jiraUpdatedAt": str(task.get("jiraUpdatedAt") or "")[:50],
        "active": bool(active),
        "queueScore": analysis.get("queueScore"),
        "signal": analysis.get("signal"),
        "needsEmail": analysis.get("needsEmail"),
        "nextActionUk": str(analysis.get("nextActionUk") or "")[:3000],
        "standardDescription": str(analysis.get("standardDescription") or "")[:12000],
        "emailSubject": str(email.get("subject") or "")[:1200],
        "emailBody": str(email.get("body") or "")[:MAX_TEXT],
        "manualStatus": manual_status,
        "note": str(note or "")[:MAX_TEXT],
        "savedEmailDraft": {
            "subject": str((draft or {}).get("subject") or "")[:1200],
            "body": str((draft or {}).get("body") or "")[:MAX_TEXT],
            "to": str((draft or {}).get("to") or "")[:600],
        } if isinstance(draft, dict) else None,
    }


def append(conn, key, state, origin):
    if not re.fullmatch(r"CCON-\d+", str(key)) or origin not in ("IMPORT", "MANUAL"):
        raise ValueError("Invalid history event.")
    raw = json.dumps(state, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    if len(raw.encode("utf-8")) > 110000:
        raise ValueError("Task history entry too large.")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    prev = conn.execute(
        "SELECT signature,snapshot_json FROM task_history WHERE task_key=? ORDER BY id DESC LIMIT 1", (key,)
    ).fetchone()
    if prev and prev["signature"] == digest:
        return False
    before = json.loads(prev["snapshot_json"]) if prev else {}
    labels = [k for k in state if before.get(k) != state.get(k)]
    conn.execute("""INSERT INTO task_history
        (task_key,recorded_at,origin,signature,snapshot_json,change_labels)
        VALUES (?,?,?,?,?,?)""", (
            key, utc_now(), origin, digest, raw,
            json.dumps(labels, ensure_ascii=False),
        ))
    return True


def history_page(conn, key, limit=20, offset=0):
    if not re.fullmatch(r"CCON-\d+", str(key)):
        raise ValueError("Invalid task key.")
    if type(limit) is not int or not 1 <= limit <= MAX_HISTORY_PAGE:
        raise ValueError("Invalid history limit.")
    if type(offset) is not int or not 0 <= offset <= 100000:
        raise ValueError("Invalid history offset.")
    total = conn.execute("SELECT COUNT(*) FROM task_history WHERE task_key=?", (key,)).fetchone()[0]
    rows = conn.execute("""SELECT id,recorded_at,origin,snapshot_json,change_labels
        FROM task_history WHERE task_key=? ORDER BY id DESC LIMIT ? OFFSET ?""",
        (key, limit, offset)).fetchall()
    return {"key": key, "total": total, "offset": offset,
            "hasMore": offset + len(rows) < total,
            "revisions": [{
                "id": row["id"], "at": row["recorded_at"], "origin": row["origin"],
                "changed": json.loads(row["change_labels"]),
                "state": json.loads(row["snapshot_json"]),
            } for row in rows]}
