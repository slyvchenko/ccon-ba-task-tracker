import copy
import json
import shutil
import unittest
import uuid
from pathlib import Path

from jira_sync import adf_text, sync
from server import Desk
from pipeline_lock import pipeline_lock


def issue(key, description='Source description'):
    return {'key': key, 'fields': {
        'summary': 'Task ' + key, 'description': description,
        'status': {'name': 'Analyze', 'statusCategory': {'key': 'indeterminate'}},
        'priority': {'name': 'High'}, 'updated': '2026-10-07T08:00:00Z',
        'issuetype': {'name': 'Task'}, 'issuelinks': [],
        'reporter': {'displayName': 'Reporter', 'emailAddress': 'reporter@example.com'}}}


class FakeJira:
    def __init__(self):
        self.first = issue('CCON-1')
        self.second = issue('CCON-2')
        self.external = issue('OTHER-1')
        self.first['fields']['issuelinks'] = [
            {'id': '1', 'type': {'name': 'Blocks', 'inward': 'is blocked by', 'outward': 'blocks'},
             'outwardIssue': self.second},
            {'id': '2', 'type': {'name': 'Blocks', 'inward': 'is blocked by', 'outward': 'blocks'},
             'inwardIssue': self.external}]
        self.calls = []
        self.comment_text = 'Updated evidence'
        self.incomplete = False

    def get(self, path, params=None):
        self.calls.append((path, copy.deepcopy(params)))
        if path.endswith('/search/jql'):
            if params.get('nextPageToken') == 'second':
                return {'issues': [copy.deepcopy(self.second)], 'isLast': True}
            result = {'issues': [copy.deepcopy(self.first)], 'isLast': False}
            if not self.incomplete:
                result['nextPageToken'] = 'second'
            return result
        if path.endswith('/comment'):
            key = path.split('/')[-2]
            if key != 'CCON-1':
                return {'comments': [], 'total': 0, 'startAt': 0}
            start = params['startAt']
            return {'comments': [{'id': str(start + 1), 'body': self.comment_text + str(start),
                                  'created': '2026-10-07T08:00:00Z', 'updated': '2026-10-07T08:00:00Z',
                                  'author': {'displayName': 'Comment author'}}],
                    'total': 2, 'startAt': start}
        if path.endswith('/OTHER-1'):
            return copy.deepcopy(self.external)
        raise AssertionError('Unexpected route: ' + path)


class JiraSyncTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent / ('test-data-sync-' + uuid.uuid4().hex)
        self.root.mkdir()
        self.client = FakeJira()

    def tearDown(self):
        target = self.root.resolve()
        assert target.is_relative_to(Path(__file__).resolve().parent) and target.name.startswith('test-data-sync-')
        shutil.rmtree(target)

    def snapshot(self):
        return json.loads((self.root / 'inbox' / 'CCON_BA_Snapshot.json').read_text(encoding='utf-8'))

    def test_all_issue_and_comment_pages_linked_context_and_no_plain_credentials(self):
        result = sync(self.root, self.client)
        self.assertEqual(result['retrievedCount'], 2)
        self.assertEqual(result['linkedIssueCount'], 1)
        self.assertEqual(result['commentCount'], 2)
        context = json.loads((self.root / 'data' / 'jira_context.json').read_text(encoding='utf-8'))
        first = context['issues']['CCON-1']
        self.assertEqual(len(first['comments']), 2)
        self.assertEqual(first['blockedBy'], ['OTHER-1'])
        self.assertEqual(first['blocks'], ['CCON-2'])
        self.assertEqual(first['reporter']['emailAddress'], 'reporter@example.com')
        self.assertEqual(context['linkedIssues']['OTHER-1']['description'], 'Source description')
        snapshot = self.snapshot()
        self.assertTrue(snapshot['complete'])
        self.assertEqual([task['key'] for task in snapshot['tasks']], ['CCON-1', 'CCON-2'])
        self.assertNotIn('descriptionAdf', snapshot['tasks'][0])
        self.assertNotIn('analysis', snapshot['tasks'][0])
        self.assertIn('Повний опис', snapshot['tasks'][0]['statusReason'])
        self.assertEqual(sum(path.endswith('/search/jql') for path, _ in self.client.calls), 2)

    def test_unchanged_analysis_preserved_changed_comment_marks_stale_and_keeps_manual_state(self):
        sync(self.root, self.client)
        doc = self.snapshot()
        doc['tasks'][0].update(aiStatus='ACTIONABLE NOW', statusReason='Українське пояснення',
                               nextAction='Перевірити приклад',
                               analysis={'signal': 'READY', 'stale': False, 'reasonUk': 'Є дані.',
                                         'nextActionUk': 'Перевірити приклад', 'queueScore': 80})
        path = self.root / 'inbox' / 'CCON_BA_Snapshot.json'
        path.write_text(json.dumps(doc), encoding='utf-8')
        desk = Desk(self.root)
        desk.import_snapshot()
        desk.save('CCON-1', {'manualStatus': 'WAITING INPUT', 'note': 'Чекати відповідь'})
        sync(self.root, self.client)
        unchanged = self.snapshot()['tasks'][0]
        self.assertFalse(unchanged['analysis']['stale'])
        self.assertEqual(unchanged['nextAction'], 'Перевірити приклад')
        self.client.comment_text = 'Different new evidence'
        sync(self.root, self.client)
        changed = self.snapshot()['tasks'][0]
        self.assertTrue(changed['analysis']['stale'])
        self.assertEqual(changed['aiStatus'], 'NOT ANALYZED')
        desk.import_snapshot()
        saved = next(task for task in desk.view()['tasks'] if task['key'] == 'CCON-1')
        self.assertEqual(saved['manualStatus'], 'WAITING INPUT')
        self.assertEqual(saved['note'], 'Чекати відповідь')

    def test_incomplete_search_does_not_replace_complete_files(self):
        sync(self.root, self.client)
        snapshot = (self.root / 'inbox' / 'CCON_BA_Snapshot.json').read_bytes()
        cache = (self.root / 'data' / 'jira_context.json').read_bytes()
        self.client.incomplete = True
        with self.assertRaisesRegex(ValueError, 'complete Jira pagination'):
            sync(self.root, self.client)
        self.assertEqual((self.root / 'inbox' / 'CCON_BA_Snapshot.json').read_bytes(), snapshot)
        self.assertEqual((self.root / 'data' / 'jira_context.json').read_bytes(), cache)

    def test_adf_keeps_structure_mentions_and_cards(self):
        doc = {'type': 'doc', 'content': [
            {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Hello '},
                                             {'type': 'mention', 'attrs': {'text': '@Reporter'}}]},
            {'type': 'bulletList', 'content': [{'type': 'listItem', 'content': [
                {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Example'}]}]}]},
            {'type': 'inlineCard', 'attrs': {'url': 'https://example.com'}}]}
        self.assertEqual(adf_text(doc), 'Hello @Reporter\n- Example\nhttps://example.com')

    def test_sync_rejects_overlapping_pipeline_before_network_or_file_changes(self):
        sync(self.root,self.client)
        snapshot=(self.root/'inbox'/'CCON_BA_Snapshot.json').read_bytes()
        context=(self.root/'data'/'jira_context.json').read_bytes()
        calls=len(self.client.calls)
        with pipeline_lock(self.root):
            with self.assertRaisesRegex(ValueError,'Another Jira sync'):
                sync(self.root,self.client)
        self.assertEqual(len(self.client.calls),calls)
        self.assertEqual((self.root/'inbox'/'CCON_BA_Snapshot.json').read_bytes(),snapshot)
        self.assertEqual((self.root/'data'/'jira_context.json').read_bytes(),context)


if __name__ == '__main__':
    unittest.main()
