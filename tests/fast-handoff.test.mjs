import test from 'node:test';
import assert from 'node:assert/strict';
import {quickHandoff, priorityExplanation, priorityDimensions, completionPrompt}
  from '../assets/fast-handoff.mjs';
import {rankTasks} from '../assets/task-rules.mjs';

function task(key, signal='READY', overrides={}) {
  return {key, summary:'Synthetic supplier issue', active:true,
    contextFingerprint:'current', manualStatus:'AUTO',
    activeSprint:true, activeSprintStatus:'VERIFIED', blocking:false,
    analysis:{
      contextFingerprint:'current', signal, reasonUk:'Пояснення',
      nextActionUk:'Порівняй REST поля.',
      queueScore:55, needsEmail:signal==='WRITE',
      standardDescription:'#### Objective\nRetain exact StatusCode and DeliveryStatusCode.\n#### QA\nCheck CANCELLED.',
      qualityGate:{state:'STRUCTURALLY_VERIFIED'}
    },...overrides};
}

test('fast ready handoff exposes one current next action and structurally checked draft only', () => {
  const item=task('CCON-101');
  const fast=quickHandoff(item);
  assert.equal(fast.nextAction,'Порівняй REST поля.');
  assert.equal(fast.readyForCopy,true);
  assert.match(fast.description,/StatusCode and DeliveryStatusCode/);
  assert.match(fast.evidenceNote,/але факти/);
  assert.match(completionPrompt(item),/Копіювання Jira-чернетки не означає/);
  assert.match(completionPrompt(item),/локальний статус DONE/);
});

test('WRITE letter still requires real manual transmission, never auto marked sent', () => {
  const item=task('CCON-102','WRITE');
  const plan=priorityExplanation(item);
  assert.equal(plan.write,true);
  assert.equal(plan.activeSprint,true);
  assert.match(plan.sourceOrder.join('|'),/Лист: потрібен зараз/);
  assert.match(completionPrompt(item),/Лист має бути відправлений вручну/);
  assert.ok(!completionPrompt(item).includes('автоматично надіслати'));
});

test('deep task with source review cannot get shortcut copy approval', () => {
  const item=task('CCON-103','REVIEW');
  item.analysis.qualityGate={state:'NEEDS_REVIEW'};
  assert.equal(quickHandoff(item).readyForCopy,false);
  assert.match(quickHandoff(item).evidenceNote,/потребує перевірки/);
  assert.equal(priorityExplanation(item).signal,'REVIEW');
});

test('blocked or missing verified proof prevents quick copied description', () => {
  for (const gate of ['BLOCKED', 'NEEDS_REVIEW', null, undefined]) {
    const item=task('CCON-104');
    item.analysis.qualityGate=gate ? {state:gate} : gate;
    assert.equal(quickHandoff(item).readyForCopy,false);
  }
  const blocked=task('CCON-105');
  blocked.analysis.qualityGate={state:'BLOCKED'};
  assert.match(quickHandoff(blocked).evidenceNote,/блокує/);
});

test('stale Jira context does not expose stale action or stale draft for quick copy', () => {
  const item=task('CCON-106');
  item.analysis.contextFingerprint='old';
  assert.equal(quickHandoff(item).readyForCopy,false);
  assert.equal(quickHandoff(item).nextAction,'');
  assert.equal(quickHandoff(item).description,'');
  assert.equal(priorityExplanation(item).score,null);
});

test('WAIT, manual Done and archived issues do not become quick wins', () => {
  const wait=task('CCON-107','WAIT');
  const done=task('CCON-108','READY',{manualStatus:'DONE'});
  const archive=task('CCON-109','READY',{active:false});
  assert.equal(priorityExplanation(wait).tier,1);
  assert.equal(quickHandoff(done).readyForCopy,false);
  assert.equal(quickHandoff(archive).readyForCopy,false);
  assert.equal(priorityExplanation(done).lane,2);
  assert.equal(priorityExplanation(archive).lane,3);
});

test('rank explanations match hard lane and action order without changing actual sorting', () => {
  const backlog=task('CCON-202','WRITE',{activeSprint:false});
  const sprint=task('CCON-201','READY',{activeSprint:true});
  const sprintWrite=task('CCON-203','WRITE',{activeSprint:true});
  const ranked=rankTasks([backlog,sprint,sprintWrite]);
  assert.deepEqual(ranked.map(x=>x.key),['CCON-203','CCON-201','CCON-202']);
  assert.deepEqual(ranked.map(x=>priorityExplanation(x).lane),[0,0,1]);
  assert.equal(priorityExplanation(backlog).action,0);
  assert.equal(priorityExplanation(sprint).action,1);
  assert.equal(priorityExplanation(backlog).score,55);
});

test('missing score is unknown, not a fabricated zero-point confirmed score', () => {
  const entry=task('CCON-204');
  delete entry.analysis.queueScore;
  assert.equal(priorityExplanation(entry).score,null);
  assert.match(priorityExplanation(entry).sourceOrder.join(' '),/ще не підтверджено/);
});

test('quick action metadata never mutates task or human text', () => {
  const item=task('CCON-205');
  const original=structuredClone(item);
  quickHandoff(item);
  priorityExplanation(item);
  completionPrompt(item);
  assert.deepEqual(item,original);
});

test('impact, urgency, dependencies, effort and unblocking are independent of speed and pin',()=>{
  const item=task('CCON-220');
  item.analysis.priorityFactors={
    businessImpact:25,urgency:20,dependencies:15,baDecision:20,actionability:8
  };
  item.analysis.queueScore=88;
  const dimensions=priorityDimensions(item,{
    label:'M · 5–20 хв',source:'MANUAL'
  });
  assert.deepEqual(dimensions,{
    impact:'25/25',urgency:'20/25',dependencies:'15/20',
    effort:'M · 5–20 хв',effortSource:'моя оцінка',
    unblocking:'не підтверджено'
  });
  item.blocking=true;
  assert.equal(priorityDimensions(item,{label:'XL',source:'HEURISTIC'}).unblocking,
    'підтверджено');
  assert.equal(priorityDimensions(item,{label:'XL',source:'HEURISTIC'}).effortSource,
    'гіпотеза, низька впевненість');
  const stale=task('CCON-221');
  stale.analysis.priorityFactors={businessImpact:100,urgency:100};
  stale.analysis.contextFingerprint='stale';
  assert.equal(priorityDimensions(stale,null).impact,'не підтверджено');
  assert.equal(priorityDimensions(stale,null).urgency,'не підтверджено');
});

test('P0: human WAIT/DONE/DECIDE suppresses obsolete write explanations', () => {
  for (const manualStatus of ['WAITING INPUT','WAITING DEPENDENCY','NEEDS DECISION','DONE']) {
    const item=task('CCON-230','WRITE',{manualStatus});
    assert.equal(priorityExplanation(item).write,false,manualStatus);
    assert.equal(priorityExplanation(item).sourceOrder[1],
      'Лист: без пріоритету листа',manualStatus);
  }
  // Human IN PROGRESS does not itself suppress a current genuine needsEmail.
  const working=task('CCON-231','WRITE',{manualStatus:'IN PROGRESS'});
  assert.equal(priorityExplanation(working).write,true);
});
