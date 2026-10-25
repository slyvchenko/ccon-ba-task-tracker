"""Synthetic local HTTP caching tests: no Jira credentials or private source data."""
import json
import tempfile
import threading
import unittest
from pathlib import Path

from desk_store import Desk
from performance_smoke import synthetic_document


class JsonSnapshotCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ccon-json-cache-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Desk(self.root)
        self.source = self.store.inbox / 'CCON_BA_Snapshot.json'
        self.put_snapshot(100)

    def put_snapshot(self, count, timestamp='2026-10-25T10:00:00+00:00'):
        doc = synthetic_document(count)
        doc['generatedAt'] = timestamp
        self.source.write_text(json.dumps(doc), encoding='utf-8')
        self.store.import_snapshot()

    def assert_identical(self, store):
        raw = store.view_json_bytes()
        self.assertIsInstance(raw, bytes)
        self.assertEqual(json.loads(raw), store.view())
        return raw

    def test_cache_bytes_stable_until_committed_revision_change(self):
        first = self.assert_identical(self.store)
        self.assertIs(first, self.store.view_json_bytes())
        current = self.store.revision()['revision']
        self.store.save('CCON-1', {'manualStatus':'IN PROGRESS',
                                  'note':'Private synthetic draft',
                                  'expectedManualRevision':0})
        self.assertEqual(self.store.revision()['revision'], current+1)
        second = self.assert_identical(self.store)
        self.assertIsNot(first, second)
        self.assertIs(second, self.store.view_json_bytes())
        self.assertEqual(json.loads(second)['tasks'][0]['note'],'Private synthetic draft')

    def test_external_process_write_invalidates_other_desk_instance_cache(self):
        old = self.store.view_json_bytes()
        secondary = Desk(self.root)
        secondary.save('CCON-1', {'manualStatus':'WAITING INPUT',
                                  'note':'Fresh synthetic update',
                                  'expectedManualRevision':0})
        now = self.assert_identical(self.store)
        self.assertNotEqual(old, now)
        self.assertEqual(json.loads(now)['tasks'][0]['note'],'Fresh synthetic update')

    def test_valid_import_invalidates_and_preserves_manual_overrides(self):
        self.store.save('CCON-1', {'manualStatus':'IN PROGRESS',
                                  'note':'Remember me',
                                  'expectedManualRevision':0})
        before = self.store.view_json_bytes()
        self.put_snapshot(500,'2026-10-25T11:00:00+00:00')
        after = self.assert_identical(self.store)
        self.assertNotEqual(before, after)
        self.assertEqual(len(json.loads(after)['tasks']),500)
        self.assertEqual(json.loads(after)['tasks'][0]['note'],'Remember me')
        self.assertIs(after,self.store.view_json_bytes())

    def test_duplicate_import_and_failed_import_error_invalidate_correctly(self):
        before = self.store.view_json_bytes()
        self.store.import_snapshot()
        self.assertIs(before,self.store.view_json_bytes())
        self.source.write_text('{malformed',encoding='utf-8')
        with self.assertRaises(ValueError):
            self.store.import_snapshot()
        after = self.assert_identical(self.store)
        self.assertNotEqual(before,after)
        self.assertIn('Import failed',json.loads(after)['error'])

    def test_raw_dict_view_is_not_backed_by_mutable_cached_reference(self):
        initial = self.store.view_json_bytes()
        view = self.store.view()
        view['tasks'][0]['summary']='locally mutated'
        self.assertEqual(self.store.view_json_bytes(),initial)
        self.assertNotEqual(self.store.view()['tasks'][0]['summary'],'locally mutated')

    def test_concurrent_cache_reads_and_saves_resolve_without_partial_documents(self):
        failures=[]
        def reader():
            try:
                for _ in range(24):
                    raw=self.store.view_json_bytes()
                    doc=json.loads(raw)
                    assert len(doc['tasks'])==100
                    assert isinstance(doc['revision'],int)
            except Exception as exc:
                failures.append(type(exc).__name__)
        def writer():
            try:
                for i in range(10):
                    self.store.save('CCON-1',{
                      'manualStatus':'IN PROGRESS','note':str(i),
                      'expectedManualRevision':i})
            except Exception as exc:
                failures.append(type(exc).__name__)
        threads=[threading.Thread(target=reader) for _ in range(3)]
        threads.append(threading.Thread(target=writer))
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(failures,[])
        self.assert_identical(self.store)
        self.assertEqual(self.store.revision()['revision'],11)


if __name__ == '__main__':
    unittest.main()
