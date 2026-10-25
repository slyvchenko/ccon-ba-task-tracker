import {STATUS_LABELS, defaultRecipients, analysisOf, analysisIsStale, hasAnalysis, effectiveSignal, signalInfo, statusTone, queueTier, priorityLane, rankTasks, filterTasks} from './task-rules.mjs';
import {createLogsController} from './logs.mjs';
import {needsFullTaskRefresh} from './revision-policy.mjs';
import {baseManualRevision, manualVersionChanged, withExpectedRevision} from './manual-edit-policy.mjs';
import {createDraftRecoveryStore,RETENTION_DAYS} from './draft-recovery.mjs';
import {isTextEditingTarget, shortcutAction, adjacentTaskKey, captureTaskView,
  restoreTaskView, captureEditorFocus, restoreEditorFocus, sanitizeSessionFocus}
  from './focus-navigation.mjs';
import {quickHandoff, priorityExplanation, completionPrompt} from './fast-handoff.mjs';
import {createQueueModel,createSearchDebouncer,selectedAfterFilter} from './queue-performance.mjs';
import {EFFORT_LABELS, effortInfo, quickWinCandidate, quickWinExplanation} from './effort-planning.mjs';
import {loadTaskEvidence, loadTaskQuestions} from './evidence-ui.mjs';
import {loadTaskDecisions} from './decisions-ui.mjs';
import {loadTaskActions, loadTaskHistory} from './action-history.mjs';


