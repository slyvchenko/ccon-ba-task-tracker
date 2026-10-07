import json
import copy
import shutil
import uuid
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError
from server import Desk, handler

class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent / ('test-data-' + uuid.uuid4().hex)
        self.root.mkdir()
        self.desk = Desk(self.root)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.desk))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.doc = {'generatedAt': '2026-10-06T12:00:00Z', 'tasks': [
            {'key': 'CCON-1', 'summary': 'Task one', 'aiStatus': 'WAITING INPUT'},
            {'key': 'CCON-2', 'summary': 'Task two'}]}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        target = self.root.resolve()
        assert target.is_relative_to(Path(__file__).resolve().parent) and target.name.startswith('test-data-')
        shutil.rmtree(target)

    def request(self, path, data=None, origin=None):
        req = Request(self.base+path, data=None if data is None else json.dumps(data).encode(),
                      headers={'Origin': origin or self.base, 'Content-Type': 'application/json'})
        with build_opener(ProxyHandler({})).open(req) as r:
            return r.read()

    def snapshot(self):
        (self.desk.inbox/'CCON_BA_Snapshot.json').write_text(json.dumps(self.doc), encoding='utf-8')
        return json.loads(self.request('/api/import', {}))

    def test_daily_import_and_restart(self):
        self.snapshot()
        self.request('/api/tasks/CCON-1', {'manualStatus': 'IN PROGRESS', 'note': 'Зателефонувати завтра'})
        self.request('/api/tasks/CCON-2', {'manualStatus': 'DONE', 'note': 'Complete'})
        self.doc['generatedAt'] = '2026-10-07T12:00:00Z'
        self.doc['tasks'][0]['aiStatus'] = 'ACTIONABLE NOW'
        self.snapshot()
        self.snapshot()  # idempotent
        task = json.loads(self.request('/api/tasks'))['tasks'][0]
        self.assertEqual(task['manualStatus'], 'IN PROGRESS')
        self.assertEqual(task['note'], 'Зателефонувати завтра')
        self.assertEqual(task['aiStatus'], 'ACTIONABLE NOW')
        saved = self.doc['tasks'].pop(0)
        self.doc['generatedAt'] = '2026-10-08T12:00:00Z'
        self.snapshot()
        self.assertFalse(next(t for t in self.desk.view()['tasks'] if t['key']=='CCON-1')['active'])
        self.doc['tasks'].append(saved)
        self.doc['generatedAt'] = '2026-10-09T12:00:00Z'
        self.snapshot()
        reopened = Desk(self.root).view()['tasks']
        self.assertEqual(next(t for t in reopened if t['key']=='CCON-1')['note'], 'Зателефонувати завтра')
        self.assertEqual(next(t for t in reopened if t['key']=='CCON-2')['manualStatus'], 'DONE')
        self.assertIn(b'CCON BA Desk', self.request('/'))
        self.assertEqual(len(json.loads(self.request('/api/export'))['tasks']), 2)

    def test_invalid_import_is_atomic(self):
        self.snapshot()
        original = self.desk.view()['tasks']
        for change in ('duplicate', 'older', 'invalid'):
            if change=='duplicate':
                self.doc['tasks'].append(self.doc['tasks'][0])
            elif change=='older':
                self.doc['tasks'].pop()
                self.doc['generatedAt'] = '2026-10-05T12:00:00Z'
            else:
                self.doc['generatedAt'] = '2026-10-10T12:00:00Z'
                self.doc['tasks'][0]['blocking'] = 'yes'
            with self.assertRaises(HTTPError) as ctx:
                self.snapshot()
            self.assertEqual(ctx.exception.code, 400)
            self.assertEqual(self.desk.view()['tasks'], original)
        (self.desk.inbox/'CCON_BA_Snapshot.json').write_text('{partial', encoding='utf-8')
        with self.assertRaises(HTTPError):
            self.request('/api/import', {})
        self.assertEqual(self.desk.view()['tasks'], original)

    def test_foreign_site_rejected(self):
        with self.assertRaises(HTTPError) as ctx:
            self.request('/api/import', {}, origin='https://example.com')
        self.assertEqual(ctx.exception.code, 403)

    def test_draft_survives_import_missing_task_and_restart(self):
        self.doc['tasks'][0]['analysis'] = {
            'signal': 'WRITE', 'reasonUk': 'Потрібен приклад помилки.',
            'nextActionUk': 'Попросити приклад.', 'missingInfo': ['Час помилки'],
            'waitingRequired': False, 'waitingOnUk': '', 'needsEmail': True,
            'queueScore': 90, 'evidence': [{'text': 'Коментар Jira', 'url': 'https://example.com/CCON-1'}],
            'standardDescription': 'Опис задачі', 'stale': False,
            'emailDraft': {'to': '', 'subject': 'CCON-1: уточнення', 'body': 'Please provide an example.'}}
        self.snapshot()
        draft = {'to': 'reporter@example.com', 'subject': 'CCON-1: уточнення', 'body': 'My edited draft'}
        self.request('/api/tasks/CCON-1', {'manualStatus': 'IN PROGRESS', 'note': 'Зберегти чернетку', 'emailDraft': draft})
        self.doc['generatedAt'] = '2026-10-07T12:00:00Z'
        self.doc['tasks'][0]['analysis']['emailDraft']['body'] = 'New generated draft'
        self.snapshot()
        task = next(t for t in self.desk.view()['tasks'] if t['key'] == 'CCON-1')
        self.assertEqual(task['savedEmailDraft'], draft)
        self.assertEqual(task['analysis']['emailDraft']['body'], 'New generated draft')
        # Ordinary status saves must preserve the draft even when emailDraft is omitted.
        self.request('/api/tasks/CCON-1', {'manualStatus': 'WAITING INPUT', 'note': 'Відправлено вручну'})
        self.doc['tasks'].pop(0)
        self.doc['generatedAt'] = '2026-10-08T12:00:00Z'
        self.snapshot()
        restarted = Desk(self.root)
        task = next(t for t in restarted.view()['tasks'] if t['key'] == 'CCON-1')
        self.assertFalse(task['active'])
        self.assertEqual(task['savedEmailDraft'], draft)
        self.assertEqual(task['manualStatus'], 'WAITING INPUT')
        self.request('/api/tasks/CCON-1', {'manualStatus': 'WAITING INPUT', 'note': 'Відправлено вручну', 'emailDraft': None})
        self.assertIsNone(next(t for t in self.desk.view()['tasks'] if t['key'] == 'CCON-1')['savedEmailDraft'])

    def test_invalid_nested_analysis_does_not_replace_valid_snapshot(self):
        self.snapshot()
        original = self.desk.view()['tasks']
        original_doc = copy.deepcopy(self.doc)
        invalid_analyses = [
            [], {'signal': 'UNKNOWN'}, {'reasonUk': []}, {'needsEmail': 'yes'},
            {'waitingRequired': 1}, {'stale': None}, {'queueScore': True},
            {'queueScore': float('nan')}, {'queueScore': 10**400},
            {'missingInfo': ['valid', {'bad': 'item'}]},
            {'missingInfo': ['too many'] * 101},
            {'evidence': [{'text': 'Evidence', 'url': 'javascript:alert(1)'}]},
            {'emailDraft': {'to': '', 'subject': 'Missing body'}},
            {'emailDraft': {'to': '', 'subject': 'Header\ninjection', 'body': ''}},
            {'emailDraft': {'to': '', 'subject': '', 'body': 'x' * 50001}}]
        for analysis in invalid_analyses:
            with self.subTest(analysis=str(analysis)[:100]):
                self.doc = copy.deepcopy(original_doc)
                self.doc['generatedAt'] = '2026-10-07T12:00:00Z'
                self.doc['tasks'][0]['summary'] = 'Must not replace old summary'
                self.doc['tasks'][1]['analysis'] = analysis
                with self.assertRaises(HTTPError) as ctx:
                    self.snapshot()
                self.assertEqual(ctx.exception.code, 400)
                self.assertEqual(self.desk.view()['tasks'], original)

    def test_invalid_draft_does_not_save_partial_manual_changes(self):
        self.snapshot()
        original = self.desk.view()['tasks']
        for draft in ([], {'to': '', 'subject': '', 'body': []},
                      {'to': 'a@example.com\r\nBcc: b@example.com', 'subject': '', 'body': ''}):
            with self.assertRaises(HTTPError) as ctx:
                self.request('/api/tasks/CCON-1', {
                    'manualStatus': 'DONE', 'note': 'Must not save', 'emailDraft': draft})
            self.assertEqual(ctx.exception.code, 400)
            self.assertEqual(self.desk.view()['tasks'], original)

    def test_context_lookup_and_missing_or_partial_file(self):
        self.assertFalse(json.loads(self.request('/api/context/CCON-1'))['contextAvailable'])
        context_path = self.root / 'data' / 'jira_context.json'
        context_path.parent.mkdir()
        context_path.write_text(json.dumps({'issues': {'CCON-1': {
            'description': 'Деталі Jira', 'comments': [{'body': 'Latest relevant comment'}]}}}), encoding='utf-8')
        context = json.loads(self.request('/api/context/CCON-1'))
        self.assertTrue(context['contextAvailable'])
        self.assertEqual(context['key'], 'CCON-1')
        self.assertEqual(context['description'], 'Деталі Jira')
        self.assertFalse(json.loads(self.request('/api/context/CCON-2'))['contextAvailable'])
        context_path.write_text('{partial', encoding='utf-8')
        self.assertFalse(json.loads(self.request('/api/context/CCON-1'))['contextAvailable'])
        self.assertEqual(json.loads(self.request('/api/health'))['app'], 'CCON BA Desk')
        with self.assertRaises(HTTPError) as ctx:
            self.request('/api/context/..')
        self.assertEqual(ctx.exception.code, 400)

if __name__ == '__main__':
    unittest.main()

