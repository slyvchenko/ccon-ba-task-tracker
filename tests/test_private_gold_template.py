"""Synthetic tests for a blank, private-only, never-passing gold review template."""
import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace

from private_gold_review import summarize
from private_gold_template import CONFIRM, DISTRIBUTION, blank_cohort, create_template, main, _has_reparse_attribute


class GoldTemplateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ccon-gold-template-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.output = self.root / "review.json"

    def test_all_six_archetypes_and_no_fabricated_acceptance(self):
        pack = blank_cohort()
        self.assertEqual(len(pack["cases"]), 26)
        self.assertEqual(
            {k: sum(x["archetype"] == k for x in pack["cases"])
             for k, _ in DISTRIBUTION},
            dict(DISTRIBUTION))
        report = summarize(pack)
        self.assertFalse(report["criteriaReadyForHumanDecision"])
        self.assertEqual(report["humanAcceptance"], "NOT_RECORDED")
        self.assertFalse(report["releaseApproved"])
        self.assertEqual(report["independentReviewCount"], 0)
        self.assertEqual(report["frozenBeforeAiCount"], 0)
        self.assertEqual(report["results"]["BLOCKED"], 26)
        for row in pack["cases"]:
            self.assertEqual(row["facts"], "INCONCLUSIVE")
            self.assertEqual(row["result"], "BLOCKED")
            self.assertIsNone(row["ttnaSeconds"])
            self.assertFalse(row["independentReview"])

    def test_windows_legacy_reparse_attribute_detected_without_path_is_junction(self):
        # Python 3.10/3.11 lack Path.is_junction(), but NTFS lstat reports
        # FILE_ATTRIBUTE_REPARSE_POINT (0x400) for a real junction.
        self.assertTrue(_has_reparse_attribute(
            SimpleNamespace(st_file_attributes=0x400)))
        self.assertFalse(_has_reparse_attribute(
            SimpleNamespace(st_file_attributes=0x20)))
        self.assertFalse(_has_reparse_attribute(
            SimpleNamespace(st_mode=0o700)))

    def test_output_is_private_and_compatible_with_existing_validator(self):
        state = create_template(self.output, CONFIRM)
        self.assertEqual(state["caseCount"], 26)
        self.assertFalse(state["externalSends"])
        self.assertFalse(state["releaseApproved"])
        pack = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertFalse(summarize(pack)["criteriaReadyForHumanDecision"])
        self.assertEqual([x["id"] for x in pack["cases"]],
                         [f"GOLD-{n:02d}" for n in range(1, 27)])
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)

    def test_no_consent_or_existing_file_can_be_overwritten(self):
        for answer in ("", "YES", "CREATE PRIVATE GOLD", CONFIRM.lower()):
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                create_template(self.output, answer)
            self.assertFalse(self.output.exists())
        self.output.write_text("DON'T OVERWRITE", encoding="utf-8")
        with self.assertRaises(ValueError):
            create_template(self.output, CONFIRM)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "DON'T OVERWRITE")

    def test_symlink_target_and_parent_are_rejected(self):
        harmless = self.root / "harmless.txt"
        harmless.write_text("KEEP", encoding="utf-8")
        try:
            self.output.symlink_to(harmless)
        except (OSError, NotImplementedError):
            return
        with self.assertRaises(ValueError):
            create_template(self.output, CONFIRM)
        self.assertEqual(harmless.read_text(encoding="utf-8"), "KEEP")
        self.output.unlink()
        other = self.root / "other"
        other.mkdir()
        redirected = self.root / "redirected"
        try:
            redirected.symlink_to(other, target_is_directory=True)
        except (OSError, NotImplementedError):
            return
        with self.assertRaises(ValueError):
            create_template(redirected / "private.json", CONFIRM)

    def test_symlink_followed_by_parent_traversal_cannot_redirect_into_other_folder(self):
        # Raw /private/link/../review.json has different semantics from
        # abspath(): an OS resolves the symlink *before* processing '..'.
        private = self.root / "private"
        private.mkdir()
        other = self.root / "real"
        (other / "subdir").mkdir(parents=True)
        link = private / "redirect"
        try:
            link.symlink_to(other / "subdir", target_is_directory=True)
        except (OSError, NotImplementedError):
            return
        target = link / ".." / "review.json"
        with self.assertRaises(ValueError):
            create_template(target, CONFIRM)
        self.assertFalse((other / "review.json").exists())
        self.assertFalse((private / "review.json").exists())
        with self.assertRaises(ValueError):
            create_template(self.root / ".." / "private-review.json", CONFIRM)

    def test_cli_redacts_user_supplied_arguments_and_does_not_write_on_error(self):
        cases = [
            ["--output", str(self.output)],
            ["--output", str(self.output), "--confirm", CONFIRM, "SECRET-PNR-54321"],
            ["--output", str(self.output), "--confirm", "SECRET-ADDRESS"],
        ]
        for argv in cases:
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(main(argv), 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertNotIn(str(self.root), stderr.getvalue())
            self.assertNotIn("SECRET-", stderr.getvalue())
            self.assertFalse(self.output.exists())
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(main(["--output", str(self.output), "--confirm", CONFIRM]), 0)
        self.assertNotIn(str(self.root), stdout.getvalue())
        self.assertNotIn("GOLD-01", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