const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const recoveryStore=createDraftRecoveryStore({
  local:window.localStorage,session:window.sessionStorage,
  newId:()=>window.crypto.randomUUID()
});
const LOCAL_VIEW_KEY = 'ccon-ba-desk.view-context.v1';
const restoredFocusView = readViewContext();
let tasks = [], selected = restoredFocusView.selected, latest = null, busy = false, browserRecoveryAvailable = true, loadRequest = 0, cloudMode = false;
let signature = '', renderedTaskVersion = '', renderedTaskKey = null, pendingDetail = false;
let currentRevision = null, currentRevisionError = '', pollingInFlight = false, pollCycle = 0;
const queueModel=createQueueModel();
const searchRefresh=createSearchDebouncer(()=>applyFilters());
const forms = new Map();
const manualConflicts = new Map();
const taskViews = new Map(Object.entries(restoredFocusView.views));
const saveFailures = new Map();
const expandedEmails = new Set();
const recoveredForms = recoveryStore.load();
const {loadLogs} = createLogsController({api, escapeHtml, message, getSelected: () => selected});

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
  $('recoverOther').disabled = !old.length;
  $('purgeOld').disabled = !old.some(x=>x.stale);
}
function normalizedDraft(value) {
  return {to:typeof value?.to === 'string' ? value.to : '', subject:typeof value?.subject === 'string' ? value.subject : '', body:typeof value?.body === 'string' ? value.body : ''};
}
function savedForm(task) {
  const emailDraft = normalizedDraft(task.savedEmailDraft ?? task.analysis?.emailDraft);
  if (task.savedEmailDraft == null || !emailDraft.to.trim()) emailDraft.to = defaultRecipients(task);
  return {manualStatus:STATUS_LABELS[task.manualStatus] ? task.manualStatus : 'AUTO',
    manualEffort:EFFORT_LABELS[task.manualEffort] ? task.manualEffort : 'UNKNOWN',
    note:task.note || '', emailDraft};
}
function formFor(task) {
  if (!forms.has(task.key)) {
    const base = savedForm(task), recovered = recoveredForms[task.key];
    const value = recovered && STATUS_LABELS[recovered.manualStatus] && typeof recovered.note === 'string'
      ? {manualStatus:recovered.manualStatus, note:recovered.note,
        manualEffort:EFFORT_LABELS[recovered.manualEffort] ? recovered.manualEffort : base.manualEffort,
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
function signalBadge(task) {
  const info = signalInfo(task), manual = task.manualStatus && task.manualStatus !== 'AUTO';
  const label = manual ? STATUS_LABELS[task.manualStatus] : hasAnalysis(task) ? info.label : analysisIsStale(task) ? 'Аналіз потребує оновлення' : 'Ще без нового аналізу';
  return `<span class="badge tone-${info.tone}"><span class="dot" aria-hidden="true"></span>${escapeHtml(label)}</span>`;
}
function renderList() {
  const focusedRow = document.activeElement?.closest?.('#list [data-key]')?.dataset.key || null;
  const previousListScroll = $('list').scrollTop;
  const previousSidebarScroll = $('list').closest('aside')?.scrollTop || 0;
  updateSnapshotInfo();
  const items = visibleTasks(), current = tasks.filter(task => task.active), analyzed = current.filter(hasAnalysis).length;
  const mailCount = tasks.filter(task => task.active && effectiveSignal(task) === 'WRITE').length;
  const potentialQuick = current.filter(quickWinCandidate).length;
  $('bulkEmail').textContent = `Відкрити всі листи (${mailCount})`;
  $('bulkEmail').disabled = !mailCount || busy;
  $('bulkEmail').hidden = cloudMode;
  const verified = current.filter(task => task.activeSprintStatus === 'VERIFIED').length;
  const sprintCount = current.filter(task => task.activeSprintStatus === 'VERIFIED' && task.activeSprint).length;
  $('count').textContent = `${items.length} у списку · ${sprintCount} активний спринт · ${current.length} поточних · аналіз ${analyzed}/${current.length} · короткі кандидати ${potentialQuick} (без зміни черги)` +
    (verified < current.length ? ' · спринт ще не підтверджено' : '');
  let previousGroup = '';
  $('list').innerHTML = items.map((task, index) => {
    const scope = ['Активний спринт · головна черга', 'Поза активним спринтом / не підтверджено', 'Завершені', 'Архів'][priorityLane(task)];
    const group = scope + ' · ' + ['Можна просувати зараз', 'Очікуємо', 'Завершені', 'Відсутні в останньому snapshot'][queueTier(task)];
    const heading = group !== previousGroup ? `<div class="queue-group">${escapeHtml(group)}</div>` : '';
    previousGroup = group;
    return `${heading}<button class="row ${task.key === selected ? 'selected' : ''}" data-key="${escapeHtml(task.key)}" aria-pressed="${task.key === selected}"><span class="row-number" aria-label="Позиція ${index + 1}">${index + 1}</span><span class="row-content"><span class="row-head"><span class="rank">${escapeHtml(task.key)}</span><span>${isDirty(task.key) ? '<span class="edit-dot" title="Є незбережені зміни">● </span>' : ''}</span></span><span class="row-title" title="${escapeHtml(task.summary)}">${escapeHtml(task.summary)}</span><span class="row-statuses">${task.activeSprintStatus === "VERIFIED" && task.activeSprint === true ? '<span class="badge tone-blue">Спринт</span>' : ''}${signalBadge(task)}${quickWinCandidate(task) ? '<span class="effort-hint" title="Можлива коротка дія, оцінка орієнтовна. Порядок черги не змінено.">S?</span>' : ''}${task.blocking ? '<span class="badge tone-red">Блокує інших</span>' : ''}</span></span></button>`;
  }).join('') || '<div class="empty">Немає задач за цими фільтрами.</div>';
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
function sourceMarkup(analysis) {
  if (!Array.isArray(analysis.evidence) || !analysis.evidence.length) return '<p class="muted">Джерела оцінки ще не додані.</p>';
  return '<ul class="source-list">' + analysis.evidence.map(item => {
    const url = safeUrl(item.url);
    return `<li class="wordbreak">${escapeHtml(item.text || 'Джерело')}${url ? ` · <a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Відкрити ↗</a>` : ''}</li>`;
  }).join('') + '</ul>';
}

function briefingMarkup(briefing, stale) {
  if (!briefing || typeof briefing !== 'object') {
    return '<section class="panel ba-brief"><h3>Ситуація за 30 секунд</h3><p class="muted">Структурований BA-брифінг ще не підготовлено. Перевір поточний аналіз та джерела нижче.</p></section>';
  }
  const readiness = {
    READY_FOR_REVIEW:'Чернетка готова до перевірки BA',
    NEEDS_CONFIRMATION:'Є відкриті рішення',
    INSUFFICIENT_CONTEXT:'Недостатньо підтверджених даних'
  }[briefing.readiness] || 'Рівень готовності не визначено';
  const source = (url, label='Джерело') => {
    const safe = safeUrl(url);
    return safe ? ` <a href="${escapeHtml(safe)}" target="_blank" rel="noopener noreferrer">${label} ↗</a>` : '<span class="muted"> (не підтверджено джерелом)</span>';
  };
  const entries = (items, render) => Array.isArray(items) && items.length
    ? `<ul class="brief-list">${items.map(item => `<li>${render(item)}</li>`).join('')}</ul>`
    : '<p class="muted">Не встановлено з доступних джерел.</p>';
  const field = (heading, value) => `<div class="section-label">${heading}</div><p class="pre">${escapeHtml(value || 'Не встановлено з доступних джерел.')}</p>`;
  const facts = entries(briefing.confirmedFacts, item => `${escapeHtml(item.textUk)}${source(item.sourceUrl)}`);
  const history = entries(briefing.timeline, item => `${escapeHtml(item.date || 'Дата невідома')} · ${escapeHtml(item.status)}: ${escapeHtml(item.eventUk)}${source(item.sourceUrl)}`);
  const sourceAudit = entries(briefing.sourceAudit, item => `${escapeHtml(item.status)}: ${escapeHtml(item.descriptionUk)}${source(item.sourceUrl)}`);
  const rules = entries(briefing.rules, item => `<b>IF</b> ${escapeHtml(item.whenUk)} <b>THEN</b> ${escapeHtml(item.thenUk)} · ${escapeHtml(item.certainty)}${source(item.sourceUrl)}`);
  const tests = entries(briefing.verification, item => `<b>Сценарій:</b> ${escapeHtml(item.scenarioUk)} <b>Очікування:</b> ${escapeHtml(item.expectedUk)}${source(item.sourceUrl)}`);
  const plain = values => entries(values, item => escapeHtml(item));
  return `<section class="panel ba-brief" aria-label="Розбір ситуації та вимог">
    <div class="panel-title"><h3>Ситуація за 30 секунд</h3><span class="badge ${briefing.readiness === 'READY_FOR_REVIEW' ? 'tone-green' : 'tone-amber'}">${escapeHtml(readiness)}</span></div>
    ${stale ? '<p class="analysis-missing">Брифінг застарів: використовуй лише після оновлення джерел.</p>' : ''}
    <p class="pre brief-overview">${escapeHtml(briefing.overviewUk || 'Контекст поки не сформовано.')}</p>
    ${field('Що відбувається зараз', briefing.currentUk)}
    ${field('Що має бути в результаті', briefing.targetUk)}
    <details class="description" open><summary>Підтверджені факти та джерела</summary>${facts}</details>
    <details class="description"><summary>Перевірені й недоступні джерела</summary>${sourceAudit}</details>
    <details class="description"><summary>Історія рішень і суперечностей</summary>${history}</details>
    <details class="description"><summary>Правила IF / THEN</summary>${rules}</details>
    <details class="description"><summary>QA та перевірки приймання</summary>${tests}</details>
    <details class="description"><summary>Scope, бізнес-вплив і ризики</summary>
      ${field('Технічні межі', briefing.technicalScopeUk)}
      ${field('Бізнес-вплив', briefing.businessImpactUk)}
      <div class="section-label">Ризики</div>${plain(briefing.risksUk)}
    </details>
    <details class="description"><summary>Що не встановлено</summary>${plain(briefing.unknownsUk)}</details>
    ${field('Чому саме такий рівень готовності', briefing.readinessReasonUk)}
    <p class="muted">Це підготовлений аналіз, а не гарантія правильності. Перед рішенням перевір першоджерела та непідтверджені припущення.</p>
  </section>`;
}

function priorityBreakdown(analysis) {
  const factors = analysis?.priorityFactors;
  if (!factors || typeof factors !== 'object') return '';
  const definitions = [
    ['businessImpact', 'Бізнес-вплив', 25],
    ['urgency', 'Терміновість', 25],
    ['dependencies', 'Залежності', 20],
    ['baDecision', 'Рішення BA', 20],
    ['actionability', 'Можливість діяти', 10],
  ];
  return `<details class="description">
    <summary>Пояснювана оцінка: ${escapeHtml(analysis.queueScore)} / 100</summary>
    <ul class="brief-list">${definitions.map(([name,label,max]) => `<li>${label}: <b>${escapeHtml(factors[name] ?? 'не визначено')} / ${max}</b></li>`).join('')}</ul>
    <p class="muted">Оцінка визначає порядок у межах групи; активний спринт має окремий вищий пріоритет.</p>
  </details>`;
}

function legacyMarkup(task) {
  const parts = [['Попереднє пояснення', task.statusReason], ['Попередня дія', task.nextAction], ['Попередній підготовлений текст', task.readyOutput]].filter(item => item[1]);
  if (!parts.length) return '';
  return `<details class="description"><summary>Вихідний текст попереднього snapshot</summary>${parts.map(([title, text]) => `<div class="section-label">${escapeHtml(title)}</div><p class="pre">${escapeHtml(text)}</p>`).join('')}</details>`;
}
function previousAnalysisMarkup(task) {
  const previous = analysisOf(task);
  if (!analysisIsStale(task) || !(previous.reasonUk || previous.nextActionUk)) return '';
  return `<details class="description"><summary>Попередній аналіз — застарів після зміни контексту</summary><p class="muted">Ці висновки збережені лише як історія; вони не визначають поточну чергу чи сигнали.</p><div class="section-label">Попереднє пояснення</div><p class="pre">${escapeHtml(previous.reasonUk || '')}</p><div class="section-label">Попередня дія</div><p class="pre">${escapeHtml(previous.nextActionUk || '')}</p><div class="section-label">Попередні джерела</div>${sourceMarkup(previous)}</details>`;
}
function taskVersion(task) { return JSON.stringify([latest?.hash || latest?.generated_at || '', task]); }
function qualityGateMarkup(gate) {
  if (!gate) return '';
  const names = {BLOCKED:'Потрібне підтвердження', NEEDS_REVIEW:'Перевірити опис',
    STRUCTURALLY_VERIFIED:'Структура перевірена (не доказ правильності)'};
  const findings = (gate.findings || []).slice(0, 25).map(f =>
    '<li><b>' + escapeHtml(f.code) + '</b> · ' + escapeHtml(f.ref) + ': ' + escapeHtml(f.messageUk) + '</li>').join('');
  const coverage = (gate.qaCoverage || []).slice(0, 25).map(r =>
    '<li>' + escapeHtml(r.ruleId) + ': ' + escapeHtml((r.covered || []).join(', ') || 'Тестів немає') +
    ((r.missing || []).length ? ' · бракує ' + escapeHtml(r.missing.join(', ')) : ' · покрито') + '</li>').join('');
  const summary = gate.summary || {};
  const density = summary.descriptionProfile || {};
  const compactHint = Number.isFinite(density.words) && density.words > 0
    ? ' Опис: ' + escapeHtml(density.words) + ' слів, ' +
      escapeHtml(density.qaChecks || 0) + ' QA-перевірок. ' +
      (summary.compactnessSuggestions ? 'Є підказки щодо стислості. ' : '')
    : '';
  return '<details class="description"><summary>Перевірка доказів і QA · ' +
    escapeHtml(names[gate.state] || 'Недостатньо даних') + '</summary><p class="muted">' +
    'Цитат у прочитаних джерелах: ' + escapeHtml(summary.sourceExcerptsPresent || 0) + '/' +
    escapeHtml(summary.claimsChecked || 0) + '. Правил із QA: ' +
    escapeHtml(summary.rulesFullyCovered || 0) + '/' + escapeHtml(summary.rulesTracked || 0) +
    '. Зауважень до BA-результату: ' + escapeHtml(summary.outputFindings || 0) + '.' +
    compactHint + ' Це структурна перевірка, не підтвердження бізнес-правильності.</p>' +
    (coverage ? '<div class="section-label">Покриття умов</div><ul>' + coverage + '</ul>' : '') +
    (findings ? '<div class="section-label">Що виправити</div><ul>' + findings + '</ul>' : '') + '</details>';
}

async function loadApprovedDescription(key) {
  const node = $('approvedReview');
  if (!node) return;
  try {
    const data = await api('/api/approved/' + encodeURIComponent(key));
    if (selected !== key || !$('approvedReview')) return;
    const labels = {NO_APPROVED_REFERENCE:'Ще немає вручну схваленого опису',
      UNCHANGED:'Опис збігається з останнім схваленим',
      NEW_DRAFT_DIFFERS:'Новий опис відрізняється від схваленого',
      SOURCE_CHANGED:'Jira-контекст змінився: потрібна повторна перевірка'};
    node.innerHTML = '<p>' + escapeHtml(labels[data.state] || 'Статус невідомий') + '</p>' +
      (data.diff ? '<details><summary>Показати зміни від схваленої версії</summary>' +
       '<pre class="pre">' + escapeHtml(data.diff) + '</pre></details>' : '');
  } catch (error) {
    if (selected === key && $('approvedReview')) $('approvedReview').textContent = 'Порівняння недоступне: ' + error.message;
  }
}

function renderDetail() {
  const task = tasks.find(item => item.key === selected);
  if (!task) {
    $('detail').innerHTML = tasks.length ? '<div class="empty"><h2>Оберіть задачу з черги</h2>Зміни фільтр, щоб побачити інші задачі.</div>' : '<div class="empty"><h2>Почни зі snapshot</h2>Збережи <b>CCON_BA_Snapshot.json</b> у папку <b>inbox</b> поруч із застосунком.<br>Дані імпортуються автоматично. Ручні статуси, нотатки та збережені чернетки залишаються між днями.</div>';
    renderedTaskVersion = '';
    renderedTaskKey = null;
    return;
  }
  const retainPosition = renderedTaskKey === task.key;
  const state = retainPosition ? {...captureTaskView($('detail')),
    focus:taskViews.get(task.key)?.focus} : taskViews.get(task.key);
  const focusedEditor = retainPosition ? captureEditorFocus(document.activeElement, $('detail')) : null;
  const analyzed = hasAnalysis(task), stale = analysisIsStale(task), analysis = analyzed ? analysisOf(task) : {};
  const form = formFor(task).value, info = signalInfo(task), url = safeUrl(task.url);
  const savedDraft = task.savedEmailDraft !== null && task.savedEmailDraft !== undefined;
  const staleGeneratedDraft = stale && !savedDraft && !!analysisOf(task).emailDraft?.body;
  const manualWaiting = ['WAITING INPUT','WAITING DEPENDENCY'].includes(task.manualStatus);
  const waiting = task.manualStatus !== 'AUTO' ? manualWaiting : analysis.waitingRequired, email = manualWaiting || task.manualStatus === 'DONE' ? false : analysis.needsEmail;
  const missing = Array.isArray(analysis.missingInfo) ? analysis.missingInfo : [];
  const quick = quickHandoff(task);
  const ranking = priorityExplanation(task);
  const effort = effortInfo({...task, manualEffort:form.manualEffort});
  const potentialQuick = quickWinCandidate({...task, manualEffort:form.manualEffort});
  $('detail').innerHTML = `
    <div class="task-top task-toolbar"><span class="task-key">${escapeHtml(task.key)}${url ? ` <a class="jira-button" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Відкрити Jira ↗</a>` : ''}</span><span class="badge tone-${info.tone}"><span class="dot" aria-hidden="true"></span>${escapeHtml(analyzed || task.manualStatus !== 'AUTO' ? info.label : 'Потрібен аналіз')}</span><span class="muted task-date">${task.importedAt ? 'Дані: ' + dateLabel(task.importedAt) : ''}</span></div>
    <h2>${escapeHtml(task.summary)}</h2>
    <div class="task-badges signal-strip task-meta" aria-label="Статус Jira, листування та очікування"><span class="badge">Jira: ${escapeHtml(task.jiraStatus || 'Не вказано')}</span>${task.activeSprintStatus === "VERIFIED" ? `<span class="badge ${task.activeSprint ? 'tone-blue' : 'tone-gray'}">${escapeHtml(task.activeSprint ? 'Активний спринт: ' + (task.activeSprintNames || []).join(', ') : 'Поза активним спринтом')}</span>` : '<span class="badge tone-amber">Активний спринт не підтверджено</span>'}${task.blocking ? '<span class="badge tone-red">Блокує інших</span>' : ''}${!task.active ? '<span class="badge tone-gray">Відсутня в останньому snapshot · стан збережений</span>' : ''}
      ${effectiveSignal(task) === 'WRITE' && email === true ? '' : `<span class="signal-text text-${email === true ? 'blue' : email === false ? 'green' : 'gray'}">${email === true ? 'Потрібен лист' : email === false ? 'Лист не потрібен' : 'Потребу в листі не визначено'}</span>`}
      <span class="signal-text text-${waiting === true ? 'red' : waiting === false ? 'green' : 'gray'}">${escapeHtml(waiting === true ? manualWaiting ? 'Очікуємо за моїм статусом' : 'Очікуємо: ' + (analysis.waitingOnUk || 'адресат не вказаний') : waiting === false ? 'Не очікуємо' : 'Очікування не визначено')}</span>
    </div>
    <section class="panel quick-handoff" aria-label="Найближча дія та швидка передача">
      <div class="section-label">Що зробити зараз</div>
      <p class="pre next-action" id="nextText">${escapeHtml(quick.nextAction || (stale ? 'Онови аналіз за актуальним контекстом Jira, перш ніж діяти.' : 'Перевір контекст і сформуй конкретну дію.'))}</p>
      <div class="actions quick-handoff-actions">
        ${quick.nextAction ? '<button id="copyNext" class="quiet">Скопіювати дію</button>' : ''}
        ${quick.description ? `<button id="copyFastDescription" class="quiet" ${quick.readyForCopy ? '' : 'disabled'}>Скопіювати Jira-чернетку</button>` : ''}
      </div>
      <p class="muted quick-proof-note">${escapeHtml(quick.evidenceNote)}</p>
      <p class="muted effort-summary">${escapeHtml('Обсяг: ' + effort.label +
        (effort.source === 'MANUAL' ? ' · моя оцінка' : ' · автоматична гіпотеза, низька впевненість') +
        '. ' + effort.reason)}
        ${potentialQuick ? '<span class="effort-hint">Кандидат короткої дії, не новий пріоритет</span>' : ''}
      </p>
      <details class="description"><summary>Чому задача в цій позиції черги</summary>
        <ol class="brief-list">${ranking.sourceOrder.map(item => '<li>' + escapeHtml(item) + '</li>').join('')}</ol>
        <p class="muted">Порядок: активний спринт, потреба в листі, тип дії, оцінка та блокування. Копіювання не змінює Jira.</p>
      </details>
    </section>
    <div id="staleNotice" class="saved-note" hidden></div>
    ${stale ? '<div class="analysis-missing"><b>Контекст Jira змінився — попередній аналіз застарів.</b><br>Черга й сигнали потребують нового аналізу опису, коментарів та залежностей. Твій ручний стан і збережена чернетка залишаються чинними.</div>' : !analyzed ? '<div class="analysis-missing"><b>Для цієї задачі ще немає повного аналізу українською.</b><br>Потрібно прочитати опис, коментарі й залежності. Попередній snapshot не дає достатніх підстав для нової оцінки.</div>' : ''}
    ${briefingMarkup(analyzed ? analysis.briefing : undefined, stale)}
    <div class="detail-grid">
      <div>
        <section class="panel analysis-lead" aria-label="Пояснення та наступна дія">
          <div class="section-label">Чому така оцінка</div>
          <p class="pre assessment-reason">${escapeHtml(analysis.reasonUk || (stale ? 'Попередні висновки не підтверджені новим контекстом. Потрібен повторний аналіз.' : 'Щоденний аналіз ще не підготовлений.'))}</p>
          ${priorityBreakdown(analysis)}
          <details class="description"><summary>Мій план дій і наступна перевірка</summary>
            <div id="actionPlan" class="muted">Завантажую план…</div>
          </details>
        </section>
        <section class="panel" aria-label="Відсутні дані та підстави оцінки">
          <div class="section-label">Відкриті питання BA</div>
          <details class="description"><summary>Історія питань і відповіді</summary>
            <div id="questionTracker" class="question-tracker muted">Завантажую…</div>
          </details>
          <details class="description"><summary>Рішення та їхня історія</summary>
            <div id="decisionTracker" class="question-tracker muted">Завантажую рішення…</div>
          </details>
          ${missing.length ? '<ol class="missing-info">' + missing.map(item => '<li>' + escapeHtml(item) + '</li>').join('') + '</ol>' : `<p class="muted">${analyzed ? 'Аналіз не виявив додаткових питань. Перевір пояснення та джерела нижче.' : 'Поки не визначено — потрібен аналіз контексту.'}</p>`}
          <details class="description"><summary>Підтвердження з REST / Supplier / Errors</summary>
            <div id="evidenceSummary" class="muted">Завантажую…</div>
          </details>
          <div class="section-label">На чому ґрунтується оцінка</div>
          ${sourceMarkup(analysis)}
          ${qualityGateMarkup(analysis.qualityGate)}
          <details class="description"><summary>Чернетка опису задачі</summary><p class="pre">${escapeHtml(analysis.standardDescription || 'Чернетку не підготовлено. Перевір причину в поясненні аналізу.')}</p>${analysis.standardDescription ? '<button id="copyDescription" class="quiet">Скопіювати опис</button> <button id="approveDescription" class="quiet">Схвалити опис</button>' : ''}<div id="approvedReview" class="muted">Перевіряю схвалену версію…</div></details>
          ${previousAnalysisMarkup(task)}
          <details class="description"><summary>Історія змін задачі</summary>
            <div id="taskHistory" class="muted">Завантажую історію…</div>
          </details>
          ${legacyMarkup(task)}
        </section>
        <section class="panel" aria-label="Контекст Jira">
          <div class="panel-title"><h3>Контекст Jira</h3><button id="loadContext" class="quiet">Показати опис і коментарі</button></div>
          <div id="contextPreview" class="muted">Повний вихідний контекст можна відкрити для перевірки аналізу.</div>
        </section>
      </div>
      <div class="right-column">
        <section class="panel work-state" aria-label="Мій робочий стан">
          <div class="manual-status-label"><label for="manual">Мій статус</label><details class="status-help"><summary aria-label="Як працює мій статус">ⓘ</summary><p>«Автоматично» використовує оцінку щоденного аналізу. Ручний вибір фіксує твій власний статус і має пріоритет. Вибір статусу зберігається автоматично.</p></details></div>
          <select id="manual" class="status-select tone-${statusTone(form.manualStatus, task)}">${['AUTO','IN PROGRESS','NEEDS DECISION','WAITING INPUT','WAITING DEPENDENCY','DONE'].map(value => `<option value="${value}" ${form.manualStatus === value ? 'selected' : ''}>${escapeHtml(STATUS_LABELS[value])}</option>`).join('')}</select>
          <label for="manualEffort">Моя оцінка тривалості</label>
          <select id="manualEffort" aria-describedby="effortHelp">${Object.entries(EFFORT_LABELS).map(([key,label]) =>
            `<option value="${key}" ${form.manualEffort === key ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('')}</select>
          <p id="effortHelp" class="muted">Збережеться разом із нотатками. Оцінка не змінює порядок задач і не передається в Jira.</p>
          <label for="note">Мої нотатки</label><textarea id="note" maxlength="20000" placeholder="Додай домовленість або наступний контакт…">${escapeHtml(form.note)}</textarea>
          <div class="actions state-actions"><span id="savedIndicator" role="status">✓ Збережено</span><button id="save">Зберегти все</button><button id="done" class="primary">Виконано → Далі</button><button id="discard" class="quiet" title="Скинути незбережене">Скинути</button></div>
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
        <details id="emailDetails" class="panel email-panel ${email === true || form.emailDraft.body ? 'email-first' : ''}" ${email === true || form.emailDraft.body || form.emailDraft.subject || expandedEmails.has(task.key) ? 'open' : ''}>
          <summary class="email-summary"><span>${email === false && !form.emailDraft.body && !form.emailDraft.subject ? 'Лист зараз не потрібен' : 'Чернетка листа'}</span><span class="email-toggle">Підготувати лист</span></summary>
          <div class="email-fields" role="region" aria-label="Редагована чернетка листа">
          <div class="panel-title email-meta"><span class="badge ${staleGeneratedDraft ? 'tone-amber' : email === true ? 'tone-blue' : 'tone-gray'}">${staleGeneratedDraft ? 'Зі старого аналізу' : savedDraft && stale ? 'Моя збережена чернетка' : email === true ? 'Потрібна' : email === false ? 'За потреби' : 'Потребу ще не визначено'}</span></div>
          <p class="email-intro">${stale && form.emailDraft.body ? savedDraft ? 'Твоя збережена чернетка залишилася без змін. Аналіз застарів: перевір лист за новим контекстом перед використанням.' : 'Новий контекст ще не проаналізовано. Ця чернетка збережена зі старого аналізу або твоїх незбережених правок; перевір її актуальність перед використанням.' : form.emailDraft.body ? 'Перевір адресата й текст. Усі поля можна відредагувати.' : email === false && analyzed ? 'За поточним аналізом лист зараз не потрібен. За потреби можеш підготувати власну чернетку.' : email === true ? 'Потрібен лист, але готової чернетки ще немає. Підготуй текст за конкретними відкритими питаннями задачі.' : 'Потребу в листі ще не визначено. Спочатку перевір контекст і наступну дію.'}</p>
          <label for="draftTo">Кому</label><input id="draftTo" maxlength="2000" autocomplete="off" placeholder="Email адресата, якщо він відомий" value="${escapeHtml(form.emailDraft.to)}">
          <label for="draftSubject">Тема</label><input id="draftSubject" maxlength="2000" placeholder="Тема листа" value="${escapeHtml(form.emailDraft.subject)}">
          <label for="draftBody">Текст листа</label><textarea id="draftBody" maxlength="50000" placeholder="Чернетка за описом, коментарями та відкритими питаннями задачі…">${escapeHtml(form.emailDraft.body)}</textarea>
          <section id="emailLogs" class="email-logs" aria-label="Логи до листа"><div class="logs-heading"><h4>Логи до листа</h4></div><p class="muted" role="status">Перевіряю архіви задачі…</p></section>
          <div class="actions"><button id="copyEmail" class="quiet">Скопіювати лист</button><button id="email" class="primary">Відкрити в пошті ↗</button></div>
          </div>
        </details>
      </div>
    </div>`;
  renderedTaskVersion = taskVersion(task);
  renderedTaskKey = task.key;
  pendingDetail = false;
  restoreTaskView($('detail'), state);
  // Renders triggered by Save must preserve an active note/email caret.
  // A background refresh intentionally doesn't rerender while the editor
  // is focused; this also safely handles explicit same-task rerenders.
  restoreEditorFocus($('detail'), focusedEditor || state?.focus,
    {focusElement:Boolean(focusedEditor)});
  ['note', 'draftTo', 'draftSubject', 'draftBody'].forEach(id => $(id).addEventListener('input', captureForm));
  $('manualEffort').addEventListener('change', captureForm);
  $('manual').addEventListener('change', () => saveStatus($('manual').value));
  if ($('copyNext')) $('copyNext').addEventListener('click', () =>
    copyText(quick.nextAction, 'Дію скопійовано. Це не означає її виконання.'));
  if ($('copyFastDescription')) $('copyFastDescription').addEventListener('click', () =>
    copyText(quick.description, 'Jira-чернетку скопійовано. Перевір факти й передай вручну.'));
  if ($('copyDescription')) $('copyDescription').addEventListener('click', () => copyText(analysis.standardDescription, 'Чернетку опису скопійовано.'));
  if ($('approveDescription')) $('approveDescription').addEventListener('click', async () => {
    if (!confirm('Схвалити поточний BA-опис як контрольну версію? Це не змінює Jira.')) return;
    try {
      await api('/api/approved/' + encodeURIComponent(task.key), {});
      message('BA-опис схвалено локально. Jira не змінено.');
      if (selected === task.key) loadApprovedDescription(task.key);
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
  if (cloudMode) $('email').textContent = 'Зберегти й скопіювати лист';
  $('emailDetails').addEventListener('toggle', () => { if ($('emailDetails').open) expandedEmails.add(task.key); else expandedEmails.delete(task.key); });
  $('loadContext').addEventListener('click', () => loadContext(task.key));
  updateFormStatus();
  showManualConflict();
  loadTaskEvidence(task.key, api, escapeHtml, () => selected);
  loadTaskQuestions(task.key, api, escapeHtml, message, () => selected);
  loadTaskDecisions(task.key, api, escapeHtml, message, () => selected);
  loadTaskActions(task.key, api, escapeHtml, message, () => selected,
                  analysis.nextActionUk || '');
  loadTaskHistory(task.key, api, escapeHtml, () => selected);
  loadApprovedDescription(task.key);
  loadLogs(task.key);
}
function captureForm() {
  const task = tasks.find(item => item.key === selected);
  if (!task) return;
  const form = formFor(task);
  form.value = {manualStatus:$('manual').value, manualEffort:$('manualEffort').value,
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
    if (!confirm('Після порівняння перезаписати актуальний локальний статус, нотатку й лист МОЄЮ версією? Jira та пошта не змінюються.')) return;
    const task = tasks.find(item => item.key === key);
    const form = formFor(task);
    const own = structuredClone(form.value);
    const response = await api('/api/tasks/' + encodeURIComponent(key),
      withExpectedRevision(own, remote.manualRevision));
    Object.assign(task, {manualStatus:own.manualStatus, manualEffort:own.manualEffort, note:own.note,
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
  if (!confirm('Скинути незбережені зміни статусу, нотаток і чернетки цієї задачі?')) return;
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
  ['manual', 'manualEffort', 'note', 'draftTo', 'draftSubject', 'draftBody', 'save', 'done', 'email', 'discard',
    'conflictOverwrite', 'conflictUseSaved'].forEach(id => { if ($(id)) $(id).disabled = value; });
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
    const saved = await api('/api/tasks/' + encodeURIComponent(task.key),
      withExpectedRevision({manualStatus:status, note:task.note || ''}, form.baseRevision));
    task.manualStatus = status;
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
  captureForm();
  const form = formFor(task);
  const value = structuredClone(form.value);
  if (done) value.manualStatus = 'DONE';
  setBusy(true);
  try {
    if (!Number.isSafeInteger(form.baseRevision)) {
      await loadManualConflict(task.key);
      return false;
    }
    const saved = await api('/api/tasks/' + encodeURIComponent(task.key),
      withExpectedRevision(value, form.baseRevision));
    Object.assign(task, {manualStatus:value.manualStatus, manualEffort:value.manualEffort, note:value.note,
      savedEmailDraft:value.emailDraft, manualRevision:saved.manualRevision,
      modifiedAt:new Date().toISOString()});
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
    message(cloudMode ? 'Статус, нотатки та чернетку збережено у приватній базі.' : 'Статус, нотатки та чернетку збережено в локальній базі.');
    return true;
  } catch (error) {
    if (error.code === 'TASK_REVISION_CONFLICT') await loadManualConflict(task.key);
    else {
      saveFailures.set(task.key, error.message);
      message(error.message, true);
    }
    return false;
  } finally { setBusy(false); }
}
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
  finally { $('bulkClose').disabled = false; $('bulkOpen').disabled = !bulkItems.length; }
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
  if (!draft?.subject.trim() || !draft?.body.trim()) { message('Додай тему й текст листа перед відкриттям чернетки.', true); return; }
  if (!await saveTask(false)) return;
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
async function loadContext(key) {
  const button = $('loadContext');
  button.disabled = true;
  try {
    const context = await api('/api/context/' + encodeURIComponent(key));
    if (selected !== key || !$('contextPreview')) return;
    if (!context.contextAvailable) { $('contextPreview').textContent = 'Повний контекст ще не завантажений. Відкрий задачу у Jira або дочекайся щоденного оновлення.'; return; }
    renderContext(context);
    button.textContent = 'Контекст завантажено';
  } catch (error) { if (selected === key && $('contextPreview')) $('contextPreview').textContent = 'Не вдалося завантажити контекст: ' + error.message; }
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
      const label = [issue.key, issue.summary].filter(Boolean).join(' — ');
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
  $('snapshotInfo').textContent = latest ? tasks.filter(task => task.active).length + ' задач · ' + tasks.filter(task => task.active && effectiveSignal(task) === 'WRITE').length + ' листів · Оновлено ' + dateLabel(latest.generated_at) : 'Очікую snapshot';
}
async function load() {
  const request = ++loadRequest;
  try {
    const data = await api('/api/tasks');
    if (busy || request !== loadRequest) return;
    const nextSignature = JSON.stringify(data);
    const changed = nextSignature !== signature;
    if (!changed && !pendingDetail) return;
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
        if (!isDirty(key)) { forms.delete(key); return; }
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
    if (detailChanged || pendingDetail || !$('detail').hasChildNodes()) {
      if (isDirty(selected) || detailInteractionFocused()) {
        pendingDetail = true;
        updateFormStatus();
      }
      else renderDetail();
    }
    if (data.error) message(data.error, true);
    else if (changed) message(hasUnsaved() ? 'Дані оновлено. Незбережені правки залишаються у твоїх формах.' : '');
  } catch (error) { message('Сервер недоступний. Запусти Start CCON BA.bat. ' + error.message, true); }
}
async function loadDeltaStrip() {
  const target = $('deltaStrip');
  try {
    const result = await api('/api/daily-report');
    if (result.available === false || !result.summary) {
      target.hidden = true;
      return;
    }
    const summary = result.summary;
    target.replaceChildren();
    const label = document.createElement('span');
    label.textContent = 'Зміни останнього аналізу: ' +
      'нові ' + (summary.NEW ?? 0) +
      ' · змінені ' + (summary.UPDATED ?? 0) +
      ' · Done у Jira ' + (summary.JIRA_DONE ?? 0) +
      ' · поза JQL ' + (summary.LEFT_SCOPE ?? 0) +
      ' · +питання ' + (summary.questionsAdded ?? 0) +
      ' · −питання ' + (summary.questionsRemoved ?? 0) +
      ' · попереджень ' + (summary.warnings ?? 0);
    const link = document.createElement('a');
    link.href = '/api/daily-report.md';
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Повний звіт ↗';
    target.append(label, link);
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
  if (action === 'SAVE' && !$('detail').contains(event.target)) return;
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
for (const id of ['filter','signalFilter','sprintFilter']) {
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
  const newest=others[0];
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
  const restored=Object.keys(result.added).length;
  // On a previously opened clean form, prefer not to silently replace even
  // in-memory defaults. The import remains visible after re-select/reload.
  message('Відновлено '+restored+' чернеток. Пропущено конфліктних: '+
    result.skipped.length+'. Перевір кожну та збережи вручну.'); 
  updateRecoveryStatus();
  $('dataMenu').open=false;
  renderList();
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
async function pollChanges() {
  if (pollingInFlight || busy || document.visibilityState === 'hidden') return;
  pollingInFlight = true;
  try {
    const revision = await api('/api/tasks/revision');
    if (needsFullTaskRefresh(currentRevision, currentRevisionError, revision)) await load();
    pollCycle++;
    if (pollCycle % 3 === 0) await loadLogs();
    if (pollCycle % 6 === 0) {
      await loadDeltaStrip();
      await loadCloudCapabilities();
    }
  } catch (error) {
    message('Локальний сервер недоступний: ' + error.message, true);
  } finally {
    pollingInFlight = false;
  }
}
setInterval(pollChanges, 5000);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') pollChanges();
  else rememberViewContext();
});

function rankedTasks() { return queueModel.rankedTasks(tasks); }
function visibleTasks() {
  return queueModel.visibleTasks(tasks, {
    search:$('search').value.trim().toLocaleLowerCase('uk-UA'),
    filter:$('filter').value, signal:$('signalFilter').value, sprint:$('sprintFilter').value
  });
}
