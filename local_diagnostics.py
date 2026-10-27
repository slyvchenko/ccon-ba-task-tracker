"""Local, opt-in, metadata-only diagnostics. NEVER read Jira, ZIP or log contents.

No background collection or upload. Consent is required for writing even the
small metadata ZIP; on Windows ACL cannot be proved by portable stdlib APIs.
"""
import argparse
import json
import os
import stat
import sys
import zipfile
from pathlib import Path

from app_config import ROOT, VERSION

CONFIRM = "EXPORT SANITIZED BA DIAGNOSTICS"
PRIVATE = (
    ("sqlite", "ba_state.db", "file"),
    ("wal", "ba_state.db-wal", "file"),
    ("shm", "ba_state.db-shm", "file"),
    ("inbox_dir", "inbox", "dir"),
    ("snapshot", "inbox/CCON_BA_Snapshot.json", "file"),
    ("data_dir", "data", "dir"),
    ("backups_dir", "backups", "dir"),
    ("downloads_dir", "downloads", "dir"),
    ("ccon_downloads_dir", "downloads/ccon", "dir"),
    ("logs_dir", "logs", "dir"),
)
ZIP_SCAN_LIMIT = 200


def _audit_path(path, kind):
    """lstat never follows a malicious symlink. Do not return path or mode."""
    try:
        details = path.lstat()
    except FileNotFoundError:
        return "ABSENT"
    except OSError:
        return "UNVERIFIED_READ_ERROR"
    if stat.S_ISLNK(details.st_mode):
        return "UNSAFE_SYMLINK"
    expected = stat.S_ISDIR if kind == "dir" else stat.S_ISREG
    if not expected(details.st_mode):
        return "UNSAFE_TYPE"
    # Never guess Windows DACL/SID/encryption from os.stat or icacls text,
    # which is localized and may contain user-specific names.
    if os.name == "nt":
        return "UNVERIFIED_WINDOWS_ACL"
    if details.st_uid != os.getuid():
        return "UNVERIFIED_OWNER"
    return ("UNSAFE_SHARED_MODE" if details.st_mode & 0o077
            else "OWNER_ONLY_MODE")


def _audit_bounded_path(root, relative, kind):
    """Avoid metadata reads through any symlinked private path ancestor."""
    parent = root
    for component in Path(relative).parts[:-1]:
        parent = parent / component
        status = _audit_path(parent, "dir")
        if status in ("UNSAFE_SYMLINK", "UNSAFE_TYPE", "UNVERIFIED_READ_ERROR"):
            return "UNSAFE_ANCESTOR"
        if status == "ABSENT":
            return "ABSENT"
    return _audit_path(root / relative, kind)


def _zip_permissions(root):
    """Bounded metadata-only traversal of known supplier ZIP handoff tree."""
    folder = root / "downloads" / "ccon"
    # lstat of a child alone misses a symlink in its parent. Never scan
    # outside the real workspace via downloads -> /external/ccon.
    parent_state = _audit_path(root / "downloads", "dir")
    state = (_audit_path(folder, "dir") if parent_state not in
             ("UNSAFE_SYMLINK", "UNSAFE_TYPE", "UNVERIFIED_READ_ERROR")
             else "UNSAFE_ANCESTOR")
    result = {"scope": "supplier_zip_handoff", "folder": state,
              "examined": 0, "complete": True, "statusCounts": {}}
    if state not in ("OWNER_ONLY_MODE", "UNSAFE_SHARED_MODE", "UNVERIFIED_WINDOWS_ACL"):
        return result
    try:
        # A symlinked issue directory is rejected, never traversed.
        for issue in folder.iterdir():
            if result["examined"] >= ZIP_SCAN_LIMIT:
                result["complete"] = False
                break
            result["examined"] += 1
            if issue.is_symlink():
                result["statusCounts"]["UNSAFE_SYMLINK"] = (
                    result["statusCounts"].get("UNSAFE_SYMLINK", 0) + 1)
                continue
            if not issue.is_dir():
                continue
            label = _audit_path(issue, "dir")
            result["statusCounts"][label] = result["statusCounts"].get(label, 0) + 1
            for child in issue.iterdir():
                if result["examined"] >= ZIP_SCAN_LIMIT:
                    result["complete"] = False
                    break
                result["examined"] += 1
                # Names and sizes are NEVER returned, including PNR/flow IDs.
                label = _audit_path(child, "file")
                result["statusCounts"][label] = result["statusCounts"].get(label, 0) + 1
    except OSError:
        result["complete"] = False
        result["statusCounts"]["UNVERIFIED_READ_ERROR"] = (
            result["statusCounts"].get("UNVERIFIED_READ_ERROR", 0) + 1)
    return result


