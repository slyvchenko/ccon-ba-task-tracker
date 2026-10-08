import test from 'node:test';
import assert from 'node:assert/strict';
import {effectiveSignal, hasAnalysis, rankTasks, filterTasks, defaultRecipients, signalInfo} from '../assets/task-rules.mjs';

function task(key, signal = 'WRITE', score = 50, extra = {}) {
  return {key, summary: key, active: true, manualStatus: 'AUTO', contextFingerprint: 'current',
    analysis: {signal, queueScore: score, reasonUk: 'Причина', nextActionUk: 'Уточни деталі', contextFingerprint: 'current'}, ...extra};
}

test('manual decisions override generated actions, including stale analyses', () => {
  for (const [manualStatus, expected] of [['DONE', 'DONE'], ['WAITING INPUT', 'WAIT'], ['WAITING DEPENDENCY', 'WAIT'], ['NEEDS DECISION', 'DECIDE'], ['IN PROGRESS', 'READY']]) {
    const item = task('CCON-1', 'WRITE', 100, {manualStatus});
    item.analysis.stale = true;
    assert.equal(effectiveSignal(item), expected);
  }
  assert.equal(signalInfo(task('CCON-1', 'WRITE', 0, {manualStatus: 'IN PROGRESS'})).label, 'Аналітика');
});

test('stale or incomplete generated analyses cannot determine the action', () => {
  const stale = task('CCON-1'); stale.analysis.contextFingerprint = 'previous';
  assert.equal(hasAnalysis(stale), false);
  assert.equal(effectiveSignal(stale), 'REVIEW');
  const incomplete = task('CCON-2'); delete incomplete.analysis.nextActionUk;
  assert.equal(effectiveSignal(incomplete), 'REVIEW');
});

test('queue groups, risk priority and tie ordering remain stable without mutating input', () => {
  const input = [task('low', 'READY', 1), task('wait', 'WAIT', 999), task('high', 'WRITE', 90),
    task('same', 'READY', 90), task('done', 'DONE', 999), task('archive', 'WRITE', 999, {active: false})];
  const before = structuredClone(input);
  assert.deepEqual(rankTasks(input).map(item => item.key), ['high', 'same', 'low', 'wait', 'done', 'archive']);
  assert.deepEqual(input, before);
});

test('filters respect manual completion, archived tasks and current actions', () => {
  const input = [task('CCON-1'), task('CCON-2', 'WRITE', 50, {manualStatus: 'DONE'}), task('CCON-3', 'WRITE', 50, {active: false})];
  assert.deepEqual(filterTasks(input, {signal: 'WRITE'}).map(item => item.key), ['CCON-1']);
  assert.deepEqual(filterTasks(input, {filter: 'done'}).map(item => item.key), ['CCON-2']);
  assert.deepEqual(filterTasks(input, {filter: 'archive'}).map(item => item.key), ['CCON-3']);
  assert.deepEqual(filterTasks(input, {search: 'уточни'}).map(item => item.key), ['CCON-1']);
});

test('recipient defaults keep the approved supplier mappings', () => {
  assert.match(defaultRecipients({summary: 'Airtuerk. bookings'}), /systems@airtuerk\.de.*odemir@airtuerk\.de/);
  assert.match(defaultRecipients({summary: 'AF/KL. Retrieve'}), /mail\.afkl\.ndc\.production@airfrance\.fr.*mail\.afkl\.ndc\.team@airfrance\.fr/);
  assert.match(defaultRecipients({summary: 'SQ213. PNR Modify'}), /leon_woon@singaporeair\.com\.sg.*NDC_Support@singaporeair\.com\.sg/);
  assert.equal(defaultRecipients({summary: 'Other supplier'}), '');
});
