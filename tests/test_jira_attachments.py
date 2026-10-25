"""EVD-13 synthetic tests. No corporate Jira attachments are committed."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from jira_attachments import (
    attachment_path, evidence_for_model, inspect_bytes, prepare, process,
)
from model_analysis import task_source
from storage import read_json, write_json


def zip_bytes(files):
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class JiraAttachmentIntakeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ccon-attachment-")
        self.root = Path(self.directory.name)
        self.attachments = [
            {"id": "1001", "filename": "evidence.json", "mimeType": "application/json",
             "content": "https://aerticket.atlassian.net/rest/api/3/attachment/content/1001"},
            {"id": "1002", "filename": "workflow.xml", "mimeType": "application/xml",
             "content": "https://aerticket.atlassian.net/rest/api/3/attachment/content/1002"},
            {"id": "1003", "filename": "flow.zip", "mimeType": "application/zip",
             "content": "https://aerticket.atlassian.net/rest/api/3/attachment/content/1003"},
            {"id": "1004", "filename": "requirements.pdf", "mimeType": "application/pdf",
             "content": "https://aerticket.atlassian.net/rest/api/3/attachment/content/1004"},
        ]
        self.issue = {"key": "CCON-5", "fingerprint": "jira-fp1",
                      "attachments": self.attachments, "links": []}
        self.save_context()

    def tearDown(self):
        self.directory.cleanup()

    def save_context(self):
        write_json(self.root / "data/jira_context.json",
                   {"complete": True, "issues": {"CCON-5": self.issue}})

    def save(self, ident, ext, content):
        path = attachment_path(self.root, "CCON-5", ident, ext)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_plan_uses_exact_jira_metadata_and_private_download_paths(self):
        plan = prepare(self.root, "CCON-5")
        self.assertEqual(len(plan["jobs"]), 4)
        self.assertTrue(plan["readOnlyBrowser"])
        self.assertEqual(plan["jobs"][0]["attachmentId"], "1001")
        self.assertEqual(Path(plan["jobs"][0]["saveAs"]),
                         attachment_path(self.root, "CCON-5", "1001", ".json"))
        self.assertTrue(plan["jobs"][0]["downloadUrl"].endswith("/1001"))
        self.assertEqual(process(self.root)["results"][0]["state"], "PENDING")
        for illegal in ("../CCON-5", "OTHER-2", "CCON-0/x"):
            with self.subTest(illegal=illegal), self.assertRaises(ValueError):
                attachment_path(self.root, illegal, "1001", ".json")

    def test_read_only_json_xml_zip_inspection_does_not_store_payload_values(self):
        prepare(self.root)
        self.save("1001", ".json",
                  b'{"TypeCode":"TO","passengerName":"SYNTHETIC_PERSON","rules":[1,2]}')
        self.save("1002", ".xml",
                  b'<Order><SegmentRefID>SEG1</SegmentRefID><SegmentRefID>SEG2</SegmentRefID></Order>')
        self.save("1003", ".zip", zip_bytes({
            "rest/request.json": '{"TypeCode":"SYNTHETIC_VALUE"}',
            "supplier/AFKL/response.xml": "<Reply><Price>syntheticPrice</Price></Reply>",
            "notes.txt": "unread private data",
        }))
        result = process(self.root)
        self.assertEqual([r["state"] for r in result["results"]],
                         ["STRUCTURE_ONLY", "STRUCTURE_ONLY", "STRUCTURE_ONLY", "PENDING"])
        reports = [read_json(self.root / "data/attachment_evidence/CCON-5" /
                             (str(i) + ".json")) for i in range(1001, 1004)]
        self.assertEqual(reports[0]["shape"]["rootFields"],
                         ["TypeCode", "passengerName", "rules"])
        self.assertEqual(reports[1]["shape"]["tagCounts"]["SegmentRefID"], 2)
        self.assertEqual(len(reports[2]["shape"]["parsedEntries"]), 2)
        serialized = json.dumps(reports)
        for secret in ("SYNTHETIC_PERSON", "SYNTHETIC_VALUE", "syntheticPrice",
                       "unread private data", "rest/request.json", "notes.txt"):
            self.assertNotIn(secret, serialized)
        self.assertIn("STRUCTURE_IS_NOT_VALUE_MAPPING_OR_BUSINESS_PROOF", serialized)
        source = task_source({"issues": {"CCON-5": self.issue}}, {"key": "CCON-5"},
                             "", root=self.root)
        self.assertEqual(len(source["attachmentEvidence"]), 3)
        self.assertNotIn("SYNTHETIC_PERSON", json.dumps(source))

    def test_pdf_is_explicitly_unread_and_never_proof(self):
        prepare(self.root)
        self.save("1004", ".pdf", b"%PDF-1.7\nsynthetic-internal-text")
        result = process(self.root)
        self.assertEqual(result["results"][-1]["state"], "PDF_TEXT_NOT_EXTRACTED")
        entry = evidence_for_model(self.root, "CCON-5", self.issue)[0]
        self.assertEqual(entry["format"], "PDF")
        self.assertIsNone(entry["shape"])

    def test_rejects_xml_entities_zip_traversal_and_signin_html(self):
        with self.assertRaisesRegex(ValueError, "XML_DTD_OR_ENTITY_FORBIDDEN"):
            inspect_bytes(b'<!DOCTYPE a [<!ENTITY x "unsafe">]><a>&x;</a>', ".xml")
        with self.assertRaisesRegex(ValueError, "UNSAFE_ZIP_PATH"):
            inspect_bytes(zip_bytes({"../escape.json": "{}"}), ".zip")
        with self.assertRaisesRegex(ValueError, "INVALID_JSON"):
            inspect_bytes(b"<html>log in</html>", ".json")
        with self.assertRaisesRegex(ValueError, "ZIP_UNPACKED_LIMIT"):
            inspect_bytes(zip_bytes({"huge.json": "A" * (9 * 1024 * 1024)}), ".zip")

    def test_stale_source_cannot_reuse_prior_attachment_manifest(self):
        prepare(self.root)
        self.save("1001", ".json", b'{"TypeCode":"TO"}')
        self.assertEqual(process(self.root)["results"][0]["state"], "STRUCTURE_ONLY")
        self.issue["fingerprint"] = "updated"
        self.save_context()
        self.assertEqual(process(self.root)["results"][0]["state"], "STALE")
        self.assertEqual(evidence_for_model(self.root, "CCON-5", self.issue), [])

    def test_symlink_and_unlisted_attachment_are_never_read(self):
        prepare(self.root)
        target = self.root / "outside.json"
        target.write_text('{"hidden":"secret"}')
        download = attachment_path(self.root, "CCON-5", "1001", ".json")
        download.parent.mkdir(parents=True, exist_ok=True)
        try:
            download.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink unsupported on runner")
        self.assertEqual(process(self.root)["results"][0]["state"], "PENDING")
        self.assertEqual(evidence_for_model(self.root, "CCON-5", self.issue), [])
        self.assertEqual(inspect_bytes(b"{}", ".json")["shape"]["rootType"], "dict")


if __name__ == "__main__":
    unittest.main()
