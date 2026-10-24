import test from 'node:test';
import assert from 'node:assert/strict';
import {actionPlanMarkup, taskHistoryMarkup} from '../assets/action-history.mjs';

const esc = x => String(x ?? '').replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

test('action plan is collapsed detail content and AI suggestion requires click', () => {
  const html = actionPlanMarkup({actions:[],overdueCount:0}, esc, 'Check supplier <payload>');
  assert.match(html, /Додати до плану/);
  assert.match(html, /AI-пропозиція не стає задачею автоматично/);
  assert.match(html, /&lt;payload&gt;/);
  assert.doesNotMatch(html, /<payload>/);
});

test('action status shows overdue and editable controls', () => {
  const html = actionPlanMarkup({actions:[{
    id:'A-123456789abc', description:'Send email', owner:'BA',
    status:'WAITING', overdue:true, dueDate:'2026-10-20',
    nextReviewDate:'2026-10-24', waitingOn:'AF/KL'
  }],overdueCount:1}, esc);
  assert.match(html,/Прострочено/);
  assert.match(html,/2026-10-20/);
  assert.match(html,/Зберегти дію/);
  assert.match(html,/Очікуємо/);
});

test('task history shows changes, revision content and paging without exposing raw markup', () => {
  const html = taskHistoryMarkup({
    total:23,hasMore:true,revisions:[{
      id:42,at:'2026-10-24T10:00:00Z',origin:'MANUAL',
      changed:['note','manualStatus'],
      state:{summary:'<script>evil</script>',note:'Check & document',
             manualStatus:'IN PROGRESS',savedEmailDraft:{body:'Edited text'}}
    }]
  },esc);
  assert.match(html,/Ручна зміна/);
  assert.match(html,/Показати попередні зміни/);
  assert.match(html,/Check &amp; document/);
  assert.match(html,/Edited text/);
  assert.doesNotMatch(html,/<script>/);
});

test('empty history is explicit',()=>{
  assert.match(taskHistoryMarkup({total:0,revisions:[],hasMore:false},esc),/Збережених ревізій ще немає/);
});
