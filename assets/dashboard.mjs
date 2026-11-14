import {STATUS_LABELS, defaultRecipients, analysisOf, analysisIsStale, hasAnalysis, effectiveSignal, signalInfo, statusTone, queueTier, priorityLane, MANUAL_PRIORITY_LABELS, WORK_PRIORITIES, supportPriorityLabel, workPriority, workPriorityRank, rankTasks, filterTasks} from './task-rules.mjs';
import {createLogsController} from './logs.mjs';
import {needsFullTaskRefresh} from './revision-policy.mjs';
import {detailContentFingerprint,createDetailRequestScope} from './detail-refresh-policy.mjs';
import {baseManualRevision, manualVersionChanged, withExpectedRevision} from './manual-edit-policy.mjs';
import {makeUndoToken,canUndoLocalDone,undoLocalDonePayload,rebaseUndoForm} from './manual-done-undo.mjs';
import {createDraftRecoveryStore,RETENTION_DAYS,safeBrowserStorage} from './draft-recovery.mjs';
import {isTextEditingTarget, shortcutAction, adjacentTaskKey, captureTaskView,
  restoreTaskView, restoreInsertedDisclosureStates, isMainFormSaveTarget,
  captureEditorFocus, restoreEditorFocus, sanitizeSessionFocus, focusAfterAction}
  from './focus-navigation.mjs';
import {quickHandoff, priorityExplanation, priorityDimensions, completionPrompt} from './fast-handoff.mjs';
import {CANDIDATE_TEMPLATES,candidateTemplateFor} from './candidate-templates.mjs';
import {handoffCopyPolicy,mailActionLabels,readyToCopyCurrentHandoff} from './handoff-ui-policy.mjs';
import {advancedFilterSummary,evidenceSectionLabel} from './progressive-layout.mjs';
import {queueSummary,queueEmptyState,conciseSnapshotInfo,statusPresentation,shouldRenderBriefing,assessmentReason} from './visual-clarity.mjs';
import {createQueueModel,createSearchDebouncer,selectedAfterFilter} from './queue-performance.mjs';
import {createQueueDomRenderer} from './queue-dom.mjs';
import {createReconnectPolicy} from './reconnect-policy.mjs';
import {EFFORT_LABELS, effortInfo, quickWinCandidate, quickWinExplanation} from './effort-planning.mjs';
import {loadTaskEvidence} from './evidence-ui.mjs';
import {loadTaskDecisions} from './decisions-ui.mjs';


const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/\u2014/g, '\u2013').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const recoveryStore=createDraftRecoveryStore({
  local:safeBrowserStorage(()=>window.localStorage),
  session:safeBrowserStorage(()=>window.sessionStorage),
  newId:()=>window.crypto.randomUUID()
});
const LOCAL_VIEW_KEY = 'ccon-ba-desk.view-context.v1';
const LOCAL_PIN_KEY = 'ccon-ba-desk.personal-focus-pin.v1';
let pinnedKey = readPersonalPin();
const restoredFocusView = readViewContext();
let tasks = [], selected = restoredFocusView.selected, latest = null, busy = false, browserRecoveryAvailable = true, loadRequest = 0, cloudMode = false;
let signature = '', renderedTaskVersion = '', renderedTaskKey = null, pendingDetail = false;
let currentRevision = null, currentRevisionError = '', pollingInFlight = false, pollCycle = 0;
const transportRecovery=createReconnectPolicy();
const queueModel=createQueueModel();
queueModel.setPinnedKey(pinnedKey);
const queueDom=createQueueDomRenderer();
const detailRequests=createDetailRequestScope(()=>selected);
let disclosureObserver=null, disclosureState=null;
const searchRefresh=createSearchDebouncer(()=>applyFilters());
const forms = new Map();
const manualConflicts = new Map();
const taskViews = new Map(Object.entries(restoredFocusView.views));
const saveFailures = new Map();
let lastDoneToken = null;
const expandedEmails = new Set();
const recoveredForms = recoveryStore.load();
const {loadLogs} = createLogsController({api, escapeHtml, message, getSelected: () => selected});
// SessionStorage may be cloned by Duplicate Tab. Detect a live same-ID peer
// before accepting concurrent edits, and rotate only one copy. Native browser
// channel is optional; without it, SQLite CAS still protects actual saves.
const tabInstanceId=window.crypto.randomUUID();
if (typeof BroadcastChannel === 'function' && recoveryStore.id) {
  const channel=new BroadcastChannel('ccon-ba-desk-draft-owner-v3');
  channel.onmessage=event=>{
    const other=event.data;
    if (!other || other.instance===tabInstanceId || other.tab!==recoveryStore.id) return;
    if (other.type==='HELLO')
      channel.postMessage({type:'ALIVE',tab:other.tab,instance:tabInstanceId});
    if ((other.type==='HELLO'||other.type==='ALIVE') &&
        tabInstanceId.localeCompare(other.instance)>0) {
      if (recoveryStore.rotateTabId()) {
        rememberEdits();
        message('Виявлено дубль вкладки. Незбережені чернетки відокремлено.');
      } else {
        browserRecoveryAvailable=false;
        message('Не вдалося розділити браузерні чернетки вкладок. Збережи правки вручну.',true);
      }
    }
  };
  channel.postMessage({type:'HELLO',tab:recoveryStore.id,instance:tabInstanceId});
}

function readPersonalPin() {
  try {
    const value=sessionStorage.getItem(LOCAL_PIN_KEY);
    return typeof value === 'string' && /^CCON-\d+$/.test(value) ? value : null;
  } catch { return null; }
}
function setPersonalPin(key) {
  pinnedKey=queueModel.setPinnedKey(key);
  try {
    if (pinnedKey) sessionStorage.setItem(LOCAL_PIN_KEY,pinnedKey);
    else sessionStorage.removeItem(LOCAL_PIN_KEY);
  } catch { /* Disabled session storage cannot change Jira priority. */ }
}
function reconcilePersonalPin() {
  if (pinnedKey && !tasks.some(task => task.key === pinnedKey &&
      task.active && effectiveSignal(task) !== 'DONE')) setPersonalPin(null);
}

