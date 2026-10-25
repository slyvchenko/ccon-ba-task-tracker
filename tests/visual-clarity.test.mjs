import test from 'node:test';
import assert from 'node:assert/strict';
import {queueSummary,conciseSnapshotInfo,statusPresentation,
  shouldRenderBriefing,assessmentReason} from '../assets/visual-clarity.mjs';

test('primary queue has only scan-critical counters while all previous counts survive',()=>{
  const result=queueSummary({visible:17,sprint:8,write:4,active:35,analyzed:31,quick:5,unverified:2});
  assert.equal(result.primary,'17 у списку · спринт 8 · листи 4');
  for(const text of ['35','31/35','5','2'])
    assert.ok(result.diagnostics.includes(text));
  assert.equal(result.primary.includes('аналіз'),false);
  assert.equal(result.primary.includes('короткі'),false);
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

test('neutral email/wait statuses are omitted, not treated as ready',()=>{
  const r=statusPresentation({manualStatus:'AUTO',email:false,waiting:false,isWrite:false});
  assert.deepEqual(r.alerts,[]);
  assert.match(r.provenance.join(','),/Мій стан: Автоматично/);
});

test('avoid duplicate empty briefing and reason only, no loss of real data',()=>{
  assert.equal(shouldRenderBriefing(undefined),false);
  assert.equal(shouldRenderBriefing(null),false);
  assert.equal(shouldRenderBriefing([]),false);
  assert.equal(shouldRenderBriefing({confirmedFacts:[]}),true);
  assert.equal(assessmentReason(null),'');
  assert.equal(assessmentReason('  '),'');
  assert.equal(assessmentReason(' Supplier requires new RT fields '),'Supplier requires new RT fields');
});
