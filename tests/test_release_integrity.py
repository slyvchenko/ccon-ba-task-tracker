"""Synthetic release verification, tamper detection and non-mutating rollback advice."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from build_release import build_release
from release_integrity import inventory, rollback_preflight, verify_release


class ReleaseIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ccon-release-integrity-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "assets").mkdir()
        (self.root / "assets" / "dashboard.css").write_text("SYNTHETIC-CSS", encoding="utf-8")
        (self.root / "app_config.py").write_text("SYNTHETIC-CODE", encoding="utf-8")
        (self.root / "release_manifest.json").write_text(
            json.dumps(["assets/dashboard.css", "app_config.py"]), encoding="utf-8")
        self.archive = self.root / "build.zip"

    def test_verified_archive_and_read_only_rollback_advice(self):
        build_release(self.archive, self.root)
        result = verify_release(self.archive, inventory(self.root))
        self.assertEqual(result["files"], 2)
        self.assertTrue(result["verified"])
        self.assertFalse(result["signed"])
        self.assertFalse(result["deployed"])
        self.assertFalse(result["dataModified"])
        rollback = rollback_preflight("2.50.3", "2.50.2", True)
        self.assertFalse(rollback["automaticRollback"])
        self.assertFalse(rollback["migrationCompatibilityProven"])
        self.assertFalse(rollback["allowedToReplaceInstalledApp"])

    def test_modified_archive_is_rejected_even_if_zip_crc_is_correct(self):
        build_release(self.archive, self.root)
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr("ccon-ba-desk/assets/dashboard.css", "MUTATED CSS")
            archive.writestr("ccon-ba-desk/app_config.py", "SYNTHETIC-CODE")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            verify_release(self.archive, inventory(self.root))

    def test_inventory_rejects_extra_files_and_untrusted_signature_claim(self):
        build_release(self.archive, self.root)
        inv = inventory(self.root)
        inv["signerVerified"] = True
        with self.assertRaises(ValueError):
            verify_release(self.archive, inv)
        inv["signerVerified"] = False
        with zipfile.ZipFile(self.archive, "a") as archive:
            archive.writestr("ccon-ba-desk/private-note.txt", "PRIVATE SYNTHETIC")
        with self.assertRaisesRegex(ValueError, "differ"):
            verify_release(self.archive, inv)

    def test_unexpected_directory_entry_is_rejected_even_when_files_match(self):
        build_release(self.archive, self.root)
        expected = inventory(self.root)
        with zipfile.ZipFile(self.archive, "a") as archive:
            archive.writestr("ccon-ba-desk/app_config.py/", "")
        with self.assertRaisesRegex(ValueError, "unexpected directory"):
            verify_release(self.archive, expected)

    def test_path_traversal_duplicate_and_invalid_digest_rejected(self):
        build_release(self.archive, self.root)
        for entry in [
            {"relative": "../secrets.txt", "sha256": "a" * 64},
            {"relative": "payload.txt", "sha256": "invalid"},
        ]:
            inv = inventory(self.root)
            inv["entries"].append(entry)
            with self.assertRaises(ValueError):
                verify_release(self.archive, inv)
        inv = inventory(self.root)
        inv["entries"].append(inv["entries"][0])
        with self.assertRaises(ValueError):
            verify_release(self.archive, inv)

    def test_archive_does_not_touch_source_or_write_backup(self):
        original = (self.root / "app_config.py").read_bytes()
        build_release(self.archive, self.root)
        verify_release(self.archive, inventory(self.root))
        self.assertEqual((self.root / "app_config.py").read_bytes(), original)
        self.assertEqual(set(x.name for x in self.root.iterdir()),
                         {"assets", "app_config.py", "release_manifest.json", "build.zip"})


if __name__ == "__main__":
    unittest.main()
