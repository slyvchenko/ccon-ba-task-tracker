import io
import json
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile

from server import Desk
from supplier_logs import (flow_references, inspect_bundle, make_plan, ingest,
                           read_json, write_json, logs_root, verified_method)

FLOW = '11111111-2222-4333-8444-555555555555'
KIBANA = "http://192.168.197.246:5601/app/kibana#/discover/saved?_a=(filters:!((meta:(key:cconFlowId,params:(query:'" + FLOW + "',type:phrase),value:'" + FLOW + "'),query:(match:(cconFlowId:(query:'" + FLOW + "'))))))"


def bundle(extra=None, altered=False, reverse=False):
    files = [
        ('supplier/Airtuerk/111-retrievePNR-doByLocatorPullPnr-10-response-body.xml', b'<Response><providerError><code>TOURCONEX_INVALID_RECORD_LOCATOR</code><message>Invalid record locator</message></providerError></Response>'),
        ('supplier/Airtuerk/111-retrievePNR-doByLocatorPullPnr-10-request-body.xml', b'<Request>changed</Request>' if altered else b'<Request/>'),
        ('supplier/Airtuerk/112-verify-fare-doVerifyAvailableFare-2-response-body.xml', b'<Response/>'),
        ('supplier/Airtuerk/112-verify-fare-doVerifyAvailableFare-2-request-body.xml', b'<Request/>'),
        ('supplier/Airtuerk/111-retrievePNR-rq-rs-10.txt', b'discard'),
        ('supplier/biletBank/111-pnrs-Login-0-request-body.xml', b'<Secret/>'),
        ('rest/request.json', b'{}'),
    ]
    files += extra or []
    stream = io.BytesIO()
    with ZipFile(stream, 'w') as archive:
        for name, data in reversed(files) if reverse else files:
            archive.writestr(name, data)
    return stream.getvalue()


class SupplierLogsTests(unittest.TestCase):
    def test_safe_links_and_flow_filter(self):
        link = 'https://eur02.safelinks.protection.outlook.com/?url=' + quote(KIBANA, safe='')
        issue = {'descriptionAdf': {'type': 'doc', 'content': [{'type': 'text', 'marks': [{'type': 'link', 'attrs': {'href': link}}]}]}}
        self.assertEqual(flow_references(issue), [{'flowId': FLOW, 'sourceUrl': KIBANA}])
        self.assertEqual(flow_references({'description': KIBANA.replace('key:cconFlowId', 'key:otherId')}), [])
        self.assertEqual(flow_references({'description': KIBANA.replace('192.168.197.246', 'example.com')}), [])

    def test_numeric_order_pairs_native_method_and_exact_bytes(self):
        result = inspect_bundle(bundle(), ['Airtuerk'], 'Airtuerk. retrievePNR. TOURCONEX_INVALID_RECORD_LOCATOR')
        self.assertEqual([item['output'] for item in result['files']], ['01-doVerifyAvailableFareRQ.xml', '01-doVerifyAvailableFareRS.xml', '02-doByLocatorPullPnrRQ.xml', '02-doByLocatorPullPnrRS.xml'])
        self.assertEqual(result['preferredMethod'], 'doByLocatorPullPnr')
        self.assertEqual(result['files'][0]['data'], b'<Request/>')
        self.assertEqual(result['exchangeCount'], 2)
        self.assertFalse(result['warnings'])

    def test_unknown_method_is_reported_not_invented(self):
        result = inspect_bundle(bundle(), ['Airtuerk'], 'Airtuerk. retrievePNR. OTHER_ERROR')
        self.assertIsNone(result['preferredMethod'])
        self.assertTrue(result['warnings'])

    def test_missing_response_is_preserved_with_warning(self):
        result = inspect_bundle(bundle([('supplier/Airtuerk/123-pnrs-doRetrieve-20-request-body.xml', b'<Request/>')]), ['Airtuerk'], 'Airtuerk. retrievePNR. TOURCONEX_INVALID_RECORD_LOCATOR')
        self.assertEqual(len(result['files']), 5)
        self.assertTrue(any(w.get('seq') == 20 for w in result['warnings']))

    def test_unsafe_and_ambiguous_bundles_are_rejected(self):
        for extra in [('../outside.xml', b'<x/>'), ('supplier/Airtuerk/123-pnrs-otherMethod-10-request-body.xml', b'<x/>'), ('supplier/Airtuerk/unrecognized.xml', b'<x/>')]:
            with self.subTest(extra=extra[0]), self.assertRaises(ValueError):
                inspect_bundle(bundle([extra]), ['Airtuerk'], 'Airtuerk')
        with self.assertRaises(ValueError):
            inspect_bundle(b'<html>Sign in</html>', ['Airtuerk'], 'Airtuerk')
        with self.assertRaises(ValueError):
            inspect_bundle(bundle(), ['AirFranceKLM'], 'AF/KL')


