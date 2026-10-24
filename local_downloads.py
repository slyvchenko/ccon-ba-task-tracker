"""Local browser -> ZIP -> supplier-only attachment handoff without browser credentials.

Codex opens URLs from the evidence plan in the ALREADY AUTHENTICATED browser,
saves each full ZIP to the assigned local path. Python never makes the HTTP
request, obtains cookies, or infers cconFlowId from a random filename.
"""
import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from app_config import ROOT, utc_now
from storage import read_json, write_json
from supplier_logs import make_plan, ingest

KEY = re.compile(r"^CCON-\d+$")
UUID = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
MAX_SIZE = 100 * 1024 * 1024


def inbox(root):
    return Path(root) / "downloads" / "ccon"


def download_path(root, key, flow):
    if not isinstance(key, str) or not KEY.fullmatch(key):
        raise ValueError("Invalid Jira issue key.")
    if not isinstance(flow, str) or not UUID.fullmatch(flow):
        raise ValueError("Invalid flow ID.")
    return inbox(root) / key / (flow + ".zip")


def status_path(root):
    return Path(root) / "data/download_handoff_status.json"


def record_status(root, key, flow, fingerprint, state, reason):
    if state not in ("READY", "FAILED", "PENDING", "STALE", "NEEDS_REVIEW"):
        raise ValueError("Invalid download state.")
    current = read_json(status_path(root), {})
    if not isinstance(current, dict):
        current = {}
    current[key + "/" + flow] = {
        "state": state, "reasonCode": reason, "contextFingerprint": fingerprint,
        "updatedAt": utc_now(),
    }
    write_json(status_path(root), current, 1024 * 1024)


def prepare(root=ROOT, issue=None):
    root = Path(root)
    plan = make_plan(root, issue_key=issue, mode="evidence")
    jobs = []
    for job in plan["jobs"]:
        key, flow = job["key"], job["flowId"]
        path = download_path(root, key, flow)
        path.parent.mkdir(parents=True, exist_ok=True)
        jobs.append({
            "issueKey": key, "flowId": flow,
            "supplier": job["supplier"]["name"],
            "sourceUrl": job["sourceUrl"],
            "downloadUrl": job["downloadUrl"],
            "saveAs": str(path), "cached": job["cached"],
            "contextFingerprint": job["contextFingerprint"],
            "browserInstructionsUk": (
                "В авторизованому браузері відкрий downloadUrl і збережи "
                "саме отриманий CCON ZIP у saveAs. Не експортуй cookies/token. "
                "Не плутай архіви між cconFlowId.")
        })
    result = {
        "generatedAt": plan["generatedAt"], "readOnlyBrowser": True,
        "status": "BROWSER_ACTIONS_PENDING",
        "workflow": "OPEN_AUTHENTICATED_BROWSER_THEN_SAVE_ZIP_THEN_PROCESS",
        "jobs": jobs, "skipped": plan["skipped"],
    }
    write_json(root / "data/browser_handoff.json", result, 3 * 1024 * 1024)
    return result


def _fresh_download(path, plan_time):
    try:
        timestamp = datetime.fromisoformat(plan_time.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, AttributeError):
        return False
    return path.stat().st_mtime >= timestamp - 120


def process(root=ROOT, issue=None, strict=False):
    root = Path(root)
    plan = read_json(root / "data/log_plan.json", {})
    context = read_json(root / "data/jira_context.json", {})
    if not isinstance(plan, dict) or plan.get("mode") != "evidence":
        raise ValueError("Run local_downloads.py prepare before processing.")
    if context.get("complete") is not True:
        raise ValueError("Complete Jira sync required.")
    if issue and not KEY.fullmatch(issue):
        raise ValueError("Invalid issue key.")
    rows = []
    for job in plan.get("jobs", []):
        key, flow = job["key"], job["flowId"]
        if issue and key != issue:
            continue
        fingerprint = context.get("issues", {}).get(key, {}).get("fingerprint")
        if not fingerprint or fingerprint != job["contextFingerprint"]:
            state, reason = "STALE", "JIRA_CONTEXT_CHANGED"
        elif job.get("cached"):
            state, reason = "READY", "VERIFIED_SUPPLIER_ARCHIVE_CACHED"
        else:
            path = download_path(root, key, flow)
            if not path.is_file() or path.is_symlink():
                state, reason = "PENDING", "BROWSER_ZIP_NOT_SAVED"
            else:
                try:
                    if not _fresh_download(path, plan["generatedAt"]):
                        raise ValueError("OLD_DOWNLOAD")
                    if path.stat().st_size < 4 or path.stat().st_size > MAX_SIZE:
                        raise ValueError("INVALID_DOWNLOAD_SIZE")
                    with path.open("rb") as source:
                        if source.read(4) != b"PK\x03\x04":
                            raise ValueError("NOT_ZIP_SIGNIN_OR_ERROR_PAGE")
                    outcome = ingest(root, key, flow, path)
                    if outcome.get("evidencePrepared") is False:
                        state, reason = "NEEDS_REVIEW", "SUPPLIER_ZIP_READY_EVIDENCE_PARTIAL"
                    elif outcome.get("warnings"):
                        state, reason = "NEEDS_REVIEW", "SUPPLIER_ZIP_READY_WITH_WARNINGS"
                    else:
                        state, reason = "READY", "SUPPLIER_ONLY_ZIP_READY"
                except (ValueError, OSError, TypeError, KeyError) as exc:
                    state = "FAILED"
                    safe = str(exc)
                    reason = safe if safe in (
                        "OLD_DOWNLOAD", "INVALID_DOWNLOAD_SIZE",
                        "NOT_ZIP_SIGNIN_OR_ERROR_PAGE",
                    ) else "ZIP_INSPECTION_OR_CONTEXT_FAILED"
        record_status(root, key, flow, job["contextFingerprint"], state, reason)
        rows.append({"issueKey": key, "flowId": flow, "state": state, "reasonCode": reason})
        if strict and state in ("FAILED", "STALE"):
            raise ValueError(f"Log preparation {state}: {key}, {flow}, {reason}")
    return {"processed": len(rows), "results": rows,
            "pendingCount": sum(x["state"] == "PENDING" for x in rows),
            "failedCount": sum(x["state"] == "FAILED" for x in rows),
            "readyCount": sum(x["state"] == "READY" for x in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "process"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--issue", default=None)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = prepare(args.root, args.issue) if args.action == "prepare" else process(
        args.root, args.issue, args.strict
    )
    if args.action == "prepare":
        result = {"jobs": len(result["jobs"]),
                  "handoffFile": str(Path(args.root) / "data/browser_handoff.json"),
                  "skipped": result["skipped"]}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
