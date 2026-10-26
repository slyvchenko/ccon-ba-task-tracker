"""Synthetic privacy tests: no production logs are read, copied, or exported."""
import io
import json
import os
import stat
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from local_diagnostics import CONFIRM, collect, export, main


SECRET = "SYNTHETIC-SECRET-TOKEN-EXAMPLE@unsafe.invalid"


class LocalDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory(prefix="ccon-diagnostic-test-")
        self.addCleanup(workspace.cleanup)
        self.base = Path(workspace.name)
        self.root = self.base / "app"
        self.root.mkdir()
        self.output = self.base / "explicit-diagnostics.zip"
        (self.root / "data").mkdir()
        (self.root / "logs").mkdir()
        (self.root / "inbox").mkdir()
        (self.root / "downloads" / "ccon" / "CCON-4242").mkdir(parents=True)
        self.hidden = (
            self.root / "ba_state.db",
            self.root / "data" / "jira_context.json",
            self.root / "logs" / "real_supplier.log",
            self.root / "inbox" / "CCON_BA_Snapshot.json",
            self.root / "downloads" / "ccon" / "CCON-4242" / "secret.zip",
        )
        for path in self.hidden:
            path.write_bytes((SECRET + " PNR ZX97YJ / REST RS / private email").encode())

    def test_check_is_read_only_and_does_not_export_or_expose_private_values(self):
        before = list(self.base.iterdir())
        result = collect(self.root)
        self.assertEqual(sorted(before), sorted(self.base.iterdir()))
        raw = json.dumps(result)
        for value in (SECRET, "ZX97YJ", "CCON-4242", "jira_context",
                      "real_supplier", str(self.root), "private email"):
            self.assertNotIn(value, raw)
        self.assertFalse(result["externalSends"])
        self.assertFalse(result["encryptionVerified"])
        self.assertFalse(result["windowsAclVerified"])
        self.assertEqual(result["contentPolicy"], "METADATA_ONLY_NO_LOG_OR_SOURCE_READS")
        self.assertEqual(result["supplierZipChecks"]["examined"], 2)

    def test_no_export_without_exact_consent_or_explicit_output(self):
        for consent in ("", "YES", CONFIRM.lower(), "EXPORT SANITIZED"):
            with self.subTest(consent=consent), self.assertRaises(ValueError):
                export(self.root, self.output, consent)
        self.assertFalse(self.output.exists())
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            self.assertEqual(main(["export", "--root", str(self.root)]), 1)
        self.assertFalse(self.output.exists())

    def test_bundle_has_exactly_two_safe_entries_and_not_raw_payloads(self):
        status = export(self.root, self.output, CONFIRM)
        self.assertTrue(status["created"])
        self.assertTrue(self.output.is_file())
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(set(archive.namelist()), {"diagnostics.json", "README.txt"})
            report = json.loads(archive.read("diagnostics.json"))
            self.assertEqual(report["appVersion"], report["appVersion"].strip())
            self.assertIn("supplierZipChecks", report)
            self.assertEqual(report["supplierZipChecks"]["examined"], 2)
            exported = b"".join(archive.read(name) for name in archive.namelist())
        for value in (SECRET, "ZX97YJ", "CCON-4242", "jira_context",
                      "real_supplier", str(self.root), "private email"):
            self.assertNotIn(value.encode(), exported)
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)

    def test_refuse_inside_workspace_and_existing_or_symlink_target(self):
        with self.assertRaisesRegex(ValueError, "inside"):
            export(self.root, self.root / "internal.zip", CONFIRM)
        self.output.write_bytes(b"existing")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            export(self.root, self.output, CONFIRM)
        self.assertEqual(self.output.read_bytes(), b"existing")
        self.output.unlink()
        try:
            self.output.symlink_to(self.root / "ba_state.db")
        except (OSError, NotImplementedError):
            return
        with self.assertRaises(ValueError):
            export(self.root, self.output, CONFIRM)
        self.assertTrue((self.root / "ba_state.db").is_file())

    def test_posix_world_access_and_symlink_are_reported_not_hidden(self):
        database = self.root / "ba_state.db"
        if os.name != "nt":
            database.chmod(0o644)
            self.assertEqual(collect(self.root)["accessChecks"]["sqlite"], "UNSAFE_SHARED_MODE")
            database.chmod(0o600)
            self.assertEqual(collect(self.root)["accessChecks"]["sqlite"], "OWNER_ONLY_MODE")
        else:
            self.assertEqual(collect(self.root)["accessChecks"]["sqlite"],
                             "UNVERIFIED_WINDOWS_ACL")
        database.unlink()
        try:
            database.symlink_to(self.root / "data" / "jira_context.json")
        except (OSError, NotImplementedError):
            return
        info = collect(self.root)
        self.assertEqual(info["accessChecks"]["sqlite"], "UNSAFE_SYMLINK")
        self.assertTrue(info["filesystemRiskObserved"])

    def test_output_errors_remove_partial_zip(self):
        with patch("local_diagnostics.zipfile.ZipFile", side_effect=OSError("Private test path")):
            with self.assertRaises(OSError):
                export(self.root, self.output, CONFIRM)
        self.assertFalse(self.output.exists())

    def test_zip_scan_bounded_and_does_not_list_issue_ids(self):
        base = self.root / "downloads" / "ccon"
        for index in range(205):
            (base / ("CCON-" + str(5000+index))).mkdir()
        state = collect(self.root)["supplierZipChecks"]
        self.assertFalse(state["complete"])
        self.assertEqual(state["examined"], 200)
        self.assertNotIn("CCON-", json.dumps(state))
        self.assertTrue(collect(self.root)["filesystemRiskObserved"])

    def test_root_group_or_world_writable_is_not_mistaken_for_private(self):
        if os.name == "nt":
            self.assertEqual(collect(self.root)["accessChecks"]["workspace_dir"],
                             "UNVERIFIED_WINDOWS_ACL")
            return
        self.root.chmod(0o777)
        self.assertEqual(collect(self.root)["accessChecks"]["workspace_dir"],
                         "UNSAFE_SHARED_MODE")
        self.assertTrue(collect(self.root)["filesystemRiskObserved"])
        self.root.chmod(0o700)
        self.assertEqual(collect(self.root)["accessChecks"]["workspace_dir"],
                         "OWNER_ONLY_MODE")

    def test_symlink_in_parent_downloads_is_never_traversed(self):
        import shutil
        outside = self.base / "external"
        (outside / "ccon" / "CCON-999").mkdir(parents=True)
        (outside / "ccon" / "CCON-999" / "external.zip").write_bytes(
            SECRET.encode())
        downloads = self.root / "downloads"
        shutil.rmtree(downloads)
        try:
            downloads.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            return
        audit = collect(self.root)
        self.assertEqual(audit["accessChecks"]["downloads_dir"], "UNSAFE_SYMLINK")
        self.assertEqual(audit["supplierZipChecks"]["folder"], "UNSAFE_ANCESTOR")
        self.assertEqual(audit["supplierZipChecks"]["examined"], 0)
        self.assertTrue(audit["filesystemRiskObserved"])
        self.assertNotIn("CCON-999", json.dumps(audit))

    def test_invalid_command_tokens_cannot_echo_paths_or_pnr(self):
        for fragments in [
            ["export", "--root", str(self.root), "--output",
             str(self.output), "PRIVATE-PNR123"],
            ["unknown-command", "--root", SECRET],
            ["check", "--root", str(self.root), "user-home-SYNTHETIC-SECRET"],
        ]:
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = main(fragments)
            self.assertEqual(result, 1)
            self.assertNotIn(SECRET, stdout.getvalue() + stderr.getvalue())
            self.assertNotIn("PRIVATE-PNR123", stdout.getvalue() + stderr.getvalue())
            self.assertNotIn("user-home-SYNTHETIC-SECRET",
                             stdout.getvalue() + stderr.getvalue())
            self.assertFalse(self.output.exists())

    def test_check_mode_stdout_is_synthetic_metadata_only(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["check", "--root", str(self.root)]), 0)
        self.assertIn("METADATA_ONLY_NO_LOG_OR_SOURCE_READS", out.getvalue())
        self.assertNotIn(SECRET, out.getvalue())
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