function readViewContext() {
  try { return sanitizeSessionFocus(JSON.parse(sessionStorage.getItem(LOCAL_VIEW_KEY) || '{}')); }
  catch { return {selected:null,views:{}}; }
}
function storeCurrentTaskView() {
  if (renderedTaskKey && document.getElementById('detail')?.hasChildNodes()) {
    const previous = taskViews.get(renderedTaskKey);
    const current = captureTaskView($('detail'));
    const activeFocus = captureEditorFocus(document.activeElement, $('detail'));
    taskViews.set(renderedTaskKey, {
      ...current,...((activeFocus || previous?.focus) ? {focus:activeFocus || previous.focus} : {})
    });
    if (taskViews.size > 12) taskViews.delete(taskViews.keys().next().value);
  }
}
function rememberViewContext() {
  storeCurrentTaskView();
  try {
    const views = Object.fromEntries(taskViews);
    sessionStorage.setItem(LOCAL_VIEW_KEY,
      JSON.stringify(sanitizeSessionFocus({selected,views})));
  } catch { /* A disabled session store never blocks work. */ }
}
function pendingFormRecords() {
  const records={...recoveredForms};
  forms.forEach((form,key)=>{
    if(isDirty(key))records[key]={...form.value,changedAt:form.changedAt,
      baseRevision:form.baseRevision};
    else delete records[key];
  });
  return records;
}
function updateRecoveryStatus() {
  if (!$('recoveryState')) return;
  const old=recoveryStore.others();
  const pending=Object.keys(pendingFormRecords()).length;
  $('recoveryState').textContent = recoveryStore.error || !browserRecoveryAvailable ?
    'Браузерне відновлення недоступне. Перед закриттям збережи правки в SQLite.' :
    'Незбережено в цій вкладці: '+pending+
    ' · інші вкладки: '+old.length+' · старі ('+RETENTION_DAYS+'+ днів): '+
    old.filter(x=>x.stale).length;
  const sourceSelect=$('recoverySource');
  const selectedSource=sourceSelect.value;
  sourceSelect.replaceChildren(...old.map((entry,index)=>{
    const option=document.createElement('option');
    option.value=entry.id;
    option.textContent='Набір '+(index+1)+' · '+entry.count+' чернеток · '+entry.ageDays+' дн. тому';
    return option;
  }));
  if (old.some(entry=>entry.id===selectedSource)) sourceSelect.value=selectedSource;
  sourceSelect.disabled=!old.length;
  $('recoverOther').disabled = !old.length;
  $('purgeOld').disabled = !old.some(x=>x.stale);
}
function normalizedDraft(value) {
  return {to:typeof value?.to === 'string' ? value.to : '', subject:typeof value?.subject === 'string' ? value.subject : '', body:typeof value?.body === 'string' ? value.body : ''};
}
function savedForm(task) {
  // Never infer supplier recipient from a task title. In particular, a
  // deliberately cleared "To" field must stay empty after Save/Reload.
  const emailDraft = normalizedDraft(task.savedEmailDraft ?? task.analysis?.emailDraft);
  return {manualStatus:STATUS_LABELS[task.manualStatus] ? task.manualStatus : 'AUTO',
    manualEffort:EFFORT_LABELS[task.manualEffort] ? task.manualEffort : 'UNKNOWN',
    manualPriority:MANUAL_PRIORITY_LABELS[task.manualPriority] ? task.manualPriority : 'NONE',
    note:task.note || '', emailDraft};
}
function formFor(task) {
  if (!forms.has(task.key)) {
    const base = savedForm(task), recovered = recoveredForms[task.key];
    const value = recovered && STATUS_LABELS[recovered.manualStatus] && typeof recovered.note === 'string'
      ? {manualStatus:recovered.manualStatus, note:recovered.note,
        manualEffort:EFFORT_LABELS[recovered.manualEffort] ? recovered.manualEffort : base.manualEffort,
        manualPriority:MANUAL_PRIORITY_LABELS[recovered.manualPriority] ? recovered.manualPriority : base.manualPriority,
        emailDraft:normalizedDraft(recovered.emailDraft)} : base;
    forms.set(task.key, {value, base:JSON.stringify(base),
      baseRevision:baseManualRevision(recovered, task),
      changedAt:recovered?.changedAt || null});
    delete recoveredForms[task.key];
  }
  return forms.get(task.key);
}
function isDirty(key) { const form = forms.get(key); return !!form && JSON.stringify(form.value) !== form.base; }
function hasUnsaved() { return [...forms.keys()].some(isDirty) || Object.keys(recoveredForms).length > 0; }
function rememberEdits() {
  browserRecoveryAvailable=recoveryStore.persist(pendingFormRecords());
  if ($('dataMenu')?.open) updateRecoveryStatus();
}
function safeUrl(value) {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : ''; }
  catch { return ''; }
}
function dateLabel(value) {
  const date = new Date(value); return Number.isFinite(date.getTime()) ? date.toLocaleString('uk-UA', {timeZone:'Europe/Warsaw', day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'}) : 'дата невідома';
}
function message(text, error = false) { $('message').textContent = text; $('statusbar').classList.toggle('error', error); }
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {cache:'no-store'} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) {
    const error = Error(result.error || 'Не вдалося виконати дію.');
    error.code = result.code || '';
    error.currentManualRevision = result.currentManualRevision;
    throw error;
  }
  return result;
}
function signalTone(task) { return signalInfo(task).tone || 'gray'; }
function signalLabel(task) {
  const info = signalInfo(task), manual = task.manualStatus && task.manualStatus !== 'AUTO';
  const label = manual ? STATUS_LABELS[task.manualStatus] : hasAnalysis(task) ? info.label : analysisIsStale(task) ? 'Потрібне оновлення аналізу' : 'Ще без аналізу';
  return `<span class="row-signal-label tone-text-${escapeHtml(info.tone || 'gray')}"><i aria-hidden="true"></i>${escapeHtml(label)}</span>`;
}
function priorityBadge(task) {
  if (!task.active || effectiveSignal(task) === 'DONE') return '';
  const kind = workPriority(task);
  if (kind === 'STANDARD') return '';
  const config = WORK_PRIORITIES[kind];
  const source = kind === 'SUPPORT' ?
    'Автоматично за Jira label: ' + supportPriorityLabel(task) :
    'Ручний пріоритет BA, лише локально';
  return `<span class="badge tone-${config.tone}" title="${escapeHtml(source)}">${escapeHtml(config.label)}</span>`;
}
function updateUndoControl() {
  const token=lastDoneToken;
  const task=token ? tasks.find(x=>x.key===token.key) : null;
  if(token && !canUndoLocalDone(token,task)) lastDoneToken=null;
  $('undoLastDone').hidden=!lastDoneToken;
  $('undoLastDone').disabled=busy || !lastDoneToken;
  if(lastDoneToken) $('undoLastDone').textContent='Скасувати «Виконано» · '+lastDoneToken.key;
}
function renderList() {
  reconcilePersonalPin();
  updateUndoControl();
  const focusedRow = document.activeElement?.closest?.('#list [data-key]')?.dataset.key || null;
  const previousListScroll = $('list').scrollTop;
  const previousSidebarScroll = $('list').closest('aside')?.scrollTop || 0;
  updateSnapshotInfo();
  const items = visibleTasks(), current = tasks.filter(task => task.active), analyzed = current.filter(hasAnalysis).length;
  const mailCount = tasks.filter(task => task.active && effectiveSignal(task) === 'WRITE').length;
  $('bulkEmail').textContent = `${mailActionLabels().batch} · ${mailCount}`;
  $('bulkEmail').disabled = !mailCount || busy;
  $('bulkEmail').hidden = cloudMode;
  const verified = current.filter(task => task.activeSprintStatus === 'VERIFIED').length;
  const sprintCount = current.filter(task => task.activeSprintStatus === 'VERIFIED' && task.activeSprint).length;
  const summary=queueSummary({visible:items.length,sprint:sprintCount,
    write:mailCount,active:current.length,analyzed,
    unverified:current.length-verified});
  $('count').textContent=summary.primary;
  $('countDetails').textContent=summary.diagnostics;
  $('advancedFilterCount').textContent=advancedFilterSummary({
    signal:$('signalFilter').value,sprint:$('sprintFilter').value,
     priority:$('priorityFilter').value});
  let previousGroup = '';
  const groupOf = task => {
    const lane = ['Активний спринт', 'Поза спринтом', 'Завершені', 'Архів'][priorityLane(task)];
    const kind = workPriority(task);
    return workPriorityRank(task) < 4 && kind !== 'STANDARD' ? WORK_PRIORITIES[kind].label + ' · ' + lane : lane;
  };
  const groupCounts = items.reduce((acc, task) => { const g = groupOf(task); acc[g] = (acc[g] || 0) + 1; return acc; }, {});
  const entries=[];
  items.forEach((task, index) => {
    const group = groupOf(task);
    if (group !== previousGroup) entries.push({id:'group:'+index+':'+group,
      html:`<div class="queue-group" role="heading" aria-level="3"><span>${escapeHtml(group)}</span><span class="queue-group-count">${groupCounts[group] || 0}</span></div>`});
    previousGroup = group;
    entries.push({id:'task:'+task.key,html:`<button class="row row-tone-${signalTone(task)} ${task.key === selected ? 'selected' : ''}" data-key="${escapeHtml(task.key)}" aria-pressed="${task.key === selected}"><span class="row-content"><span class="row-head"><span class="rank">${escapeHtml(task.key)}</span><span>${isDirty(task.key) ? '<span class="edit-dot" title="Є незбережені зміни">● </span>' : ''}</span></span><span class="row-title" title="${escapeHtml(task.summary)}">${escapeHtml(task.summary)}</span><span class="row-signal">${signalLabel(task)}${task.blocking ? '<span class="row-flag">Блокує інших</span>' : ''}${task.key === pinnedKey ? '<span class="row-flag row-flag-focus">Фокус</span>' : ''}</span></span></button>`});
  });
  if (!entries.length) {
    const state=queueEmptyState({visible:items.length,total:tasks.filter(task=>task.active!==false).length,
      hasSnapshot:!!latest,importError:!!currentRevisionError});
    entries.push({id:'empty:'+state.kind,html:'<div class="empty queue-empty" role="status" data-state="' +
      escapeHtml(state.kind) + '">' + escapeHtml(state.text) + '</div>'});
  }
  queueDom.render($('list'),entries);
  $('list').scrollTop = previousListScroll;
  if ($('list').closest('aside')) $('list').closest('aside').scrollTop = previousSidebarScroll;
  // innerHTML replaces buttons: restore keyboard focus only if it WAS on
  // the queue, never steal focus from a typed note, search or a dialog.
  if (focusedRow) {
    const replacementRow = [...$('list').querySelectorAll('[data-key]')]
      .find(button => button.dataset.key === focusedRow);
    replacementRow?.focus({preventScroll:true});
  }
}
function updateQueueSelection(previous,key) {
  const list=$('list');
  if (previous) {
    const oldRow=[...list.querySelectorAll('[data-key]')].find(row=>row.dataset.key===previous);
    if (oldRow) {oldRow.classList.remove('selected');oldRow.setAttribute('aria-pressed','false');}
  }
  if (key) {
    const newRow=[...list.querySelectorAll('[data-key]')].find(row=>row.dataset.key===key);
    if (newRow) {newRow.classList.add('selected');newRow.setAttribute('aria-pressed','true');}
  }
}
$('list').addEventListener('click',event=>{
  const row=event.target.closest?.('[data-key]');
  if (row && $('list').contains(row)) selectTask(row.dataset.key);
});
function selectTask(key) {
  if (busy || selected === key) return;
  storeCurrentTaskView();
  const previous=selected;
  selected = key;
  pendingDetail = false;
  updateQueueSelection(previous,key);
  $('queueAnnouncer').textContent='Вибрано задачу '+key+'.';
  renderDetail();
  rememberViewContext();
}

const ATTACHMENT_STATES = {
  LOCAL_TEXT_VERIFIED: 'Текст прочитано',
  FORMAT_REQUIRES_MANUAL_REVIEW: 'Формат потребує ручного перегляду',
  NOT_DOWNLOADED: 'Файл ще не завантажено',
  DOWNLOAD_UNAVAILABLE: 'Не вдалося отримати файл через Jira API',
  LOCAL_FILE_MISMATCH: 'Локальна копія не пройшла перевірку',
  PDF_PARSER_NOT_INSTALLED: 'Потрібен локальний обробник PDF',
  PDF_TEXT_NOT_EXTRACTED: 'Текст PDF не вдалося прочитати',
  INSPECTION_UNAVAILABLE: 'Файл отримано. Вміст не пройшов локальну перевірку'
};
function briefingMarkup(briefing, stale) {
  if (!shouldRenderBriefing(briefing)) return '';
  const readiness = {
    READY_FOR_REVIEW:'Чернетка готова до перевірки BA',
    NEEDS_CONFIRMATION:'Є відкриті рішення',
    INSUFFICIENT_CONTEXT:'Недостатньо підтверджених даних'
  }[briefing.readiness] || 'Рівень готовності не визначено';
  const row = (label, value, cls = '') => `<span class="brief-label">${label}</span><p class="pre brief-text ${cls}">${escapeHtml(value || 'Не встановлено з доступних джерел.')}</p>`;
  return `<section class="panel ba-brief" aria-label="Розбір ситуації та вимог">
    <div class="panel-title brief-head"><h3 class="focus-title">Ситуація за 30 секунд</h3><span class="badge ${briefing.readiness === 'READY_FOR_REVIEW' ? 'tone-green' : 'tone-amber'}">${escapeHtml(readiness)}</span></div>
    ${stale ? '<p class="analysis-missing">Брифінг застарів: використовуй лише після оновлення джерел.</p>' : ''}
    <div class="brief-grid">
      ${row('Коротко', briefing.overviewUk || 'Контекст поки не сформовано.', 'brief-overview')}
      ${row('Зараз', briefing.currentUk)}
      ${row('Має бути', briefing.targetUk)}
    </div>
  </section>`;
}

// Simplified UI: briefing details are secondary and live in one collapsed group.
function briefingSecondaryMarkup(briefing, attachments) {
  if (!shouldRenderBriefing(briefing)) return '';
  return [
    secSection('Підтверджені факти', briefing.confirmedFacts, item => secRow({text:item.textUk, url:item.sourceUrl})),
    secSection('Джерела: прочитані й недоступні', [...(briefing.sourceAudit || []), ...(attachments || []).map(a => ({attachment:a}))], item => item.attachment
      ? secRow({tag:item.attachment.state === 'LOCAL_TEXT_VERIFIED' ? secTag('Прочитано', 'tone-green') : secTag('Вкладення', 'tone-amber'),
          text:`${item.attachment.format || 'Файл'} #${item.attachment.attachmentId} – ${ATTACHMENT_STATES[item.attachment.state] || 'Текст недоступний'}`})
      : secRow({tag:secTag(...(SOURCE_TAGS[item.status] || [item.status, 'tone-gray'])), text:item.descriptionUk, url:item.sourceUrl})),
    secSection('Історія рішень', briefing.timeline, item => secRow({
      tag:secTag(...(DECISION_TAGS[item.status] || [item.status, 'tone-gray'])),
      meta:item.date || 'Дата невідома', text:item.eventUk, url:item.sourceUrl})),
    secSection('QA-сценарії', briefing.verification, item => secRow({text:item.scenarioUk, meta:'Очікування: ' + (item.expectedUk || '–'), metaBelow:true, url:item.sourceUrl})),
    secSection('Scope, вплив і ризики', [
      {label:'Технічні межі', value:briefing.technicalScopeUk},
      {label:'Бізнес-вплив', value:briefing.businessImpactUk},
      ...(briefing.risksUk || []).map((risk, i) => ({label:i ? '' : 'Ризики', value:risk}))
    ].filter(f => f.value || f.label === 'Технічні межі' || f.label === 'Бізнес-вплив'),
      f => `<li class="sec-row sec-field"><span class="sec-label">${escapeHtml(f.label)}</span><span class="sec-text">${escapeHtml(f.value || 'Не встановлено')}</span><span></span></li>`,
      (briefing.risksUk || []).length)
  ].join('');
}

// Uniform rows for «Другорядне»: [tag column][text][source link], all aligned.
const SOURCE_TAGS = {READ:['Прочитано','tone-green'], UNAVAILABLE:['Недоступно','tone-amber'], REFERENCE_ONLY:['Посилання','tone-gray']};
const DECISION_TAGS = {CONFIRMED:['Підтверджено','tone-green'], PROPOSED:['Пропозиція','tone-amber'], DISPUTED:['Суперечність','tone-red'], SUPERSEDED:['Замінено','tone-gray']};
function secTag(label, tone) { return `<span class="badge sec-tag ${tone}">${escapeHtml(label)}</span>`; }
function secRow({tag = '', text, meta = '', metaBelow = false, url}) {
  const safe = safeUrl(url);
  const link = safe ? `<a class="sec-link" href="${escapeHtml(safe)}" target="_blank" rel="noopener noreferrer">Джерело ↗</a>` : '<span class="sec-link muted">–</span>';
  const metaHtml = meta ? `<span class="sec-meta">${escapeHtml(meta)}</span>` : '';
  return `<li class="sec-row${tag ? ' has-tag' : ''}">${tag ? `<span class="sec-tagcol">${tag}</span>` : ''}<span class="sec-text">${metaBelow ? '' : metaHtml}${escapeHtml(text || '')}${metaBelow ? metaHtml : ''}</span>${link}</li>`;
}
function secSection(title, items, render, count) {
  const list = Array.isArray(items) ? items : [];
  const n = count ?? list.length;
  return `<details class="description sec-section"><summary><span class="sec-title">${escapeHtml(title)}</span><span class="sec-count${n ? '' : ' empty'}">${n}</span></summary>${
    list.length ? `<ul class="sec-list">${list.map(render).join('')}</ul>` : '<p class="sec-empty">Не встановлено з доступних джерел.</p>'}</details>`;
}
function taskVersion(task) { return detailContentFingerprint(task); }




