import io
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import es_logs
import sprint_move
from supplier_logs import inspect_bundle

FLOW = 'dfd2ab53-0ee2-4c78-ae86-42a42e549af8'
RQ = ('<?xml version="1.0"?><e:Envelope xmlns:e="s" xmlns:w="w"><e:Header><w:Security><w:UsernameToken>'
      '<w:Username>user</w:Username><w:Password Type="x">TopSecret123</w:Password><w:Nonce>abc==</w:Nonce>'
      '<u:Created>2026-10-08T11:12:18Z</u:Created></w:UsernameToken></w:Security></e:Header>'
      '<e:Body><OrderRetrieveRQ><Passenger><GivenName>ANNA</GivenName></Passenger></OrderRetrieveRQ></e:Body></e:Envelope>')
RS = '<?xml version="1.0"?><e:Envelope xmlns:e="s"><e:Body><OrderViewRS/></e:Body></e:Envelope>'
DOCS = [
    {'time': '2026-10-09T12:54:46.204800', 'domain': 'supplier', 'supplier': 'AirFranceKLM',
     'requestorMethodName': 'air-docs', 'request_action': 'OrderRetrieve',
     'request_url': 'https://api.example/W1?apikey=abc', 'request_body': RQ, 'response_body': RS},
    {'time': '2026-10-09T12:54:47', 'domain': 'rest', 'requestorMethodName': 'pnrs',
     'request_body_json': {'login': 'a', 'password': 'p@ss', 'nested': {'authToken': 't0k'}, 'passengerCount': 2},
     'response_body_json': {'ok': True}},
    {'time': '2026-10-09T12:54:48', 'domain': 'error', 'requestorMethodName': 'pnrs',
     'error': 'Supplier error', 'message': 'retry with Authorization: Bearer eyJhbGciOi.payload.sig'},
]


def page(ids, total, scroll='S1', **extra):
    return {'_scroll_id': scroll, 'timed_out': False, '_shards': {'total': 2, 'successful': 2, 'failed': 0},
            'hits': {'total': {'value': total}, 'hits': [{'_source': {'time': f'2026-10-09T00:00:{i:02d}', 'i': i}} for i in ids]},
            **extra}


