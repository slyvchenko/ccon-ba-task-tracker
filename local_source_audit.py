"""Only locally verified source text may support a Jira claim.

This module opens no remote URLs, persists no payload or excerpts, and never
turns text occurrence into semantic proof. Model gets only bounded metadata.
"""
import hashlib
import re
from pathlib import Path

from jira_attachments import _attachment_spec, _download_url, attachment_path, evidence_path, MAX_FILE
from local_document_text import extract_text
from confluence_local import current_sources as wiki_sources, linked_pages
from storage import inside, read_json

ASSIGNMENT = re.compile(
    r"\b([A-Za-z][A-Za-z0-9]{1,60}Code)\s*(?:==|=|:)\s*[\"']?([A-Z][A-Z0-9_]{1,45}|[a-z][a-z0-9_]{1,45})\b"
)


def _attachment_sources(root, key, issue):
    sources, metadata = {}, []
    for attachment in (issue.get("attachments") or [])[:30]:
        if not isinstance(attachment, dict):
            continue
        extension = Path(str(attachment.get("filename", ""))).suffix.lstrip(".").upper()
        status = {"attachmentId": str(attachment.get("id", "")), "format": extension,
                  "state": "FORMAT_REQUIRES_MANUAL_REVIEW"}
        metadata.append(status)
        spec = _attachment_spec(attachment)
        if spec is None:
            continue
        ident, suffix = spec
        status["state"] = "NOT_DOWNLOADED"
        original = _download_url(attachment)
        if not original:
            status["state"] = "DOWNLOAD_UNAVAILABLE"
            status["reasonCode"] = "ATTACHMENT_LINK_INVALID"
            continue
        try:
            record = read_json(evidence_path(Path(root), key, ident), {})
        except (ValueError, OSError):
            continue
        if (not isinstance(record, dict) or record.get("issueKey") != key
                or record.get("attachmentId") != ident
                or record.get("contextFingerprint") != issue.get("fingerprint")):
            continue
        if record.get("status") in ("DOWNLOAD_UNAVAILABLE", "INSPECTION_UNAVAILABLE"):
            status.update(state=record["status"], reasonCode=record.get("reasonCode", ""))
            continue
        try:
            target = attachment_path(root, key, ident, suffix)
            inside(Path(root), target.relative_to(root))
            if not target.is_file() or target.is_symlink() or target.stat().st_size > MAX_FILE:
                continue
            raw = target.read_bytes()
        except (ValueError, OSError):
            continue
        if hashlib.sha256(raw).hexdigest() != record.get("sourceSha256"):
            status["state"] = "LOCAL_FILE_MISMATCH"
            continue
        state, parsed, details = extract_text(raw, suffix)
        status["state"] = state
        if state != "LOCAL_TEXT_EXTRACTED":
            continue
        sources[original] = parsed
        status.update(state="LOCAL_TEXT_VERIFIED", sourceSha256=record["sourceSha256"])
    return sources, metadata


def _value_variants(source_map):
    """Potential value differences, not contradictions or mapping defects.

    Do not return compared raw enum values or potentially sensitive quotes.
    """
    found = {}
    for url, content in source_map.items():
        for field, value in ASSIGNMENT.findall(content[:100000])[:150]:
            found.setdefault(field, {}).setdefault(value, set()).add(url)
    return [{"field": field, "state": "POTENTIAL_DIFFERENT_ENUM_VALUE_REVIEW",
             "sourceCount": len(set.union(*values.values())),
             "limitation": "Different conditions or versions can legitimately use different values."}
            for field, values in sorted(found.items())
            if len(values) > 1 and len(set.union(*values.values())) > 1][:20]


def local_sources(root, key, issue, jira_source=None):
    """Return (verified local text registry, privacy-bounded audit metadata)."""
    attached, attached_meta = _attachment_sources(root, key, issue)
    pages, page_meta = wiki_sources(root, key, issue)
    evidence = {**attached, **pages}
    scope = len([x for x in issue.get("attachments") or [] if isinstance(x, dict)
                 and _attachment_spec(x)]) + len(linked_pages(issue))
    compared = dict(evidence)
    if jira_source is not None:
        compared["__jira_only__"] = jira_source
    audit = {"eligibleLinkedSourceCount": scope,
             "verifiedLocalSourceCount": len(evidence),
             "notVerifiedCount": max(0, scope - len(evidence)),
             "attachments": attached_meta[:30], "wikiPages": page_meta[:40],
             "variantCandidates": _value_variants(compared),
             "unreadSourceStatus": "NOT_READ_IS_NOT_PROOF",
             "sourceConfidence": "TEXT_OCCURRENCE_NOT_BUSINESS_TRUTH",
             "browserAccess": "NOT_PERFORMED_BY_PYTHON"}
    return evidence, audit
