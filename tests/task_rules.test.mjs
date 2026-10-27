import test from 'node:test';
import assert from 'node:assert/strict';
import {effectiveSignal, hasAnalysis, priorityEmail, actionRank, rankTasks, filterTasks, defaultRecipients, signalInfo} from '../assets/task-rules.mjs';

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


test('verified active sprint outranks any outside-sprint score including urgent backlog', () => {
  const item = (key, score, activeSprint, signal='READY') => task(key, signal, score, {
    activeSprintStatus: 'VERIFIED', activeSprint,
  });
  const items = [item('backlog-max', 100, false), item('sprint-low', 0, true),
    item('sprint-wait', 0, true, 'WAIT'), item('backlog-high', 99, false)];
  assert.deepEqual(rankTasks(items).map(x => x.key),
    ['sprint-low', 'sprint-wait', 'backlog-max', 'backlog-high']);
  assert.deepEqual(filterTasks(items, {sprint: 'active'}).map(x => x.key),
    ['sprint-low', 'sprint-wait']);
  assert.deepEqual(filterTasks(items, {sprint: 'outside'}).map(x => x.key),
    ['backlog-max', 'backlog-high']);
});

test('unverified sprint membership is not silently treated as in sprint', () => {
  const items = [task('not-configured', 'WRITE', 100),
    task('in-sprint', 'READY', 0, {activeSprintStatus:'VERIFIED',activeSprint:true})];
  assert.deepEqual(rankTasks(items).map(x => x.key), ['in-sprint','not-configured']);
  assert.deepEqual(filterTasks(items, {sprint:'unverified'}).map(x => x.key), ['not-configured']);
});

test('manual done remains below open backlog even if its sprint membership is true', () => {
  const items = [task('manual-done', 'READY', 100, {activeSprintStatus:'VERIFIED',
      activeSprint:true,manualStatus:'DONE'}),
    task('backlog-ready', 'READY', 0, {activeSprintStatus:'VERIFIED',activeSprint:false})];
  assert.deepEqual(rankTasks(items).map(x=>x.key), ['backlog-ready','manual-done']);
});

test('search finds mixed technical method, supplier alias and linked issue tokens', () => {
  const entry = task('CCON-888','REVIEW',32,{
    summary: 'AF/KL. retrievePNR. Cancelled segment',
    jiraStatus:'In Progress',
    links:[{linkedKey:'CCON-456'}]
  });
  entry.analysis.briefing = {technicalScopeUk:'REST GetOrder',rules:[
    {whenUk:'StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED',thenUk:'Omit segment'}]};
  const list = [entry, task('CCON-999')];
  assert.deepEqual(filterTasks(list, {search:'afkl retrievepnr'}).map(x=>x.key), ['CCON-888']);
  assert.deepEqual(filterTasks(list, {search:'CCON-456 REMOVED'}).map(x=>x.key), ['CCON-888']);
  assert.deepEqual(filterTasks(list, {search:'rest GetOrder'}).map(x=>x.key), ['CCON-888']);
  assert.deepEqual(filterTasks(list, {search:'unknown method'}), []);
});

test('punctuation-only query must not match all tasks via empty folded text', () => {
  const list = [
    task('CCON-101', 'READY', 50, {summary:'Normal synthetic order'}),
    task('CCON-102', 'READY', 50, {summary:'Synthetic: method failed'}),
    task('CCON-103', 'READY', 50, {summary:'Value 100% is observed'})
  ];
  assert.deepEqual(filterTasks(list,{search:'!!!'}).map(x=>x.key),[]);
  assert.deepEqual(filterTasks(list,{search:'@'}).map(x=>x.key),[]);
  assert.deepEqual(filterTasks(list,{search:'%'}).map(x=>x.key),['CCON-103']);
  assert.deepEqual(filterTasks(list,{search:'method !!!'}).map(x=>x.key),[]);
  assert.deepEqual(filterTasks(list,{search:'method:'}).map(x=>x.key),['CCON-102']);
});

test('P0: manual WAIT and NEEDS DECISION cannot inherit stale WRITE ranking', () => {
  const ready=task('CCON-900','READY',0);
  for (const manualStatus of ['WAITING INPUT','WAITING DEPENDENCY','NEEDS DECISION','DONE']) {
    const overridden=task('CCON-901','WRITE',100,{manualStatus});
    overridden.analysis.needsEmail=true;
    assert.equal(priorityEmail(overridden),false,manualStatus);
    assert.ok(actionRank(overridden)>0,manualStatus);
    assert.deepEqual(rankTasks([overridden,ready]).map(x=>x.key),
      ['CCON-900','CCON-901'],manualStatus);
  }

  // Explicit current email work remains first among otherwise active tasks.
  const email=task('CCON-902','REVIEW',0);
  email.analysis.needsEmail=true;
  assert.equal(priorityEmail(email),true);
  assert.deepEqual(rankTasks([ready,email]).map(x=>x.key),['CCON-902','CCON-900']);
});

test('P0: stale needsEmail never creates a WRITE priority', () => {
  const stale=task('CCON-903','WRITE',100);
  stale.analysis.needsEmail=true;
  stale.analysis.contextFingerprint='old';
  const ready=task('CCON-904','READY',0);
  assert.equal(priorityEmail(stale),false);
  assert.equal(actionRank(stale),2);
  assert.deepEqual(rankTasks([stale,ready]).map(x=>x.key),['CCON-904','CCON-903']);
});