function qualityGateFocusMarkup(gate) {
  if (!gate) return '<p class="focus-status"><span class="badge tone-gray">Немає</span> Перевірки QA ще немає</p>';
  const names = {BLOCKED:['Потрібне підтвердження','tone-amber'], NEEDS_REVIEW:['Перевірити опис','tone-amber'],
    STRUCTURALLY_VERIFIED:['Структура перевірена','tone-green']};
  const [label, tone] = names[gate.state] || ['Недостатньо даних','tone-gray'];
  const summary = gate.summary || {};
  const findings = (gate.findings || []).slice(0, 8).map(f => '<li>' + escapeHtml(f.messageUk) + '</li>').join('');
  const coverage = (gate.qaCoverage || []).slice(0, 25).map(r =>
    '<li>' + escapeHtml(r.ruleId) + ': ' + escapeHtml((r.covered || []).join(', ') || 'Тестів немає') +
    ((r.missing || []).length ? ' · бракує ' + escapeHtml(r.missing.join(', ')) : ' · покрито') + '</li>').join('');
  return '<p class="focus-status"><span class="badge ' + tone + '">' + escapeHtml(label) + '</span> <span class="muted">Цитати в джерелах: ' +
    escapeHtml(summary.sourceExcerptsPresent || 0) + '/' + escapeHtml(summary.claimsChecked || 0) +
    ' · правил із повним QA: ' + escapeHtml(summary.rulesFullyCovered || 0) + '/' + escapeHtml(summary.rulesTracked || 0) + '</span></p>' +
    (findings ? '<ul class="focus-items">' + findings + '</ul>' : '') +
    (coverage ? '<details class="focus-more"><summary>Покриття умов</summary><ul class="focus-list">' + coverage + '</ul>' +
      '<p class="muted">Структурна перевірка, не підтвердження бізнес-правильності.</p></details>' : '');
}

// "Важливо для мене": status tiles on top, one detail panel below.
// Each panel's first status badge is the tile's value and tone.
const focusTabs = new Map();
const ATTENTION_TONES = ['tone-red', 'tone-amber'];
const TILE_TONES = ['tone-gray', 'tone-green', 'tone-amber', 'tone-red', 'tone-blue'];
// Value and tone come from the panel's first status badge. A panel without a badge
// is "loading" until its loaders settle, then shown as "–" (never stuck on loading).
function refreshFocusTiles(root, settled) {
  for (const tile of root.querySelectorAll('.focus-tile')) {
    const panel = root.querySelector(`[data-focus-panel="${tile.dataset.focus}"]`);
    const badge = panel?.querySelector('.focus-status .badge');
    const tone = badge ? [...badge.classList].find(c => c.startsWith('tone-')) || 'tone-gray' : 'tone-gray';
    tile.classList.remove(...TILE_TONES);
    tile.classList.add(tone);
    tile.querySelector('.tile-value').textContent = badge ? badge.textContent.trim() : settled ? '–' : 'Завантаження…';
  }
}
function setupFocusTiles(key, settled = false) {
  const root = document.querySelector('.focus-table');
  if (!root) return;
  const tiles = [...root.querySelectorAll('.focus-tile')];
  refreshFocusTiles(root, settled);
  for (const tile of tiles) {
    if (!tile.dataset.bound) {
      tile.dataset.bound = '1';
      tile.addEventListener('click', () => { focusTabs.set(key, tile.dataset.focus); showFocusPanel(root, tile.dataset.focus); });
    }
  }
  if (!root.dataset.observed) {
    // Panels re-hydrate on their own (e.g. a decision is confirmed): keep tiles in sync.
    root.dataset.observed = '1';
    // Observe the panels only: tiles live outside them, so refreshing a tile never re-triggers this.
    const observer = new MutationObserver(() => refreshFocusTiles(root, true));
    for (const panel of root.querySelectorAll('.focus-panel')) observer.observe(panel, {childList:true, subtree:true});
  }
  const chosen = focusTabs.get(key) ||
    tiles.find(tile => ATTENTION_TONES.some(tone => tile.classList.contains(tone)))?.dataset.focus || 'questions';
  showFocusPanel(root, chosen);
}
function showFocusPanel(root, name) {
  for (const tile of root.querySelectorAll('.focus-tile')) {
    const active = tile.dataset.focus === name;
    tile.setAttribute('aria-selected', String(active));
    tile.classList.toggle('active', active);
  }
  for (const panel of root.querySelectorAll('.focus-panel')) panel.hidden = panel.dataset.focusPanel !== name;
}

async function loadApprovedDescription(key, current=()=>selected) {
  const node = $('approvedReview');
  if (!node) return;
  try {
    const data = await api('/api/approved/' + encodeURIComponent(key));
    if (current() !== key || !$('approvedReview')) return;
    const labels = {NO_APPROVED_REFERENCE:'Ще немає вручну схваленого опису',
      UNCHANGED:'Опис збігається з останнім схваленим',
      NEW_DRAFT_DIFFERS:'Новий опис відрізняється від схваленого',
      SOURCE_CHANGED:'Jira-контекст змінився: потрібна повторна перевірка'};
    node.innerHTML = '<p>' + escapeHtml(labels[data.state] || 'Статус невідомий') + '</p>' +
      (data.diff ? '<details><summary>Показати зміни від схваленої версії</summary>' +
       '<pre class="pre">' + escapeHtml(data.diff) + '</pre></details>' : '');
  } catch (error) {
    if (current() === key && $('approvedReview')) $('approvedReview').textContent = 'Порівняння недоступне: ' + error.message;
  }
}

