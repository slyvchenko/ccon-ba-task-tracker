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
        self.doc = {
            'generatedAt': '2026-10-06T12:00:00Z',
            'tasks': [
                {
                    'key': 'CCON-1',
                    'summary': 'Task one',
                    'jiraStatus': 'Analysis',
                    'aiStatus': 'ACTIONABLE NOW',
                    'aiPriority': 'P1 DO NOW',
                    'focusRank': 1,
                    'taskBrief': 'A compact BA brief.',
                    'currentSituation': 'Current facts are known.',
                    'latestChange': {'date': '2026-10-06', 'source': 'COMMENT', 'text': 'Reporter added an example.'},
                    'surfaceAnalysis': 'First-pass analysis.',
                    'facts': ['Fact A'],
                    'hypotheses': ['Hypothesis A'],
                    'unknowns': ['Unknown A'],
                    'confidence': 'MEDIUM',
                    'blocking': False,
                    'actionType': 'INVESTIGATE',
                    'nextAction': 'Inspect the supplied example.',
                    'whyNextAction': 'It separates the two likely causes.',
                    'actionPlan': ['Open the example', 'Compare expected and actual result'],
                    'afterNextAction': ['If mismatch is internal -> draft a To Do'],
                    'definitionOfDone': 'Ownership is clear.',
                    'contactNeeded': False,
                    'contactType': 'NONE',
                    'contactTarget': '',
                    'contactPurpose': '',
                    'readyOutputType': 'NONE',
                    'readyOutputTitle': '',
                    'readyOutput': '',
                    'changedSinceLastReview': 'UNKNOWN',
                    'changeSummary': ''
                },
                {
                    'key': 'CCON-2',
                    'summary': 'Task two',
                    'jiraStatus': 'Open',
                    'aiStatus': 'WAITING INPUT',
                    'aiPriority': 'P4 WAITING',
                    'waitingOn': 'SUPPLIER',
                    'waitingEvidence': 'Question sent on 2026-10-05; no answer yet.',
                    'focusRank': None
                }
            ]
        }

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        target = self.root.resolve()
        assert target.is_relative_to(Path(__file__).resolve().parent) and target.name.startswith('test-data-')
        shutil.rmtree(target)

    def request(self, path, data=None, origin=None):
        req = Request(
            self.base + path,
            data=None if data is None else json.dumps(data).encode(),
            headers={'Origin': origin or self.base, 'Content-Type': 'application/json'}
        )
        with build_opener(ProxyHandler({})).open(req) as r:
            return r.read()

    def snapshot(self):
        (self.desk.inbox / 'CCON_BA_Snapshot.json').write_text(json.dumps(self.doc), encoding='utf-8')
        return json.loads(self.request('/api/import', {}))

    def task(self, key):
        return next(t for t in json.loads(self.request('/api/tasks'))['tasks'] if t['key'] == key)

    def test_manual_state_survives_snapshot_and_restart(self):
        self.snapshot()
        self.request('/api/tasks/CCON-1', {
            'manualStatus': 'IN PROGRESS',
            'manualWaitingOn': '',
            'note': 'Check Kibana first'
        })
        self.request('/api/tasks/CCON-2', {
            'manualStatus': 'WAITING',
            'manualWaitingOn': 'SUPPLIER',
            'note': 'Follow up after supplier reply'
        })

        self.doc['generatedAt'] = '2026-10-07T12:00:00Z'
        self.doc['tasks'][0]['aiStatus'] = 'NEEDS DECISION'
        self.doc['tasks'][0]['currentSituation'] = 'Rovo updated its assessment.'
        self.snapshot()
        self.snapshot()  # idempotent

        one = self.task('CCON-1')
        two = self.task('CCON-2')
        self.assertEqual(one['manualStatus'], 'IN PROGRESS')
        self.assertEqual(one['note'], 'Check Kibana first')
        self.assertEqual(one['aiStatus'], 'NEEDS DECISION')
        self.assertEqual(two['manualStatus'], 'WAITING')
        self.assertEqual(two['manualWaitingOn'], 'SUPPLIER')

        reopened = Desk(self.root).view()['tasks']
        self.assertEqual(next(t for t in reopened if t['key'] == 'CCON-1')['note'], 'Check Kibana first')
        self.assertEqual(next(t for t in reopened if t['key'] == 'CCON-2')['manualWaitingOn'], 'SUPPLIER')

    def test_done_task_gets_review_again_after_meaningful_change(self):
        self.snapshot()
        self.request('/api/tasks/CCON-1', {
            'manualStatus': 'DONE',
            'manualWaitingOn': '',
            'note': 'Done after initial analysis'
        })

        self.doc['generatedAt'] = '2026-10-07T12:00:00Z'
        self.doc['tasks'][0]['changedSinceLastReview'] = 'CHANGED'
        self.doc['tasks'][0]['changeSummary'] = 'Supplier added a new requirement.'
        self.doc['tasks'][0]['latestChange'] = {
            'date': '2026-10-07', 'source': 'COMMENT', 'text': 'Supplier added a new requirement.'
        }
        self.snapshot()

        task = self.task('CCON-1')
        self.assertEqual(task['manualStatus'], 'DONE')
        self.assertTrue(task['reviewAgain'])

        self.request('/api/tasks/CCON-1', {
            'manualStatus': 'DONE',
            'manualWaitingOn': '',
            'note': 'Reviewed, still done',
            'clearReviewAgain': True
        })
        self.assertFalse(self.task('CCON-1')['reviewAgain'])

    def test_missing_and_returning_task_preserves_local_state(self):
        self.snapshot()
        self.request('/api/tasks/CCON-1', {
            'manualStatus': 'PARKED',
            'manualWaitingOn': '',
            'note': 'Keep local context'
        })
        saved = self.doc['tasks'].pop(0)
        self.doc['generatedAt'] = '2026-10-07T12:00:00Z'
        self.snapshot()
        self.assertFalse(self.task('CCON-1')['active'])

        self.doc['tasks'].append(saved)
        self.doc['generatedAt'] = '2026-10-08T12:00:00Z'
        self.snapshot()
        task = self.task('CCON-1')
        self.assertTrue(task['active'])
        self.assertEqual(task['manualStatus'], 'PARKED')
        self.assertEqual(task['note'], 'Keep local context')

    def test_invalid_import_is_atomic(self):
        self.snapshot()
        original = self.desk.view()['tasks']

        self.doc['tasks'].append(self.doc['tasks'][0])
        with self.assertRaises(HTTPError) as ctx:
            self.snapshot()
        self.assertEqual(ctx.exception.code, 400)
        self.assertEqual(self.desk.view()['tasks'], original)

        self.doc['tasks'].pop()
        self.doc['generatedAt'] = '2026-10-05T12:00:00Z'
        with self.assertRaises(HTTPError):
            self.snapshot()
        self.assertEqual(self.desk.view()['tasks'], original)

        (self.desk.inbox / 'CCON_BA_Snapshot.json').write_text('{partial', encoding='utf-8')
        with self.assertRaises(HTTPError):
            self.request('/api/import', {})
        self.assertEqual(self.desk.view()['tasks'], original)

    def test_http_surface_is_local_and_read_only_toward_jira(self):
        self.snapshot()
        self.assertIn(b'CCON BA Desk', self.request('/'))
        self.assertEqual(len(json.loads(self.request('/api/export'))['tasks']), 2)

        with self.assertRaises(HTTPError) as ctx:
            self.request('/api/import', {}, origin='https://example.com')
        self.assertEqual(ctx.exception.code, 403)

        # There are no Jira write endpoints. Unknown local endpoints are rejected.
        with self.assertRaises(HTTPError) as ctx:
            self.request('/api/jira/comment', {'body': 'must never be sent'})
        self.assertEqual(ctx.exception.code, 404)


if __name__ == '__main__':
    unittest.main()