class LogPipelineTests(unittest.TestCase):
    def setUp(self):
        self.test_parent = Path(tempfile.gettempdir()).resolve()
        self.root = self.test_parent / ('ccl-' + uuid.uuid4().hex[:12])
        self.root.mkdir()
        self.desk = Desk(self.root)
        analysis = {'signal': 'WRITE', 'needsEmail': True, 'contextFingerprint': 'current'}
        self.doc = {'generatedAt': '2026-10-08T05:00:00+00:00', 'tasks': [{'key': 'CCON-1', 'summary': 'Airtuerk. retrievePNR. TOURCONEX_INVALID_RECORD_LOCATOR', 'analysis': analysis}]}
        write_json(self.desk.inbox / 'CCON_BA_Snapshot.json', self.doc)
        self.desk.import_snapshot()
        write_json(self.root / 'data/jira_context.json', {'complete': True, 'issues': {'CCON-1': {'fingerprint': 'current', 'description': KIBANA}}})
        self.source = self.root / 'download.zip'
        self.source.write_bytes(bundle())

    def tearDown(self):
        target = self.root.resolve()
        assert target.is_relative_to(self.test_parent) and target.name.startswith('ccl-')
        shutil.rmtree(target)

    def test_eligible_plan_ingest_cache_and_immutable_versions(self):
        plan = make_plan(self.root)
        self.assertEqual(len(plan['jobs']), 1)
        self.assertFalse(plan['jobs'][0]['cached'])
        before = self.desk.view()['tasks']
        first = ingest(self.root, 'CCON-1', FLOW, self.source)
        self.assertEqual(verified_method(self.root, 'CCON-1', 'current'), 'doByLocatorPullPnr')
        self.assertIsNone(verified_method(self.root, 'CCON-1', 'old'))
        archive = logs_root(self.root) / first['archiveRelativePath']
        self.assertTrue(archive.exists())
        self.assertEqual(self.desk.view()['tasks'], before)
        with ZipFile(archive) as zipped:
            self.assertEqual(len(zipped.namelist()), 4)
            self.assertTrue(all(name.endswith('.xml') for name in zipped.namelist()))
        self.assertTrue(make_plan(self.root)['jobs'][0]['cached'])
        # ZIP entry ordering changes, but identical XML is not duplicated.
        self.source.write_bytes(bundle(reverse=True))
        second = ingest(self.root, 'CCON-1', FLOW, self.source)
        self.assertEqual(first['archiveRelativePath'], second['archiveRelativePath'])
        self.source.write_bytes(bundle(altered=True))
        third = ingest(self.root, 'CCON-1', FLOW, self.source)
        self.assertNotEqual(first['archiveRelativePath'], third['archiveRelativePath'])
        self.assertTrue(archive.exists())

    def test_manual_decisions_and_stale_analysis_skip_downloads(self):
        self.desk.save('CCON-1', {'manualStatus': 'DONE', 'note': 'keep'})
        self.assertFalse(make_plan(self.root)['jobs'])
        self.desk.save('CCON-1', {'manualStatus': 'AUTO', 'note': 'keep'})
        context = read_json(self.root / 'data/jira_context.json')
        context['issues']['CCON-1']['fingerprint'] = 'new'
        write_json(self.root / 'data/jira_context.json', context)
        self.assertEqual(make_plan(self.root)['skipped'][0]['reason'], 'stale_analysis')

    def test_new_analysis_can_plan_before_final_import(self):
        source = self.root / 'analysis.json'
        write_json(source, {'analyses': {'CCON-1': self.doc['tasks'][0]['analysis']}})
        self.assertEqual(len(make_plan(self.root, source)['jobs']), 1)
        write_json(source, {'analyses': {'CCON-1': {'signal': 'READY', 'needsEmail': False}}})
        self.assertFalse(make_plan(self.root, source)['jobs'])

    def test_changed_context_and_damaged_cache_are_not_silently_used(self):
        make_plan(self.root)
        entry = ingest(self.root, 'CCON-1', FLOW, self.source)
        archive = logs_root(self.root) / entry['archiveRelativePath']
        archive.write_bytes(b'broken')
        self.assertFalse(make_plan(self.root)['jobs'][0]['cached'])
        with self.assertRaises(ValueError):
            ingest(self.root, 'CCON-1', FLOW, self.source)
        context = read_json(self.root / 'data/jira_context.json')
        context['issues']['CCON-1']['fingerprint'] = 'changed'
        write_json(self.root / 'data/jira_context.json', context)
        with self.assertRaises(ValueError):
            ingest(self.root, 'CCON-1', FLOW, self.source)

    def test_broken_log_metadata_does_not_block_analysis_import(self):
        (self.root / 'data/log_plan.json').write_text('{partial', encoding='utf-8')
        self.assertIsNone(verified_method(self.root, 'CCON-1', 'current'))
