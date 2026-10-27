import test from 'node:test';
import assert from 'node:assert/strict';
import {makeUndoToken,canUndoLocalDone,undoLocalDonePayload,rebaseUndoForm} from '../assets/manual-done-undo.mjs';

test('a local successful DONE creates one CAS protected reversible action',()=>{
  const t={key:'CCON-101',manualStatus:'DONE',manualRevision:18,active:true,
    note:'Keep these human notes',savedEmailDraft:{body:'Not sent'}};
  const token=makeUndoToken(t,'IN PROGRESS',18);
  assert.equal(canUndoLocalDone(token,t),true);
  assert.deepEqual(undoLocalDonePayload(token,t),
    {manualStatus:'IN PROGRESS',note:'Keep these human notes',expectedManualRevision:18});
  assert.equal(undoLocalDonePayload(token,{...t,manualRevision:19}),null);
});
test('cannot undo a third-party status update or another issue',()=>{
  const token=makeUndoToken({key:'CCON-2'},'AUTO',3);
  assert.equal(canUndoLocalDone(token,{key:'CCON-3',manualStatus:'DONE',manualRevision:3}),false);
  assert.equal(canUndoLocalDone(token,{key:'CCON-2',manualStatus:'WAITING INPUT',manualRevision:3}),false);
  assert.equal(canUndoLocalDone(token,{key:'CCON-2',manualStatus:'DONE',manualRevision:4}),false);
  assert.equal(canUndoLocalDone(token,{key:'CCON-2',manualStatus:'DONE',manualRevision:3,active:false}),false);
});
test('no token can be made for already-DONE/invalid version and no external replay',()=>{
  assert.equal(makeUndoToken({key:'CCON-1'},'DONE',2),null);
  assert.equal(makeUndoToken({key:'CCON-1'},'AUTO',-1),null);
  assert.equal(makeUndoToken({key:'ES8SQX'},'AUTO',2),null);
  const result=makeUndoToken({key:'CCON-1'},'AUTO',5);
  assert.equal(typeof result.send,'undefined');
  assert.equal(typeof result.updateJira,'undefined');
});
