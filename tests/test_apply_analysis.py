import json
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from apply_analysis import apply
from server import Desk
from pipeline_lock import pipeline_lock

class AnalysisIntegrity(unittest.TestCase):
    def setUp(self):
        self.root=Path(__file__).resolve().parent/('test-data-'+uuid.uuid4().hex)
        (self.root/'data').mkdir(parents=True)
        self.desk=Desk(self.root)
        self.snapshot={'generatedAt':'2026-10-07T08:00:00Z','tasks':[{'key':'CCON-1','summary':'One','contextFingerprint':'current'}]}
        self.target=self.root/'inbox/CCON_BA_Snapshot.json'
        self.target.write_text(json.dumps(self.snapshot),encoding='utf-8')
        self.desk.import_snapshot()
        (self.root/'data/jira_context.json').write_text(json.dumps({'complete':True,'issues':{'CCON-1':{'fingerprint':'current'}}}),encoding='utf-8')
        self.analysis={'signal':'WRITE','reasonUk':'Потрібне уточнення меж вимоги.','nextActionUk':'Уточни очікуваний результат.',
          'missingInfo':['Очікуваний результат'],'waitingRequired':False,'waitingOnUk':'Ніхто','needsEmail':True,
          'queueScore':80,'evidence':[],'standardDescription':'','emailDraft':{'to':'','subject':'Question','body':'Could you clarify?'},'contextFingerprint':'current'}
        self.path=self.root/'data/daily_analysis.json'

    def tearDown(self):
        target=self.root.resolve()
        assert target.is_relative_to(Path(__file__).resolve().parent) and target.name.startswith('test-data-')
        shutil.rmtree(target)

    def run_apply(self,analyses):
        self.path.write_text(json.dumps({'analyses':analyses}),encoding='utf-8')
        apply(self.path,self.root)

    def test_incomplete_or_stale_analysis_keeps_last_snapshot(self):
        original=self.target.read_bytes()
        with self.assertRaises(ValueError):
            self.run_apply({})
        self.assertEqual(self.target.read_bytes(),original)
        self.analysis['contextFingerprint']='old'
        with self.assertRaises(ValueError):
            self.run_apply({'CCON-1':self.analysis})
        self.assertEqual(self.target.read_bytes(),original)

    def test_invalid_nested_draft_does_not_replace_snapshot(self):
        original=self.target.read_bytes()
        self.analysis['emailDraft']['body']=42
        with self.assertRaises(ValueError):
            self.run_apply({'CCON-1':self.analysis})
        self.assertEqual(self.target.read_bytes(),original)

    def test_current_analysis_preserves_manual_state_and_draft(self):
        draft={'to':'','subject':'Edited','body':'My edited draft'}
        self.desk.save('CCON-1',{'manualStatus':'IN PROGRESS','note':'Ручна нотатка','emailDraft':draft})
        self.run_apply({'CCON-1':self.analysis})
        task=self.desk.view()['tasks'][0]
        self.assertEqual(task['analysis']['signal'],'WRITE')
        self.assertFalse(task['analysis']['stale'])
        self.assertEqual(task['note'],'Ручна нотатка')
        self.assertEqual(task['manualStatus'],'IN PROGRESS')
        self.assertEqual(task['savedEmailDraft'],draft)

    def test_matching_analysis_cannot_validate_snapshot_from_another_sync(self):
        self.snapshot['tasks'][0]['contextFingerprint']='other-sync'
        self.target.write_text(json.dumps(self.snapshot),encoding='utf-8')
        original=self.target.read_bytes()
        with self.assertRaisesRegex(ValueError,'different syncs'):
            self.run_apply({'CCON-1':self.analysis})
        self.assertEqual(self.target.read_bytes(),original)
        self.assertNotIn('analysis',self.desk.view()['tasks'][0])

    def test_lock_rejects_overlapping_apply_and_releases_after_error(self):
        original=self.target.read_bytes()
        with pipeline_lock(self.root):
            with self.assertRaisesRegex(ValueError,'Another Jira sync'):
                self.run_apply({'CCON-1':self.analysis})
        self.assertEqual(self.target.read_bytes(),original)
        self.analysis['contextFingerprint']='old'
        with self.assertRaises(ValueError):
            self.run_apply({'CCON-1':self.analysis})
        self.analysis['contextFingerprint']='current'
        self.run_apply({'CCON-1':self.analysis})
        self.assertFalse(self.desk.view()['tasks'][0]['analysis']['stale'])

    def test_lock_is_shared_between_processes(self):
        code=('from pipeline_lock import pipeline_lock\nfrom pathlib import Path\nimport sys\n'
              'try:\n    with pipeline_lock(Path(sys.argv[1])):\n        sys.exit(0)\n'
              'except ValueError:\n    sys.exit(3)\n')
        with pipeline_lock(self.root):
            result=subprocess.run([sys.executable,'-c',code,str(self.root)],
                                  cwd=Path(__file__).resolve().parents[1],
                                  capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,3,result.stderr)
        result=subprocess.run([sys.executable,'-c',code,str(self.root)],
                              cwd=Path(__file__).resolve().parents[1],
                              capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_external_context_change_during_validation_preserves_snapshot(self):
        original=self.target.read_bytes()
        validate=Desk.validate_analysis
        def change_context(analysis):
            validate(analysis)
            path=self.root/'data/jira_context.json'
            context=json.loads(path.read_text(encoding='utf-8'))
            context['externalEdit']=True
            path.write_text(json.dumps(context),encoding='utf-8')
        with patch.object(Desk,'validate_analysis',side_effect=change_context):
            with self.assertRaisesRegex(ValueError,'changed during'):
                self.run_apply({'CCON-1':self.analysis})
        self.assertEqual(self.target.read_bytes(),original)
        self.assertNotIn('analysis',self.desk.view()['tasks'][0])

    def test_repeated_apply_accepts_current_fingerprint_and_preserves_draft(self):
        draft={'to':'','subject':'Keep edited subject','body':'Keep edited body'}
        self.desk.save('CCON-1',{'manualStatus':'WAITING INPUT','note':'Мій вибір','emailDraft':draft})
        self.run_apply({'CCON-1':self.analysis})
        self.run_apply({'CCON-1':self.analysis})
        task=self.desk.view()['tasks'][0]
        self.assertFalse(task['analysis']['stale'])
        self.assertEqual(task['savedEmailDraft'],draft)
        self.assertEqual(task['manualStatus'],'WAITING INPUT')
        self.assertEqual(task['note'],'Мій вибір')
