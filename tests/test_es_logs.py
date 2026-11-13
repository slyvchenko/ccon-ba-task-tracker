import io
import sys
import unittest
from pathlib import Path
from unittest import mock
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import es_logs
from supplier_logs import inspect_bundle

RQ = ('<?xml version="1.0"?><e:Envelope xmlns:e="s" xmlns:w="w"><e:Header><w:Security><w:UsernameToken>'
      '<w:Username>user</w:Username><w:Password Type="x">TopSecret123</w:Password><w:Nonce>abc==</w:Nonce>'
      '</w:UsernameToken></w:Security></e:Header><e:Body><OrderRetrieveRQ/></e:Body></e:Envelope>')
RS = '<?xml version="1.0"?><e:Envelope xmlns:e="s"><e:Body><OrderViewRS/></e:Body></e:Envelope>'
DOCS = [
    {'time': '2026-10-09T12:54:46.204800', 'domain': 'supplier', 'supplier': 'AirFranceKLM',
     'requestorMethodName': 'air-docs', 'request_action': 'OrderRetrieve',
     'request_url': 'https://api.example/W1?apikey=abc', 'request_body': RQ, 'response_body': RS},
    {'time': '2026-10-09T12:54:47', 'domain': 'rest', 'requestorMethodName': 'pnrs',
     'request_body_json': {'login': 'a', 'password': 'p@ss', 'nested': {'token': 't0k'}},
     'response_body_json': {'ok': True}},
    {'time': '2026-10-09T12:54:48', 'domain': 'error', 'requestorMethodName': 'pnrs', 'error': 'Supplier error'},
]


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
        bundle = inspect_bundle(data, ['AirFranceKLM'], 'AF/KL. Retrieve')
        self.assertEqual(bundle['exchangeCount'], 1)

    def test_credentials_and_query_strings_are_never_written(self):
        _, _, archive = self.build()
        blob = b''.join(archive.read(n) for n in archive.namelist()).decode()
        for secret in ('TopSecret123', 'abc==', 'p@ss', 't0k', 'apikey=abc'):
            self.assertNotIn(secret, blob)
        self.assertIn('<w:Password Type="x">***</w:Password>', blob)

    def test_headers_are_not_requested(self):
        self.assertFalse([f for f in es_logs.FIELDS if 'header' in f.lower()])

    def test_paginates_with_search_after(self):
        pages = [{'hits': {'hits': [{'_source': {'i': i}, 'sort': [i]} for i in range(es_logs.PAGE)]}},
                 {'hits': {'hits': [{'_source': {'i': 'last'}, 'sort': [9]}]}}]
        calls = []
        with mock.patch.object(es_logs, '_search', side_effect=lambda u, i, body: calls.append(dict(body)) or pages[len(calls) - 1]):
            docs = es_logs.fetch_flow('dfd2ab53-0ee2-4c78-ae86-42a42e549af8', Path('.'))
        self.assertEqual(len(docs), es_logs.PAGE + 1)
        self.assertEqual(calls[1]['search_after'], [es_logs.PAGE - 1])

    def test_oversized_flow_is_rejected_not_truncated(self):
        full = {'hits': {'hits': [{'_source': {'i': i}, 'sort': [i]} for i in range(es_logs.PAGE)]}}
        with mock.patch.object(es_logs, 'MAX_DOCS', es_logs.PAGE + 10), \
                mock.patch.object(es_logs, '_search', return_value=full):
            with self.assertRaisesRegex(ValueError, 'more than'):
                es_logs.fetch_flow('dfd2ab53-0ee2-4c78-ae86-42a42e549af8', Path('.'))

    def test_plan_fetches_are_serialized(self):
        active, peak = [0], [0]

        def slow(root, issue, prepare, process):
            active[0] += 1
            peak[0] = max(peak[0], active[0])
            import time
            time.sleep(0.05)
            active[0] -= 1
            return {}
        import threading
        with mock.patch.object(es_logs, '_fetch_for_plan_locked', side_effect=slow):
            threads = [threading.Thread(target=es_logs.fetch_for_plan, args=(Path('.'), f'CCON-{i}')) for i in range(3)]
            [t.start() for t in threads]
            [t.join() for t in threads]
        self.assertEqual(peak[0], 1)

    def test_rejects_invalid_flow(self):
        with self.assertRaises(ValueError):
            es_logs.fetch_flow('not-a-uuid')


if __name__ == '__main__':
    unittest.main()
