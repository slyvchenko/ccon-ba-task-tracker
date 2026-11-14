import json
import shutil
import unittest
import uuid
from pathlib import Path

from analysis_kit import Kit
from daily_delta import check, dump, worklist


class DailyDelta(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent / ('test-data-' + uuid.uuid4().hex)
        (self.root / 'data').mkdir(parents=True)
        (self.root / 'inbox').mkdir()
        verified = {'signal': 'READY', 'contextFingerprint': 'fp1', 'queueScore': 40,
                    'qualityGate': {'state': 'STRUCTURALLY_VERIFIED'}}
        tasks = [
            {'key': 'CCON-1', 'summary': 'Verified', 'analysis': verified},
            {'key': 'CCON-2', 'summary': 'Changed', 'analysis': dict(verified, contextFingerprint='old')},
            {'key': 'CCON-3', 'summary': 'New'},
            {'key': 'CCON-4', 'summary': 'Weak', 'activeSprint': True,
             'analysis': dict(verified, contextFingerprint='fp4', qualityGate={'state': 'NEEDS_REVIEW'})},
        ]
        (self.root / 'inbox/CCON_BA_Snapshot.json').write_text(json.dumps({'tasks': tasks}), encoding='utf-8')
        issues = {f'CCON-{n}': {'key': f'CCON-{n}', 'url': f'https://aerticket.atlassian.net/browse/CCON-{n}', 'summary': 'Seat price shown as 0 EUR', 'fingerprint': f'fp{n}',
                                'jiraStatus': 'Analyze', 'description': 'AR\nSupplier error | Unable to reserve services\nER\nNo errors',
                                'comments': [{'body': 'Please check why it happens.', 'created': '2026-11-13T08:00:00Z',
                                              'author': {'displayName': 'Dev'}}], 'links': [], 'attachments': []}
                  for n in range(1, 5)}
        (self.root / 'data/jira_context.json').write_text(json.dumps({'complete': True, 'issues': issues}), encoding='utf-8')

    def tearDown(self):
        target = self.root.resolve()
        assert target.is_relative_to(Path(__file__).resolve().parent) and target.name.startswith('test-data-')
        shutil.rmtree(target)

    def test_worklist_contains_only_new_changed_or_failing_tasks(self):
        rows = worklist(self.root)
        self.assertEqual([(r['key'], r['reason']) for r in rows],
                         [('CCON-4', 'QUALITY'), ('CCON-2', 'CHANGED'), ('CCON-3', 'NEW')])

    def test_dump_includes_description_comments_and_previous_result(self):
        text = dump(['CCON-2'], self.root)
        self.assertIn('Unable to reserve services', text)
        self.assertIn('Please check why it happens.', text)
        self.assertIn('--- PREVIOUS READY 40', text)
        with self.assertRaises(ValueError):
            dump(['CCON-99'], self.root)

    def build(self, kit, excerpt='Supplier error | Unable to reserve services'):
        return kit.build(
            'CCON-3', signal='REVIEW', factors={'businessImpact': 10, 'urgency': 0, 'dependencies': 0,
                                                 'baDecision': 10, 'actionability': 10},
            reason='Помилка постачальника при бронюванні місць.', next_='Перевірити свіжий flow.',
            missing=[], evidence=[('Опис задачі.', None)], title='Seats', email={'to': '', 'subject': '', 'body': ''},
            desc='Seats\n\n#### AR\nSupplier error | Unable to reserve services\n\n#### ER\nNo errors.\n\n'
                 '#### QA\n- Check seat booking for an available seat: booked.\n- Check an unavailable seat: clear error.',
            audience='INTERNAL', email_lim='Лист не потрібен.', overview='Місця не бронюються.',
            current='Помилка.', target='Без помилки.', impact='Агенти не бронюють місця.', scope='Seats-book.',
            audit=[('Опис', 'READ', None)], facts=[('AR.', excerpt)], timeline=[('2026-11-13', 'Створено.')],
            rules=[('R1', 'Бронювання доступного місця', 'Місце заброньовано без помилки.', excerpt)],
            qa=[('POSITIVE', 'Доступне місце', 'Заброньовано.', ['R1']),
                ('NEGATIVE', 'Недоступне місце', 'Зрозуміла помилка.', ['R1'])],
            risks=[], unknowns=[], readiness_reason='Причина не перевірена.')

    def test_kit_rejects_non_verbatim_excerpt_and_check_passes_valid_file(self):
        kit = Kit(self.root)
        with self.assertRaisesRegex(ValueError, 'not verbatim'):
            self.build(kit, excerpt='Supplier error | invented text')
        path = kit.write({'CCON-3': self.build(kit)}, self.root / 'data/partial.json')
        ok, rows = check(path, self.root)
        self.assertTrue(ok, rows)
        self.assertEqual(rows[0]['state'], 'STRUCTURALLY_VERIFIED')

    def test_check_flags_stale_fingerprint(self):
        kit = Kit(self.root)
        analysis = self.build(kit)
        analysis['contextFingerprint'] = 'old'
        path = kit.write({'CCON-3': analysis}, self.root / 'data/partial.json')
        ok, rows = check(path, self.root)
        self.assertFalse(ok)
        self.assertFalse(rows[0]['fresh'])


    def test_check_uses_persisted_question_state_like_the_import(self):
        kit = Kit(self.root)
        analysis = self.build(kit)
        analysis['briefing']['readiness'] = 'READY_FOR_REVIEW'
        for rule in analysis['briefing']['rules']:
            rule['certainty'] = 'CONFIRMED'
        path = kit.write({'CCON-3': analysis}, self.root / 'data/partial.json')
        ok, rows = check(path, self.root)
        self.assertTrue(ok, rows)
        # Unreadable private question state counts as an OPEN question during
        # import; the preflight must not approve what the import would block.
        (self.root / 'data/questions').mkdir(parents=True)
        (self.root / 'data/questions/CCON-3.json').write_text('{broken', encoding='utf-8')
        ok, rows = check(path, self.root)
        self.assertFalse(ok, rows)
        self.assertNotEqual(rows[0]['state'], 'STRUCTURALLY_VERIFIED')

    def test_incomplete_es_response_is_unverifiable_not_zero(self):
        from unittest import mock
        import es_logs
        from daily_delta import errors
        partial = {'timed_out': False, '_shards': {'total': 3, 'successful': 2, 'failed': 1},
                   'hits': {'total': {'value': 0}, 'hits': []},
                   'aggregations': {'last30': {'doc_count': 0}, 'last7': {'doc_count': 0},
                                    'supplier': {'buckets': []}, 'method': {'buckets': []}}}
        with mock.patch.object(es_logs, 'config', return_value=('https://es.invalid', 'idx')), \
                mock.patch.object(es_logs, '_request', return_value=partial):
            result = errors(['Unable to reserve services'], self.root)
        self.assertEqual(result, {'Unable to reserve services': {'unverifiable': 'INCOMPLETE_ES_RESPONSE'}})


    def test_check_rejects_what_the_import_schema_rejects(self):
        kit = Kit(self.root)
        analysis = self.build(kit)
        del analysis['nextActionUk']
        path = self.root / 'data/partial.json'
        path.write_text(json.dumps({'analyses': {'CCON-3': analysis}}), encoding='utf-8')
        ok, rows = check(path, self.root)
        self.assertFalse(ok)
        self.assertEqual(rows[0]['state'], 'IMPORT_SCHEMA_INVALID')

    def test_short_window_does_not_truncate_fixed_30_and_7_day_counts(self):
        from unittest import mock
        import es_logs
        from daily_delta import errors
        seen = []
        response = {'timed_out': False, '_shards': {'total': 1, 'successful': 1, 'failed': 0},
                    'hits': {'total': {'value': 9}, 'hits': []},
                    'aggregations': {'window': {'doc_count': 2}, 'last30': {'doc_count': 5},
                                     'last7': {'doc_count': 2}, 'supplier': {'buckets': []},
                                     'method': {'buckets': []}}}
        def request(url, path, body):
            seen.append(body)
            return response
        with mock.patch.object(es_logs, 'config', return_value=('https://es.invalid', 'idx')), \
                mock.patch.object(es_logs, '_request', side_effect=request):
            result = errors(['Unable to reserve services'], self.root, days=7)
        ranges = [f['range'] for f in seen[0]['query']['bool']['filter'] if 'range' in f]
        self.assertEqual(ranges[0]['@timestamp']['gte'], 'now-30d')
        self.assertEqual(result['Unable to reserve services']['7d'], 2)
        self.assertEqual(result['Unable to reserve services']['30d'], 5)


if __name__ == '__main__':
    unittest.main()
