"""Synthetic, local-only manual priority persistence and safety tests."""
import json
import tempfile
import unittest
from pathlib import Path
from desk_store import Desk, SaveConflict


class ManualWorkPriorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.desk = Desk(self.root)
        self.doc = {'generatedAt':'2026-11-06T10:00:00Z','tasks':[
            {'key':'CCON-100','summary':'Synthetic support issue','labels':['AIS_Prio_Bug']},
            {'key':'CCON-101','summary':'Synthetic focus issue'}]}
        self.write_snapshot()
        self.desk.import_snapshot()

    def tearDown(self):
        self.tmp.cleanup()

    def write_snapshot(self):
        (self.root/'inbox'/'CCON_BA_Snapshot.json').write_text(
            json.dumps(self.doc),encoding='utf-8')

    def task(self,key='CCON-100'):
        return next(t for t in self.desk.view()['tasks'] if t['key']==key)

    def test_default_upgrade_and_manual_priority_roundtrip(self):
        self.assertEqual(self.task()['manualPriority'],'NONE')
        prior=self.task()['manualRevision']
        self.desk.save('CCON-100',{'manualStatus':'AUTO','note':'',
            'manualPriority':'BUSINESS','expectedManualRevision':prior})
        self.assertEqual(self.task()['manualPriority'],'BUSINESS')
        self.assertEqual(Desk(self.root).view()['tasks'][0]['manualPriority'],'BUSINESS')
        self.doc['generatedAt']='2026-11-07T10:00:00Z'
        self.doc['tasks'][0]['summary']='Updated in Jira'
        self.write_snapshot()
        self.desk.import_snapshot()
        self.assertEqual(self.task()['manualPriority'],'BUSINESS')
        self.assertEqual(self.task()['summary'],'Updated in Jira')
        self.assertEqual(self.desk.history('CCON-100')['revisions'][0]['state']['manualPriority'],'BUSINESS')

    def test_legacy_status_writes_do_not_reset_priority(self):
        self.desk.save('CCON-100',{'manualStatus':'AUTO','note':'',
            'manualPriority':'URGENT'})
        self.desk.save('CCON-100',{'manualStatus':'WAITING INPUT','note':'Waiting'})
        self.assertEqual(self.task()['manualPriority'],'URGENT')
        self.assertEqual(self.task()['note'],'Waiting')

    def test_invalid_priority_is_atomic(self):
        original=self.desk.view()
        for value in ('SUPPORT','P1',None,10,{}):
            with self.assertRaises(ValueError):
                self.desk.save('CCON-100',{'manualStatus':'AUTO',
                    'note':'should not persist','manualPriority':value})
            self.assertEqual(self.desk.view(),original)

    def test_stale_revision_cannot_overwrite_priority(self):
        version=self.task()['manualRevision']
        self.desk.save('CCON-100',{'manualStatus':'AUTO','note':'',
            'manualPriority':'BUSINESS','expectedManualRevision':version})
        with self.assertRaises(SaveConflict):
            self.desk.save('CCON-100',{'manualStatus':'AUTO','note':'stale',
                'manualPriority':'URGENT','expectedManualRevision':version})
        self.assertEqual(self.task()['manualPriority'],'BUSINESS')
        self.assertEqual(self.task()['note'],'')

    def test_bad_label_shape_rejected_without_partial_import(self):
        previous=self.desk.view()
        self.doc['generatedAt']='2026-11-08T10:00:00Z'
        self.doc['tasks'][0]['labels']='AIS_Prio_Bug'
        self.write_snapshot()
        with self.assertRaises(ValueError):
            self.desk.import_snapshot()
        self.assertEqual(self.desk.view()['tasks'],previous['tasks'])
        self.assertEqual(self.desk.view()['revision'],previous['revision'])


if __name__ == '__main__':
    unittest.main()
