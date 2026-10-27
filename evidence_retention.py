"""Conservative local evidence retention for immutable CCON log versions.

No deletion occurs without --apply and an explicit confirmation string.
Current index-referenced versions are always pinned. Backups, Jira state,
generated supplier-only attachments in use, and other folders are untouched.
Corporate raw ZIP contents never appear in the audit output.
"""
import argparse
import hashlib
import json
import re
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path

from app_config import ROOT, utc_now
from pipeline_lock import pipeline_lock
from storage import inside, read_json, write_json
from supplier_logs import logs_root

KEY = re.compile(r"CCON-\d+\Z")
FLOW = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
VERSION = re.compile(r"[0-9a-f]{12}-[0-9a-f]{8}\Z")
CONFIRMATION = "DELETE_UNREFERENCED_LOG_VERSIONS"
DEFAULT_RETENTION_DAYS = 30
DEFAULT_QUOTA_MB = 2048


def _index_pins(directory):
    index_file = directory / "index.json"
    if not index_file.exists() or index_file.is_symlink():
        raise ValueError("Log index missing or unsafe; no cleanup allowed.")
    index = read_json(index_file, None)
    if not isinstance(index, dict):
        raise ValueError("Invalid log index; no cleanup allowed.")
    pinned = set()
    for key, record in index.items():
        if not isinstance(key, str) or not re.fullmatch(
                r"CCON-\d+/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", key
        ) or not isinstance(record, dict):
            raise ValueError("Malformed index record; no cleanup allowed.")
        prefix = key.split("/")
        for field in ("archiveRelativePath", "factsRelativePath"):
            name = record.get(field)
            if not isinstance(name, str) or not name:
                raise ValueError("Incomplete log index pointer; no cleanup allowed.")
            path = inside(directory, name)
            relative = path.relative_to(directory)
            if (len(relative.parts) < 4 or list(relative.parts[:2]) != prefix or
                    not VERSION.fullmatch(relative.parts[2])):
                raise ValueError("Log index path has invalid scope; no cleanup allowed.")
            pinned.add(tuple(relative.parts[:3]))
    return pinned


def _directory_info(root, version_dir):
    total, latest, file_count = 0, 0.0, 0
    for path in version_dir.rglob("*"):
        if path.is_symlink():
            raise ValueError("Symlink inside log version; no cleanup allowed.")
        info = path.lstat()
        if stat.S_ISREG(info.st_mode):
            total += info.st_size
            latest = max(latest, info.st_mtime)
            file_count += 1
        elif not stat.S_ISDIR(info.st_mode):
            raise ValueError("Special file inside log version; no cleanup allowed.")
    latest = max(latest, version_dir.stat().st_mtime)
    relative = version_dir.relative_to(root)
    return {"path": version_dir, "relative": relative,
            "id": hashlib.sha256(str(relative).encode()).hexdigest()[:16],
            "bytes": total, "latest": latest, "fileCount": file_count}