def collect(root=ROOT):
    """Only fixed-key file metadata and mode checks. Zero content reads."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Local workspace must be an existing nonsymlink directory.")
    checks = {"workspace_dir": _audit_path(root, "dir")}
    checks.update({label: _audit_bounded_path(root, relative, kind)
                   for label, relative, kind in PRIVATE})
    zips = _zip_permissions(root)
    unsafe = {"UNSAFE_SYMLINK", "UNSAFE_TYPE", "UNSAFE_SHARED_MODE",
              "UNVERIFIED_READ_ERROR", "UNVERIFIED_OWNER", "UNSAFE_ANCESTOR"}
    statuses = list(checks.values()) + list(zips["statusCounts"])
    attention = bool(unsafe.intersection(statuses) or
                     "UNVERIFIED_WINDOWS_ACL" in statuses or
                     zips["folder"] in unsafe or
                     zips["folder"] == "UNVERIFIED_WINDOWS_ACL" or
                     not zips["complete"])
    # Even perfect UNIX file modes do NOT prove disk encryption. Windows DACL
    # is intentionally UNVERIFIED, not falsely reported as private.
    return {
        "schemaVersion": 1,
        "appVersion": VERSION,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "platformFamily": "windows" if os.name == "nt" else "posix",
        "contentPolicy": "METADATA_ONLY_NO_LOG_OR_SOURCE_READS",
        "accessChecks": checks,
        "supplierZipChecks": zips,
        "filesystemRiskObserved": attention,
        "windowsAclVerified": False,
        "encryptionVerified": False,
        "scopeLimits": ("Checks paths known to the local application, not every "
                        "nested data file or external download; does not assert "
                        "encryption, user group membership, or Windows DACL."),
        "externalSends": False,
    }


def export(root, output, confirm):
    if confirm != CONFIRM:
        raise ValueError("Explicit export confirmation required.")
    root = Path(root)
    destination = Path(output)
    # Both parents must exist before collection; no accidental directory tree.
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise ValueError("Export parent must be an existing nonsymlink directory.")
    canonical_root = root.resolve(strict=True)
    canonical_parent = destination.parent.resolve(strict=True)
    if canonical_parent == canonical_root or canonical_root in canonical_parent.parents:
        raise ValueError("Refusing diagnostic export inside the application workspace.")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Refusing to overwrite an existing diagnostic export.")
    data = collect(root)  # no raw logs, task rows, filenames or source bytes.
    # Exclusive creation never follows an existing file or symlink. POSIX mode
    # 0600 is requested; Windows inherits DACL, hence payload has no PII.
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("diagnostics.json",
                                 json.dumps(data, sort_keys=True, indent=2) + "\n")
                archive.writestr("README.txt",
                    "CCON BA Desk sanitized local diagnostic bundle.\n"
                    "Explicit consent only; not collected in the background.\n"
                    "No Jira data, PNR, REST bodies, credentials, ZIP, inbox,\n"
                    "logs, email, note, hostname, local path, or user identity.\n"
                    "Windows ACL and disk encryption are NOT verified.\n"
                    "Review metadata yourself before sharing.\n")
    except BaseException:
        # Prevent accidentally sharing a truncated ZIP after any exception.
        destination.unlink(missing_ok=True)
        raise
    return {"created": True, "containsSourceContent": False,
            "outsideWorkspace": True, "requiresReviewBeforeSharing": True}


class _PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes unrecognized tokens, possibly including
        # user names, filenames or PNR. Never include those in terminal logs.
        raise ValueError("Invalid sanitized diagnostics arguments.")


def main(argv=None):
    parser = _PrivateArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "export"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--confirm", default="")
    try:
        args = parser.parse_args(argv)
        if args.command == "check":
            if args.output or args.confirm:
                raise ValueError("Check mode cannot export files.")
            result = collect(args.root)
        else:
            if args.output is None:
                raise ValueError("Choose an explicit export destination.")
            result = export(args.root, args.output, args.confirm)
    except (OSError, ValueError) as error:
        # Never echo user-supplied paths, permission details, exception or
        # private content into terminal output.
        print("Sanitized diagnostics failed: confirm options and filesystem safety.",
              file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
