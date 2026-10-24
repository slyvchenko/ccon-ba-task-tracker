"""Human-approved BA task descriptions and safe local revision comparisons.

Never edits Jira. An AI refresh cannot replace the stored approved reference:
only an explicit analyst action can approve the new description.
"""
import difflib
import hashlib
import re
from pathlib import Path

from app_config import utc_now
from ba_questions import task_in_scope
from desk_store import Desk
from storage import read_json, write_json

MAX_DESCRIPTION = 15000


def file_path(root, key):
    if not re.fullmatch(r"CCON-\d+", str(key)):
        raise ValueError("Invalid Jira task key.")
    return Path(root) / "data/approved_descriptions" / (key + ".json")


def current(root, key):
    task_in_scope(root, key)
    task = next((x for x in Desk(root).view()["tasks"] if x["key"] == key), None)
    if not task or not task.get("active"):
        raise ValueError("Current active personal Jira task required.")
    analysis = task.get("analysis") or {}
    text = analysis.get("standardDescription") or ""
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_DESCRIPTION:
        raise ValueError("Valid ready BA description required.")
    if analysis.get("stale") or (
            analysis.get("contextFingerprint") != task.get("contextFingerprint")):
        raise ValueError("Jira task description analysis is stale.")
    return task, text


def describe(root, key):
    task_in_scope(root, key)
    source = read_json(file_path(root, key), None)
    task = next((x for x in Desk(root).view()["tasks"] if x["key"] == key), None)
    candidate = ((task or {}).get("analysis") or {}).get("standardDescription") or ""
    if not isinstance(source, dict):
        return {"key": key, "state": "NO_APPROVED_REFERENCE",
                "hasApproved": False, "changed": None, "diff": ""}
    before = source.get("text")
    if not isinstance(before, str):
        raise ValueError("Invalid approved description storage.")
    changed = before != candidate
    delta = "".join(difflib.unified_diff(
        before.splitlines(keepends=True), str(candidate).splitlines(keepends=True),
        fromfile="human_approved", tofile="current_AI_draft"))
    stale_source = source.get("contextFingerprint") != (task or {}).get("contextFingerprint")
    return {
        "key": key, "state": ("SOURCE_CHANGED" if stale_source else
                             "NEW_DRAFT_DIFFERS" if changed else "UNCHANGED"),
        "hasApproved": True, "changed": changed,
        "approvedAt": source.get("approvedAt"),
        "sourceFingerprintChanged": bool(stale_source),
        "approvedSha256": source.get("sha256"), "diff": delta[:6000],
        "reminderUk": ("Перевір усі зміни проти нової Jira вимоги, "
                       "перш ніж схвалювати опис. AI не може схвалити його сам."),
    }


def approve(root, key):
    task, text = current(root, key)
    prior = read_json(file_path(root, key), None)
    data = {
        "key": key, "text": text, "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "contextFingerprint": task["contextFingerprint"],
        "approvedAt": utc_now(), "approvalMode": "EXPLICIT_ANALYST_ACTION",
        "previousSha256": prior.get("sha256") if isinstance(prior, dict) else None,
    }
    write_json(file_path(root, key), data, 35000)
    return describe(root, key)
