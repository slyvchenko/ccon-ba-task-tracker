"""Human-owned per-issue BA action plan and derived overdue/follow-up indicators.

AI nextActionUk is an UNACCEPTED suggestion, never an assigned work item.
No Jira writes, automatic emails or background jobs. Local files live under
data/actions/ (gitignored) and survive Jira snapshot refresh.
"""
import re
import uuid
from datetime import date
from pathlib import Path

from app_config import ROOT, utc_now
from ba_questions import task_in_scope
from storage import read_json, write_json

STATES = ("OPEN", "WAITING", "DONE")
MAX_ACTIONS = 40
ITEM = re.compile(r"A-[a-f0-9]{12}$")


def action_path(root, key):
    if not re.fullmatch(r"CCON-\d+", str(key)):
        raise ValueError("Invalid issue key.")
    return Path(root) / "data/actions" / (key + ".json")


def _text(value, limit, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError("Invalid action text.")
    return value.strip()


def _date(value):
    if not isinstance(value, str):
        raise ValueError("Date must be YYYY-MM-DD.")
    if not value:
        return ""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Date must be YYYY-MM-DD.")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError("Invalid action date.") from None
    return value


def _read(root, key):
    data = read_json(action_path(root, key), {"key": key, "actions": []})
    if not isinstance(data, dict) or not isinstance(data.get("actions"), list):
        raise ValueError("Invalid action store.")
    return data


def display_actions(root, key, *, today=None):
    task_in_scope(root, key)
    date_today = date.fromisoformat(today) if today else date.today()
    data = _read(root, key)
    actions = []
    for item in data["actions"]:
        deadline = item.get("dueDate") or item.get("nextReviewDate") or ""
        is_open = item.get("status") != "DONE"
        actions.append({**item,
            "overdue": bool(is_open and deadline and deadline < date_today.isoformat()),
            "dueToday": bool(is_open and deadline == date_today.isoformat()),
        })
    return {"key": key, "actions": actions, "openCount": sum(a["status"] != "DONE" for a in actions),
            "overdueCount": sum(a["overdue"] for a in actions)}


def edit_action(root, key, *, action="add", identifier=None, description="",
                owner="", due_date="", next_review_date="", status="OPEN",
                waiting_on="", source="MANUAL"):
    task_in_scope(root, key)
    if action not in ("add", "update") or status not in STATES:
        raise ValueError("Invalid action/status.")
    description = _text(description, 2000, required=True)
    owner = _text(owner, 160)
    waiting_on = _text(waiting_on, 160)
    due_date, next_review_date = _date(due_date), _date(next_review_date)
    if source != "MANUAL":
        raise ValueError("Only manually accepted actions may be saved.")
    data = _read(root, key)
    now = utc_now()
    if action == "add":
        if len(data["actions"]) >= MAX_ACTIONS:
            raise ValueError("Action capacity reached.")
        item = {"id": "A-" + uuid.uuid4().hex[:12], "createdAt": now}
        data["actions"].append(item)
    else:
        if not isinstance(identifier, str) or not ITEM.fullmatch(identifier):
            raise ValueError("Invalid action ID.")
        item = next((x for x in data["actions"] if x.get("id") == identifier), None)
        if not item:
            raise ValueError("Unknown action.")
    item.update({
        "description": description, "owner": owner, "dueDate": due_date,
        "nextReviewDate": next_review_date, "status": status,
        "waitingOn": waiting_on, "updatedAt": now, "source": source,
    })
    data["updatedAt"] = now
    write_json(action_path(root, key), data, 350 * 1024)
    return display_actions(root, key)


def all_actions(root, tasks, today=None):
    """Flat personal queue, sprint comes first; overdue and due next."""
    context = read_json(Path(root) / "data/jira_context.json", {})
    if context.get("complete") is not True:
        return {"tasks": [], "error": "A complete Jira sync is required."}
    scoped = set(context.get("issues", {}))
    values = []
    for task in tasks:
        key = task.get("key")
        if not task.get("active") or key not in scoped:
            continue
        for item in display_actions(root, key, today=today)["actions"]:
            if item["status"] == "DONE":
                continue
            values.append({**item, "key": key, "summary": str(task.get("summary") or "")[:180],
                           "inSprint": task.get("activeSprintStatus") == "VERIFIED"
                             and bool(task.get("activeSprint")),
                           "needsEmail": bool((task.get("analysis") or {}).get("needsEmail"))})
    values.sort(key=lambda i: (
        0 if i["inSprint"] else 1,
        0 if i["overdue"] else 1 if i["dueToday"] else 2,
        0 if i["needsEmail"] else 1,
        i.get("dueDate") or i.get("nextReviewDate") or "9999-12-31",
        i["key"], i["id"],
    ))
    return {"actions": values[:250], "total": len(values),
            "overdueCount": sum(x["overdue"] for x in values)}
