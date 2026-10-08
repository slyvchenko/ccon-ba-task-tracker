import json
import shutil
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from server import Desk, LocalServer, handler
from supplier_logs import ingest, logs_root, make_plan, read_json, write_json
from test_supplier_logs import bundle, FLOW, KIBANA


class LogAttachmentsTests(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.gettempdir()).resolve()
        self.root = self.parent / ('cca-' + uuid.uuid4().hex[:12])
        self.root.mkdir()
        self.desk = Desk(self.root)
        analysis = {'signal': 'WRITE', 'needsEmail': True, 'contextFingerprint': 'current'}
        write_json(self.desk.inbox / 'CCON_BA_Snapshot.json', {'generatedAt': '2026-10-08T05:00:00Z', 'tasks': [
            {'key': key, 'summary': 'Airtuerk. retrievePNR. TOURCONEX_INVALID_RECORD_LOCATOR', 'analysis': analysis}
            for key in ('CCON-1', 'CCON-2', 'CCON-3')]})
        self.desk.import_snapshot()
        write_json(self.root / 'data/jira_context.json', {'complete': True, 'issues': {
            key: {'fingerprint': 'current', 'description': KIBANA} for key in ('CCON-1', 'CCON-2', 'CCON-3')}})
        source = self.root / 'source.zip'
        source.write_bytes(bundle())
        make_plan(self.root)
        self.entries = {key: ingest(self.root, key, FLOW, source) for key in ('CCON-1', 'CCON-2')}
        self.server = LocalServer(('127.0.0.1', 0), handler(self.desk))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        target = self.root.resolve()
        assert target.is_relative_to(self.parent) and target.name.startswith('cca-')
        shutil.rmtree(target)

    def request(self, path, data=None, origin=None):
        request = Request(self.base + path, data=None if data is None else json.dumps(data).encode(),
                          headers={'Origin': origin or self.base, 'Content-Type': 'application/json'})
        return build_opener(ProxyHandler({})).open(request)

    def test_task_scoped_catalog_and_exact_zip_download(self):
        before = self.desk.view()['tasks']
        with self.request('/api/logs/CCON-1') as response:
            catalog = json.load(response)
        self.assertEqual(len(catalog['items']), 1)
        item = catalog['items'][0]
        self.assertTrue(item['filename'].endswith('-CCON-1.zip'))
        self.assertEqual(item['method'], 'doByLocatorPullPnr')
        self.assertFalse(item['stale'])
        with self.request(item['downloadUrl']) as response:
            self.assertEqual(response.headers['Content-Type'], 'application/zip')
            self.assertIn('attachment;', response.headers['Content-Disposition'])
            self.assertEqual(response.read(), (logs_root(self.root) / self.entries['CCON-1']['archiveRelativePath']).read_bytes())
        with self.request('/api/logs') as response:
            all_logs = json.load(response)
        self.assertTrue(all_logs['CCON-2']['items'][0]['filename'].endswith('-CCON-2.zip'))
        self.assertEqual(all_logs['CCON-3']['items'], [])
        self.assertEqual(self.desk.view()['tasks'], before)

    def test_missing_id_and_partially_prepared_examples_are_explicit(self):
        context = read_json(self.root / 'data/jira_context.json')
        second_flow = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
        context['issues']['CCON-1']['description'] += ' ' + KIBANA.replace(FLOW, second_flow)
        context['issues']['CCON-3']['description'] = 'No log reference yet'
        write_json(self.root / 'data/jira_context.json', context)
        with self.request('/api/logs') as response:
            catalog = json.load(response)
        self.assertEqual(catalog['CCON-1']['pendingCount'], 1)
        self.assertEqual(len(catalog['CCON-1']['items']), 1)
        self.assertIn('cconFlowId', catalog['CCON-3']['emptyMessage'])

    def test_download_does_not_follow_index_into_another_task_or_original_zip(self):
        directory = logs_root(self.root)
        index = read_json(directory / 'index.json')
        entry = index['CCON-1/' + FLOW]
        for path in (self.entries['CCON-2']['archiveRelativePath'],
                     str(Path(entry['archiveRelativePath']).parent / 'original.zip'), '../outside.zip'):
            entry['archiveRelativePath'] = path
            write_json(directory / 'index.json', index)
            with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                self.request('/api/logs/CCON-1/' + FLOW + '/download')
            self.assertEqual(error.exception.code, 400)

    def test_changed_context_is_labelled_and_damaged_zip_is_rejected(self):
        context = read_json(self.root / 'data/jira_context.json')
        context['issues']['CCON-1']['fingerprint'] = 'new'
        write_json(self.root / 'data/jira_context.json', context)
        with self.request('/api/logs/CCON-1') as response:
            self.assertTrue(json.load(response)['items'][0]['stale'])
        archive = logs_root(self.root) / self.entries['CCON-1']['archiveRelativePath']
        archive.write_bytes(b'corrupted')
        with self.assertRaises(HTTPError) as error:
            self.request('/api/logs/CCON-1/' + FLOW + '/download')
        self.assertEqual(error.exception.code, 400)

    def test_folder_opens_only_the_selected_task_and_rejects_external_origin(self):
        with patch('log_attachments.os.startfile', create=True) as launch:
            with self.request('/api/logs/CCON-1/folder', {}) as response:
                self.assertIn('message', json.load(response))
            launch.assert_called_once_with(str(logs_root(self.root) / 'CCON-1'))
            with self.assertRaises(HTTPError) as error:
                self.request('/api/logs/CCON-2/folder', {}, 'https://outside.example')
            self.assertEqual(error.exception.code, 403)
            self.assertEqual(launch.call_count, 1)

    def test_unknown_task_and_invalid_flow_are_rejected(self):
        for path in ('/api/logs/CCON-999', '/api/logs/CCON-1/%2e%2e/download', '/api/logs/%2e%2e'):
            with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                self.request(path)
            self.assertEqual(error.exception.code, 400)
