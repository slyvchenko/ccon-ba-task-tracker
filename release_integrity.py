"""Offline release integrity and rollback *preflight*, never an automatic deployment.

SHA-256 detects accidental changes only. It is NOT an authenticated signature
without a trusted external signing key and independently verified provenance.
"""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from app_config import VERSION
from build_release import release_files

MAX_FILES = 400


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def inventory(root):
    files = release_files(root)
    if len(files) > MAX_FILES:
        raise ValueError("Release contains too many files for offline inventory")
    # User workspace files are excluded by the existing source-only manifest.
    return {
        "schemaVersion": 1, "appVersion": VERSION,
        "integrityMethod": "SHA256_NOT_A_DIGITAL_SIGNATURE",
        "signerVerified": False,
        "sourceOnly": True,
        "entries": [{"relative": name, "sha256": digest(path)}
                    for name, path in sorted(files)],
    }


def verify_release(zip_path, expected):
    if expected.get("schemaVersion") != 1 or expected.get("signerVerified") is not False:
        raise ValueError("Unsupported or misleading release inventory")
    entries = expected.get("entries")
    if not isinstance(entries, list) or not entries or len(entries) > MAX_FILES:
        raise ValueError("Invalid release inventory")
    wanted = {}
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("Invalid entry")
        name, hash_value = item.get("relative"), item.get("sha256")
        if (not isinstance(name, str) or not name or name.startswith("/") or
                ".." in Path(name).parts or ("ccon-ba-desk/" + name) in wanted or
                not isinstance(hash_value, str) or len(hash_value) != 64 or
                any(ch not in "0123456789abcdef" for ch in hash_value)):
            raise ValueError("Unsafe/duplicate inventory entry")
        wanted["ccon-ba-desk/" + name] = hash_value
    with zipfile.ZipFile(zip_path) as archive:
        # Our source-only builder emits files only. Reject hidden extra
        # directory entries, especially paths conflicting with a real file.
        # Filtering is_dir() would incorrectly accept a malformed ZIP.
        files = archive.infolist()
        if any(x.is_dir() for x in files):
            raise ValueError("Release archive contains an unexpected directory")
        names = [x.filename for x in files]
        if len(names) != len(wanted) or set(names) != set(wanted):
            raise ValueError("Release archive contents differ from manifest")
        for member in files:
            with archive.open(member) as stream:
                h = hashlib.sha256()
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(block)
                if h.hexdigest() != wanted[member.filename]:
                    raise ValueError("Release archive hash mismatch")
    return {"verified": True, "files": len(wanted),
            "signed": False, "deployed": False, "dataModified": False}


def rollback_preflight(current_version, previous_version, backup_verified):
    """Conservative advisory, never perform a potentially destructive downgrade."""
    if not all(isinstance(x, str) and x for x in (current_version, previous_version)):
        raise ValueError("Explicit version labels required")
    if type(backup_verified) is not bool:
        raise ValueError("Independent backup verification flag required")
    return {
        "automaticRollback": False,
        "backupVerifiedByCaller": backup_verified,
        "migrationCompatibilityProven": False,
        "allowedToReplaceInstalledApp": False,
        "nextStep": "Verify real SQLite backup and test prior app against copied DB; manual human approval required.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--zip", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_release(args.zip, inventory(args.root))
    except (OSError, ValueError, zipfile.BadZipFile):
        parser.exit(1, "Offline integrity validation failed.\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
