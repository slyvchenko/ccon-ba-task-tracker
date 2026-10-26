"""Local opt-in aggregate privacy, no task IDs and no automatic rank mutation."""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from local_handoff_metrics import (
    CONSENT, summary, record_handoff, record_correction, _path
)


class LocalMetricsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-ba-metrics-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.secret = "CCON-1234 PRIVATE-SUPPLIER-TOKEN"
        (self.root / "ba_state.db").write_text(self.secret, encoding="utf-8")

    def test_summary_does_not_initialize_or_modify_app_state(self):
        before = (self.root / "ba_state.db").read_bytes()
        result = summary(self.root)
        self.assertEqual(result["handoffByArchetype"]["ERROR_TRIAGE"]["count"], 0)
        self.assertIsNone(result["handoffByArchetype"]["ERROR_TRIAGE"]["avgSeconds"])
        self.assertFalse((self.root / "data").exists())
        self.assertEqual(before, (self.root / "ba_state.db").read_bytes())
        self.assertFalse(result["cloudTelemetry"])
        self.assertFalse(result["noAutomaticPriorityChanges"])

    def test_manual_handoff_and_wrong_priority_feedback_are_aggregate_only(self):
        record_handoff(self.root, "ERROR_TRIAGE", 240, CONSENT)
        record_handoff(self.root, "ERROR_TRIAGE", 360, CONSENT)
        record_handoff(self.root, "SUPPLIER_QUESTION", 600, CONSENT)
        record_correction(self.root, "LOW", "HIGH", "URGENCY", CONSENT)
        record_correction(self.root, "HIGH", "MEDIUM", "STALE_CONTEXT", CONSENT)
        report=summary(self.root)
        self.assertEqual(report["handoffByArchetype"]["ERROR_TRIAGE"],
                         {"count":2,"avgSeconds":300})
        self.assertEqual(report["handoffByArchetype"]["SUPPLIER_QUESTION"],
                         {"count":1,"avgSeconds":600})
        self.assertEqual(report["wrongPriorityReasons"]["URGENCY"],1)
        self.assertEqual(report["manualBandCorrections"]["LOW_TO_HIGH"],1)
        self.assertEqual(report["manualBandCorrections"]["HIGH_TO_MEDIUM"],1)
        serialized=json.dumps(report)
        raw=_path(self.root).read_text(encoding="utf-8")
        for secret in (self.secret,"CCON-1234","PRIVATE-SUPPLIER",str(self.root),
                       "task_key","email","phone","timestamp","jiraStatus"):
            self.assertNotIn(secret,raw)
            self.assertNotIn(secret,serialized)
        self.assertEqual((self.root/"ba_state.db").read_text(),self.secret)
        if os.name!="nt":
            self.assertEqual(stat.S_IMODE(_path(self.root).stat().st_mode),0o600)

    def test_records_require_explicit_optin_and_valid_category(self):
        for name,seconds,consent in [
            ("ERROR_TRIAGE",12,""),("INVALID",10,CONSENT),
            ("REBOOKING",0,CONSENT),("ERROR_TRIAGE",28801,CONSENT),
            ("ERROR_TRIAGE",True,CONSENT)]:
            with self.subTest(name=name,seconds=seconds),self.assertRaises(ValueError):
                record_handoff(self.root,name,seconds,consent)
        for b,a,reason,consent in [
            ("HIGH","HIGH","URGENCY",CONSENT),
            ("MEDIUM","HIGH","NEW_UNKNOWN",CONSENT),
            ("LOW","HIGH","URGENCY","")
        ]:
            with self.assertRaises(ValueError):
                record_correction(self.root,b,a,reason,consent)
        self.assertFalse((self.root/"data").exists())

    def test_symlink_private_metrics_dir_is_not_followed(self):
        outside=self.root/"external"
        outside.mkdir()
        (self.root/"data").mkdir()
        try:
            (self.root/"data"/"private_metrics").symlink_to(
                outside,target_is_directory=True)
        except (OSError,NotImplementedError):
            return
        with self.assertRaises(ValueError):
            record_handoff(self.root,"API_ANALYSIS",45,CONSENT)
        self.assertEqual(list(outside.iterdir()), [])

    def test_private_directory_never_relaxes_existing_permissions(self):
        record_handoff(self.root,"EMAIL_HANDOFF",40,CONSENT)
        private=self.root/"data"/"private_metrics"
        if os.name=="nt":
            self.assertFalse(summary(self.root)["windowsAclVerified"])
            return
        private.chmod(0o755)
        with self.assertRaises(ValueError):
            summary(self.root)
        with self.assertRaises(ValueError):
            record_handoff(self.root,"EMAIL_HANDOFF",50,CONSENT)
        self.assertEqual(_path(self.root,create=False) if False else private.stat().st_mode & 0o777,
                         0o755)


if __name__ == "__main__":
    unittest.main()
