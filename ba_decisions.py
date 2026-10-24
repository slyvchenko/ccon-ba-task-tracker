"""Per-issue append-only decision events with manual confirmation.

AI/Jira timeline may propose a decision, but only an explicit human action can
confirm, dispute, or supersede it. A supersession preserves the old record and
records both status transitions. This never modifies Jira or drafted text.
"""
import hashlib
import re
from pathlib import Path
from urllib.parse import urlsplit

from app_config import utc_now
from storage import read_json, write_json
from ba_questions import task_in_scope

MAX_DECISIONS = 200
MAX_EVENTS = 600
STATES = {"PROPOSED", "CONFIRMED", "SUPERSEDED", "DISPUTED"}
ID = re.compile(r"D-[a-f0-9]{14}$")


def decision_path(root, key):
    if not re.fullmatch(r"CCON-\d+", str(key)):
        raise ValueError("Invalid issue key.")
    return Path(root) / "data/decisions" / (key + ".json")


def safe_text(value, limit, required=True):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError("Invalid decision text.")
    return value.strip()


def source_link(url):
    url = safe_text(url, 2000)
    parsed = urlsplit(url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or
            parsed.username or parsed.password):
        raise ValueError("Decision source must be a safe HTTP(S) URL.")
    return url


def read_decisions(root, key):
    data = read_json(decision_path(root, key), {"key": key, "decisions": [], "events": []})
    if not isinstance(data, dict) or not isinstance(data.get("decisions"), list) or not isinstance(data.get("events"), list):
        raise ValueError("Invalid local decision history.")
    return data


def _new_id(key, source, text):
    digest = hashlib.sha256((key + "\0" + source + "\0" + text).encode()).hexdigest()[:14]
    return "D-" + digest


def _event(data, identifier, old, new, reason, actor):
    if len(data["events"]) >= MAX_EVENTS:
        raise ValueError("Decision history capacity reached, export/archive first.")
    data["events"].append({"id": identifier, "from": old, "to": new,
                           "reason": reason[:1000], "actor": actor, "at": utc_now()})


def sync_decision_proposals(root, key, analysis):
    """Model timeline entries stay PROPOSED even if its claimed status is CONFIRMED."""
    task_in_scope(root, key)
    data = read_decisions(root, key)
    for item in ((analysis or {}).get("briefing") or {}).get("timeline", [])[:30]:
        if not isinstance(item, dict):
            continue
        message = str(item.get("eventUk") or "").strip()
        url = item.get("sourceUrl") or ""
        if not message or not url:
            continue
        try:
            message = safe_text(message, 1500)
            url = source_link(url)
        except ValueError:
            continue
        identifier = _new_id(key, "AI:" + url, message)
        if any(x["id"] == identifier for x in data["decisions"]):
            continue
        if len(data["decisions"]) >= MAX_DECISIONS:
            break
        data["decisions"].append({
            "id": identifier, "text": message, "status": "PROPOSED",
            "sourceUrl": url, "impact": "", "origin": "AI_TIMELINE_PROPOSAL",
            "sourceDate": str(item.get("date") or "")[:60],
            "createdAt": utc_now(), "updatedAt": utc_now(),
            "supersedes": None,
        })
        _event(data, identifier, None, "PROPOSED", "Candidate from retrieved timeline, human review required.", "AI_PROPOSAL")
    write_json(decision_path(root, key), data, 2 * 1024 * 1024)
    return data


def apply_decision(root, key, *, action, identifier=None, text="", source_url="", impact="", reason=""):
    task_in_scope(root, key)
    data = read_decisions(root, key)
    if action not in ("propose", "confirm", "dispute", "supersede"):
        raise ValueError("Unknown decision action.")
    reason = safe_text(reason, 1000, required=False)
    impact = safe_text(impact, 1500, required=False)
    existing = {x["id"]: x for x in data["decisions"]}
    current = existing.get(identifier)
    if action != "propose" and (not isinstance(identifier, str) or not ID.fullmatch(identifier) or not current):
        raise ValueError("Existing decision ID required.")
    if action in ("propose", "supersede"):
        text = safe_text(text, 1500)
        source_url = source_link(source_url)
        if len(data["decisions"]) >= MAX_DECISIONS:
            raise ValueError("Decision capacity reached.")
        if action == "supersede" and current["status"] != "CONFIRMED":
            raise ValueError("Only confirmed decisions can be superseded.")
        new_id = _new_id(key, "HUMAN:" + source_url, text)
        if new_id in existing:
            raise ValueError("The same manual decision already exists.")
        updated = {
            "id": new_id, "text": text, "sourceUrl": source_url,
            "status": "CONFIRMED" if action == "supersede" else "PROPOSED",
            "impact": impact, "origin": "HUMAN",
            "sourceDate": "", "createdAt": utc_now(),
            "updatedAt": utc_now(),
            "supersedes": identifier if action == "supersede" else None,
        }
        # Never change existing history if the append cannot fit.
        if len(data["events"]) + (2 if action == "supersede" else 1) > MAX_EVENTS:
            raise ValueError("Decision event capacity reached.")
        data["decisions"].append(updated)
        _event(data, new_id, None, updated["status"],
               reason or ("Replaces " + identifier if action == "supersede" else "Human proposal"), "HUMAN")
        if action == "supersede":
            current["status"] = "SUPERSEDED"
            current["updatedAt"] = utc_now()
            current["supersededBy"] = new_id
            _event(data, identifier, "CONFIRMED", "SUPERSEDED", reason or "Replaced by " + new_id, "HUMAN")
    elif action == "confirm":
        if current["status"] != "PROPOSED":
            raise ValueError("Only proposed decisions can be confirmed.")
        url = source_link(source_url or current.get("sourceUrl", ""))
        # A human approves an interpretation; URL is a reference, not
        # machine-verified semantic evidence. Preserve the original source.
        current["sourceUrl"] = url
        current["status"] = "CONFIRMED"
        current["impact"] = impact or current.get("impact", "")
        current["updatedAt"] = utc_now()
        _event(data, identifier, "PROPOSED", "CONFIRMED", reason or "Approved by analyst", "HUMAN")
    else:
        if current["status"] not in ("PROPOSED", "CONFIRMED"):
            raise ValueError("Only open/confirmed decisions can be disputed.")
        if not reason:
            raise ValueError("Dispute requires a reason.")
        old = current["status"]
        current["status"] = "DISPUTED"
        current["updatedAt"] = utc_now()
        _event(data, identifier, old, "DISPUTED", reason, "HUMAN")
    data["updatedAt"] = utc_now()
    write_json(decision_path(root, key), data, 2 * 1024 * 1024)
    return data
