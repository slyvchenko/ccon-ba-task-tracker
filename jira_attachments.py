"""Local read-only Jira attachment handoff and bounded structural inspection.

The authenticated local browser downloads files; Python never requests Jira
attachment URLs or credentials. Only source-independent structural metadata is
saved locally. PDF contents, ZIP entry values and wiki pages are NOT verified.
"""
import argparse
import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from zipfile import ZipFile, BadZipFile

from app_config import ROOT, utc_now
from storage import read_json, write_json
from jira_sync import JIRA_URL

KEY_RE = re.compile(r"^CCON-\d+$")
ID_RE = re.compile(r"^\d{1,20}$")
ALLOWED = {".json", ".xml", ".zip", ".pdf"}
MAX_FILE = 8 * 1024 * 1024
MAX_UNPACKED = 16 * 1024 * 1024
MAX_ENTRIES = 60


def _safe_field(value):
    if not isinstance(value, str):
        return None
    # Structural names only, not any raw payload values or arbitrary ZIP names.
    return value if re.fullmatch(r"[\w.:-]{1,90}", value) else None


def _metadata(root, key):
    if not isinstance(key, str) or not KEY_RE.fullmatch(key):
        raise ValueError("Invalid Jira issue key.")
    context = read_json(Path(root) / "data/jira_context.json", {})
    if context.get("complete") is not True:
        raise ValueError("Complete Jira sync required.")
    issue = (context.get("issues") or {}).get(key)
    if not isinstance(issue, dict) or not issue.get("fingerprint"):
        raise ValueError("Current personal Jira issue context required.")
    return issue


def _attachment_spec(item):
    ident = str(item.get("id", ""))
    if not ID_RE.fullmatch(ident):
        return None
    suffix = Path(str(item.get("filename", ""))).suffix.lower()
    if suffix not in ALLOWED:
        return None
    return ident, suffix


def attachment_path(root, key, ident, suffix):
    if not KEY_RE.fullmatch(str(key)) or not ID_RE.fullmatch(str(ident)) or suffix not in ALLOWED:
        raise ValueError("Invalid issue, attachment id or extension.")
    return Path(root) / "downloads/jira" / key / (ident + suffix)


def _download_url(item):
    url = item.get("content")
    if not isinstance(url, str) or len(url) > 2048:
        return None
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.netloc != "aerticket.atlassian.net"
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            return None
        if not (parsed.path.startswith("/rest/api/3/attachment/content/")
                or parsed.path.startswith("/secure/attachment/")):
            return None
        return url
    except ValueError:
        return None


def prepare(root=ROOT, key=None):
    root = Path(root)
    context = read_json(root / "data/jira_context.json", {})
    if context.get("complete") is not True:
        raise ValueError("Complete Jira sync required.")
    issues = context.get("issues") or {}
    keys = [key] if key else sorted(issues)
    jobs = []
    for issue_key in keys:
        issue = _metadata(root, issue_key)
        for item in issue.get("attachments") or []:
            if not isinstance(item, dict):
                continue
            spec = _attachment_spec(item)
            if spec is None:
                continue
            ident, suffix = spec
            target = attachment_path(root, issue_key, ident, suffix)
            jobs.append({
                "issueKey": issue_key, "attachmentId": ident,
                "extension": suffix, "contextFingerprint": issue["fingerprint"],
                "downloadUrl": _download_url(item),
                "saveAs": str(target),
                "state": "BROWSER_DOWNLOAD_REQUIRED",
            })
    if len(jobs) > 200:
        raise ValueError("Attachment handoff exceeds the safe job limit.")
    result = {"generatedAt": utc_now(), "readOnlyBrowser": True,
              "status": "BROWSER_ACTIONS_PENDING", "jobs": jobs}
    write_json(root / "data/jira_attachment_handoff.json", result, 1024 * 1024)
    return result


