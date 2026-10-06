import json
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

if __name__ == '__main__':
    unittest.main()
