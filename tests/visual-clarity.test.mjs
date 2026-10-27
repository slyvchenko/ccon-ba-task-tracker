import {readFileSync} from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {queueSummary,queueEmptyState,conciseSnapshotInfo,statusPresentation,
  shouldRenderBriefing,assessmentReason} from '../assets/visual-clarity.mjs';

test('primary queue has only scan-critical counters while all previous counts survive',()=>{
  const result=queueSummary({visible:17,sprint:8,write:4,active:35,analyzed:31,unverified:2});
  assert.equal(result.primary,'17 у списку · спринт 8 · листи 4');
  for(const text of ['35','31/35','2'])
    assert.ok(result.diagnostics.includes(text));
  assert.equal(result.primary.includes('аналіз'),false);
  assert.equal(result.primary.includes('короткі'),false);
  assert.equal(result.diagnostics.includes('короткі кандидати'),false);
});

test('header no longer duplicates queue size and WRITE totals',()=>{
  assert.equal(conciseSnapshotInfo({generated_at:'2026-10-25'},()=> 'сьогодні'),'Оновлено сьогодні');
  assert.equal(conciseSnapshotInfo(null,()=>''),'Очікую snapshot');
});

test('source distinction: Jira / manual / sprint are not a single status',()=>{
  const view=statusPresentation({
    jiraStatus:'In Progress',manualStatus:'WAITING INPUT',manualLabel:'Очікую відповідь',
    activeSprintStatus:'VERIFIED',activeSprint:true,
    activeSprintNames:['Synthetic Sprint']});
  assert.deepEqual(view.provenance,
    ['Jira: In Progress','Мій стан: Очікую відповідь','Активний спринт: Synthetic Sprint']);
  assert.deepEqual(view.alerts,[]);
});

test('only actionable warnings visible, but all critical blockers retained',()=>{
  const result=statusPresentation({
    jiraStatus:'Blocked',manualStatus:'AUTO',activeSprintStatus:'UNVERIFIED',
    active:false,blocking:true,email:true,waiting:true,waitingLabel:'Очікуємо Supplier',
    isWrite:true});
  assert.match(result.provenance.join(' '),/Спринт не підтверджено/);
  for(const text of ['Блокує інших','Поза поточним snapshot','Потрібен лист','Очікуємо Supplier'])
    assert.ok(result.alerts.includes(text));
  assert.ok(!result.provenance.join(' ').includes('Не очікуємо'));
});

test('manual IN PROGRESS still shows an actual supplier email action',()=>{
 const r=statusPresentation({manualStatus:'IN PROGRESS',email:true,isWrite:false,
   waiting:false});
 assert.ok(r.alerts.includes('Потрібен лист'));
});

test('neutral email/wait statuses are omitted, not treated as ready',()=>{
  const r=statusPresentation({manualStatus:'AUTO',email:false,waiting:false,isWrite:false});
  assert.deepEqual(r.alerts,[]);
  assert.match(r.provenance.join(','),/Мій стан: Автоматично/);
});

test('avoid duplicate empty briefing and reason only, no loss of real data',()=>{
  assert.equal(shouldRenderBriefing(undefined),false);
  assert.equal(shouldRenderBriefing(null),false);
  assert.equal(shouldRenderBriefing([]),false);
  assert.equal(shouldRenderBriefing({confirmedFacts:[]}),false);
  assert.equal(shouldRenderBriefing({confirmedFacts:[],rules:[],timeline:[]}),false);
  assert.equal(shouldRenderBriefing({currentUk:'   ',targetUk:'',unknownsUk:[]}),false);
  assert.equal(shouldRenderBriefing({readiness:'INSUFFICIENT_CONTEXT'}),true);
  assert.equal(shouldRenderBriefing({confirmedFacts:[{textUk:'Synthetic fact',sourceUrl:'https://example.invalid'}]}),true);
  assert.equal(shouldRenderBriefing({rules:[{whenUk:'IF A',thenUk:'THEN B'}]}),true);
  assert.equal(shouldRenderBriefing({unknownsUk:['Needs source review']}),true);
  assert.equal(shouldRenderBriefing({currentUk:'Synthetic verified state'}),true);
  assert.equal(assessmentReason(null),'');
  assert.equal(assessmentReason('  '),'');
  assert.equal(assessmentReason(' Supplier requires new RT fields '),'Supplier requires new RT fields');
});

test('empty queue messaging separates no snapshot, empty scope, filtered and stale',()=>{
  assert.equal(queueEmptyState({visible:1,total:4,hasSnapshot:true}),null);
  const states=[
    queueEmptyState({visible:0,total:0,hasSnapshot:false}),
    queueEmptyState({visible:0,total:0,hasSnapshot:true}),
    queueEmptyState({visible:0,total:7,hasSnapshot:true}),
    queueEmptyState({visible:0,total:7,hasSnapshot:true,importError:true}),
    queueEmptyState({visible:0,total:0,hasSnapshot:false,importError:true})
  ];
  assert.deepEqual(states.map(x=>x.kind),['unavailable','empty','no-matches','stale','error']);
  for (const state of states) {
    assert.ok(state.text.trim());
    assert.ok(!/успішно синхронізовано/i.test(state.text));
  }
  assert.match(states[2].text,/фільтр/);
  assert.match(states[3].text,/не вдалося/);
  assert.match(states[4].text,/Попереднього списку немає/);
});

test('archived tasks cannot masquerade as populated current snapshot',()=>{
 const js=readFileSync(new URL('../assets/dashboard.mjs',import.meta.url),'utf8');
 assert.match(js,/queueEmptyState\(\{visible:items\.length,total:tasks\.filter\(task=>task\.active!==false\)\.length,/);
 assert.equal(queueEmptyState({visible:0,total:0,hasSnapshot:true}).kind,'empty');
 assert.equal(queueEmptyState({visible:0,total:2,hasSnapshot:true}).kind,'no-matches');
});