// FOCUS-05: a compact next action over the existing detail, only after the
// original action panel has scrolled out of view. The zero-height sticky slot
// does not move the user's current scroll position or duplicate the full panel.
function updateStickyNextAction() {
  const sticky=document.getElementById('stickyAction');
  const lead=document.querySelector('#detail .quick-handoff');
  if (!sticky || !lead) return;
  const host=$('detail');
  const scrollTop=host.getBoundingClientRect().top;
  const mobile=window.matchMedia('(max-width:750px)').matches;
  // The toolbar can wrap to multiple rows; derive its actual height so the
  // pinned action never covers the Jira link or task identity on mobile.
  if (mobile) {
    const toolbar=host.querySelector('.task-toolbar');
    const height=toolbar?.getBoundingClientRect().height || 64;
    sticky.style.setProperty('--task-toolbar-height', Math.ceil(height + 8)+'px');
  } else sticky.style.removeProperty('--task-toolbar-height');
  const threshold=mobile ? 0 : scrollTop;
  const visible=lead.getBoundingClientRect().bottom <= threshold + 8;
  if (sticky.hidden===visible) sticky.hidden=!visible;
}
$('detail').addEventListener('scroll',updateStickyNextAction,{passive:true});
window.addEventListener('scroll',updateStickyNextAction,{passive:true});
window.addEventListener('resize',updateStickyNextAction,{passive:true});
function renderDetail() {
  disclosureObserver?.disconnect();
  disclosureObserver=null;
  disclosureState=null;
  const task = tasks.find(item => item.key === selected);
  // Every render invalidates responses belonging to a previous detail DOM,
  // even if the same key is still selected after a manual edit.
  const currentDetail = detailRequests.begin(task?.key || null);
  if (!task) {
    $('detail').innerHTML = tasks.length ? '<div class="empty"><h2>Оберіть задачу з черги</h2>Зміни фільтр, щоб побачити інші задачі.</div>' : '<div class="empty"><h2>Почни зі snapshot</h2>Збережи <b>CCON_BA_Snapshot.json</b> у папку <b>inbox</b> поруч із застосунком.<br>Дані імпортуються автоматично. Ручні статуси, нотатки та збережені чернетки залишаються між днями.</div>';
    renderedTaskVersion = '';
    renderedTaskKey = null;
    return;
  }
  // A clean form may still represent an older DOM/revision while focus held
  // a background refresh. Only throw it away when the deferred DOM can
  // actually be replaced. Never promote stale displayed values to new CAS.
  if (pendingDetail && renderedTaskKey === task.key &&
      !isDirty(task.key) && !detailInteractionFocused()) forms.delete(task.key);
  const retainPosition = renderedTaskKey === task.key;
  const state = retainPosition ? {...captureTaskView($('detail')),
    focus:taskViews.get(task.key)?.focus} : taskViews.get(task.key);
  const focusedEditor = retainPosition ? captureEditorFocus(document.activeElement, $('detail')) : null;
  const analyzed = hasAnalysis(task), stale = analysisIsStale(task), analysis = analyzed ? analysisOf(task) : {};
  const form = formFor(task).value, info = signalInfo(task), url = safeUrl(task.url);
  const suggestedRecipient=defaultRecipients(task);
  const savedDraft = task.savedEmailDraft !== null && task.savedEmailDraft !== undefined;
  const staleGeneratedDraft = stale && !savedDraft && !!analysisOf(task).emailDraft?.body;
  const manualWaiting = ['WAITING INPUT','WAITING DEPENDENCY'].includes(task.manualStatus);
  const waiting = task.manualStatus !== 'AUTO' ? manualWaiting : analysis.waitingRequired, email = manualWaiting || task.manualStatus === 'DONE' ? false : analysis.needsEmail;
  const missing = Array.isArray(analysis.missingInfo) ? analysis.missingInfo : [];
  const openPoints = [...new Set([...missing, ...(analyzed && Array.isArray(analysis.briefing?.unknownsUk) ? analysis.briefing.unknownsUk : [])].map(item => String(item).trim()).filter(Boolean))];
  const quick = quickHandoff(task);
  const handoff=handoffCopyPolicy({description:quick.description,
    readyForCopy:quick.readyForCopy,qualityState:quick.state});
  const statusView=statusPresentation({jiraStatus:task.jiraStatus,manualStatus:form.manualStatus,
    manualLabel:STATUS_LABELS[form.manualStatus],activeSprintStatus:task.activeSprintStatus,
    activeSprint:task.activeSprint,activeSprintNames:task.activeSprintNames||[],
    active:task.active,blocking:task.blocking,email,waiting,
    waitingLabel:manualWaiting?'Очікуємо за моїм статусом':
      'Очікуємо: '+(analysis.waitingOnUk||'адресат не вказаний'),
    isWrite:effectiveSignal(task)==='WRITE'});
  $('detail').innerHTML = `
    ${quick.nextAction ? `<div id="stickyAction" class="sticky-next-action" hidden role="region" aria-label="Наступна дія під час прокручування"><div class="sticky-action-inner"><span class="sticky-action-text">${escapeHtml(quick.nextAction)}</span><button id="stickyCopyNext" class="quiet" type="button">Скопіювати дію</button></div></div>` : ''}
    <div class="task-top task-toolbar"><span class="task-key">${escapeHtml(task.key)}${url ? ` <a class="jira-button" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Jira ↗</a>` : ''}</span><span class="badge tone-${info.tone}"><span class="dot" aria-hidden="true"></span>${escapeHtml(analyzed || task.manualStatus !== 'AUTO' ? info.label : 'Потрібен аналіз')}</span>${priorityBadge(task)}<span class="muted task-date">${task.importedAt ? 'Дані: ' + dateLabel(task.importedAt) : ''}</span></div>
    <h2>${escapeHtml(task.summary)}</h2>
    <div class="task-meta-compact" aria-label="Джерело станів задачі">
      <span class="task-status-provenance">${statusView.provenance.map(value=>'<span>'+escapeHtml(value)+'</span>').join('<span aria-hidden="true"> · </span>')}</span>
      ${statusView.alerts.length?'<span class="task-status-alerts">'+statusView.alerts.map(value=>'<span class="badge tone-amber">'+escapeHtml(value)+'</span>').join('')+'</span>':''}
    </div>
    <div class="split-row">
      <div class="split-col">
        <section class="panel quick-handoff do-now" aria-label="Найближча дія та швидка передача">
        <div class="card-head"><h3 class="focus-title">Що зробити зараз</h3></div>
        <p class="pre next-action" id="nextText">${escapeHtml(quick.nextAction || (stale ? 'Онови аналіз за актуальним контекстом Jira, перш ніж діяти.' : 'Перевір контекст і сформуй конкретну дію.'))}</p>
        <p class="muted quick-proof-note">${escapeHtml(quick.evidenceNote)}</p>
        <div class="actions quick-handoff-actions card-foot">
        ${quick.nextAction ? '<button id="copyNext" class="quiet">Скопіювати дію</button>' : ''}
        ${handoff.showFastCopy ? `<button id="copyFastDescription" class="quiet" ${handoff.fastEnabled ? '' : 'disabled'}>${escapeHtml(handoff.fastLabel)}</button>` : ''}
        </div>
        </section>
      </div>
      <div class="split-col">
        <section class="panel work-state" aria-label="Мій робочий стан">
        <div class="card-head"><h3 class="focus-title">Мій статус</h3><details class="status-help"><summary aria-label="Як працює мій статус">ⓘ</summary><p>«Автоматично» використовує оцінку щоденного аналізу. Ручний вибір фіксує твій власний статус і має пріоритет. Вибір статусу зберігається автоматично.</p></details></div>
        <label class="card-label" for="manual">Статус</label><select id="manual" class="status-select tone-${statusTone(form.manualStatus, task)}">${['AUTO','IN PROGRESS','NEEDS DECISION','WAITING INPUT','WAITING DEPENDENCY','DONE'].map(value => `<option value="${value}" ${form.manualStatus === value ? 'selected' : ''}>${escapeHtml(STATUS_LABELS[value])}</option>`).join('')}</select>
        <label class="card-label" for="manualPriority">Пріоритет</label><select id="manualPriority" aria-describedby="manualPriorityHelp">${Object.entries(MANUAL_PRIORITY_LABELS).map(([key,label]) =>
          `<option value="${key}" ${form.manualPriority === key ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('')}</select>
        <p id="manualPriorityHelp" class="card-help">P1 – щоденний бізнес-фокус · P2 – терміново. P3 ставиться автоматично за Jira label.</p>
        <label class="card-label" for="note">Нотатки</label><textarea id="note" maxlength="20000" placeholder="Додай домовленість або наступний контакт…">${escapeHtml(form.note)}</textarea>
        <div class="actions state-actions card-foot"><span id="savedIndicator" role="status">✓ Збережено</span><button id="save">Зберегти все</button><button id="done" class="primary">Виконано й далі</button><button id="discard" class="quiet" title="Скинути незбережене">Скинути</button></div>
        <div id="saved" class="save-state" role="status"></div>
        <div id="manualConflict" class="analysis-missing" role="alert" hidden>
        <b>Конфлікт ручних правок</b>
        <p>Цю задачу збережено в іншій вкладці. Твій текст залишився у формі.
        Перед перезаписом порівняй його з актуальною версією.</p>
        <details><summary>Показати актуальний збережений статус, нотатку й лист</summary>
        <pre class="pre" id="conflictSavedText"></pre>
        </details>
        <div class="actions">
        <button id="conflictOverwrite" class="quiet">Перевірив, зберегти мої правки</button>
        <button id="conflictUseSaved" class="quiet">Взяти збережену версію</button>
        </div>
        </div>
        </section>
      </div>
    </div>
    <div id="staleNotice" class="saved-note" hidden></div>
    ${stale ? '<div class="analysis-missing"><b>Контекст Jira змінився – попередній аналіз застарів.</b><br>Черга й сигнали потребують нового аналізу опису, коментарів та залежностей. Твій ручний стан і збережена чернетка залишаються чинними.</div>' : !analyzed ? '<div class="analysis-missing"><b>Для цієї задачі ще немає повного аналізу українською.</b><br>Потрібно прочитати опис, коментарі й залежності. Попередній snapshot не дає достатніх підстав для нової оцінки.</div>' : ''}
    ${briefingMarkup(analyzed ? analysis.briefing : undefined, stale)}
    <details id="emailDetails" class="panel email-panel ${email === true || form.emailDraft.body ? 'email-first' : ''}" open>
    <summary class="email-summary"><span class="email-title">${email === false && !form.emailDraft.body && !form.emailDraft.subject ? 'Лист зараз не потрібен' : 'Чернетка листа'}</span><span class="badge email-badge ${staleGeneratedDraft ? 'tone-amber' : email === true ? 'tone-blue' : 'tone-gray'}">${staleGeneratedDraft ? 'Зі старого аналізу' : savedDraft && stale ? 'Моя збережена чернетка' : email === true ? 'Потрібна' : email === false ? 'За потреби' : 'Потребу ще не визначено'}</span><span class="email-toggle">Підготувати лист</span></summary>
    <div class="email-fields" role="region" aria-label="Редагована чернетка листа">
    <p class="email-intro">${stale && form.emailDraft.body ? savedDraft ? 'Твоя збережена чернетка залишилася без змін. Аналіз застарів: перевір лист за новим контекстом перед використанням.' : 'Новий контекст ще не проаналізовано. Ця чернетка збережена зі старого аналізу або твоїх незбережених правок; перевір її актуальність перед використанням.' : form.emailDraft.body ? 'Перевір адресата й текст. Усі поля можна відредагувати.' : email === false && analyzed ? 'За поточним аналізом лист зараз не потрібен. За потреби можеш підготувати власну чернетку.' : email === true ? 'Потрібен лист, але готової чернетки ще немає. Підготуй текст за конкретними відкритими питаннями задачі.' : 'Потребу в листі ще не визначено. Спочатку перевір контекст і наступну дію.'}</p>
    <div class="email-grid">
      <label class="email-label" for="draftTo">Кому</label><div class="email-cell"><input id="draftTo" maxlength="2000" autocomplete="off" placeholder="Email адресата, якщо він відомий" value="${escapeHtml(form.emailDraft.to)}">${suggestedRecipient ? '<div class="email-hint"><button id="useRecipientHint" class="quiet" title="Шаблонна адреса постачальника – перевір отримувача">Адреса з шаблону</button></div>' : ''}</div>
      <label class="email-label" for="draftSubject">Тема</label><div class="email-cell"><input id="draftSubject" maxlength="2000" placeholder="Тема листа" value="${escapeHtml(form.emailDraft.subject)}"></div>
      <label class="email-label" for="draftBody">Текст</label><div class="email-cell"><textarea id="draftBody" maxlength="50000" placeholder="Чернетка за описом, коментарями та відкритими питаннями задачі…">${escapeHtml(form.emailDraft.body)}</textarea></div>
      <span class="email-label">Логи</span><section id="emailLogs" class="email-cell email-logs" aria-label="Логи до листа"><p class="muted" role="status">Перевіряю архіви задачі…</p></section>
      <span></span><div class="email-cell actions"><button id="copyEmail" class="quiet">${escapeHtml(mailActionLabels().copy)}</button><button id="email" class="primary">${escapeHtml(mailActionLabels().open)}</button></div>
    </div>
    </div>
    </details>
    <section class="panel focus-table" aria-label="Важливо для мене">
      <h3 class="focus-title">Важливо для мене</h3>
      <div class="focus-tiles" role="tablist" aria-label="Що потребує уваги">
        <button type="button" class="focus-tile" role="tab" data-focus="questions" aria-controls="focus-panel-questions" aria-selected="false"><span class="tile-label">Відкриті питання</span><span class="tile-value">…</span></button>
        <button type="button" class="focus-tile" role="tab" data-focus="decisions" aria-controls="focus-panel-decisions" aria-selected="false"><span class="tile-label">Рішення</span><span class="tile-value">…</span></button>
        <button type="button" class="focus-tile" role="tab" data-focus="logs" aria-controls="focus-panel-logs" aria-selected="false"><span class="tile-label">Логи</span><span class="tile-value">…</span></button>
        <button type="button" class="focus-tile" role="tab" data-focus="qa" aria-controls="focus-panel-qa" aria-selected="false"><span class="tile-label">Перевірка QA</span><span class="tile-value">…</span></button>
        <button type="button" class="focus-tile" role="tab" data-focus="description" aria-controls="focus-panel-description" aria-selected="false"><span class="tile-label">Опис для Jira</span><span class="tile-value">…</span></button>
      </div>
      <div class="focus-panel" role="tabpanel" id="focus-panel-questions" data-focus-panel="questions" hidden><h4 class="sub-heading focus-panel-title">Відкриті питання</h4>${openPoints.length ? '<p class="focus-status"><span class="badge tone-amber">' + openPoints.length + ' ' + (openPoints.length === 1 ? 'питання' : 'питання(нь)') + '</span> Потрібна відповідь, щоб рухатися далі</p><ul class="focus-items">' + openPoints.map(item => '<li>' + escapeHtml(item) + '</li>').join('') + '</ul>' : (analyzed ? '<p class="focus-status"><span class="badge tone-green">Немає</span> Відкритих питань немає</p>' : '<p class="focus-status"><span class="badge tone-gray">Не визначено</span> Аналізу ще немає – питання з’являться після нього</p>')}</div>
      <div class="focus-panel" role="tabpanel" id="focus-panel-decisions" data-focus-panel="decisions" hidden><h4 class="sub-heading focus-panel-title">Рішення</h4><div id="decisionTracker" class="muted">Завантажую рішення…</div></div>
      <div class="focus-panel" role="tabpanel" id="focus-panel-logs" data-focus-panel="logs" hidden><h4 class="sub-heading focus-panel-title">Логи<span class="focus-sub">REST · Supplier · Errors</span></h4><div id="evidenceSummary" class="muted">Завантажую…</div></div>
      <div class="focus-panel" role="tabpanel" id="focus-panel-qa" data-focus-panel="qa" hidden><h4 class="sub-heading focus-panel-title">Перевірка QA</h4>${qualityGateFocusMarkup(analysis.qualityGate)}</div>
      <div class="focus-panel" role="tabpanel" id="focus-panel-description" data-focus-panel="description" hidden><h4 class="sub-heading focus-panel-title">Опис для Jira</h4>${analysis.standardDescription ? '<p class="focus-status"><span class="badge ' + (handoff.fastEnabled ? 'tone-green' : 'tone-amber') + '">' + (handoff.fastEnabled ? 'Готова до передачі' : 'Чернетка') + '</span> ' + (handoff.fastEnabled ? 'Перевір і скопіюй у Jira' : 'Потребує перевірки перед передачею в Jira') + '</p>' : '<p class="focus-status"><span class="badge tone-gray">Немає</span> Чернетку не підготовлено</p>'}${analysis.descriptionTitle ? '<p class="focus-strong">' + escapeHtml(analysis.descriptionTitle) + '</p>' : ''}<details class="focus-more"><summary>${analysis.standardDescription ? 'Показати повний опис' : 'Чернетку не підготовлено'}</summary><p class="pre">${escapeHtml(analysis.standardDescription || 'Чернетку не підготовлено. Перевір причину в поясненні аналізу.')}</p>${analysis.standardDescription ? (handoff.showFallbackCopy ? '<button id="copyDescription" class="quiet" aria-describedby="fallbackCopyWarning">'+escapeHtml(handoff.fallbackLabel)+'</button><p id="fallbackCopyWarning" class="analysis-missing">'+escapeHtml(handoff.warning)+'</p> ' : '') + '<button id="approveDescription" class="quiet">'+escapeHtml(handoff.approvalLabel)+'</button>' : ''}<div id="approvedReview" class="muted">Перевіряю схвалену версію…</div></details></div>
    </section>
    <details class="panel secondary-details" aria-label="Другорядні деталі аналізу">
      <summary><span class="secondary-title">Другорядне</span><span class="secondary-sub">факти, джерела, історія рішень, QA-сценарії, scope</span></summary>
      <div class="accordion">
      ${briefingSecondaryMarkup(analyzed ? analysis.briefing : undefined, analysis.qualityGate?.sourceAudit?.attachments)}
      ${secSection('Джерела оцінки', analysis.evidence, item => secRow({text:item.text || 'Джерело', url:item.url}))}
      ${task.active && effectiveSignal(task)!=='DONE' ? `<details class="description sec-section" id="candidateTemplates"><summary><span class="sec-title">Шаблони для дрібних BA задач</span></summary><div class="sec-body">
        <p class="muted">Лише порожні каркаси. Жодного підтвердження джерела чи виконаної дії.</p>
        <label for="candidateTemplate">Оберіть каркас</label>
        <select id="candidateTemplate" aria-label="Кандидатний BA шаблон"><option value="">Оберіть тип задачі</option>${CANDIDATE_TEMPLATES.map(item=>`<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)}</option>`).join('')}</select>
        <p id="candidateNotice" class="muted" role="status">Дані задачі не підставляються автоматично.</p>
        <pre id="candidatePreview" class="pre" hidden></pre>
        <button id="copyCandidate" class="quiet" type="button" disabled>Скопіювати порожній каркас</button>
      </div></details>` : ''}
      ${task.active && effectiveSignal(task) !== 'DONE' ? `<details class="description sec-section"><summary><span class="sec-title">Мій фокус у групі</span></summary><div class="sec-body"><button type="button" class="quiet" id="pinDeepWork" aria-pressed="${task.key === pinnedKey}" ${busy ? 'disabled' : ''}>${task.key === pinnedKey ? 'Скинути мій фокус' : 'Закріпити мій фокус у цій групі'}</button><p class="muted">Фокус лише для цієї вкладки та поточної групи дій. Не обходить активний спринт або WRITE, не змінює Jira.</p></div></details>` : ''}
      </div>
    </details>`;
  renderedTaskVersion = taskVersion(task);
  renderedTaskKey = task.key;
  pendingDetail = false;
  restoreTaskView($('detail'), state);
  // Async panels hydrate later. Preserve nested disclosure choices from the
  // previous render and track the user's subsequent toggles by stable key.
  disclosureState=new Map(state?.sections || []);
  disclosureObserver=new MutationObserver(changes=>
    restoreInsertedDisclosureStates(changes,disclosureState));
  disclosureObserver.observe($('detail'),{subtree:true,childList:true});
  // Renders triggered by Save must preserve an active note/email caret.
  // A background refresh intentionally doesn't rerender while the editor
  // is focused; this also safely handles explicit same-task rerenders.
  restoreEditorFocus($('detail'), focusedEditor || state?.focus,
    {focusElement:Boolean(focusedEditor)});
  ['note', 'draftTo', 'draftSubject', 'draftBody'].forEach(id => $(id).addEventListener('input', captureForm));
  if ($('pinDeepWork')) $('pinDeepWork').addEventListener('click',()=>{
    if (busy) return;
    setPersonalPin(task.key === pinnedKey ? null : task.key);
    renderList();
    renderDetail();
    focusAfterAction(document,['pinDeepWork']);
    message(pinnedKey ? 'Короткочасний фокус закріплено лише в цій групі. Ручний пріоритет і Jira не змінено.' :
      'Мій фокус скинуто. Офіційний порядок відновлено.');
  });
  if ($('useRecipientHint')) $('useRecipientHint').addEventListener('click',()=>{
    if($('draftTo').value.trim() && !confirm('Замінити поточного адресата шаблонною адресою? Перевір його вручну.'))return;
    $('draftTo').value=suggestedRecipient;
    captureForm();
    $('draftTo').focus({preventScroll:true});
    message('Адресу підставлено для перевірки, не підтверджено і не надіслано.');
  });
  $('manualPriority').addEventListener('change', captureForm);
  $('manual').addEventListener('change', () => saveStatus($('manual').value));
  if ($('candidateTemplate')) {
    const select=$('candidateTemplate');
    const preview=$('candidatePreview');
    const button=$('copyCandidate');
    const notice=$('candidateNotice');
    select.addEventListener('change',()=>{
      const candidate=candidateTemplateFor(task,select.value);
      preview.textContent=candidate?.text || '';
      preview.hidden=!candidate;
      button.disabled=!candidate;
      notice.textContent=candidate?.notice || 'Дані задачі не підставляються автоматично.';
    });
    button.addEventListener('click',()=>{
      const candidate=candidateTemplateFor(task,select.value);
      if(candidate)copyText(candidate.text,'Порожній каркас скопійовано. Перевір джерела й заповни вручну.');
    });
  }
  if ($('copyNext')) $('copyNext').addEventListener('click', () =>
    copyText(quick.nextAction, 'Дію скопійовано. Це не означає її виконання.'));
  if ($('stickyCopyNext')) $('stickyCopyNext').addEventListener('click', () =>
    copyText(quick.nextAction, 'Дію скопійовано. Це не означає її виконання.'));
  if ($('copyFastDescription')) $('copyFastDescription').addEventListener('click', () => {
    // The rendered button can remain enabled during a deferred snapshot while
    // a user edits a note. Recheck latest quality/state and the display version.
    const liveTask=tasks.find(item=>item.key===task.key);
    const liveQuick=liveTask ? quickHandoff(liveTask) : null;
    if (!readyToCopyCurrentHandoff({selectedKey:selected,displayedKey:renderedTaskKey,
      taskKey:task.key,renderedVersion:renderedTaskVersion,
      latestVersion:taskVersion(liveTask),shown:quick,latest:liveQuick})) {
      message('Чернетка змінилася або Quality Gate вже не підтверджений. Онови панель перед копіюванням.',true);
      return;
    }
    copyText(liveQuick.description, 'Jira-чернетку скопійовано. Перевір факти й передай вручну.');
  });
  if ($('copyDescription')) $('copyDescription').addEventListener('click', () =>
    copyText(analysis.standardDescription,
      'Неперевірену чернетку скопійовано лише для ручного доопрацювання. Це не передача Jira.'));
  if ($('approveDescription')) $('approveDescription').addEventListener('click', async () => {
    if (!confirm('Схвалити поточний BA-опис як контрольну версію? Це не змінює Jira.')) return;
    try {
      await api('/api/approved/' + encodeURIComponent(task.key), {});
      message('BA-опис схвалено локально. Jira не змінено.');
      const live = detailRequests.current();
      if (live() === task.key) loadApprovedDescription(task.key,live);
    } catch (error) { message('Опис не схвалено: ' + error.message, true); }
  });
  $('save').addEventListener('click', () => saveTask(false));
  $('done').addEventListener('click', () => saveTask(true));
  $('discard').addEventListener('click', discardForm);
  $('conflictOverwrite').addEventListener('click', overwriteAfterReview);
  $('conflictUseSaved').addEventListener('click', takeSavedVersion);
  $('copyEmail').addEventListener('click', () => {
    const subject = $('draftSubject').value.trim();
    const body = $('draftBody').value.trim();
    if (!subject && !body) return message('Немає тексту листа для копіювання.', true);
    copyText((subject ? 'Subject: ' + subject + '\n\n' : '') + body,
             'Тему й текст листа скопійовано.');
  });
  $('email').addEventListener('click', openEmail);
  if (cloudMode) $('email').textContent = mailActionLabels(true).open;
  // The email draft is a primary block: it stays open (keyboard/pointer cannot collapse it).
  $('emailDetails').addEventListener('toggle', () => { if (!$('emailDetails').open) $('emailDetails').open = true; expandedEmails.add(task.key); });
  $('emailDetails').querySelector('summary').addEventListener('click', event => event.preventDefault());
  updateFormStatus();
  showManualConflict();
  setupFocusTiles(task.key);
  Promise.allSettled([loadTaskEvidence(task.key, api, escapeHtml, currentDetail),
    loadTaskDecisions(task.key, api, escapeHtml, message, currentDetail, ()=>detailRequests.current())])
    .then(() => { if (currentDetail() === task.key) setupFocusTiles(task.key, true); });
  loadApprovedDescription(task.key,currentDetail);
  loadLogs(task.key);
  updateStickyNextAction();
}
function captureForm() {
  const task = tasks.find(item => item.key === selected);
  if (!task) return;
  const form = formFor(task);
  form.value = {manualStatus:$('manual').value, manualEffort:$('manualEffort')?.value ?? formFor(task).value.manualEffort,
    manualPriority:$('manualPriority').value,
    note:$('note').value, emailDraft:{to:$('draftTo').value, subject:$('draftSubject').value, body:$('draftBody').value}};
  form.changedAt = new Date().toISOString();
  saveFailures.delete(task.key);
  $('manual').className = 'status-select tone-' + statusTone(form.value.manualStatus, task);
  rememberEdits();
  updateFormStatus();
  // A keystroke changes only this row's unsaved dot; do not rebuild 1,000
  // rows, rerun priority rank or move focus out of the active editor.
  const row=[...$('list').querySelectorAll('[data-key]')].find(element=>element.dataset.key===task.key);
  if (row) {
    let dot=row.querySelector('.edit-dot');
    if (isDirty(task.key) && !dot) {
      dot=document.createElement('span');
      dot.className='edit-dot';
      dot.title='Є незбережені зміни';
      dot.textContent='● ';
      row.querySelector('.row-head > span:last-child')?.append(dot);
    } else if (!isDirty(task.key) && dot) dot.remove();
    // Inline DOM change and queuePatchIndexes cache must agree after Save/Discard.
    queueDom.invalidateRow(task.key);
  }
}
function updateFormStatus() {
  const task = tasks.find(item => item.key === selected);
  if (!task || !$('saved')) return;
  const dirty = isDirty(task.key);
  const conflict = manualConflicts.has(task.key);
  const failure = saveFailures.get(task.key);
  const state = conflict ? 'Конфлікт версій. Правки не перезаписано.' :
    busy ? 'Зберігаю зміни…' :
    failure ? 'Не збережено: ' + failure :
    dirty && !browserRecoveryAvailable ?
      'Є незбережені правки. Браузер не зміг створити резервну чернетку: збережи зміни вручну.' :
    dirty ? 'Є незбережені правки.' : '';
  if ($('saved').textContent !== state) $('saved').textContent = state;
  $('saved').hidden = !state;
  $('savedIndicator').hidden = dirty || conflict || busy || !!failure;
  $('save').hidden = !dirty;
  $('save').disabled = !dirty || busy || conflict;
  $('done').disabled = busy || conflict;
  $('saved').classList.toggle('unsaved', dirty);
  $('discard').hidden = !dirty;
  $('discard').disabled = !dirty || busy;
  if ($('staleNotice')) {
    $('staleNotice').hidden = !pendingDetail;
    $('staleNotice').textContent = 'Надійшли нові дані. Поточний текст залишається у формі; новий аналіз з’явиться після збереження правок. Якщо правок немає, достатньо вийти з поля.';
  }
  showManualConflict();
}
function showManualConflict() {
  const node = $('manualConflict');
  if (!node) return;
  const conflict = manualConflicts.get(selected);
  node.hidden = !conflict;
  if (!conflict) return;
  const remote = conflict.remote;
  const draft = normalizedDraft(remote.savedEmailDraft ?? remote.analysis?.emailDraft);
  // textContent prevents HTML execution and preserves the raw private value
  // in the local browser only; no notes or email bodies enter GitHub/logs.
  $('conflictSavedText').textContent =
    'Статус: ' + (STATUS_LABELS[remote.manualStatus] || remote.manualStatus) +
    '\nОцінка часу: ' + (EFFORT_LABELS[remote.manualEffort] || 'Не оцінено') +
     '\nМій пріоритет: ' + (MANUAL_PRIORITY_LABELS[remote.manualPriority] || MANUAL_PRIORITY_LABELS.NONE) +
    '\nНотатка:\n' + (remote.note || '(порожньо)') +
    '\n\nЛист кому: ' + draft.to +
    '\nТема: ' + draft.subject + '\nТекст:\n' + draft.body;
}

async function loadManualConflict(key) {
  try {
    const payload = await api('/api/tasks');
    const remote = payload.tasks.find(task => task.key === key);
    if (!remote) throw Error('Задачу вже немає у збереженому списку.');
    manualConflicts.set(key, {remote});
    if (selected === key) {
      showManualConflict();
      updateFormStatus();
    }
    message('Зміни в іншій вкладці. Твої правки залишено. Порівняй версії перед збереженням.', true);
  } catch (error) {
    message('Не вдалося отримати актуальний стан. Твої правки збережені у формі: ' +
      error.message, true);
  }
}

async function takeSavedVersion() {
  const key = selected;
  if (!manualConflicts.has(key) || busy) return;
  if (!confirm('Відкинути МОЇ незбережені правки цієї задачі та взяти актуальну збережену версію?')) return;
  setBusy(true);
  try {
    const payload = await api('/api/tasks');
    tasks = payload.tasks;
    latest = payload.latest;
    signature = JSON.stringify(payload);
    currentRevision = payload.revision;
    currentRevisionError = payload.error || '';
    // The refresh is global, but only this task's local buffer was discarded.
    // Keep other dirty tasks and mark conflicts if their row changed too.
    forms.forEach((form, otherKey) => {
      if (otherKey === key) return;
      if (!isDirty(otherKey)) { forms.delete(otherKey); return; }
      const remote = tasks.find(item => item.key === otherKey);
      if (remote && manualVersionChanged(form.baseRevision, remote.manualRevision))
        manualConflicts.set(otherKey, {remote});
    });
    forms.delete(key);
    delete recoveredForms[key];
    manualConflicts.delete(key);
    saveFailures.delete(key);
    rememberEdits();
    renderList();
    renderDetail();
    message('Актуальну збережену версію завантажено. Інші задачі не змінено.');
  } catch (error) {
    message('Сервер недоступний. Твої правки залишилися у формі: ' + error.message, true);
  } finally { setBusy(false); }
}

async function overwriteAfterReview() {
  const key = selected, viewed = manualConflicts.get(key);
  if (!viewed || busy) return;
  setBusy(true);
  try {
    // Re-read immediately before the explicit overwrite. If the stored
    // version changed since preview, user must compare again.
    const payload = await api('/api/tasks');
    const remote = payload.tasks.find(task => task.key === key);
    if (!remote) throw Error('Актуальну задачу не знайдено.');
    if (manualVersionChanged(viewed.remote.manualRevision, remote.manualRevision)) {
      manualConflicts.set(key, {remote});
      showManualConflict();
      message('Збережена версія ще раз змінилася. Перевір новий текст і повтори дію.', true);
      return;
    }
    if (!confirm('Після порівняння перезаписати актуальний локальний статус, пріоритет, нотатку й лист МОЄЮ версією? Jira та пошта не змінюються.')) return;
    const task = tasks.find(item => item.key === key);
    const form = formFor(task);
    const own = structuredClone(form.value);
    const response = await api('/api/tasks/' + encodeURIComponent(key),
      withExpectedRevision(own, remote.manualRevision));
    Object.assign(task, {manualStatus:own.manualStatus, manualEffort:own.manualEffort,
      manualPriority:own.manualPriority, note:own.note,
      savedEmailDraft:own.emailDraft, manualRevision:response.manualRevision,
      modifiedAt:new Date().toISOString()});
    queueModel.invalidate();
    forms.delete(key);
    delete recoveredForms[key];
    manualConflicts.delete(key);
    saveFailures.delete(key);
    rememberEdits();
    signature = '';
    renderList();
    renderDetail();
    message('Твою версію свідомо збережено. Jira та листи не змінено.');
  } catch (error) {
    if (error.code === 'TASK_REVISION_CONFLICT') await loadManualConflict(key);
    else message('Твої правки не перезаписано: ' + error.message, true);
  } finally { setBusy(false); }
}

function discardForm() {
  if (busy || !isDirty(selected)) return;
  if (!confirm('Скинути незбережені зміни статусу, пріоритету, нотаток і чернетки цієї задачі?')) return;
  forms.delete(selected);
  manualConflicts.delete(selected);
  saveFailures.delete(selected);
  delete recoveredForms[selected];
  rememberEdits();
  renderList();
  renderDetail();
}
function setBusy(value) {
  busy = value;
  ['manual', 'manualPriority', 'manualEffort', 'note', 'draftTo', 'draftSubject', 'draftBody', 'save', 'done', 'email', 'discard',
    'conflictOverwrite', 'conflictUseSaved', 'undoLastDone', 'pinDeepWork'].forEach(id => { if ($(id)) $(id).disabled = value; });
  $('import').disabled = value;
  updateFormStatus();
}
async function saveStatus(status) {
  if (busy || !STATUS_LABELS[status]) return;
  const task = tasks.find(item => item.key === selected);
  if (!task || task.manualStatus === status) return;
  if (status === 'DONE' && !confirm(completionPrompt(task))) {
    $('manual').value = formFor(task).value.manualStatus;
    return;
  }
  captureForm();
  if (manualConflicts.has(task.key)) {
    message('Спочатку порівняй незбережені правки з актуальною версією.', true);
    return;
  }
  const scroll = $('detail').scrollTop;
  setBusy(true);
  try {
    // Only persist the status; keep typed note/draft buffers separate.
    const form = formFor(task);
    if (!Number.isSafeInteger(form.baseRevision)) {
      await loadManualConflict(task.key);
      return;
    }
    const previousStatus=task.manualStatus;
    const saved = await api('/api/tasks/' + encodeURIComponent(task.key),
      withExpectedRevision({manualStatus:status, note:task.note || ''}, form.baseRevision));
    task.manualStatus = status;
    if(status==='DONE') lastDoneToken=makeUndoToken(task,previousStatus,saved.manualRevision);
    else if(lastDoneToken?.key===task.key) lastDoneToken=null;
    task.manualRevision = saved.manualRevision;
    queueModel.invalidate();
    task.modifiedAt = new Date().toISOString();
    form.value.manualStatus = status;
    form.base = JSON.stringify(savedForm(task));
    form.baseRevision = saved.manualRevision;
    saveFailures.delete(task.key);
    rememberEdits();
    signature = '';
    renderList();
    renderDetail();
    $('detail').scrollTop = scroll;
    $('manual')?.focus({preventScroll:true});
    message('Мій статус збережено автоматично.');
  } catch (error) {
    if (error.code === 'TASK_REVISION_CONFLICT') await loadManualConflict(task.key);
    else {
      saveFailures.set(task.key, error.message);
      message(error.message, true);
    }
  } finally { setBusy(false); }
}
async function saveTask(done = false) {
  if (busy) return false;
  const task = tasks.find(item => item.key === selected);
  if (!task) return false;
  if (done && !confirm(completionPrompt(task))) return false;
  const editingBeforeSave = isTextEditingTarget(document.activeElement);
  let restoreAfterSave = false;
  captureForm();
  const form = formFor(task);
  const value = structuredClone(form.value);
  const previousStatus=task.manualStatus;
  if (done) value.manualStatus = 'DONE';
  setBusy(true);
  try {
    if (!Number.isSafeInteger(form.baseRevision)) {
      await loadManualConflict(task.key);
      return false;
    }
    const saved = await api('/api/tasks/' + encodeURIComponent(task.key),
      withExpectedRevision(value, form.baseRevision));
    Object.assign(task, {manualStatus:value.manualStatus, manualEffort:value.manualEffort,
      manualPriority:value.manualPriority, note:value.note,
      savedEmailDraft:value.emailDraft, manualRevision:saved.manualRevision,
      modifiedAt:new Date().toISOString()});
    if (done) lastDoneToken=makeUndoToken(task,previousStatus,saved.manualRevision);
    else if(lastDoneToken?.key===task.key) lastDoneToken=null;
    queueModel.invalidate();
    forms.delete(task.key);
    manualConflicts.delete(task.key);
    saveFailures.delete(task.key);
    delete recoveredForms[task.key];
    rememberEdits();
    signature = '';
    if (done) selected = visibleTasks().find(item => item.key !== task.key)?.key || null;
    renderList();
    renderDetail();
    // The original Save button is replaced and hidden once the form is clean.
    // Restore to an enabled editor after busy clears, not to hidden Save.
    restoreAfterSave = !done && !editingBeforeSave;
    message(cloudMode ? 'Статус, нотатки та чернетку збережено у приватній базі.' : 'Статус, нотатки та чернетку збережено в локальній базі.');
    return true;
  } catch (error) {
    if (error.code === 'TASK_REVISION_CONFLICT') await loadManualConflict(task.key);
    else {
      saveFailures.set(task.key, error.message);
      message(error.message, true);
    }
    return false;
  } finally {
    setBusy(false);
    if (restoreAfterSave && selected === task.key && document.activeElement === document.body)
      focusAfterAction(document,['note','manual']);
  }
}
async function undoLastDone() {
  if(busy || !lastDoneToken) return;
  const token=lastDoneToken;
  const task=tasks.find(item=>item.key===token.key);
  if(!canUndoLocalDone(token,task)) {
    lastDoneToken=null;
    updateUndoControl();
    message('Не вдалося скасувати: стан задачі вже змінився. Перевір актуальну версію.',true);
    return;
  }
  setBusy(true);
  try {
    // CAS guarantees no newer manual edits get silently overwritten.
    const response=await api('/api/tasks/'+encodeURIComponent(token.key),
      undoLocalDonePayload(token,task));
    task.manualStatus=token.priorStatus;
    task.manualRevision=response.manualRevision;
    task.modifiedAt=new Date().toISOString();
    // A prior status-only save may leave user edits unsaved in the form.
    // Rebase their CAS token and saved status without discarding buffers.
    const restored=rebaseUndoForm(forms.get(token.key),savedForm(task),response.manualRevision);
    if(restored) forms.set(token.key,restored);
    else forms.delete(token.key);
    // Keep crash/reload recovery consistent with the restored CAS revision.
    rememberEdits();
    lastDoneToken=null;
    selected=task.key;
    queueModel.invalidate();
    signature='';
    renderList();
    renderDetail();
    message('Локальний стан «Виконано» скасовано. Jira і пошта не змінювалися.');
    $('detail')?.focus({preventScroll:true});
  } catch(error) {
    lastDoneToken=null;
    if(error.code==='TASK_REVISION_CONFLICT')
      message('Undo зупинено: інша вкладка вже змінила цей запис. Перевір актуальні правки.',true);
    else message('Undo не виконано: '+error.message,true);
  } finally {
    setBusy(false);
    updateUndoControl();
  }
}
$('undoLastDone').addEventListener('click',undoLastDone);

async function copyText(text, notice) {
  try { await navigator.clipboard.writeText(text); message(notice); }
  catch { message('Копіювання недоступне. Виділи видимий текст і скопіюй вручну.', true); }
}
let bulkItems = [];
let bulkPreviewRequest = 0;
let bulkReturnFocus = null;
async function previewBulkEmails() {
  bulkReturnFocus = document.activeElement;
  const request = ++bulkPreviewRequest;
  const candidates = rankedTasks().filter(task => task.active && effectiveSignal(task) === 'WRITE');
  bulkItems = [];
  $('bulkList').innerHTML = candidates.map(task => {
    const draft = structuredClone(formFor(task).value.emailDraft);
    const missing = [!draft.to.trim() && 'адресат', !draft.subject.trim() && 'тема', !draft.body.trim() && 'текст'].filter(Boolean);
    if (!missing.length) bulkItems.push({key:task.key, draft});
    return `<div class="bulk-row"><div>${escapeHtml(task.key)} · ${escapeHtml(task.summary)}</div><div class="muted">${missing.length ? 'Пропущено: не заповнено ' + missing.join(', ') : escapeHtml(draft.to)}</div><div class="bulk-logs muted" data-log-key="${escapeHtml(task.key)}">Перевіряю архіви…</div></div>`;
  }).join('');
  $('bulkResult').textContent = `Готово: ${bulkItems.length} із ${candidates.length}.`;
  $('bulkOpen').textContent = `Відкрити чернетки (${bulkItems.length})`;
  $('bulkOpen').disabled = !bulkItems.length;
  $('bulkDialog').showModal();
  // Focus the safe Close action, not a potentially external mail opener.
  $('bulkClose').focus({preventScroll:true});
  try {
    const catalog = await api('/api/logs');
    if (request !== bulkPreviewRequest || !$('bulkDialog').open) return;
    $('bulkList').querySelectorAll('[data-log-key]').forEach(row => {
      const items = catalog[row.dataset.logKey]?.items || [];
      row.innerHTML = items.length ? 'Логи: ' + items.map((item, index) => `<a href="${escapeHtml(item.downloadUrl)}" download title="${escapeHtml(item.filename)}">ZIP ${index + 1} · ${escapeHtml(item.fileCount ?? '?')} XML</a>${item.stale || item.needsReview ? '<span class="text-amber">перевір актуальність</span>' : ''}`).join(' ') + (catalog[row.dataset.logKey].pendingCount ? `<span>ще ${escapeHtml(catalog[row.dataset.logKey].pendingCount)} очікують підготовки</span>` : '') : escapeHtml(catalog[row.dataset.logKey]?.emptyMessage || 'Логи ще не підготовлені');
    });
  } catch {
    if (request === bulkPreviewRequest) $('bulkList').querySelectorAll('[data-log-key]').forEach(row => { row.textContent = 'Архіви зараз недоступні'; });
  }
}
async function openBulkEmails() {
  const items = bulkItems;
  $('bulkOpen').disabled = true;
  $('bulkClose').disabled = true;
  try {
    const result = await api('/api/email/open-batch', {items});
    bulkItems = items.filter(item => !result.opened.includes(item.key));
    $('bulkResult').textContent = `Передано поштовій програмі: ${result.opened.length}. Не вдалося відкрити: ${result.failed.length}. Перевір вікна Outlook.`;
    $('bulkOpen').textContent = `Повторити невдалі (${bulkItems.length})`;
  } catch (error) { $('bulkResult').textContent = error.message; }
  finally {
    $('bulkClose').disabled = false;
    $('bulkOpen').disabled = !bulkItems.length;
    if ($('bulkDialog').open) focusAfterAction(document,
      bulkItems.length ? ['bulkOpen','bulkClose'] : ['bulkClose']);
  }
}
$('bulkEmail').addEventListener('click', previewBulkEmails);
$('bulkOpen').addEventListener('click', openBulkEmails);
$('bulkClose').addEventListener('click', () => $('bulkDialog').close());
$('bulkDialog').addEventListener('close', () => {
  // Native <dialog> handles Escape and modal focus containment.
  if (bulkReturnFocus?.isConnected) bulkReturnFocus.focus({preventScroll:true});
  bulkReturnFocus = null;
});
async function openEmail() {
  captureForm();
  const draft = structuredClone(forms.get(selected)?.value.emailDraft);
  if (!draft?.subject.trim() || !draft?.body.trim()) {
    message('Додай тему й текст листа перед відкриттям чернетки.', true);
    focusAfterAction(document,[!draft?.subject.trim()?'draftSubject':'draftBody']);
    return;
  }
  if (!await saveTask(false)) {
    focusAfterAction(document,['email']);
    return;
  }
  // Saving replaces the detail DOM. Restore the explicit mail action before
  // opening an external app; on return the keyboard target remains visible.
  focusAfterAction(document,['email']);
  if (cloudMode) {
    await copyText('To: ' + draft.to + '\nSubject: ' + draft.subject + '\n\n' + draft.body,
                   'Чернетку збережено та скопійовано. Надсилання залишається ручним.');
    return;
  }
  const recipient = draft.to.replace(/[\r\n]/g, '').trim();
  const mailto = 'mailto:' + encodeURIComponent(recipient).replace(/%40/gi, '@').replace(/%2C/gi, ',') + '?subject=' + encodeURIComponent(draft.subject) + '&body=' + encodeURIComponent(draft.body);
  window.location.href = mailto;
  message('Чернетку збережено. Відкриваю її в поштовій програмі.');
}
async function loadContext(key, current=()=>selected) {
  const button = $('loadContext');
  button.disabled = true;
  try {
    const context = await api('/api/context/' + encodeURIComponent(key));
    if (current() !== key || !$('contextPreview')) return;
    if (!context.contextAvailable) { $('contextPreview').textContent = 'Повний контекст ще не завантажений. Відкрий задачу у Jira або дочекайся щоденного оновлення.'; return; }
    renderContext(context);
    button.textContent = 'Контекст завантажено';
  } catch (error) { if (current() === key && $('contextPreview')) $('contextPreview').textContent = 'Не вдалося завантажити контекст: ' + error.message; }
  finally { if (button.isConnected) button.disabled = false; }
}
function plainText(value) {
  if (typeof value === 'string') return value;
  if (!value || typeof value !== 'object') return '';
  if (Array.isArray(value)) return value.map(plainText).join('\n');
  if (value.text) return value.text;
  if (Array.isArray(value.content)) return value.content.map(plainText).join(['doc','paragraph','bulletList','orderedList','listItem'].includes(value.type) ? '\n' : '');
  return '';
}
function renderContext(context) {
  const source = context.issue || context;
  const fields = source.fields || source;
  const description = plainText(context.descriptionText || fields.descriptionText || fields.description || context.description);
  const comments = context.comments || fields.comments || fields.comment?.comments || [];
  const commentItems = Array.isArray(comments) ? comments : comments.comments || [];
  const output = [];
  if (description) output.push('<div class="section-label">Опис</div><p class="pre">' + escapeHtml(description) + '</p>');
  if (commentItems.length) {
    output.push('<div class="section-label">Коментарі (' + commentItems.length + ')</div>');
    commentItems.forEach(comment => {
      const author = typeof comment.author === 'string' ? comment.author : comment.author?.displayName || 'Автор не вказаний';
      const body = plainText(comment.bodyText || comment.text || comment.body);
      output.push('<div class="description"><b>' + escapeHtml(author) + '</b>' + (comment.created ? ' · ' + escapeHtml(dateLabel(comment.created)) : '') + '<p class="pre">' + escapeHtml(body || 'Текст коментаря недоступний.') + '</p></div>');
    });
  }
  if (Array.isArray(context.links) && context.links.length) {
    output.push('<div class="section-label">Пов’язані задачі</div><ul>');
    context.links.forEach(link => {
      const issue = link.issue || {key:link.linkedKey, summary:link.summary, jiraStatus:link.jiraStatus};
      const url = safeUrl(issue.url || (issue.key ? 'https://aerticket.atlassian.net/browse/' + encodeURIComponent(issue.key) : ''));
      const label = [issue.key, issue.summary].filter(Boolean).join(' – ');
      output.push('<li>' + escapeHtml(link.relationship || link.type || 'Зв’язок') + ': ' + (url ? '<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(label) + '</a>' : escapeHtml(label)) + (issue.jiraStatus ? ' · ' + escapeHtml(issue.jiraStatus) : '') + '</li>');
    });
    output.push('</ul>');
  }
  if (context.retrievedAt) output.push('<p class="footer-note">Контекст отримано ' + escapeHtml(dateLabel(context.retrievedAt)) + '</p>');
  $('contextPreview').innerHTML = output.join('') || 'Контекст отримано; опис і коментарі відсутні.';
}
function detailInteractionFocused() {
  return $('detail').contains(document.activeElement);
}
function updateSnapshotInfo() {
  $('snapshotInfo').textContent = conciseSnapshotInfo(latest,dateLabel);
}
async function load() {
  const request = ++loadRequest;
  try {
    const data = await api('/api/tasks');
    if (busy || request !== loadRequest) return false;
    const nextSignature = JSON.stringify(data);
    const changed = nextSignature !== signature;
    if (!changed && !pendingDetail) return true;
    latest = data.latest;
    currentRevision = Number.isSafeInteger(data.revision) ? data.revision : null;
    currentRevisionError = data.error || '';
    if (changed) {
      tasks = data.tasks;
      queueModel.invalidate();
      searchRefresh.cancel();
      signature = nextSignature;
      // A new snapshot must never overwrite a typed note or email draft.
      forms.forEach((form, key) => {
        // A clean buffer must survive while its OLD DOM is still on screen.
        // Otherwise typing into that deferred DOM would create a new form
        // from the NEW revision and bypass the optimistic concurrency token.
        const displayedAndFocused = key === renderedTaskKey &&
          key === selected && detailInteractionFocused();
        if (!isDirty(key) && !displayedAndFocused) {
          forms.delete(key);
          return;
        }
        const remote = tasks.find(task => task.key === key);
        if (remote && manualVersionChanged(form.baseRevision, remote.manualRevision))
          manualConflicts.set(key, {remote});
      });
      // A pending debounced query may be canceled by this snapshot update.
      // Reconcile against the ACTUAL filtered queue, not just all snapshot
      // keys, or a nonmatching old detail remains indefinitely selected.
      const matching=visibleTasks();
      const nextSelected=selectedAfterFilter(matching,selected,{
        protectEditor:isDirty(selected)||detailInteractionFocused()
      });
      if (nextSelected!==selected) {
        storeCurrentTaskView();
        selected=nextSelected;
      }
      renderList();
      updateSnapshotInfo();
    }
    const selectedTask = tasks.find(task => task.key === selected);
    const detailChanged = selectedTask ? taskVersion(selectedTask) !== renderedTaskVersion : renderedTaskVersion !== '';
    // Global import time is still visible, without rebuilding the expensive
    // selected detail DOM or refetching source panels for unrelated changes.
    if (selectedTask && !detailChanged && renderedTaskKey === selected) {
      const date = document.querySelector('#detail .task-date');
      if (date) date.textContent = selectedTask.importedAt ?
        'Дані: ' + dateLabel(selectedTask.importedAt) : '';
    }
    if (detailChanged || pendingDetail || !$('detail').hasChildNodes()) {
      if (isDirty(selected) || detailInteractionFocused()) {
        pendingDetail = true;
        updateFormStatus();
      }
      else renderDetail();
    }
    if (data.error) message(data.error, true);
    else if (changed) message(hasUnsaved() ? 'Дані оновлено. Незбережені правки залишаються у твоїх формах.' : '');
    return true;
  } catch (error) {
    message('Сервер недоступний. Запусти Start CCON BA.bat. ' + error.message, true);
    return false;
  }
}
// Daily delta lives in the header "Звіт" link (count badge + tooltip), not in a row of chips.
async function loadDeltaStrip() {
  const target = $('reportLink');
  if (!target) return;
  try {
    const result = await api('/api/daily-report');
    if (result.available === false || !result.summary) {
      target.hidden = true;
      return;
    }
    const summary = result.summary;
    const parts = [['NEW', 'нових'], ['UPDATED', 'змінено'], ['COMPLETED', 'завершено'], ['REOPENED', 'перевідкрито'], ['JIRA_DONE', 'Done у Jira'], ['LEFT_SCOPE', 'поза JQL'],
      ['questionsAdded', '+питань'], ['questionsRemoved', '−питань'], ['warnings', 'попереджень']]
      .filter(([key]) => (summary[key] ?? 0) > 0).map(([key, label]) => summary[key] + ' ' + label);
    const fresh = (summary.NEW ?? 0) + (summary.UPDATED ?? 0);
    target.textContent = fresh ? `Звіт · ${fresh} змін ↗` : 'Звіт ↗';
    target.title = 'Зміни останнього аналізу: ' + (parts.length ? parts.join(', ') : 'без змін') + '. Відкрити повний звіт';
    target.hidden = false;
  } catch {
    target.hidden = true;
  }
}

function applyFilters() {
  if (busy) return;
  const items=visibleTasks();
  if (!items.some(task=>task.key===selected)) {
    storeCurrentTaskView();
    selected=selectedAfterFilter(items,selected);
    pendingDetail=false;
    renderList();
    renderDetail();
    rememberViewContext();
  } else renderList();
}
document.addEventListener('click', event => { if (!$('dataMenu').contains(event.target)) $('dataMenu').open = false; });
document.addEventListener('keydown', event => { if (event.key === 'Escape') { $('dataMenu').open = false; document.querySelectorAll('.status-help[open]').forEach(help => help.open = false); } });
document.addEventListener('keydown', event => {
  const action = shortcutAction(event, {
    dialogOpen:$('bulkDialog').open,editing:isTextEditingTarget(event.target)
  });
  if (!action || busy) return;
  if (action === 'SAVE' && (!$('detail').contains(event.target) ||
      !isMainFormSaveTarget(event.target))) return;
  event.preventDefault();
  if (action === 'SEARCH') {
    $('search').focus({preventScroll:true});
    $('search').select();
  } else if (action === 'NEXT' || action === 'PREVIOUS') {
    searchRefresh.flush();
    const keys = visibleTasks().map(task => task.key);
    const key = adjacentTaskKey(keys, selected, action === 'NEXT' ? 1 : -1);
    if (key && key !== selected) selectTask(key);
    const button = [...$('list').querySelectorAll('[data-key]')]
      .find(row => row.dataset.key === key);
    button?.focus({preventScroll:true});
    button?.scrollIntoView({block:'nearest'});
  } else if (action === 'COPY_ACTION') {
    if ($('copyNext') && !$('copyNext').disabled) $('copyNext').click();
    else message('Немає актуальної дії для копіювання.', true);
  } else if (action === 'SAVE') {
    if (isDirty(selected)) saveTask(false);
    else message('Незбережених змін у цій задачі немає.');
  }
});
$('search').addEventListener('input',()=>searchRefresh.schedule());
for (const id of ['filter','signalFilter','sprintFilter','priorityFilter']) {
  $(id).addEventListener('change',()=>{
    searchRefresh.cancel();
    applyFilters();
  });
}
$('dataMenu').addEventListener('toggle',()=>{
  if ($('dataMenu').open) updateRecoveryStatus();
});
$('recoverOther').addEventListener('click',()=>{
  const others=recoveryStore.others();
  if(!others.length){updateRecoveryStatus();return;}
  // The caller explicitly selects a source; do not repeatedly recover only the
  // newest browser tab while older private drafts remain inaccessible.
  const newest=others.find(item=>item.id===$('recoverySource').value);
  if (!newest) { updateRecoveryStatus(); return; }
  const own=pendingFormRecords();
  const occupied=[...forms.keys()].filter(key=>isDirty(key));
  const ready = Object.keys(own).length;
  if (!window.confirm('Відновити до '+newest.count+' чернеток з іншої вкладки ('+
      newest.ageDays+' днів тому)?\\nТвої '+ready+' незбережених чернеток не перезапишуться. '+
      'Стан Jira не змінюється; перед Save буде перевірено версію. '+
      'Якщо інша вкладка ще відкрита, вона збереже власний запис.')) return;
  const result=recoveryStore.adopt(newest.id,own,occupied);
  if(result.failed){message('Не вдалося зберегти відновлені чернетки у браузері.',true);return;}
  Object.assign(recoveredForms,result.added);
  // Clean in-memory forms can be re-created from explicit recovered drafts;
  // dirty forms are protected by 'occupied' and never overwritten.
  for(const key of Object.keys(result.added)) if (forms.has(key) && !isDirty(key)) forms.delete(key);
  const restored=Object.keys(result.added).length;
  // On a previously opened clean form, prefer not to silently replace even
  // in-memory defaults. The import remains visible after re-select/reload.
  message('Відновлено '+restored+' чернеток. Пропущено конфліктних: '+
    result.skipped.length+'. Перевір кожну та збережи вручну.'); 
  updateRecoveryStatus();
  $('dataMenu').open=false;
  renderList();
  if(Object.hasOwn(result.added,selected)) renderDetail();
});
$('purgeOld').addEventListener('click',()=>{
  const old=recoveryStore.others().filter(item=>item.stale);
  if(!old.length)return updateRecoveryStatus();
  if(!window.confirm('Назавжди видалити '+old.length+' наборів чернеток з інших вкладок '+
    'старших за '+RETENTION_DAYS+' днів? Їхній незбережений текст не можна повернути '+
    'з SQLite backup. Дія НЕ торкнеться цієї вкладки.'))return;
  const result=recoveryStore.clearExpired();
  updateRecoveryStatus();
  message('Видалено '+result.cleared+' застарілих наборів. Залишилось: '+result.remaining+'.');
});
$('import').addEventListener('click', async () => {
  $('dataMenu').open = false;
  $('import').disabled = true;
  try { await api('/api/import', {}); await load(); message('Snapshot перевірено. Нові дані імпортовані; ручні правки та чернетки збережені.'); }
  catch (error) { message(error.message, true); }
  finally { $('import').disabled = false; }
});
$('export').addEventListener('click', async () => {
  $('dataMenu').open = false;
  try {
    const data = await api('/api/export');
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type:'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = 'CCON_BA_State.json'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    message(hasUnsaved() ? 'Експортовано збережений стан. Незбережені правки спочатку збережи в задачах.' : 'Експортовано статуси, нотатки та збережені чернетки.');
  } catch (error) { message(error.message, true); }
});
window.addEventListener('beforeunload', event => {
  rememberViewContext();
  if (hasUnsaved()) { event.preventDefault(); event.returnValue = ''; }
});
window.addEventListener('pagehide', rememberViewContext);
$('detail').addEventListener('toggle', event=>{
  if (!event.target?.matches?.('details') || !disclosureState) return;
  for (const [key,open] of captureTaskView($('detail')).sections)
    disclosureState.set(key,open);
},true);
$('detail').addEventListener('focusout', event => {
  // Preserve the caret when the user switches from an unfinished deep task
  // to the queue. This stores positions, never the content of the edit.
  const cursor = captureEditorFocus(event.target, $('detail'));
  if (cursor && renderedTaskKey) {
    const existing = taskViews.get(renderedTaskKey) || captureTaskView($('detail'));
    taskViews.set(renderedTaskKey,{...existing,focus:cursor});
  }
  // Finish deferred snapshot refresh only after moving away from the editor.
  setTimeout(() => {
    if (!busy && pendingDetail && !isDirty(selected) && !detailInteractionFocused())
      renderDetail();
  }, 0);
});
let lastCloudAttemptState = null;
async function loadCloudCapabilities() {
  try {
    const health = await api('/api/health');
    cloudMode = health.cloud === true;
    if (!cloudMode) {
      const backup = health.localBackup || {};
      $('backupState').textContent = backup.backupCheckFailed ?
        'Резервування: остання автоматична спроба не вдалася. Перевір локальний запуск.' :
        backup.available ?
        'Резервна копія: ' + dateLabel(backup.createdAt) + ' · ревізія ' + backup.revision :
        'Резервна копія: відсутня. Зупини застосунок і перевір локальні дані.';
      const watcher = health.snapshotWatcher || {};
      $('watcherState').textContent =
        watcher.state === 'OK' ? 'Імпорт: перевірено · ' + (watcher.attempts ?? 0) + ' спроб' :
        watcher.state === 'FAILED' ? 'Імпорт: остання спроба не вдалася. Попередні правки збережені.' :
        watcher.state === 'NO_SNAPSHOT' ? 'Імпорт: snapshot ще не знайдено.' :
        'Імпорт: перевірка стану…';
    }
    if (cloudMode) {
      $('backupState').hidden = true;
      $('watcherState').hidden = true;
      $('bulkEmail').hidden = true;
      $('import').hidden = true;
      if ($('email')) $('email').textContent = 'Зберегти й скопіювати лист';
      const info = health.lastSuccessfulDailyRun;
      const attempt = health.lastDailyAttempt || null;
      const state = attempt?.status === 'FAILED'
        ? 'FAILED:' + (attempt.attemptedAtUtc || '')
        : attempt?.status === 'SUCCESS' ? 'SUCCESS:' + (attempt.attemptedAtUtc || '') : 'NOT_RUN';
      if (state !== lastCloudAttemptState) {
        lastCloudAttemptState = state;
        if (attempt?.status === 'FAILED')
          message('Останній хмарний аналіз завершився помилкою. Перевір статус працівника та джерела.', true);
        else if (!info) message('Хмарний режим: успішного щоденного аналізу ще немає.');
        else if (attempt?.status === 'SUCCESS') message('Щоденний хмарний аналіз успішно оновлено.');
      }
    }
  } catch {}
}
loadCloudCapabilities();
load();
loadDeltaStrip();
// Idle polling checks one SQLite revision row, not the whole Jira task payload.
// Background tabs do not spend CPU on hidden list/analysis rerenders.
async function pollChanges({force=false}={}) {
  if (pollingInFlight || busy || document.visibilityState === 'hidden' ||
      !transportRecovery.shouldPoll({force})) return;
  pollingInFlight = true;
  try {
    const revision = await api('/api/tasks/revision');
    // An API that answers 'revision' but cannot load its full payload is
    // still not recovered. Avoid acknowledging partial read-only success.
    if (needsFullTaskRefresh(currentRevision,currentRevisionError,revision) &&
        !await load()) throw Error('Не вдалось оновити задачі.');
    const wasOffline=transportRecovery.recovered();
    if (wasOffline)
      message('З’єднання відновлено. Незбережені чернетки залишилися у вкладці.');
    pollCycle++;
    if (pollCycle % 3 === 0) await loadLogs();
    if (pollCycle % 6 === 0) {
      await loadDeltaStrip();
      await loadCloudCapabilities();
    }
  } catch {
    const failure=transportRecovery.failed();
    if (failure.firstFailure)
      message('З’єднання втрачено. Незбережені поля залишилися у вкладці; '+
        'повторна перевірка лише для читання.',true);
  } finally {pollingInFlight=false;}
}
setInterval(()=>pollChanges(),5000);
window.addEventListener('online',()=>pollChanges({force:true}));
document.addEventListener('visibilitychange',()=>{
  if(document.visibilityState==='visible') pollChanges({force:true});
  else rememberViewContext();
});

function rankedTasks() { return queueModel.rankedTasks(tasks); }
function visibleTasks() {
  return queueModel.visibleTasks(tasks, {
    search:$('search').value.trim().toLocaleLowerCase('uk-UA'),
    filter:$('filter').value, signal:$('signalFilter').value,
    sprint:$('sprintFilter').value, priority:$('priorityFilter').value
  });
}

// Theme toggle: system -> light -> dark (state lives in theme-init.js / localStorage).
const THEME_ORDER = ['system', 'light', 'dark'];
const THEME_LABEL = {system: 'як у системі', light: 'світла', dark: 'темна'};
function renderThemeToggle() {
  const button = document.getElementById('themeToggle');
  if (!button || !window.cconTheme) return;
  const pref = window.cconTheme.get();
  const next = THEME_ORDER[(THEME_ORDER.indexOf(pref) + 1) % THEME_ORDER.length];
  button.dataset.pref = pref;
  const label = `Тема: ${THEME_LABEL[pref]}. Натисни – ${THEME_LABEL[next]}`;
  button.title = label;
  button.setAttribute('aria-label', label);
}
document.getElementById('themeToggle')?.addEventListener('click', () => {
  if (!window.cconTheme) return;
  const pref = window.cconTheme.get();
  window.cconTheme.set(THEME_ORDER[(THEME_ORDER.indexOf(pref) + 1) % THEME_ORDER.length]);
  renderThemeToggle();
});
renderThemeToggle();
