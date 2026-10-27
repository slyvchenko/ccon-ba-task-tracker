"""Synthetic EVD-15 lifecycle tests. No real corporate ZIP bytes or paths."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from evidence_retention import maintenance, CONFIRMATION
from storage import write_json
from supplier_logs import logs_root

FLOW = "11111111-2222-4333-8444-555555555555"
A = "a" * 12 + "-" + "1" * 8
B = "b" * 12 + "-" + "2" * 8
C = "c" * 12 + "-" + "3" * 8


class EvidenceRetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="evidence-retain-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.logs = logs_root(self.root)
        self.logs.mkdir()
        self.at = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
        self.index = self.logs / "index.json"

    def version(self, name, *, age_days=60, content=b"synthetic ZIP", key="CCON-1"):
        directory = self.logs / key / FLOW / name
        directory.mkdir(parents=True)
        original = directory / "original.zip"
        original.write_bytes(content)
        facts = directory / "facts.json"
        facts.write_text('{"synthetic":true}')
        attachment = directory / "supplier.zip"
        attachment.write_bytes(b"synthetic outgoing archive")
        stamp = (self.at - timedelta(days=age_days)).timestamp()
        for path in (original, facts, attachment, directory):
            os.utime(path, (stamp, stamp))
        return directory

    def pins(self, directory):
        relative = directory.relative_to(self.logs).as_posix()
        write_json(self.index, {f"CCON-1/{FLOW}": {
            "archiveRelativePath": relative + "/supplier.zip",
            "factsRelativePath": relative + "/facts.json",
        }})

    def test_dry_run_never_deletes_and_apply_requires_confirmation(self):
        pinned = self.version(A)
        old = self.version(B)
        self.pins(pinned)
        dry = maintenance(self.root, retention_days=30, quota_mb=10, now=self.at)
        self.assertEqual(dry["mode"], "DRY_RUN")
        self.assertEqual(dry["candidates"], 1)
        self.assertEqual(dry["removed"], 0)
        self.assertTrue(old.exists())
        self.assertTrue(pinned.exists())
        with self.assertRaisesRegex(ValueError, "confirmation"):
            maintenance(self.root, apply=True, now=self.at)
        outcome = maintenance(self.root, retention_days=30, quota_mb=10,
                              apply=True, confirm=CONFIRMATION, now=self.at)
        self.assertEqual(outcome["removed"], 1)
        self.assertFalse(old.exists())
        self.assertTrue(pinned.exists())
        self.assertTrue((self.root / "data/evidence_retention_last.json").is_file())
        self.assertNotIn("synthetic ZIP", json.dumps(outcome))

    def test_quota_removes_oldest_unreferenced_even_when_recent(self):
        pinned = self.version(A, age_days=1, content=b"p" * 600000)
        self.pins(pinned)
        old = self.version(B, age_days=4, content=b"x" * 600000)
        newer = self.version(C, age_days=2, content=b"y" * 500000)
        result = maintenance(self.root, retention_days=30, quota_mb=1, now=self.at)
        self.assertEqual(result["candidates"], 2)
        self.assertFalse(result["blockedByPinnedVersions"])
        self.assertTrue(old.exists())
        self.assertTrue(newer.exists())
        self.assertEqual([item["reason"] for item in result["decisions"]], ["QUOTA", "QUOTA"])

    def test_pinned_over_quota_is_reported_never_deleted(self):
        pinned = self.version(A, content=b"z" * 1250000)
        self.pins(pinned)
        result = maintenance(self.root, retention_days=5, quota_mb=1, now=self.at)
        self.assertTrue(result["blockedByPinnedVersions"])
        self.assertEqual(result["candidates"], 0)
        self.assertTrue(pinned.exists())

    def test_corrupt_or_missing_index_blocks_destructive_work(self):
        self.version(A)
        for value in (None, '{"corrupt":', '{"CCON-1":{}}'):
            if value is None:
                self.index.unlink(missing_ok=True)
            else:
                self.index.write_text(value)
            with self.subTest(value=value), self.assertRaises((ValueError, json.JSONDecodeError)):
                maintenance(self.root, apply=True, confirm=CONFIRMATION, now=self.at)
        self.assertTrue((self.logs / "CCON-1" / FLOW / A).exists())

    def test_untrusted_symlink_or_external_root_fails_closed(self):
        old = self.version(A)
        self.pins(old)
        external_context = tempfile.TemporaryDirectory(prefix="external-evidence-")
        self.addCleanup(external_context.cleanup)
        external = Path(external_context.name)
        inside = old / "hidden"
        try:
            inside.symlink_to(external, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unsupported")
        with self.assertRaisesRegex(ValueError, "Symlink"):
            maintenance(self.root, now=self.at)
        self.assertTrue(old.exists())
        inside.unlink()
        with patch("evidence_retention.logs_root", return_value=external):
            with self.assertRaisesRegex(ValueError, "External log root"):
                maintenance(self.root, now=self.at)

    def test_symlinked_log_root_within_workspace_is_not_resolved_away(self):
        pinned = self.version(A)
        self.pins(pinned)
        actual = self.root / "saved-evidence"
        self.logs.rename(actual)
        try:
            self.logs.symlink_to(actual, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unsupported")
        with self.assertRaisesRegex(ValueError, "Symlink log root"):
            maintenance(self.root, now=self.at, apply=True, confirm=CONFIRMATION)
        self.assertTrue((actual / "CCON-1" / FLOW / A).exists())

    def test_symlinked_custom_log_root_inside_workspace_is_rejected(self):
        pinned = self.version(A)
        self.pins(pinned)
        link = self.root / "link-to-evidence"
        try:
            link.symlink_to(self.logs, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unsupported")
        write_json(self.root / "log_config.json", {"logsDir": str(link)})
        with self.assertRaisesRegex(ValueError, "Symlink log root"):
            maintenance(self.root, now=self.at)
        self.assertTrue(pinned.exists())

    def test_does_not_touch_current_downloads_or_jira_state(self):
        recent = self.version(A, age_days=1)
        self.pins(recent)
        downloads = self.root / "downloads/ccon/CCON-1"
        downloads.mkdir(parents=True)
        (downloads / "private.zip").write_bytes(b"not part of log versions")
        write_json(self.root / "data/user_edits.json", {"note": "keep"})
        result = maintenance(self.root, retention_days=30, quota_mb=10, now=self.at,
                             apply=True, confirm=CONFIRMATION)
        self.assertEqual(result["removed"], 0)
        self.assertTrue((downloads / "private.zip").exists())
        self.assertEqual(json.loads((self.root / "data/user_edits.json").read_text()),
                         {"note": "keep"})


if __name__ == "__main__":
    unittest.main()