class EsLogsTest(unittest.TestCase):
    def build(self):
        data, counts = es_logs.build_zip(DOCS)
        return data, counts, ZipFile(io.BytesIO(data))

    def test_layout_matches_ccon_download_and_passes_validation(self):
        data, counts, archive = self.build()
        names = archive.namelist()
        self.assertIn('supplier/AirFranceKLM/1791550486204800-air-docs-OrderRetrieve-0-request-body.xml', names)
        self.assertTrue(any(n.startswith('rest/') and n.endswith('request-body-1.json') for n in names))
        self.assertTrue(any(n.startswith('error/') for n in names))
        self.assertEqual(counts, {'supplier': 1, 'rest': 1, 'error': 1})
        self.assertEqual(inspect_bundle(data, ['AirFranceKLM'], 'AF/KL. Retrieve')['exchangeCount'], 1)

    def test_credentials_are_masked_but_business_data_kept(self):
        _, _, archive = self.build()
        blob = b''.join(archive.read(n) for n in archive.namelist()).decode()
        for secret in ('TopSecret123', 'abc==', 'p@ss', 't0k', 'apikey=abc', 'eyJhbGciOi'):
            self.assertNotIn(secret, blob)
        self.assertIn('<w:Password Type="x">***</w:Password>', blob)
        self.assertIn('Bearer ***', blob.replace('Authorization: ***', 'Bearer ***'))
        for kept in ('<GivenName>ANNA</GivenName>', '2026-10-08T11:12:18Z', '"passengerCount": 2', '<w:Username>user</w:Username>'):
            self.assertIn(kept, blob)

    def test_free_text_and_structured_redaction(self):
        text = es_logs.redact('{"authToken":"v1","sessionId":"s","apiKey":12}\nAuthorization: Bearer abc.def\nurl?token=zz&x=1 Author: Bob')
        self.assertNotIn('v1', text)
        self.assertNotIn('abc.def', text)
        self.assertNotIn('zz', text)
        self.assertIn('Author: Bob', text)

    def test_masking_keeps_xml_well_formed_and_covers_cdata(self):
        import xml.dom.minidom
        masked = es_logs.redact('<r><Error token="abc" Code="705">x</Error><a secret=\'s\'/>'
                                '<ns:Password xmlns:ns="n"><![CDATA[p<a>ss]]></ns:Password>'
                                '<ns:Password xmlns:ns="n" Type="t"/><Created>T</Created></r>')
        xml.dom.minidom.parseString(masked)
        for secret in ('abc', "'s'", 'p<a>ss'):
            self.assertNotIn(secret, masked)
        self.assertIn('Code="705"', masked)
        self.assertIn('<Created>T</Created>', masked)

    def test_cookie_inside_serialized_metadata_is_masked_in_archive(self):
        data, _ = es_logs.build_zip([{'time': '2026-10-09T12:54:48', 'domain': 'error',
                                      'requestorMethodName': 'pnrs',
                                      'message': 'login failed, Cookie: SID=secret-value; x=1'}])
        archive = ZipFile(io.BytesIO(data))
        text = archive.read(archive.namelist()[0]).decode()
        self.assertNotIn('secret-value', text)
        json.loads(text)

    def test_hidden_controls_stay_hidden(self):
        css = (Path(__file__).resolve().parents[1] / 'assets/dashboard.css').read_text(encoding='utf-8')
        self.assertIn('[hidden] { display:none !important; }', css)

    def test_process_rejects_plan_without_the_issue(self):
        import local_downloads
        with tempfile.TemporaryDirectory() as root:
            data = Path(root) / 'data'
            data.mkdir()
            (data / 'log_plan.json').write_text(json.dumps({'mode': 'evidence', 'jobs': [
                {'key': 'CCON-2', 'flowId': FLOW, 'contextFingerprint': 'x'}]}), encoding='utf-8')
            (data / 'jira_context.json').write_text(json.dumps({'complete': True, 'issues': {}}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'no job for CCON-1'):
                local_downloads.process(Path(root), 'CCON-1')

    def test_headers_are_not_requested(self):
        self.assertFalse([f for f in es_logs.FIELDS if 'header' in f.lower()])

    def test_scroll_reads_every_page_and_clears_context(self):
        calls = []
        responses = iter([page(range(0, 3), 5), page(range(3, 5), 5), page([], 5)])

        def fake(url, path, body, method='POST', timeout=90):
            calls.append((method, path))
            return {} if method == 'DELETE' else next(responses)
        with mock.patch.object(es_logs, '_request', side_effect=fake):
            docs = es_logs.fetch_flow(FLOW, Path('.'))
        self.assertEqual([d['i'] for d in docs], [0, 1, 2, 3, 4])
        self.assertIn(('POST', '/_search/scroll'), calls)
        self.assertEqual(calls[-1], ('DELETE', '/_search/scroll'))

    def test_partial_or_timed_out_results_are_rejected(self):
        for bad in (page([0], 1, timed_out=True),
                    {**page([0], 1), '_shards': {'total': 2, 'successful': 1, 'failed': 1}}):
            with mock.patch.object(es_logs, '_request', return_value=bad):
                with self.assertRaisesRegex(ValueError, 'incomplete'):
                    es_logs.fetch_flow(FLOW, Path('.'))

    def test_missing_documents_are_rejected(self):
        responses = iter([page([0, 1], 3), page([], 3)])
        with mock.patch.object(es_logs, '_request', side_effect=lambda *a, **k: {} if k.get('method') == 'DELETE' else next(responses)):
            with self.assertRaisesRegex(ValueError, 'received 2 of 3'):
                es_logs.fetch_flow(FLOW, Path('.'))

    def test_oversized_flow_is_rejected_not_truncated(self):
        with mock.patch.object(es_logs, '_request', side_effect=lambda *a, **k: {} if k.get('method') == 'DELETE' else page([0], es_logs.MAX_DOCS + 1)):
            with self.assertRaisesRegex(ValueError, 'limit'):
                es_logs.fetch_flow(FLOW, Path('.'))

    def test_plan_fetches_are_serialized(self):
        active, peak = [0], [0]

        def slow(root, issue, prepare, process):
            active[0] += 1
            peak[0] = max(peak[0], active[0])
            time.sleep(0.05)
            active[0] -= 1
            return {}
        with tempfile.TemporaryDirectory() as root, \
                mock.patch.object(es_logs, '_fetch_for_plan_locked', side_effect=slow):
            threads = [threading.Thread(target=es_logs.fetch_for_plan, args=(Path(root), f'CCON-{i}')) for i in range(3)]
            [t.start() for t in threads]
            [t.join() for t in threads]
        self.assertEqual(peak[0], 1)

    def test_rejects_invalid_flow(self):
        with self.assertRaises(ValueError):
            es_logs.fetch_flow('not-a-uuid')


class SprintMovePlanTest(unittest.TestCase):
    def load(self, moves):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'plan.json'
            path.write_text(json.dumps({'moves': moves}), encoding='utf-8')
            return sprint_move.load_plan(path)

    def test_names_are_normalized(self):
        self.assertEqual(list(self.load({'  Sprint  12 ': ['CCON-1']})), ['Sprint 12'])

    def test_empty_or_duplicate_names_are_rejected(self):
        with self.assertRaises(ValueError):
            self.load({'  ': ['CCON-1']})
        with self.assertRaises(ValueError):
            self.load({'Sprint 12': ['CCON-1'], ' Sprint 12': ['CCON-2']})


if __name__ == '__main__':
    unittest.main()
