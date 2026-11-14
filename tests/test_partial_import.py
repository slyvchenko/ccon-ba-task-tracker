import copy
import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from apply_analysis import apply
from server import Desk


class PartialImport(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent / ('test-data-' + uuid.uuid4().hex)
        (self.root / 'data').mkdir(parents=True)
        self.desk = Desk(self.root)
        self.target = self.root / 'inbox/CCON_BA_Snapshot.json'
        self.target.write_text(json.dumps({'generatedAt': '2026-11-13T08:00:00Z', 'tasks': [
            {'key': 'CCON-1', 'summary': 'One', 'contextFingerprint': 'fp1'},
            {'key': 'CCON-2', 'summary': 'Two', 'contextFingerprint': 'fp2'},
        ]}), encoding='utf-8')
        self.desk.import_snapshot()
        (self.root / 'data/jira_context.json').write_text(json.dumps({'complete': True, 'issues': {
            'CCON-1': {'fingerprint': 'fp1'}, 'CCON-2': {'fingerprint': 'fp2'}}}), encoding='utf-8')
        self.path = self.root / 'data/partial.json'
        self.report = self.root / 'data/daily_review_report.json'

    def tearDown(self):
        target = self.root.resolve()
        assert target.is_relative_to(Path(__file__).resolve().parent) and target.name.startswith('test-data-')
        shutil.rmtree(target)

    def analysis(self, fingerprint, signal='WRITE'):
        return {'signal': signal, 'reasonUk': 'Потрібне уточнення меж вимоги.', 'nextActionUk': 'Уточни очікуваний результат.',
                'missingInfo': ['Очікуваний результат'], 'waitingRequired': False, 'waitingOnUk': 'Ніхто',
                'needsEmail': signal == 'WRITE', 'queueScore': 50, 'evidence': [], 'standardDescription': '',
                'emailDraft': {'to': '', 'subject': 'Question', 'body': 'Could you clarify?'},
                'contextFingerprint': fingerprint}

    def run_apply(self, analyses, only, focus_issue=None):
        self.path.write_text(json.dumps({'analyses': analyses}), encoding='utf-8')
        apply(self.path, self.root, focus_issue=focus_issue, only=only)

    def tasks(self):
        return {task['key']: task for task in self.desk.view()['tasks']}

    def test_partial_import_touches_only_requested_issue(self):
        with patch('apply_analysis.update_daily') as calibration, patch('builtins.print') as printed:
            self.run_apply({'CCON-2': self.analysis('fp2')}, only=['CCON-2'])
        calibration.assert_not_called()
        summary = json.loads(printed.call_args.args[0])
        self.assertTrue(summary['partial'])
        self.assertEqual(summary['changes']['total'], 1)
        self.assertEqual(summary['changes']['LEFT_SCOPE'], 0)
        self.assertNotIn('CCON-1', {w['key'] for w in summary['qualityWarnings']})
        tasks = self.tasks()
        self.assertNotIn('analysis', tasks['CCON-1'])
        self.assertEqual(tasks['CCON-2']['analysis']['signal'], 'WRITE')
        self.assertFalse(tasks['CCON-2']['analysis']['stale'])
        self.assertFalse(self.report.exists(), 'partial import must not rewrite the daily report')

        before = copy.deepcopy(tasks['CCON-2']['analysis'])
        self.run_apply({'CCON-1': self.analysis('fp1', signal='DECIDE')}, only=['CCON-1'])
        tasks = self.tasks()
        self.assertEqual(tasks['CCON-1']['analysis']['signal'], 'DECIDE')
        self.assertEqual(tasks['CCON-2']['analysis'], before)

    def test_partial_import_rejects_mismatched_file_or_keys(self):
        original = self.target.read_bytes()
        cases = [
            ({'CCON-1': self.analysis('fp1'), 'CCON-2': self.analysis('fp2')}, ['CCON-2'], 'exactly the requested'),
            ({'CCON-2': self.analysis('fp2')}, ['CCON-2', 'CCON-9'], 'current tasks'),
            ({}, [], 'at least one'),
            ({'CCON-2': self.analysis('old')}, ['CCON-2'], 'Stale or missing'),
        ]
        for analyses, only, message in cases:
            with self.subTest(only=only), self.assertRaisesRegex(ValueError, message):
                self.run_apply(analyses, only=only)
            self.assertEqual(self.target.read_bytes(), original)

    def test_partial_import_and_focus_issue_are_exclusive(self):
        with self.assertRaisesRegex(ValueError, 'not both'):
            self.run_apply({'CCON-2': self.analysis('fp2')}, only=['CCON-2'], focus_issue='CCON-2')

    def test_full_import_still_requires_complete_coverage(self):
        with self.assertRaisesRegex(ValueError, 'Coverage mismatch'):
            self.run_apply({'CCON-2': self.analysis('fp2')}, only=None)


if __name__ == '__main__':
    unittest.main()
