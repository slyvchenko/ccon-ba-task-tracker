"""Ready but NEVER automatically sent email for every BA task.

A draft is not a decision to email. When evidence is incomplete, the optional
draft states the uncertainty. The supplier attachment claim is added only
when a verified supplier-only ZIP is currently available.
"""
import re
from pathlib import Path

from email_rules import normalize_draft
from storage import read_json
from supplier_logs import logs_root
from log_attachments import log_catalog
from desk_store import Desk


def supplier_zip_ready(root, key):
    """Valid, current, issue-scoped supplier ZIP from the catalog."""
    try:
        data = log_catalog(Desk(root), key)
        return any(not item.get("stale") and not item.get("needsReview")
                   for item in data.get("items", []))
    except (OSError, KeyError, TypeError, ValueError):
        return False


def _english_description(analysis):
    value = (analysis.get("standardDescription") or "").strip()
    if value and len(value) <= 3000:
        return value
    return ""


def make_ready_draft(key, analysis, method=None, attachment_ready=False):
    """Preserve agent-authored text and user edits; supply factual fallback."""
    if not re.fullmatch(r"CCON-\d+", key):
        raise ValueError("Invalid BA task key.")
    original = analysis.get("emailDraft") or {}
    if not isinstance(original, dict):
        raise ValueError("Email draft must be an object.")
    draft = {field: original.get(field, "") for field in ("to", "subject", "body")}
    if not all(isinstance(x, str) for x in draft.values()):
        raise ValueError("Email draft fields must be text.")
    if not draft["subject"].strip():
        draft["subject"] = "Clarification regarding issue " + key
    if not draft["body"].strip():
        statement = _english_description(analysis)
        questions = analysis.get("missingInfo") or []
        # AI should translate/summarize Ukrainian missingInfo in its authored
        # mail. A deterministic fallback NEVER copies untranslated internal
        # comments into an English supplier letter.
        if statement:
            body = "We are reviewing the following behavior:\n" + statement
            if questions:
                body += "\n\nCould you please confirm the unresolved requirements or exceptions?"
            else:
                body += "\n\nPlease let us know if your understanding differs."
        else:
            body = ("We are reviewing issue " + key + ". "
                    "Could you please confirm the expected behavior and provide "
                    "a relevant example if available?")
        draft["body"] = body
    result = normalize_draft(key, draft, method)
    if not attachment_ready:
        # normalize_draft historically states logs are attached on all
        # drafts, even before any CCON download. Remove that false statement.
        result["body"] = re.sub(
            r"(?m)^\s*Logs are attached for your reference\.\s*\n?",
            "", result["body"]
        )
        result["body"] = re.sub(r"\n{3,}", "\n\n", result["body"]).strip()
    return result
