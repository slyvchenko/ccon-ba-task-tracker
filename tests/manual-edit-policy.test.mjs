import test from 'node:test';
import assert from 'node:assert/strict';
import {baseManualRevision, manualVersionChanged, withExpectedRevision}
  from '../assets/manual-edit-policy.mjs';

test('new form uses current server version, recovered draft pins original version', () => {
  assert.equal(baseManualRevision(undefined, {manualRevision:7}), 7);
  assert.equal(baseManualRevision({note:'unsaved',baseRevision:3}, {manualRevision:8}), 3);
  assert.equal(baseManualRevision({note:'old recovery'}, {manualRevision:8}), null);
  assert.equal(baseManualRevision(undefined, {manualRevision:undefined}), null);
  assert.equal(baseManualRevision({baseRevision:-1}, {manualRevision:8}), null);
});

test('different versions, unknown versions and stale sessions require explicit review', () => {
  assert.equal(manualVersionChanged(7,7), false);
  assert.equal(manualVersionChanged(7,8), true);
  assert.equal(manualVersionChanged(null,0), true);
  assert.equal(manualVersionChanged(-1,0), true);
  assert.equal(manualVersionChanged(0,undefined), true);
});

test('manual post payload keeps text unchanged and includes one CAS token', () => {
  const local = {
    manualStatus:'IN PROGRESS', note:'Never lose this private draft',
    emailDraft:{to:'synthetic@example.invalid', subject:'Test', body:'Supplier body'}
  };
  const initial = structuredClone(local);
  const request = withExpectedRevision(local,12);
  assert.deepEqual(request,{...local,expectedManualRevision:12});
  assert.deepEqual(local,initial);
  for (const token of [null,-1,1.2,'12',undefined]) {
    assert.throws(() => withExpectedRevision(local,token), /Unknown local edit revision/);
  }
});

test('simulated tab B cannot auto-save stale local edits without a new token', () => {
  const originalVersion = 3;
  const remoteAfterTabA = 4;
  assert.equal(manualVersionChanged(originalVersion,remoteAfterTabA), true);
  const recovered = {manualStatus:'WAITING INPUT', note:'My preserved version',
                     baseRevision:originalVersion};
  assert.equal(baseManualRevision(recovered,{manualRevision:remoteAfterTabA}), 3);
  assert.equal(withExpectedRevision(recovered, originalVersion).expectedManualRevision, 3);
  // Server rejects it with 409, user must explicitly compare latest revision.
});
