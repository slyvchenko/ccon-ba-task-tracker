import json
import tempfile
import unittest
from pathlib import Path
from desk_store import Desk


class LocalCompletionPolicyTests(unittest.TestCase):
    def test_disabled_done_is_rejected_without_touching_notes_or_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'.desk-preferences.json').write_text('{"localCompletion":false}',encoding='utf-8')
            desk=Desk(root)
            snapshot={'generatedAt':'2026-10-26T12:00:00Z','tasks':[{'key':'CCON-1','summary':'Synthetic'}]}
            (desk.inbox/'CCON_BA_Snapshot.json').write_text(json.dumps(snapshot),encoding='utf-8')
            desk.import_snapshot()
            draft={'to':'test@example.invalid','subject':'Subject','body':'Preserve body'}
            desk.save('CCON-1',{'manualStatus':'AUTO','note':'Preserve note','emailDraft':draft})
            before=desk.view()['tasks'][0]
            with self.assertRaisesRegex(ValueError,'Local completion is disabled'):
                desk.save('CCON-1',{'manualStatus':'DONE','note':'Wrong','expectedManualRevision':before['manualRevision']})
            after=desk.view()['tasks'][0]
            self.assertFalse(after['localCompletionEnabled'])
            self.assertEqual(after['note'],before['note'])
            self.assertEqual(after['savedEmailDraft'],draft)
            self.assertEqual(after['manualRevision'],before['manualRevision'])


    def test_legacy_done_is_not_effective_when_local_completion_is_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            desk=Desk(root)
            snapshot={'generatedAt':'2026-10-26T12:00:00Z','tasks':[{'key':'CCON-1','summary':'Synthetic'}]}
            (desk.inbox/'CCON_BA_Snapshot.json').write_text(json.dumps(snapshot),encoding='utf-8')
            desk.import_snapshot()
            desk.save('CCON-1',{'manualStatus':'DONE','note':'Legacy'})
            (root/'.desk-preferences.json').write_text('{"localCompletion":false}',encoding='utf-8')
            task=Desk(root).view()['tasks'][0]
            self.assertEqual(task['manualStatus'],'AUTO')
            self.assertTrue(task['legacyLocalDone'])
            self.assertEqual(task['note'],'Legacy')


if __name__=='__main__':
    unittest.main()
