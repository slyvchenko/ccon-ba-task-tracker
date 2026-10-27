"""Synthetic local document cross-check tests. No corporate file bytes."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from ba_quality_gate import claim_audit, quality_gate, source_registry
from confluence_local import (linked_pages, page_ref, page_path, prepare as wiki_prepare,
                               process as wiki_process, current_sources as wiki_sources)
from jira_attachments import (prepare as jira_prepare, process as jira_process,
                              attachment_path)
from local_document_text import extract_text
from local_source_audit import local_sources
from model_analysis import task_source
from storage import write_json

URL = "https://aerticket.atlassian.net/wiki/spaces/CCON/pages/98765/Decision"
FILE = "https://aerticket.atlassian.net/rest/api/3/attachment/content/1001"
KEY = "CCON-5"


def zip_content(files):
    buf = io.BytesIO()
    with ZipFile(buf, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return buf.getvalue()


class LocalCrossCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ccon-local-source-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.issue = {
            "key": KEY, "fingerprint": "fingerprint-1",
            "summary": "AF/KL. rules",
            "description": "Need compare TypeCode=TO",
            "descriptionAdf": {"type": "doc", "content": [{
                "type": "paragraph", "content": [{
                    "type": "text", "text": "Contract", "marks": [{
                        "type": "link", "attrs": {"href": URL}}]}]}]},
            "attachments": [{"id": "1001", "filename": "contract.json",
                             "content": FILE}],
            "comments": [],
        }
        self.sync()

    def sync(self):
        write_json(self.root / "data/jira_context.json",
                   {"complete": True, "issues": {KEY: self.issue}})

    def local(self, name, content):
        file = attachment_path(self.root, KEY, "1001", ".json") if name == "jira" else page_path(self.root, KEY, "98765")
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)
        return file

    def prepare_all(self):
        jira_prepare(self.root, KEY)
        self.local("jira", b'{"rule":"If TypeCode=no_code then TypeCode=TO",'
                           b'"name":"SYNTHETIC_CUSTOMER"}')
        self.assertEqual(jira_process(self.root, KEY)["results"][0]["state"], "STRUCTURE_ONLY")
        plan = wiki_prepare(self.root, KEY)
        self.assertEqual(len(plan["jobs"]), 1)
        self.assertEqual(plan["jobs"][0]["url"], URL)
        self.local("wiki", b"<html><head><title>ignore</title></head><body>"
                           b"<p>If TypeCode=no_code then TypeCode=TO</p>"
                           b"<script>SYNTHETIC_SECRET</script></body></html>")
        self.assertEqual(wiki_process(self.root, KEY)["results"][0]["status"], "LOCAL_TEXT_EXTRACTED")

    def test_only_current_referenced_sources_are_proof_candidates(self):
        self.prepare_all()
        found, audit = local_sources(self.root, KEY, self.issue)
        self.assertEqual(set(found), {URL, FILE})
        self.assertEqual(audit["verifiedLocalSourceCount"], 2)
        self.assertEqual(audit["notVerifiedCount"], 0)
        self.assertEqual(audit["sourceConfidence"], "TEXT_OCCURRENCE_NOT_BUSINESS_TRUTH")
        text = json.dumps(audit)
        self.assertNotIn("SYNTHETIC_CUSTOMER", text)
        self.assertNotIn("SYNTHETIC_SECRET", text)
        self.assertNotIn("no_code", text)
        briefing = {"confirmedFacts": [{
            "sourceUrl": URL, "sourceExcerpt": "If TypeCode=no_code then TypeCode=TO"}],
            "rules": []}
        claims, failures = claim_audit(briefing, {
            **source_registry(self.issue), **found})
        self.assertEqual(claims[0]["sourceState"], "TEXT_PRESENT_NOT_FACT_PROVEN")
        self.assertEqual(failures, [])
        report = task_source({"issues": {KEY: self.issue}}, {"key": KEY}, "", root=self.root)
        self.assertEqual(report["linkedDocumentAudit"]["verifiedLocalSourceCount"], 2)
        self.assertNotIn("SYNTHETIC_CUSTOMER", json.dumps(report))
        self.assertNotIn("If TypeCode=no_code then TypeCode=TO", json.dumps(report))

    def test_url_only_or_tampered_file_does_not_validate_claim(self):
        self.prepare_all()
        file = page_path(self.root, KEY, "98765")
        file.write_bytes(b"<html><p>Not the validated content</p></html>")
        found, audit = local_sources(self.root, KEY, self.issue)
        self.assertNotIn(URL, found)
        self.assertEqual(audit["notVerifiedCount"], 1)
        claims, failures = claim_audit(
            {"confirmedFacts": [{"sourceUrl": URL, "sourceExcerpt": "If TypeCode=no_code then TypeCode=TO"}]},
            {**source_registry(self.issue), **found})
        self.assertEqual(claims[0]["sourceState"], "SOURCE_NOT_READ")
        self.assertTrue(failures)
        self.issue["fingerprint"] = "new-fingerprint"
        self.sync()
        found, audit = local_sources(self.root, KEY, self.issue)
        self.assertEqual(found, {})
        self.assertEqual(audit["verifiedLocalSourceCount"], 0)

    def test_wrong_confluence_host_unlinked_page_and_signin_rejected(self):
        for wrong in ("https://evil.test/wiki/spaces/CCON/pages/98765/Decision",
                      "https://aerticket.atlassian.net/wiki/spaces/CCON/pages/98765?token=bad",
                      "http://aerticket.atlassian.net/wiki/spaces/CCON/pages/98765"):
            self.assertIsNone(page_ref(wrong))
        self.assertEqual(linked_pages(self.issue), {"98765": URL})
        wiki_prepare(self.root, KEY)
        self.local("wiki", b"<html><body><p>Sign in to Confluence</p></body></html>")
        self.assertEqual(wiki_process(self.root, KEY)["results"][0]["status"], "FAILED")
        self.assertEqual(wiki_sources(self.root, KEY, self.issue), ({}, []))

    def test_comment_adf_hyperlink_is_discovered_without_visible_url(self):
        self.issue["descriptionAdf"]={"type":"doc","content":[]}
        self.issue["comments"]=[{"body":"See Confluence decision",
                                 "bodyAdf":{"type":"doc","content":[{
                                     "type":"paragraph","content":[{
                                         "type":"text","text":"Decision notes",
                                         "marks":[{"type":"link","attrs":{"href":URL}}]
                                     }]}]}}]
        self.assertEqual(linked_pages(self.issue),{"98765":URL})

    def test_branded_login_form_never_counts_as_verified_wiki_source(self):
        wiki_prepare(self.root, KEY)
        self.local("wiki",(
            b"<html><body><header>Atlassian workspace</header>"
            b"<section><h1>Log in to continue</h1>"
            b"<form><input name='account'><input type='password'></form>"
            b"</section></body></html>"))
        self.assertEqual(wiki_process(self.root, KEY)["results"][0]["status"],"FAILED")
        self.assertEqual(wiki_sources(self.root, KEY, self.issue),({},[]))

    def test_literal_login_markup_in_script_does_not_hide_valid_page(self):
        wiki_prepare(self.root, KEY)
        self.local("wiki",(
            b"<html><body><p>Valid decision text</p>"
            b"<script>const template='<form><input type=password></form>';</script>"
            b"<!-- <form><input type=password></form> -->"
            b"<form><input type=text></form><input type=password>"
            b"</body></html>"))
        self.assertEqual(wiki_process(self.root, KEY)["results"][0]["status"],
                         "LOCAL_TEXT_EXTRACTED")

    def test_value_variants_are_cautions_not_proof_and_no_values_leaked(self):
        self.prepare_all()
        self.local("wiki", b"<html><p>TypeCode=AB</p><p>TypeCode=TO</p></html>")
        self.assertEqual(wiki_process(self.root, KEY)["results"][0]["status"], "LOCAL_TEXT_EXTRACTED")
        found, audit = local_sources(self.root, KEY, self.issue,
                                    jira_source="TypeCode=NO_CODE")
        self.assertEqual(audit["variantCandidates"][0]["field"], "TypeCode")
        self.assertEqual(audit["variantCandidates"][0]["state"],
                         "POTENTIAL_DIFFERENT_ENUM_VALUE_REVIEW")
        self.assertNotIn("NO_CODE", json.dumps(audit))
        self.assertEqual(len(found), 2)

    def test_local_pdf_parser_capability_and_fail_closed(self):
        class FakePage:
            def extract_text(self):
                return "Supplier says TypeCode=TO"
        class FakeReader:
            def __init__(self, stream, strict):
                self.pages = [FakePage()]
                self.is_encrypted = False
        status, text, report = extract_text(b"%PDF-1.7 fake", ".pdf", pdf_reader=FakeReader)
        self.assertEqual(status, "LOCAL_TEXT_EXTRACTED")
        self.assertIn("TypeCode=TO", text)
        self.assertEqual(report["pageCount"], 1)
        class TooManyPages(FakeReader):
            def __init__(self, stream, strict):
                self.pages = [FakePage()] * 13
                self.is_encrypted = False
        self.assertEqual(extract_text(b"%PDF-", ".pdf", pdf_reader=TooManyPages)[0],
                         "TEXT_UNAVAILABLE")
        self.assertEqual(extract_text(b"<html>login</html>", ".pdf")[0], "TEXT_UNAVAILABLE")

    def test_safe_zip_extraction_selected_supported_text_only(self):
        raw = zip_content({"docs/contract.json": b'{"TypeCode":"TO"}',
                           "docs/rules.xml": b"<Rule><Value>TYPE_OK</Value></Rule>",
                           "docs/image.png": b"SECRET_IGNORED",
                           "nested/embedded.zip": b"SYNTHETIC_INNER"})
        status, text, meta = extract_text(raw, ".zip")
        self.assertEqual(status, "LOCAL_TEXT_EXTRACTED")
        self.assertEqual(meta["parsedTextEntries"], 2)
        self.assertNotIn("SECRET_IGNORED", text)
        self.assertNotIn("SYNTHETIC_INNER", text)
        bad = zip_content({"../outside.json": "{}"})
        self.assertEqual(extract_text(bad, ".zip")[0], "TEXT_UNAVAILABLE")
        unsafe = zip_content({"a.xml": '<!DOCTYPE e><e />'})
        self.assertEqual(extract_text(unsafe, ".zip")[0], "TEXT_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
