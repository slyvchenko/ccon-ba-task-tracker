"""Private SQLite point-in-time backups and OFFLINE-only verified restoration.

Never copy a live .db file byte-for-byte. Always use sqlite3.Connection.backup.
No passwords, Jira descriptions, notes or emails appear in the manifest.
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from pipeline_lock import pipeline_lock, replace_file

NAME = re.compile(r"backup-\d{8}T\d{6}Z-[a-f0-9]{12}\.sqlite3\Z")
REQUIRED = frozenset(("tasks",))
CONFIRM = "RESTORE LOCAL BA DATA"


def _folder(root):
    folder = Path(root).resolve() / "backups"
    if folder.is_symlink():
        raise ValueError("Backup directory may not be a symbolic link.")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        folder.chmod(0o700)
    return folder


def _private_new(path):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    return path


def _sha(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _check_database(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError("SQLite database file is absent or unsafe.")
    # A read-only connection cannot initialize a missing database.
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise ValueError("SQLite integrity check failed.")
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not REQUIRED.issubset(tables):
            raise ValueError("Backup is missing expected BA Desk tables.")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)")}
        if not {"key", "snapshot", "manual_status", "note", "imported_at"}.issubset(columns):
            raise ValueError("SQLite is missing BA Desk task fields.")
        # Preserve backups from earlier releases, before history/version
        # migrations. Desk startup will add these columns and tables.
        if "state_revision" in tables:
            revision = connection.execute(
                "SELECT revision FROM state_revision WHERE id=1").fetchone()
            if revision is None or type(revision[0]) is not int or revision[0] < 0:
                raise ValueError("Missing or invalid application revision.")
            number = revision[0]
        else:
            number = 0
        count = connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        return {"revision": number, "tasks": count}
    finally:
        connection.close()


def backup_status(root):
    """Read metadata only; never expose a file path or private task content."""
    root = Path(root)
    if not (root / "ba_state.db").exists():
        return {"available": False, "status": "NO_DATABASE"}
    try:
        folder = _folder(root)
        manifests = sorted(folder.glob("backup-*.sqlite3.json"), reverse=True)
        for manifest in manifests:
            try:
                if manifest.is_symlink() or manifest.stat().st_size > 4096:
                    continue
                entry = json.loads(manifest.read_text(encoding="utf-8"))
                name = entry.get("filename", "")
                if not isinstance(name, str) or not NAME.fullmatch(name) or (
                    manifest.name != name + ".json"):
                    continue
                # Freshness is only valid if *both* the checksum and SQLite
                # integrity pass. Corrupt manifests must not suppress a new
                # startup backup for up to 24 hours.
                verified = verify_backup(root, name)
                return {"available": True, "status": "AVAILABLE",
                        "createdAt": verified["createdAt"],
                        "revision": verified["revision"]}
            except (OSError, ValueError, sqlite3.Error, KeyError, TypeError):
                continue
        return {"available": False, "status": "NO_BACKUP"}
    except (OSError, ValueError, sqlite3.Error, TypeError, KeyError):
        return {"available": False, "status": "CHECK_FAILED"}


def _recent_backup(root, interval_hours):
    info = backup_status(root)
    if info.get("status") != "AVAILABLE":
        return False
    try:
        stamp = datetime.fromisoformat(info["createdAt"].replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - stamp < timedelta(hours=interval_hours)
    except (TypeError, ValueError):
        return False


def create_backup(root, *, force=False, interval_hours=24, keep=7):
    """Safe with a running local server; use SQLite online backup API."""
    root = Path(root).resolve()
    database = root / "ba_state.db"
    if not database.exists():
        return {"created": False, "reason": "NO_DATABASE"}
    if database.is_symlink() or not database.is_file():
        raise ValueError("Refusing unsafe database path.")
    if not force and _recent_backup(root, interval_hours):
        return {"created": False, "reason": "RECENT_BACKUP"}
    folder = _folder(root)
    moment = datetime.now(timezone.utc)
    timestamp = moment.strftime("%Y%m%dT%H%M%SZ")
    filename = f"backup-{timestamp}-{secrets.token_hex(6)}.sqlite3"
    target = folder / filename
    temporary = folder / (filename + ".pending")
    temporary_meta = folder / (filename + ".json.pending")
    manifest = folder / (filename + ".json")
    try:
        _private_new(temporary)
        source = sqlite3.connect(database, timeout=15)
        try:
            destination = sqlite3.connect(temporary, timeout=15)
            try:
                source.backup(destination, pages=64, sleep=0.05)
            finally:
                destination.close()
        finally:
            source.close()
        checks = _check_database(temporary)
        info = {"format": 1, "filename": filename,
                "createdAt": moment.isoformat().replace("+00:00", "Z"),
                "sha256": _sha(temporary), "bytes": temporary.stat().st_size,
                **checks}
        _private_new(temporary_meta)
        temporary_meta.write_text(json.dumps(info, indent=2), encoding="utf-8")
        # Publish DB, then manifest last. An interrupted backup lacks a
        # manifest and therefore is not eligible for recovery.
        replace_file(temporary, target)
        replace_file(temporary_meta, manifest)
        verify_backup(root, filename)
        if keep > 0:
            _trim(folder, keep)
        return {"created": True, "filename": filename,
                "revision": checks["revision"], "tasks": checks["tasks"]}
    finally:
        for orphan in (temporary, temporary_meta):
            if orphan.exists():
                orphan.unlink()


def _trim(folder, count):
    manifests = sorted(folder.glob("backup-*.sqlite3.json"), reverse=True)
    for manifest in manifests[count:]:
        if manifest.is_symlink():
            continue
        name = manifest.name[:-5]
        if not NAME.fullmatch(name):
            continue
        path = folder / name
        if path.is_symlink():
            continue
        # Remove manifest FIRST; a crash should leave an ineligible .db,
        # never a dangling valid-looking manifest.
        manifest.unlink()
        path.unlink(missing_ok=True)


def verify_backup(root, filename):
    if not isinstance(filename, str) or not NAME.fullmatch(filename):
        raise ValueError("Invalid backup name; choose a file in backups/.")
    folder = _folder(root)
    target = folder / filename
    manifest = folder / (filename + ".json")
    if (not target.is_file() or target.is_symlink() or not manifest.is_file() or
            manifest.is_symlink() or manifest.stat().st_size > 4096):
        raise ValueError("Backup or manifest is missing or unsafe.")
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    if metadata.get("format") != 1 or metadata.get("filename") != filename:
        raise ValueError("Unknown or mismatched backup manifest.")
    if metadata.get("bytes") != target.stat().st_size or metadata.get("sha256") != _sha(target):
        raise ValueError("Backup checksum mismatch; current data remains unchanged.")
    details = _check_database(target)
    if any(metadata.get(field) != details[field] for field in ("revision", "tasks")):
        raise ValueError("Backup manifest and SQLite contents differ.")
    return {"filename": filename, "verified": True, **details,
            "createdAt": metadata.get("createdAt")}


def restore_backup(root, filename, confirmation):
    """Refuse when desktop server owns its lock, protect current DB first."""
    if confirmation != CONFIRM:
        raise ValueError("Restore requires exact --confirm 'RESTORE LOCAL BA DATA'.")
    root = Path(root).resolve()
    # Lock is held for the full lifetime of the running desktop server.
    # Shared with the restore CLI, distinct from daily pipeline locks.
    with pipeline_lock(root / ".local-server"):
        verified = verify_backup(root, filename)
        database = root / "ba_state.db"
        if database.exists():
            if database.is_symlink() or not database.is_file():
                raise ValueError("Refusing unsafe database path.")
            # Create an additional verified rescue copy BEFORE any write.
            rescue = create_backup(root, force=True, keep=0)
            if not rescue.get("created"):
                raise ValueError("Could not safeguard existing local data.")
            # Do not replace db while an uncheckpointed WAL could replay
            # old transactions over the restored file on the next launch.
            connection = sqlite3.connect(database, timeout=10)
            try:
                checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                if checkpoint and checkpoint[0] != 0:
                    raise ValueError("SQLite WAL is busy. Close all readers before restore.")
            finally:
                connection.close()
            if (root / "ba_state.db-wal").exists() or (root / "ba_state.db-shm").exists():
                raise ValueError("SQLite WAL files still present. Close all clients before restore.")
        folder = _folder(root)
        source = folder / filename
        stage = root / ("ba_state.db." + secrets.token_hex(6) + ".pending")
        try:
            _private_new(stage)
            # Restore with SQLite backup API rather than copying a raw file:
            # the result is standalone (not tied to its previous journal).
            origin = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
            try:
                destination = sqlite3.connect(stage, timeout=10)
                try:
                    origin.backup(destination)
                finally:
                    destination.close()
            finally:
                origin.close()
            _check_database(stage)
            replace_file(stage, database)
        finally:
            if stage.exists():
                stage.unlink()
        return {"restored": True, "revision": verified["revision"],
                "tasks": verified["tasks"], "offline": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("backup", "verify", "restore", "status"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--name", help="Filename listed in the private backups/ folder")
    parser.add_argument("--confirm", default="")
    options = parser.parse_args(argv)
    try:
        if options.command == "status":
            result = backup_status(options.root)
        elif options.command == "backup":
            result = create_backup(options.root, force=True)
        elif options.command == "verify":
            result = verify_backup(options.root, options.name)
        else:
            result = restore_backup(options.root, options.name, options.confirm)
    except (OSError, ValueError, sqlite3.Error) as exc:
        # Avoid printing source paths or private database values to terminals.
        print("Local backup action failed: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
