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
import shutil
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


def _sync_file(path):
    """Sync validated SQLite or manifest bytes before they become eligible."""
    # Windows CRT requires a writable handle for _commit / os.fsync.
    # This is our newly created private staging file, never a source DB.
    with Path(path).open("r+b") as stream:
        os.fsync(stream.fileno())


def _sync_parent(path):
    """Sync directory renames on POSIX; Windows directory fsync unavailable."""
    if os.name == "nt":
        return
    fd = os.open(Path(path).parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _publish(source, target):
    replace_file(source, target)
    _sync_parent(target)


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


def _validated_creation_time(filename, created_at):
    """Cross-check UTC filename and metadata time; reject forged freshness."""
    if not NAME.fullmatch(filename) or not isinstance(created_at, str):
        raise ValueError("Invalid backup creation identity.")
    try:
        timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        name_timestamp = datetime.strptime(
            filename[len("backup-"):len("backup-") + 16],
            "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Invalid backup creation timestamp.") from None
    if timestamp.tzinfo is None:
        raise ValueError("Backup creation time must include UTC timezone.")
    try:
        timestamp = timestamp.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        raise ValueError("Invalid backup creation timestamp.") from None
    if abs((timestamp - name_timestamp).total_seconds()) >= 1:
        raise ValueError("Backup filename and manifest creation time differ.")
    return timestamp


def _ordered_manifests(folder):
    """Sort by UTC creation timestamp, not same-second random filename suffix."""
    entries = []
    for path in folder.glob("backup-*.sqlite3.json"):
        try:
            if path.is_symlink() or path.stat().st_size > 4096:
                continue
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                continue
            when = datetime.fromisoformat(str(value.get("createdAt", "")).replace("Z", "+00:00"))
            if when.tzinfo is None:
                continue
            entries.append((when, path.stat().st_mtime_ns, path))
        except (OSError, ValueError, TypeError, OverflowError):
            continue
    entries.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [entry[2] for entry in entries]


def backup_status(root):
    """Read metadata only; never expose a file path or private task content."""
    root = Path(root)
    if not (root / "ba_state.db").exists():
        return {"available": False, "status": "NO_DATABASE"}
    try:
        folder = _folder(root)
        for manifest in _ordered_manifests(folder):
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
        age = datetime.now(timezone.utc) - stamp
        # A future-dated (clock-skewed) backup must not suppress fresh copies
        # indefinitely. Preserve the old backup but create another one.
        return timedelta(seconds=-300) <= age < timedelta(hours=interval_hours)
    except (TypeError, ValueError):
        return False


def _sweep_old_pending(folder, max_age_seconds=3600):
    # Interrupted copies may contain raw PRIVATE SQLite data. Do not follow
    # symlinks and never touch recently written files from another CLI run.
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_seconds
    for orphan in folder.glob("backup-*.pending"):
        try:
            if not orphan.is_symlink() and orphan.is_file() and orphan.stat().st_mtime < cutoff:
                orphan.unlink()
        except OSError:
            pass


def create_backup(root, *, force=False, interval_hours=24, keep=7):
    """Safe with a running local server; use SQLite online backup API."""
    root = Path(root).resolve()
    database = root / "ba_state.db"
    if not database.exists():
        return {"created": False, "reason": "NO_DATABASE"}
    if database.is_symlink() or not database.is_file():
        raise ValueError("Refusing unsafe database path.")
    folder = _folder(root)
    _sweep_old_pending(folder)
    if not force and _recent_backup(root, interval_hours):
        return {"created": False, "reason": "RECENT_BACKUP"}
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
        _sync_file(temporary)
        info = {"format": 1, "filename": filename,
                "createdAt": moment.isoformat().replace("+00:00", "Z"),
                "sha256": _sha(temporary), "bytes": temporary.stat().st_size,
                **checks}
        _private_new(temporary_meta)
        with temporary_meta.open("w", encoding="utf-8") as output:
            output.write(json.dumps(info, indent=2))
            output.flush()
            os.fsync(output.fileno())
        # Publish DB, then manifest last. An interrupted backup lacks a
        # manifest and therefore is not eligible for recovery.
        _publish(temporary, target)
        _publish(temporary_meta, manifest)
        verify_backup(root, filename)
        if keep > 0:
            _trim(folder, keep, preserve=filename)
        return {"created": True, "filename": filename,
                "revision": checks["revision"], "tasks": checks["tasks"]}
    finally:
        for orphan in (temporary, temporary_meta):
            if orphan.exists():
                orphan.unlink()


def _trim(folder, count, *, preserve=None):
    # Invalid/corrupted files are NEVER counted as successful backup points.
    valid = []
    for manifest in _ordered_manifests(folder):
        name = manifest.name[:-5]
        try:
            verify_backup(folder.parent, name)
            valid.append(manifest)
        except (OSError, ValueError, sqlite3.Error, TypeError):
            continue
    # After a clock rollback, this newly verified backup may sort before
    # older future-dated copies. Never immediately delete the copy just made.
    if preserve is not None:
        name = preserve + ".json"
        preserved = next((item for item in valid if item.name == name), None)
        if preserved is not None:
            valid = [preserved] + [item for item in valid if item != preserved]
    for manifest in valid[count:]:
        name = manifest.name[:-5]
        path = folder / name
        if path.is_symlink():
            continue
        # Remove manifest FIRST: a crash must not leave a valid-looking entry.
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
    if not isinstance(metadata, dict):
        raise ValueError("Invalid backup manifest format.")
    if metadata.get("format") != 1 or metadata.get("filename") != filename:
        raise ValueError("Unknown or mismatched backup manifest.")
    _validated_creation_time(filename, metadata.get("createdAt"))
    if metadata.get("bytes") != target.stat().st_size or metadata.get("sha256") != _sha(target):
        raise ValueError("Backup checksum mismatch; current data remains unchanged.")
    details = _check_database(target)
    if any(metadata.get(field) != details[field] for field in ("revision", "tasks")):
        raise ValueError("Backup manifest and SQLite contents differ.")
    return {"filename": filename, "verified": True, **details,
            "createdAt": metadata.get("createdAt")}


def _quarantine_corrupt_database(root, database):
    """Preserve damaged raw bytes for forensics, NEVER mark restorable/verified."""
    folder = _folder(root)
    filename = ("damaged-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") +
                secrets.token_hex(6) + ".sqlite3")
    stage = folder / (filename + ".pending")
    destination = folder / filename
    try:
        _private_new(stage)
        with database.open("rb") as source, stage.open("wb") as output:
            shutil.copyfileobj(source, output, length=1024*1024)
            output.flush()
            os.fsync(output.fileno())
        if stage.stat().st_size != database.stat().st_size:
            raise ValueError("Damaged database could not be safely preserved.")
        replace_file(stage, destination)
        return filename
    finally:
        if stage.exists():
            stage.unlink()


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
        sidecars = (root / "ba_state.db-wal", root / "ba_state.db-shm")
        # An unfinished SQLite rollback transaction uses a separate journal
        # rather than WAL. Opening DB before checking it could replay changes;
        # fail closed and ask an operator to preserve it (review #32).
        journal = root / "ba_state.db-journal"
        if journal.exists() or journal.is_symlink():
            raise ValueError("SQLite rollback journal present. Preserve it offline before restore.")
        # Orphaned WAL can replay AFTER the validated replacement even if
        # no main DB exists: refuse rather than silently alter recovered data.
        if not database.exists() and any(path.exists() or path.is_symlink() for path in sidecars):
            raise ValueError("Orphaned SQLite WAL files present. Preserve them offline before recovery.")
        if database.exists() and any(path.exists() or path.is_symlink() for path in sidecars):
            # Even sqlite3.connect() could replay or remove a damaged WAL.
            # Refuse BEFORE touching existing SQLite bytes. An operator can
            # perform an offline forensic recovery after preserving sidecars.
            raise ValueError("SQLite WAL sidecars present. Stop all clients and preserve the WAL offline.")
        if database.exists():
            if database.is_symlink() or not database.is_file():
                raise ValueError("Refusing unsafe database path.")
            rescue_valid = False
            try:
                rescue = create_backup(root, force=True, keep=0)
                rescue_valid = bool(rescue.get("created"))
                if not rescue_valid:
                    raise ValueError("Could not safeguard existing local data.")
            except (sqlite3.DatabaseError, ValueError):
                # Only a genuinely broken DB can bypass verified rescue: a
                # raw forensic copy is explicitly NOT a restorable backup.
                try:
                    _check_database(database)
                except (sqlite3.DatabaseError, ValueError):
                    if any(path.exists() or path.is_symlink() for path in sidecars):
                        raise ValueError("Damaged SQLite has WAL sidecars. Preserve and disconnect offline.")
                    _quarantine_corrupt_database(root, database)
                else:
                    raise
            if rescue_valid:
                # Healthy SQLite: safely checkpoint before replacing file.
                connection = sqlite3.connect(database, timeout=10)
                try:
                    checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                    if checkpoint and checkpoint[0] != 0:
                        raise ValueError("SQLite WAL is busy. Close all readers before restore.")
                finally:
                    connection.close()
            if any(path.exists() or path.is_symlink() for path in sidecars):
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
            _sync_file(stage)
            _publish(stage, database)
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
