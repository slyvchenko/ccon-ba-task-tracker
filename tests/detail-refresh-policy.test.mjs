import test from 'node:test';
import assert from 'node:assert/strict';
import {detailContentFingerprint,createDetailRequestScope} from '../assets/detail-refresh-policy.mjs';

test('a new global snapshot timestamp and unrelated task do not invalidate selected detail',()=>{
  const selected={key:'CCON-1',manualRevision:3,analysis:{signal:'WRITE',standardDescription:'Synthetic A'}};
  const snapshot1={at:'2026-10-26T12:00:00Z',tasks:[selected,{key:'CCON-2',summary:'Old'}]};
  const snapshot2={at:'2026-10-26T12:30:00Z',tasks:[structuredClone(selected),{key:'CCON-2',summary:'New'}]};
  assert.equal(detailContentFingerprint(snapshot1.tasks[0]),detailContentFingerprint(snapshot2.tasks[0]));
  assert.notEqual(detailContentFingerprint(snapshot1.tasks[1]),detailContentFingerprint(snapshot2.tasks[1]));
  assert.equal(detailContentFingerprint(null),'');
});
test('changes to selected source, local CAS revision or analysis do trigger detail refresh',()=>{
  const base={key:'CCON-1',manualRevision:3,analysis:{signal:'READY',reasonUk:'Synthetic'}};
  const fingerprint=detailContentFingerprint(base);
  for(const changed of [
    {...base,manualRevision:4},
    {...base,analysis:{...base.analysis,signal:'WRITE'}},
    {...base,summary:'Updated source requirement'}
  ])assert.notEqual(fingerprint,detailContentFingerprint(changed));
});
test('stale same-key responses are rejected after a new render or selecting another task',()=>{
  let selected='CCON-1';
  const gate=createDetailRequestScope(()=>selected);
  const first=gate.begin('CCON-1');
  assert.equal(first(),'CCON-1');
  const next=gate.begin('CCON-1');
  assert.equal(first(),null,'old response cannot overwrite a newer same-key DOM');
  assert.equal(next(),'CCON-1');
  selected='CCON-2';
  assert.equal(next(),null,'old response cannot overwrite a different task');
  const third=gate.begin('CCON-2');
  assert.equal(third(),'CCON-2');
  gate.begin(null);
  assert.equal(third(),null,'clearing the detail invalidates previous responses');
});
test('a delayed response is checked when it resolves, not when it starts', async()=>{
  let selected='CCON-1',release;
  const gate=createDetailRequestScope(()=>selected);
  const first=gate.begin('CCON-1');
  const delayed=new Promise(resolve=>{release=resolve;});
  const pending=delayed.then(()=>first());
  gate.begin('CCON-1');
  release();
  assert.equal(await pending,null);
});
