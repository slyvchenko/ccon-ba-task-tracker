import json
import os
import shutil
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from zipfile import ZipFile

from desk_store import Desk
from local_downloads import download_path, prepare, process
from log_attachments import log_catalog, download_archive
from supplier_logs import logs_root
from storage import write_json, read_json
from test_supplier_logs import bundle, FLOW, KIBANA

SECOND = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'


class LocalBrowserHandoffTests(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.gettempdir()).resolve()
        self.root = self.parent / ('handoff-' + uuid.uuid4().hex[:12])
        self.root.mkdir()
        self.desk = Desk(self.root)
        write_json(self.desk.inbox / "CCON_BA_Snapshot.json", {
            "generatedAt": "2026-10-24T16:00:00+00:00",
            "tasks": [
                {"key": "CCON-1", "summary": "Airtuerk. retrievePNR. TOURCONEX_INVALID_RECORD_LOCATOR",
                 "analysis": {"signal": "READY", "needsEmail": False, "contextFingerprint": "current"}},
                {"key": "CCON-2", "summary": "Airtuerk. retrievePNR. same",
                 "analysis": {"signal": "READY", "needsEmail": False, "contextFingerprint": "current"}},
            ]
        })
        self.desk.import_snapshot()
        write_json(self.root / 'data/jira_context.json', {
            "complete": True,
            "issues": {
                "CCON-1": {"fingerprint": "current", "description": KIBANA},
                "CCON-2": {"fingerprint": "current", "description": KIBANA.replace(FLOW, SECOND)},
            },
        })

    def tearDown(self):
        target = self.root.resolve()
        assert target.is_relative_to(self.parent) and target.name.startswith('handoff-')
        shutil.rmtree(target)

    def _save(self, key='CCON-1', flow=FLOW, raw=None):
        path = download_path(self.root, key, flow)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bundle() if raw is None else raw)
        return path

    def test_browser_handoff_creates_issue_flow_bound_local_plan(self):
        plan = prepare(self.root)
        self.assertEqual(len(plan["jobs"]), 2)
        entry = next(j for j in plan["jobs"] if j["issueKey"] == "CCON-1")
        self.assertEqual(entry["flowId"], FLOW)
        self.assertEqual(entry["supplier"], "Airtuerk")
        self.assertEqual(Path(entry["saveAs"]), download_path(self.root, "CCON-1", FLOW))
        self.assertIn("logs-download", entry["downloadUrl"])
        self.assertTrue((self.root / "data/browser_handoff.json").exists())
        self.assertEqual(process(self.root)["pendingCount"], 2)
        self.assertEqual(log_catalog(self.desk, "CCON-1")["state"], "PENDING")

    def test_prepared_download_produces_supplier_only_and_evidence(self):
        prepare(self.root)
        self._save()
        result = process(self.root, "CCON-1")
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["readyCount"], 1)
        catalog = log_catalog(self.desk, "CCON-1")
        self.assertEqual(catalog["state"], "READY")
        self.assertEqual(catalog["flows"][0]["state"], "READY")
        self.assertEqual(log_catalog(self.desk, "CCON-2")["state"], "PENDING")
        filename, data = download_archive(self.desk, "CCON-1", FLOW)
        self.assertIn("CCON-1.zip", filename)
        from io import BytesIO
        with ZipFile(BytesIO(data)) as z:
            self.assertEqual(len(z.namelist()), 4)
            self.assertTrue(all(n.endswith(".xml") for n in z.namelist()))
            self.assertFalse(any("/rest/" in n or "biletBank" in n for n in z.namelist()))
        evidence = read_json(self.root / "data/evidence/CCON-1" / (FLOW + ".json"))
        self.assertTrue(evidence["counts"]["rest"])
        self.assertTrue(evidence["counts"]["supplier"])

    def test_wrong_filename_or_other_task_does_not_get_silently_assigned(self):
        prepare(self.root)
        self._save("CCON-2", SECOND)
        self.assertEqual(process(self.root, "CCON-1")["pendingCount"], 1)
        self.assertEqual(log_catalog(self.desk, "CCON-1")["items"], [])
        self.assertEqual(process(self.root, "CCON-2")["readyCount"], 1)

    def test_signin_html_not_mistaken_for_zip_and_state_is_failed(self):
        prepare(self.root)
        self._save(raw=b"<!DOCTYPE html><title>Sign in</title>")
        result = process(self.root, "CCON-1")
        self.assertEqual(result["failedCount"], 1)
        self.assertEqual(result["results"][0]["reasonCode"], "NOT_ZIP_SIGNIN_OR_ERROR_PAGE")
        catalog = log_catalog(self.desk, "CCON-1")
        self.assertEqual(catalog["state"], "FAILED")
        self.assertEqual(catalog["items"], [])

    def test_old_file_is_not_reused_after_fresh_plan(self):
        prepare(self.root)
        old = self._save()
        now = time.time()
        os.utime(old, (now - 3600, now - 3600))
        result = process(self.root, "CCON-1")
        self.assertEqual(result["results"][0]["reasonCode"], "OLD_DOWNLOAD")
        self.assertEqual(log_catalog(self.desk, "CCON-1")["state"], "FAILED")

    def test_old_context_leaves_pending_stale_and_download_blocked(self):
        prepare(self.root)
        self._save()
        context = read_json(self.root / "data/jira_context.json")
        context["issues"]["CCON-1"]["fingerprint"] = "new"
        write_json(self.root / "data/jira_context.json", context)
        result = process(self.root, "CCON-1")
        self.assertEqual(result["results"][0]["state"], "STALE")
        self.assertEqual(log_catalog(self.desk, "CCON-1")["state"], "PENDING")
        self.assertEqual(log_catalog(self.desk, "CCON-1")["items"], [])

    def test_damaged_cached_zip_fails_checksum_check(self):
        prepare(self.root)
        self._save()
        process(self.root, "CCON-1")
        plan = prepare(self.root, "CCON-1")
        self.assertTrue(plan["jobs"][0]["cached"])
        catalog = log_catalog(self.desk, "CCON-1")
        path = logs_root(self.root) / read_json(logs_root(self.root) / 'index.json')['CCON-1/' + FLOW]['archiveRelativePath']
        path.write_bytes(b"corrupted")
        result = process(self.root, "CCON-1")
        self.assertEqual(result["results"][0]["reasonCode"], "ARCHIVE_INTEGRITY_FAILED")
        self.assertEqual(log_catalog(self.desk, "CCON-1")["state"], "FAILED")

    def test_manual_done_does_not_prevent_export_for_task(self):
        self.desk.save('CCON-1', {'manualStatus': 'DONE', 'note': 'completed'})
        plan = prepare(self.root, "CCON-1")
        self.assertEqual(len(plan["jobs"]), 1)
        self._save()
        self.assertEqual(process(self.root, "CCON-1")["readyCount"], 1)
        self.assertEqual(self.desk.view()["tasks"][0]["note"], 'completed')

    def test_download_path_rejects_traversal(self):
        for key, flow in (("../CCON-1", FLOW), ("CCON-1", "../invalid"), ("CCON-1", FLOW.upper())):
            with self.subTest(key=key, flow=flow), self.assertRaises(ValueError):
                download_path(self.root, key, flow)


if __name__ == "__main__":
    unittest.main()