def maintenance(root=ROOT, *, retention_days=DEFAULT_RETENTION_DAYS,
                quota_mb=DEFAULT_QUOTA_MB, apply=False, confirm=None, now=None):
    """Dry-run by default. Apply only verified, unreferenced version directories."""
    if type(retention_days) is not int or not 1 <= retention_days <= 3650:
        raise ValueError("retention_days must be between 1 and 3650.")
    if type(quota_mb) is not int or not 1 <= quota_mb <= 1048576:
        raise ValueError("quota_mb must be a positive integer.")
    if apply and confirm != CONFIRMATION:
        raise ValueError("Explicit cleanup confirmation is required.")
    # The supplier helper resolves the log path, which can conceal a symlink
    # pointing to another folder inside the same workspace. Reject links
    # BEFORE resolving paths or deleting any log version (review #22).
    requested_root = Path(root)
    if any(part.is_symlink() for part in (requested_root, *requested_root.parents)):
        raise ValueError("Symlink workspace root; no cleanup allowed.")
    root = requested_root.resolve()
    if now is None:
        now_ts = datetime.now(timezone.utc).timestamp()
    elif isinstance(now, datetime) and now.tzinfo is not None:
        now_ts = now.timestamp()
    else:
        raise ValueError("Clock must be timezone aware.")
    with pipeline_lock(root):
        config = read_json(root / "log_config.json", {})
        if not isinstance(config, dict):
            raise ValueError("Invalid log configuration; no cleanup allowed.")
        configured = config.get("logsDir")
        raw_directory = (Path(configured) if isinstance(configured, str) and configured
                         else root / "logs")
        if any(part.is_symlink() for part in (raw_directory, *raw_directory.parents)):
            raise ValueError("Symlink log root or ancestor; no cleanup allowed.")
        directory = logs_root(root)
        if not directory.is_relative_to(root):
            raise ValueError("External log root requires separate approved retention policy.")
        if not directory.exists():
            return {"mode": "APPLIED" if apply else "DRY_RUN",
                    "candidates": 0, "removed": 0, "reclaimableBytes": 0,
                    "quotaRemainingBytes": quota_mb * 1024 * 1024,
                    "blockedByPinnedVersions": False, "decisions": []}
        if directory.is_symlink():
            raise ValueError("Symlink log root; no cleanup allowed.")
        pins = _index_pins(directory)
        versions = []
        for task in sorted(directory.iterdir()):
            if task.is_symlink():
                raise ValueError("Symlink task directory; no cleanup allowed.")
            if not task.is_dir() or not KEY.fullmatch(task.name):
                continue
            for flow in sorted(task.iterdir()):
                if flow.is_symlink():
                    raise ValueError("Symlink flow directory; no cleanup allowed.")
                if not flow.is_dir() or not FLOW.fullmatch(flow.name):
                    continue
                for candidate in sorted(flow.iterdir()):
                    if candidate.is_symlink():
                        raise ValueError("Symlink version directory; no cleanup allowed.")
                    if not candidate.is_dir() or not VERSION.fullmatch(candidate.name):
                        continue
                    detail = _directory_info(directory, candidate)
                    detail["pinned"] = (task.name, flow.name, candidate.name) in pins
                    versions.append(detail)

        used = sum(v["bytes"] for v in versions)
        quota = quota_mb * 1024 * 1024
        cutoff = now_ts - retention_days * 86400
        removable = sorted((v for v in versions if not v["pinned"]),
                           key=lambda x: (x["latest"], str(x["relative"])))
        chosen = []
        for entry in removable:
            if entry["latest"] <= cutoff or used > quota:
                chosen.append(entry)
                used -= entry["bytes"]
        decisions = [{"id": v["id"], "bytes": v["bytes"],
                      "reason": "EXPIRED" if v["latest"] <= cutoff else "QUOTA",
                      "pinned": False} for v in chosen]
        if apply:
            for entry in chosen:
                # Index and inode integrity are checked under the same log pipeline lock.
                # rmtree does not traverse symlink children (preflight rejects them).
                shutil.rmtree(entry["path"])
        result = {
            "mode": "APPLIED" if apply else "DRY_RUN",
            "retentionDays": retention_days, "quotaMB": quota_mb,
            "versionCount": len(versions),
            "pinnedVersionCount": sum(x["pinned"] for x in versions),
            "candidates": len(chosen),
            "removed": len(chosen) if apply else 0,
            "reclaimableBytes": sum(x["bytes"] for x in chosen),
            "quotaRemainingBytes": max(0, quota - used),
            "blockedByPinnedVersions": used > quota,
            "decisions": decisions[:500],
        }
        if apply:
            # Only decisions/ids and counts. Never persist raw files or passenger data.
            write_json(root / "data/evidence_retention_last.json",
                       {**result, "completedAt": utc_now()}, 256 * 1024)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)
    parser.add_argument("--quota-mb", type=int, default=DEFAULT_QUOTA_MB)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default=None)
    args = parser.parse_args()
    print(json.dumps(maintenance(args.root, retention_days=args.retention_days,
                                 quota_mb=args.quota_mb, apply=args.apply,
                                 confirm=args.confirm), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
