import test from 'node:test';
import assert from 'node:assert/strict';
import {needsFullTaskRefresh} from '../assets/revision-policy.mjs';
import {filterTasks, rankTasks} from '../assets/task-rules.mjs';

function item(key, signal='READY', score=30) {
  const analysis = {signal, reasonUk:'Confirmed source text', nextActionUk:'Перевірити метод',
    queueScore:score, contextFingerprint:'current'};
  Object.defineProperty(analysis, 'briefing', {
    get() { throw Error('Unneeded deep Jira search data read'); }
  });
  return {key, active:true, summary:'Task '+key, manualStatus:'AUTO',
    contextFingerprint:'current', activeSprintStatus:'VERIFIED',
    activeSprint:key.endsWith('1'), analysis};
}

test('revision poll fetches full tasks only on change, error change, or invalid response', () => {
  assert.equal(needsFullTaskRefresh(4, '', {revision:4,error:''}), false);
  assert.equal(needsFullTaskRefresh(4, '', {revision:5,error:''}), true);
  assert.equal(needsFullTaskRefresh(4, '', {revision:4,error:'Invalid snapshot'}), true);
  assert.equal(needsFullTaskRefresh(4, 'Invalid snapshot', {revision:4,error:''}), true);
  assert.equal(needsFullTaskRefresh(null, '', {revision:0,error:''}), true);
  assert.equal(needsFullTaskRefresh(4, '', {revision:'4',error:''}), true);
  assert.equal(needsFullTaskRefresh(4, '', null), true);
  assert.equal(needsFullTaskRefresh(4, '', {revision:-1}), true);
});

test('no-query and priority-lane filters never materialize expensive Jira descriptions', () => {
  const tasks = [item('CCON-1'),item('CCON-2'),item('CCON-3','WAIT')];
  const ranked = rankTasks(tasks);
  assert.deepEqual(filterTasks(ranked).map(x => x.key), ['CCON-1','CCON-2','CCON-3']);
  assert.deepEqual(filterTasks(ranked, {signal:'READY'}).map(x => x.key),
    ['CCON-1','CCON-2']);
  assert.deepEqual(filterTasks(ranked,{sprint:'active'}).map(x => x.key),['CCON-1']);
  assert.deepEqual(filterTasks(ranked,{search:'   '}).map(x => x.key),
    ['CCON-1','CCON-2','CCON-3']);
  assert.throws(() => filterTasks(ranked,{search:'technical'}), /Unneeded deep Jira/);
});

test('outside-sprint tasks cannot jump ahead despite a higher score or faster action', () => {
  const urgent = item('CCON-1','REVIEW',1);
  const quick = item('CCON-2','WRITE',99);
  assert.deepEqual(rankTasks([quick,urgent]).map(x=>x.key),['CCON-1','CCON-2']);
});
