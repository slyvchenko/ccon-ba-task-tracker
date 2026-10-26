"""Synthetic verified backup/restore, migration, and watcher resilience checks."""
import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from desk_store import Desk
from local_backup import create_backup, verify_backup, restore_backup, backup_status, CONFIRM
from pipeline_lock import pipeline_lock
from snapshot_monitor import SnapshotMonitor


class OfflineRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ccon-private-recovery-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.desk = Desk(self.root)
        source = self.desk.inbox / "CCON_BA_Snapshot.json"
        source.write_text(json.dumps({
            "generatedAt": "2026-10-25T12:00:00Z",
            "tasks": [{"key": "CCON-1", "summary": "Synthetic order"},
                      {"key": "CCON-2", "summary": "Synthetic second order"}]
        }),encoding="utf-8")
        self.desk.import_snapshot()

    def saved(self, note, revision, status="IN PROGRESS", effort="S"):
        return self.desk.save("CCON-1", {
            "manualStatus":status, "manualEffort":effort, "note":note,
            "emailDraft":{"to":"synthetic@example.invalid",
                          "subject":"Demo", "body":"Only synthetic private draft"},
            "expectedManualRevision":revision})

    def test_complete_private_round_trip_and_rescue(self):
        self.saved("Precious user note",0,effort="M")
        snapshot=create_backup(self.root,force=True,keep=0)
        self.assertTrue(snapshot["created"])
        original_revision=self.desk.revision()["revision"]
        check=verify_backup(self.root,snapshot["filename"])
        self.assertEqual(check["revision"],original_revision)
        self.assertEqual(check["tasks"],2)
        self.assertTrue(backup_status(self.root)["available"])
        metadata=(self.root/"backups"/(snapshot["filename"]+".json")).read_text()
        for private in ("Precious user note","synthetic@example.invalid","Synthetic order"):
            self.assertNotIn(private,metadata)

        self.saved("Newer note",1,effort="XL")
        result=restore_backup(self.root,snapshot["filename"],CONFIRM)
        self.assertTrue(result["restored"])
        restarted=Desk(self.root)
        current=next(t for t in restarted.view()["tasks"] if t["key"]=="CCON-1")
        self.assertEqual(current["note"],"Precious user note")
        self.assertEqual(current["manualEffort"],"M")
        self.assertEqual(current["savedEmailDraft"]["body"],
                         "Only synthetic private draft")
        self.assertEqual(current["manualRevision"],1)
        self.assertEqual(restarted.revision()["revision"],original_revision)
        self.assertTrue(any(verify_backup(self.root,entry.name)["verified"]
            for entry in (self.root/"backups").glob("backup-*.sqlite3")
            if entry.name != snapshot["filename"]))

    def test_tampering_and_wrong_confirmation_leave_current_db_unchanged(self):
        self.saved("protected",0)
        snapshot=create_backup(self.root,force=True)
        backup=self.root/"backups"/snapshot["filename"]
        baseline=hashlib.sha256(self.desk.db.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            restore_backup(self.root,snapshot["filename"],"YES")
        self.assertEqual(hashlib.sha256(self.desk.db.read_bytes()).hexdigest(),baseline)
        backup.write_bytes(backup.read_bytes() + b"CORRUPTION")
        with self.assertRaises(ValueError):
            restore_backup(self.root,snapshot["filename"],CONFIRM)
        self.assertEqual(hashlib.sha256(self.desk.db.read_bytes()).hexdigest(),baseline)
        self.assertEqual(self.desk.view()["tasks"][0]["note"],"protected")
        # Corrupt but recent copy cannot suppress an automatic new backup.
        self.assertFalse(backup_status(self.root)["available"])
        regenerated=create_backup(self.root,force=False)
        self.assertTrue(regenerated["created"])
        self.assertTrue(verify_backup(self.root,regenerated["filename"])["verified"])

    def test_live_server_lock_blocks_offline_restore_and_preserves_db(self):
        snapshot=create_backup(self.root,force=True)
        self.saved("later",0)
        with pipeline_lock(self.root/".local-server"):
            with self.assertRaises(ValueError):
                restore_backup(self.root,snapshot["filename"],CONFIRM)
        self.assertEqual(self.desk.view()["tasks"][0]["note"],"later")
        self.assertEqual(self.desk.revision()["revision"],2)

    def test_corrupted_existing_database_is_preserved_forensically_before_restore(self):
        self.saved("Original before corruption",0)
        good = create_backup(self.root, force=True)
        broken = b"CORRUPT CURRENT DB - synthetic and unrecoverable" * 10
        self.desk.db.write_bytes(broken)
        result = restore_backup(self.root, good["filename"], CONFIRM)
        self.assertTrue(result["restored"])
        recovered = Desk(self.root).view()["tasks"][0]
        self.assertEqual(recovered["note"], "Original before corruption")
        forensic = list((self.root/"backups").glob("damaged-*.sqlite3"))
        self.assertEqual(len(forensic),1)
        self.assertEqual(forensic[0].read_bytes(),broken)
        # Damaged bytes do not carry a valid .sqlite3.json manifest.
        self.assertFalse((forensic[0].with_name(forensic[0].name+".json")).exists())

    def test_orphan_wal_blocks_restore_when_main_db_does_not_exist(self):
        good = create_backup(self.root, force=True)
        self.desk.db.unlink()
        sidecar = self.root/"ba_state.db-wal"
        sidecar.write_bytes(b"synthetic orphan WAL")
        with self.assertRaisesRegex(ValueError, "Orphaned SQLite WAL"):
            restore_backup(self.root, good["filename"], CONFIRM)
        self.assertFalse(self.desk.db.exists())
        self.assertEqual(sidecar.read_bytes(),b"synthetic orphan WAL")

    def test_corrupted_database_with_sidecar_requires_offline_operator_review(self):
        good = create_backup(self.root, force=True)
        broken = b"broken sqlite database"
        self.desk.db.write_bytes(broken)
        sidecar = self.root/"ba_state.db-wal"
        sidecar.write_bytes(b"unverified WAL")
        with self.assertRaisesRegex(ValueError, "WAL sidecars"):
            restore_backup(self.root, good["filename"], CONFIRM)
        self.assertEqual(self.desk.db.read_bytes(),broken)
        self.assertTrue(sidecar.exists())

    def test_same_second_backups_retained_by_creation_time_not_random_suffix(self):
        from unittest.mock import patch
        with patch("local_backup.secrets.token_hex",
                   side_effect=["ffffffffffff","000000000000"]):
            older = create_backup(self.root, force=True, keep=1)
            newer = create_backup(self.root, force=True, keep=1)
        self.assertTrue((self.root/"backups"/newer["filename"]).exists())
        self.assertFalse((self.root/"backups"/older["filename"]).exists())
        self.assertEqual(len(list((self.root/"backups").glob("backup-*.sqlite3.json"))),1)
        self.assertTrue(verify_backup(self.root,newer["filename"])["verified"])

    def test_nonobject_manifest_never_blocks_fresh_backup_or_startup_status(self):
        first=create_backup(self.root,force=True)
        manifest=self.root/"backups"/(first["filename"]+".json")
        for invalid in ("[]","null",'"not an object"'):
            manifest.write_text(invalid,encoding="utf-8")
            self.assertFalse(backup_status(self.root)["available"])
            with self.assertRaises(ValueError):
                verify_backup(self.root,first["filename"])
        newer=create_backup(self.root,force=False)
        self.assertTrue(newer["created"])
        self.assertTrue(verify_backup(self.root,newer["filename"])["verified"])

    def test_aged_pending_files_are_removed_but_fresh_in_progress_not_touched(self):
        folder=self.root/"backups"
        folder.mkdir(exist_ok=True)
        old=folder/"backup-20261025T000000Z-aaaaaaaaaaaa.sqlite3.pending"
        recent=folder/"backup-20261025T000001Z-bbbbbbbbbbbb.sqlite3.pending"
        old.write_bytes(b"old synthetic private bytes")
        recent.write_bytes(b"recent synthetic private bytes")
        stale=time.time()-7200
        os.utime(old,(stale,stale))
        create_backup(self.root,force=True)
        self.assertFalse(old.exists())
        self.assertEqual(recent.read_bytes(),b"recent synthetic private bytes")

    def test_unsafe_path_and_symlink_rejection(self):
        with self.assertRaises(ValueError):
            verify_backup(self.root,"../ba_state.db")
        with self.assertRaises(ValueError):
            verify_backup(self.root,"evil.sqlite3")
        snapshot=create_backup(self.root,force=True)
        name=snapshot["filename"]
        original=self.root/"backups"/name
        if hasattr(os,"symlink"):
            linked=self.root/"backups"/("backup-20261025T000000Z-aaaaaaaaaaaa.sqlite3")
            try:
                linked.symlink_to(original)
            except (OSError, NotImplementedError):
                return
            with self.assertRaises(ValueError):
                verify_backup(self.root,linked.name)

    def test_recent_backup_skip_and_retention(self):
        first=create_backup(self.root,force=True,keep=3)
        skipped=create_backup(self.root,interval_hours=24,keep=3)
        self.assertEqual(skipped["reason"],"RECENT_BACKUP")
        for _ in range(5):
            create_backup(self.root,force=True,keep=3)
        self.assertEqual(len(list((self.root/"backups").glob("backup-*.sqlite3.json"))),3)
        for item in (self.root/"backups").glob("backup-*.sqlite3.json"):
            verify_backup(self.root,item.name[:-5])

    def test_backup_manifest_time_cannot_claim_wrong_filename_or_future_freshness(self):
        from local_backup import _validated_creation_time, _recent_backup
        made=create_backup(self.root,force=True,keep=0)
        path=self.root/"backups"/(made["filename"]+".json")
        original=json.loads(path.read_text())
        name=made["filename"]
        stamp=_validated_creation_time(name,original["createdAt"])
        self.assertEqual(stamp.tzinfo.utcoffset(stamp).total_seconds(),0)
        for unsafe in ("2099-01-01T00:00:00Z", "2026-10-26T05:00:00",
                       "not-a-date"):
            changed=dict(original,createdAt=unsafe)
            path.write_text(json.dumps(changed),encoding="utf-8")
            with self.subTest(created=unsafe),self.assertRaises(ValueError):
                verify_backup(self.root,name)
            self.assertFalse(backup_status(self.root)["available"])
        path.write_text(json.dumps(original),encoding="utf-8")
        self.assertTrue(verify_backup(self.root,name)["verified"])
        self.assertTrue(_recent_backup(self.root,24))

    def test_clock_skew_does_not_prevent_future_snapshot_backup(self):
        from unittest.mock import patch
        from local_backup import _recent_backup
        made=create_backup(self.root,force=True,keep=0)
        metadata=self.root/"backups"/(made["filename"]+".json")
        # Simulate a machine clock moved backward by hours after a backup.
        real=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        class FakeDatetime:
            @staticmethod
            def now(tz=None):
                return real-__import__("datetime").timedelta(hours=3)
            @staticmethod
            def fromisoformat(value):
                return __import__("datetime").datetime.fromisoformat(value)
            @staticmethod
            def strptime(value, fmt):
                return __import__("datetime").datetime.strptime(value,fmt)
        with patch("local_backup.datetime",FakeDatetime):
            self.assertFalse(_recent_backup(self.root,24))
        self.assertTrue(metadata.is_file()) # Never delete old valid points.

    def test_snapshot_does_not_corrupt_backup_or_live_notes(self):
        self.saved("manual",0)
        original=create_backup(self.root,force=True)
        source=self.desk.inbox/"CCON_BA_Snapshot.json"
        source.write_text("{bad",encoding="utf-8")
        with self.assertRaises(ValueError):
            self.desk.import_snapshot()
        self.assertTrue(verify_backup(self.root,original["filename"])["verified"])
        self.assertEqual(self.desk.view()["tasks"][0]["note"],"manual")

    def test_can_backup_earlier_schema_before_startup_migration(self):
        with tempfile.TemporaryDirectory(prefix="ccon-pre-migrate-") as folder:
            root=Path(folder)
            with sqlite3.connect(root/"ba_state.db") as connection:
                connection.executescript("""
                  CREATE TABLE tasks(key TEXT PRIMARY KEY, snapshot TEXT NOT NULL,
                   manual_status TEXT NOT NULL, note TEXT NOT NULL,
                   imported_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
                  INSERT INTO tasks(key,snapshot,manual_status,note,imported_at) VALUES ('CCON-1',
                   '{"key":"CCON-1","summary":"Old sample"}',
                   'IN PROGRESS','Earlier note','2026-10-25T08:00:00Z');
                """)
            snap=create_backup(root,force=True)
            self.assertTrue(verify_backup(root,snap["filename"])["verified"])
            migrated=Desk(root)
            self.assertEqual(migrated.view()["tasks"][0]["note"],"Earlier note")


class WatcherResilienceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="ccon-watcher-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.desk=Desk(self.root)
        self.snapshot=self.desk.inbox/"CCON_BA_Snapshot.json"
        self.time=100.0
        self.monitor=SnapshotMonitor(self.desk,clock=lambda:self.time,retry_seconds=30)

    def test_skip_unchanged_and_retry_only_after_delay(self):
        self.assertFalse(self.monitor.check())
        self.assertEqual(self.monitor.public_status()["state"],"NO_SNAPSHOT")
        self.snapshot.write_text("{broken",encoding="utf-8")
        self.assertFalse(self.monitor.check())
        first=self.monitor.public_status()
        self.assertEqual(first["attempts"],1)
        self.assertEqual(first["failures"],1)
        for _ in range(10):
            self.assertFalse(self.monitor.check())
        self.assertEqual(self.monitor.public_status()["attempts"],1)
        self.time+=31
        self.assertFalse(self.monitor.check())
        self.assertEqual(self.monitor.public_status()["attempts"],2)
        self.snapshot.write_text(json.dumps({
            "generatedAt":"2026-10-25T12:00:00Z",
            "tasks":[{"key":"CCON-1","summary":"Synthetic"}]}),encoding="utf-8")
        self.assertTrue(self.monitor.check())
        self.assertEqual(self.monitor.public_status()["state"],"OK")
        current=self.desk.revision()["revision"]
        for _ in range(10):
            self.assertFalse(self.monitor.check())
        self.assertEqual(self.desk.revision()["revision"],current)
        self.assertEqual(self.monitor.public_status()["attempts"],3)

    def test_new_file_triggers_new_import_and_keeps_manual_state(self):
        self.snapshot.write_text(json.dumps({
            "generatedAt":"2026-10-25T12:00:00Z",
            "tasks":[{"key":"CCON-1","summary":"Initial"}]}),encoding="utf-8")
        self.assertTrue(self.monitor.check())
        self.desk.save("CCON-1",{"manualStatus":"IN PROGRESS",
                                "note":"manual","expectedManualRevision":0})
        self.snapshot.write_text(json.dumps({
            "generatedAt":"2026-10-25T13:00:00Z",
            "tasks":[{"key":"CCON-1","summary":"Later"}]}),encoding="utf-8")
        self.assertTrue(self.monitor.check())
        self.assertEqual(self.desk.view()["tasks"][0]["note"],"manual")
        self.assertEqual(self.desk.view()["tasks"][0]["summary"],"Later")


if __name__ == "__main__":
    unittest.main()