def _shape(payload, suffix):
    if suffix == ".json":
        try:
            obj = json.loads(payload)
        except (UnicodeDecodeError, ValueError):
            raise ValueError("INVALID_JSON") from None
        return {"type": "JSON", "rootType": type(obj).__name__,
                "rootFields": sorted(filter(None, (
                    _safe_field(k) for k in obj.keys())))[:60] if isinstance(obj, dict) else [],
                "arrayItems": min(len(obj), 1000000) if isinstance(obj, list) else None}
    if suffix == ".xml":
        if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", payload, re.I):
            raise ValueError("XML_DTD_OR_ENTITY_FORBIDDEN")
        try:
            root = ET.fromstring(payload)
        except ET.ParseError:
            raise ValueError("INVALID_XML") from None
        nodes = list(root.iter())
        if len(nodes) > 10000:
            raise ValueError("XML_NODE_LIMIT")
        tags = Counter(filter(None, (_safe_field(str(x.tag)) for x in nodes)))
        return {"type": "XML", "rootTag": _safe_field(str(root.tag)),
                "nodeCount": len(nodes), "tagCounts": dict(tags.most_common(40))}
    raise ValueError("UNSUPPORTED_STRUCTURE")


def _zip_shape(payload):
    rows, warnings = [], []
    try:
        with ZipFile(io.BytesIO(payload)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ENTRIES:
                raise ValueError("ZIP_ENTRY_LIMIT")
            total = 0
            for info in entries:
                if info.is_dir():
                    continue
                name = info.filename.replace("\\", "/")
                parts = PurePosixPath(name)
                if (name.startswith("/") or any(part in ("..", ".") for part in parts.parts)
                        or ":" in name or not parts.parts):
                    raise ValueError("UNSAFE_ZIP_PATH")
                if info.flag_bits & 1 or ((info.external_attr >> 16) & 0o170000) == 0o120000:
                    raise ValueError("ZIP_ENCRYPTED_OR_SYMLINK")
                total += info.file_size
                if (info.file_size > MAX_FILE or total > MAX_UNPACKED
                        or (info.compress_size and info.file_size / info.compress_size > 100)):
                    raise ValueError("ZIP_UNPACKED_LIMIT")
                suffix = Path(name).suffix.lower()
                if suffix not in (".json", ".xml"):
                    warnings.append("UNSUPPORTED_ZIP_ENTRY_NOT_READ")
                    continue
                with archive.open(info) as member:
                    data = member.read(MAX_FILE + 1)
                if len(data) > MAX_FILE:
                    raise ValueError("ZIP_MEMBER_LIMIT")
                rows.append({"extension": suffix, "shape": _shape(data, suffix)})
                if len(rows) >= 30:
                    warnings.append("ZIP_SHAPE_SAMPLE_CAPPED")
                    break
    except (BadZipFile, RuntimeError, EOFError, OSError):
        raise ValueError("INVALID_ZIP") from None
    return {"type": "ZIP", "parsedEntries": rows, "warnings": sorted(set(warnings))}


def inspect_bytes(payload, suffix):
    if len(payload) > MAX_FILE:
        raise ValueError("ATTACHMENT_TOO_LARGE")
    if suffix == ".pdf":
        if not payload.startswith(b"%PDF-"):
            raise ValueError("NOT_PDF")
        return {"type": "PDF", "status": "PDF_TEXT_NOT_EXTRACTED", "shape": None}
    if suffix == ".zip":
        if not payload.startswith(b"PK\x03\x04"):
            raise ValueError("NOT_ZIP")
        return {"type": "ZIP", "status": "STRUCTURE_ONLY", "shape": _zip_shape(payload)}
    if suffix not in (".json", ".xml"):
        raise ValueError("UNSUPPORTED_EXTENSION")
    return {"type": suffix.lstrip(".").upper(), "status": "STRUCTURE_ONLY",
            "shape": _shape(payload, suffix)}


def process(root=ROOT, key=None):
    root = Path(root)
    plan = read_json(root / "data/jira_attachment_handoff.json", {})
    if not isinstance(plan, dict) or not isinstance(plan.get("jobs"), list):
        raise ValueError("Run jira_attachments.py prepare first.")
    rows = []
    for job in plan["jobs"]:
        issue_key = job["issueKey"]
        if key and issue_key != key:
            continue
        ident, suffix = job["attachmentId"], job["extension"]
        issue = _metadata(root, issue_key)
        if issue["fingerprint"] != job["contextFingerprint"]:
            rows.append({"issueKey": issue_key, "attachmentId": ident, "state": "STALE"})
            continue
        expected = {str(x.get("id")): x for x in issue.get("attachments") or []
                    if isinstance(x, dict)}
        if ident not in expected or _attachment_spec(expected[ident]) != (ident, suffix):
            rows.append({"issueKey": issue_key, "attachmentId": ident, "state": "STALE"})
            continue
        target = attachment_path(root, issue_key, ident, suffix)
        if not target.is_file() or target.is_symlink():
            rows.append({"issueKey": issue_key, "attachmentId": ident, "state": "PENDING"})
            continue
        try:
            if target.stat().st_size > MAX_FILE:
                raise ValueError("ATTACHMENT_TOO_LARGE")
            payload = target.read_bytes()
            metadata_size = expected[ident].get("size")
            if type(metadata_size) is int and metadata_size >= 0 and metadata_size != len(payload):
                raise ValueError("JIRA_METADATA_SIZE_MISMATCH")
            result = inspect_bytes(payload, suffix)
            manifest = {
                "issueKey": issue_key, "attachmentId": ident,
                "contextFingerprint": issue["fingerprint"],
                "sourceSha256": hashlib.sha256(payload).hexdigest(),
                "status": result["status"], "format": result["type"],
                "shape": result["shape"], "inspectedAt": utc_now(),
                "limitations": ["STRUCTURE_IS_NOT_VALUE_MAPPING_OR_BUSINESS_PROOF"],
            }
            write_json(root / "data/attachment_evidence" / issue_key / (ident + ".json"),
                       manifest, 250000)
            rows.append({"issueKey": issue_key, "attachmentId": ident,
                         "state": result["status"]})
        except (ValueError, OSError) as error:
            rows.append({"issueKey": issue_key, "attachmentId": ident,
                         "state": "FAILED", "reasonCode": str(error)
                         if str(error) in ("ATTACHMENT_TOO_LARGE", "JIRA_METADATA_SIZE_MISMATCH",
                                          "INVALID_JSON", "INVALID_XML", "INVALID_ZIP",
                                          "ZIP_ENTRY_LIMIT", "UNSAFE_ZIP_PATH",
                                          "ZIP_ENCRYPTED_OR_SYMLINK", "ZIP_UNPACKED_LIMIT",
                                          "ZIP_MEMBER_LIMIT", "XML_DTD_OR_ENTITY_FORBIDDEN",
                                          "XML_NODE_LIMIT", "NOT_PDF", "NOT_ZIP")
                         else "ATTACHMENT_INSPECTION_FAILED"})
    return {"results": rows, "processed": len(rows)}


def evidence_for_model(root, key, issue):
    """Only current Jira-bound local structural metadata; never raw contents."""
    if not KEY_RE.fullmatch(str(key)):
        return []
    allowed = {str(x["id"]): _attachment_spec(x) for x in issue.get("attachments") or []
               if isinstance(x, dict) and ID_RE.fullmatch(str(x.get("id", "")))
               and _attachment_spec(x) is not None}
    reports = []
    for ident in sorted(allowed)[:30]:
        item = read_json(Path(root) / "data/attachment_evidence" / key / (ident + ".json"), None)
        if (not isinstance(item, dict) or item.get("issueKey") != key
                or item.get("attachmentId") != ident
                or item.get("contextFingerprint") != issue.get("fingerprint")
                or item.get("status") not in ("STRUCTURE_ONLY", "PDF_TEXT_NOT_EXTRACTED")):
            continue
        # Re-check the exact local bytes: stale or tampered manifests are never
        # represented as current read evidence to the model.
        target = attachment_path(root, key, ident, allowed[ident][1])
        if not target.is_file() or target.is_symlink() or target.stat().st_size > MAX_FILE:
            continue
        if hashlib.sha256(target.read_bytes()).hexdigest() != item.get("sourceSha256"):
            continue
        reports.append({
            "attachmentId": ident, "sourceSha256": item.get("sourceSha256"),
            "status": item["status"], "format": item.get("format"),
            "shape": item.get("shape"), "limitations": item.get("limitations"),
        })
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "process"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--issue", default=None)
    args = parser.parse_args()
    outcome = prepare(args.root, args.issue) if args.action == "prepare" else process(args.root, args.issue)
    print(json.dumps(outcome, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
