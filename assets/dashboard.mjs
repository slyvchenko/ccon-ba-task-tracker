import {STATUS_LABELS, defaultRecipients, analysisOf, analysisIsStale, hasAnalysis, effectiveSignal, signalInfo, statusTone, queueTier, priorityLane, rankTasks, filterTasks} from './task-rules.mjs';
import {createLogsController} from './logs.mjs';
import {setTaskMode, loadTaskEvidence, loadTaskQuestions} from './evidence-ui.mjs';


const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const LOCAL_EDITS_KEY = 'ccon-ba-desk.unsaved-forms.v2';
let tasks = [], selected = null, latest = null, busy = false, browserRecoveryAvailable = true, loadRequest = 0, cloudMode = false;
let taskMode = 'quick';
let signature = '', renderedTaskVersion = '', pendingDetail = false;
const forms = new Map();
const expandedEmails = new Set();
const recoveredForms = readRecoveredForms();
const {loadLogs} = createLogsController({api, escapeHtml, message, getSelected: () => selected});

function readRecoveredForms() {
  try { const data = JSON.parse(localStorage.getItem(LOCAL_EDITS_KEY) || '{}'); return data && typeof data === 'object' ? data : {}; }
  catch { return {}; }
}
function normalizedDraft(value) {
  return {to:typeof value?.to === 'string' ? value.to : '', subject:typeof value?.subject === 'string' ? value.subject : '', body:typeof value?.body === 'string' ? value.body : ''};
}
function savedForm(task) {
  const emailDraft = normalizedDraft(task.savedEmailDraft ?? task.analysis?.emailDraft);
  if (task.savedEmailDraft == null || !emailDraft.to.trim()) emailDraft.to = defaultRecipients(task);
  return {manualStatus:STATUS_LABELS[task.manualStatus] ? task.manualStatus : 'AUTO', note:task.note || '', emailDraft};
}
function formFor(task) {
  if (!forms.has(task.key)) {
    const base = savedForm(task), recovered = recoveredForms[task.key];
    const value = recovered && STATUS_LABELS[recovered.manualStatus] && typeof recovered.note === 'string'
      ? {manualStatus:recovered.manualStatus, note:recovered.note, emailDraft:normalizedDraft(recovered.emailDraft)} : base;
    forms.set(task.key, {value, base:JSON.stringify(base), changedAt:recovered?.changedAt || null});
    delete recoveredForms[task.key];
  }
  return forms.get(task.key);
}
function isDirty(key) { const form = forms.get(key); return !!form && JSON.stringify(form.value) !== form.base; }
function hasUnsaved() { return [...forms.keys()].some(isDirty) || Object.keys(recoveredForms).length > 0; }
function rememberEdits() {
  const data = {...recoveredForms};
  forms.forEach((form, key) => { if (isDirty(key)) data[key] = {...form.value, changedAt:form.changedAt}; });
  try { if (Object.keys(data).length) localStorage.setItem(LOCAL_EDITS_KEY, JSON.stringify(data)); else localStorage.removeItem(LOCAL_EDITS_KEY); }
  catch { browserRecoveryAvailable = false; }
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
  if (!response.ok) throw Error(result.error || 'Не вдалося виконати дію.');
  return result;
}
function signalBadge(task) {
  const info = signalInfo(task), manual = task.manualStatus && task.manualStatus !== 'AUTO';
  const label = manual ? STATUS_LABELS[task.manualStatus] : hasAnalysis(task) ? info.label : analysisIsStale(task) ? 'Аналіз потребує оновлення' : 'Ще без нового аналізу';
  return `<span class="badge tone-${info.tone}"><span class="dot" aria-hidden="true"></span>${escapeHtml(label)}</span>`;
}
function renderList() {
  updateSnapshotInfo();
  const items = visibleTasks(), current = tasks.filter(task => task.active), analyzed = current.filter(hasAnalysis).length;
  const mailCount = tasks.filter(task => task.active && effectiveSignal(task) === 'WRITE').length;
  $('bulkEmail').textContent = `Відкрити всі листи (${mailCount})`;
  $('bulkEmail').disabled = !mailCount || busy;
  $('bulkEmail').hidden = cloudMode;
  const verified = current.filter(task => task.activeSprintStatus === 'VERIFIED').length;
  const sprintCount = current.filter(task => task.activeSprintStatus === 'VERIFIED' && task.activeSprint).length;
  $('count').textContent = `${items.length} у списку · ${sprintCount} активний спринт · ${current.length} поточних · аналіз ${analyzed}/${current.length}` +
    (verified < current.length ? ' · спринт ще не підтверджено' : '');
  let previousGroup = '';
  $('list').innerHTML = items.map((task, index) => {
    const scope = ['Активний спринт · головна черга', 'Поза активним спринтом / не підтверджено', 'Завершені', 'Архів'][priorityLane(task)];
    const group = scope + ' · ' + ['Можна просувати зараз', 'Очікуємо', 'Завершені', 'Відсутні в останньому snapshot'][queueTier(task)];
    const heading = group !== previousGroup ? `<div class="queue-group">${escapeHtml(group)}</div>` : '';
    previousGroup = group;
    return `${heading}<button class="row ${task.key === selected ? 'selected' : ''}" data-key="${escapeHtml(task.key)}" aria-pressed="${task.key === selected}"><span class="row-number" aria-label="Позиція ${index + 1}">${index + 1}</span><span class="row-content"><span class="row-head"><span class="rank">${escapeHtml(task.key)}</span><span>${isDirty(task.key) ? '<span class="edit-dot" title="Є незбережені зміни">● </span>' : ''}</span></span><span class="row-title" title="${escapeHtml(task.summary)}">${escapeHtml(task.summary)}</span><span class="row-statuses">${task.activeSprintStatus === "VERIFIED" && task.activeSprint === true ? '<span class="badge tone-blue">Спринт</span>' : ''}${signalBadge(task)}${task.blocking ? '<span class="badge tone-red">Блокує інших</span>' : ''}</span></span></button>`;
  }).join('') || '<div class="empty">Немає задач за цими фільтрами.</div>';
  $('list').querySelectorAll('[data-key]').forEach(button => button.addEventListener('click', () => selectTask(button.dataset.key)));
}
function selectTask(key) {
  if (busy || selected === key) return;
  selected = key;
  pendingDetail = false;
  renderList();
  renderDetail();
  $('detail').scrollTop = 0;
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
function renderDetail() {
  const task = tasks.find(item => item.key === selected);
  if (!task) {
    $('detail').innerHTML = tasks.length ? '<div class="empty"><h2>Оберіть задачу з черги</h2>Зміни фільтр, щоб побачити інші задачі.</div>' : '<div class="empty"><h2>Почни зі snapshot</h2>Збережи <b>CCON_BA_Snapshot.json</b> у папку <b>inbox</b> поруч із застосунком.<br>Дані імпортуються автоматично. Ручні статуси, нотатки та збережені чернетки залишаються між днями.</div>';
    renderedTaskVersion = '';
    return;
  }
  const analyzed = hasAnalysis(task), stale = analysisIsStale(task), analysis = analyzed ? analysisOf(task) : {};
  const form = formFor(task).value, info = signalInfo(task), url = safeUrl(task.url);
  const savedDraft = task.savedEmailDraft !== null && task.savedEmailDraft !== undefined;
  const staleGeneratedDraft = stale && !savedDraft && !!analysisOf(task).emailDraft?.body;
  const manualWaiting = ['WAITING INPUT','WAITING DEPENDENCY'].includes(task.manualStatus);
  const waiting = task.manualStatus !== 'AUTO' ? manualWaiting : analysis.waitingRequired, email = manualWaiting || task.manualStatus === 'DONE' ? false : analysis.needsEmail;
  const missing = Array.isArray(analysis.missingInfo) ? analysis.missingInfo : [];
  $('detail').innerHTML = `
    <div class="task-top task-toolbar"><span class="task-key">${escapeHtml(task.key)}${url ? ` <a class="jira-button" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Відкрити Jira ↗</a>` : ''}</span><span class="badge tone-${info.tone}"><span class="dot" aria-hidden="true"></span>${escapeHtml(analyzed || task.manualStatus !== 'AUTO' ? info.label : 'Потрібен аналіз')}</span><span class="muted task-date">${task.importedAt ? 'Дані: ' + dateLabel(task.importedAt) : ''}</span></div>
    <h2>${escapeHtml(task.summary)}</h2>
    <div class="focus-mode-switch"><button class="mode-button" data-mode="quick">Швидко</button><button class="mode-button" data-mode="deep">Глибокий аналіз</button><button class="mode-button" data-mode="email">Лист</button></div>
    <div class="task-badges signal-strip task-meta" aria-label="Статус Jira, листування та очікування"><span class="badge">Jira: ${escapeHtml(task.jiraStatus || 'Не вказано')}</span>${task.activeSprintStatus === "VERIFIED" ? `<span class="badge ${task.activeSprint ? 'tone-blue' : 'tone-gray'}">${escapeHtml(task.activeSprint ? 'Активний спринт: ' + (task.activeSprintNames || []).join(', ') : 'Поза активним спринтом')}</span>` : '<span class="badge tone-amber">Активний спринт не підтверджено</span>'}${task.blocking ? '<span class="badge tone-red">Блокує інших</span>' : ''}${!task.active ? '<span class="badge tone-gray">Відсутня в останньому snapshot · стан збережений</span>' : ''}
      ${effectiveSignal(task) === 'WRITE' && email === true ? '' : `<span class="signal-text text-${email === true ? 'blue' : email === false ? 'green' : 'gray'}">${email === true ? 'Потрібен лист' : email === false ? 'Лист не потрібен' : 'Потребу в листі не визначено'}</span>`}
      <span class="signal-text text-${waiting === true ? 'red' : waiting === false ? 'green' : 'gray'}">${escapeHtml(waiting === true ? manualWaiting ? 'Очікуємо за моїм статусом' : 'Очікуємо: ' + (analysis.waitingOnUk || 'адресат не вказаний') : waiting === false ? 'Не очікуємо' : 'Очікування не визначено')}</span>
    </div>
    <div id="staleNotice" class="saved-note" hidden></div>
    ${stale ? '<div class="analysis-missing"><b>Контекст Jira змінився — попередній аналіз застарів.</b><br>Черга й сигнали потребують нового аналізу опису, коментарів та залежностей. Твій ручний стан і збережена чернетка залишаються чинними.</div>' : !analyzed ? '<div class="analysis-missing"><b>Для цієї задачі ще немає повного аналізу українською.</b><br>Потрібно прочитати опис, коментарі й залежності. Попередній snapshot не дає достатніх підстав для нової оцінки.</div>' : ''}
    ${briefingMarkup(analyzed ? analysis.briefing : undefined, stale)}
    <div class="detail-grid">
      <div>
        <section class="panel analysis-lead" aria-label="Пояснення та наступна дія">
          <div class="section-label">Чому така оцінка</div>
          <p class="pre assessment-reason">${escapeHtml(analysis.reasonUk || (stale ? 'Попередні висновки не підтверджені новим контекстом. Потрібен повторний аналіз.' : 'Щоденний аналіз ще не підготовлений.'))}</p>
          ${priorityBreakdown(analysis)}
          <div class="section-label">Наступна дія</div>
          <p class="pre next-action" id="nextText">${escapeHtml(analysis.nextActionUk || (stale ? 'Онови аналіз за останнім описом, коментарями й залежностями, перш ніж діяти за старою рекомендацією.' : 'Спочатку перевір контекст задачі та визнач конкретну дію.'))}</p>
          ${analysis.nextActionUk ? '<button id="copyNext" class="quiet">Скопіювати дію</button>' : ''}
        </section>
        <section class="panel" aria-label="Відсутні дані та підстави оцінки">
          <div class="section-label">Відкриті питання BA</div>
          <details class="description"><summary>Питання та підтверджені відповіді</summary><div id="questionTracker" class="question-tracker muted">Завантажую…</div></details>
          ${missing.length ? '<ol class="missing-info">' + missing.map(item => '<li>' + escapeHtml(item) + '</li>').join('') + '</ol>' : `<p class="muted">${analyzed ? 'Аналіз не виявив додаткових питань. Перевір пояснення та джерела нижче.' : 'Поки не визначено — потрібен аналіз контексту.'}</p>`}
          <div class="section-label">REST / Supplier / Errors</div><div id="evidenceSummary" class="muted">Завантажую докази…</div>
          <div class="section-label">На чому ґрунтується оцінка</div>
          ${sourceMarkup(analysis)}
          <details class="description" open><summary>Готовий опис задачі · коротко й точно</summary><p class="pre">${escapeHtml(analysis.standardDescription || 'Чернетку не підготовлено. Перевір причину в поясненні аналізу.')}</p>${analysis.standardDescription ? '<button id="copyDescription" class="quiet">Скопіювати опис</button>' : ''}</details>
          ${previousAnalysisMarkup(task)}
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
          <label for="note">Мої нотатки</label><textarea id="note" maxlength="20000" placeholder="Додай домовленість або наступний контакт…">${escapeHtml(form.note)}</textarea>
          <div class="actions state-actions"><span id="savedIndicator" role="status">✓ Збережено</span><button id="save">Зберегти все</button><button id="done" class="primary">Готово → Далі</button><button id="discard" class="quiet" title="Скинути незбережене">Скинути</button></div>
          <div id="saved" class="save-state" role="status"></div>
        </section>
        <details id="emailDetails" class="panel email-panel ${email === true || form.emailDraft.body ? 'email-first' : ''}" open>
          <summary class="email-summary"><span>${email === false && !form.emailDraft.body && !form.emailDraft.subject ? 'Готова чернетка на випадок потреби' : 'Готовий лист'}</span><span class="email-toggle">Підготувати лист</span></summary>
          <div class="email-fields" role="region" aria-label="Редагована чернетка листа">
          <div class="panel-title email-meta"><span class="badge ${staleGeneratedDraft ? 'tone-amber' : email === true ? 'tone-blue' : 'tone-gray'}">${staleGeneratedDraft ? 'Зі старого аналізу' : savedDraft && stale ? 'Моя збережена чернетка' : email === true ? 'Потрібна' : email === false ? 'За потреби' : 'Потребу ще не визначено'}</span></div>
          <p class="email-intro">${stale && form.emailDraft.body ? savedDraft ? 'Твоя збережена чернетка залишилася без змін. Аналіз застарів: перевір лист за новим контекстом перед використанням.' : 'Новий контекст ще не проаналізовано. Ця чернетка збережена зі старого аналізу або твоїх незбережених правок; перевір її актуальність перед використанням.' : form.emailDraft.body ? 'Перевір адресата й текст. Усі поля можна відредагувати.' : email === false && analyzed ? 'За поточним аналізом лист зараз не потрібен. За потреби можеш підготувати власну чернетку.' : email === true ? 'Потрібен лист, але готової чернетки ще немає. Підготуй текст за конкретними відкритими питаннями задачі.' : 'Потребу в листі ще не визначено. Спочатку перевір контекст і наступну дію.'}</p>
          <label for="draftTo">Кому</label><input id="draftTo" maxlength="2000" autocomplete="off" placeholder="Email адресата, якщо він відомий" value="${escapeHtml(form.emailDraft.to)}">
          <label for="draftSubject">Тема</label><input id="draftSubject" maxlength="2000" placeholder="Тема листа" value="${escapeHtml(form.emailDraft.subject)}">
          <label for="draftBody">Текст листа</label><textarea id="draftBody" maxlength="50000" placeholder="Чернетка за описом, коментарями та відкритими питаннями задачі…">${escapeHtml(form.emailDraft.body)}</textarea>
          <section id="emailLogs" class="email-logs" aria-label="Логи до листа"><div class="logs-heading"><h4>Логи до листа</h4></div><p class="muted" role="status">Перевіряю архіви задачі…</p></section>
          <div class="actions"><button id="email" class="primary">Відкрити в пошті ↗</button></div>
          </div>
        </details>
      </div>
    </div>`;
  renderedTaskVersion = taskVersion(task);
  pendingDetail = false;
  ['note', 'draftTo', 'draftSubject', 'draftBody'].forEach(id => $(id).addEventListener('input', captureForm));
  $('manual').addEventListener('change', () => saveStatus($('manual').value));
  if ($('copyNext')) $('copyNext').addEventListener('click', () => copyText(analysis.nextActionUk, 'Наступну дію скопійовано.'));
  if ($('copyDescription')) $('copyDescription').addEventListener('click', () => copyText(analysis.standardDescription, 'Чернетку опису скопійовано.'));
  $('save').addEventListener('click', () => saveTask(false));
  $('done').addEventListener('click', () => saveTask(true));
  $('discard').addEventListener('click', discardForm);
  $('email').addEventListener('click', openEmail);
  if (cloudMode) $('email').textContent = 'Зберегти й скопіювати лист';
  $('emailDetails').addEventListener('toggle', () => { if ($('emailDetails').open) expandedEmails.add(task.key); else expandedEmails.delete(task.key); });
  $('loadContext').addEventListener('click', () => loadContext(task.key));
  updateFormStatus();
  setTaskMode($('detail'), taskMode);
  $('detail').querySelectorAll('.mode-button').forEach(button => button.addEventListener('click', () => {
    taskMode = button.dataset.mode;
    setTaskMode($('detail'), taskMode);
  }));
  loadTaskEvidence(task.key, api, escapeHtml, () => selected);
  loadTaskQuestions(task.key, api, escapeHtml, message, () => selected);
  loadLogs(task.key);
}
function captureForm() {
  const task = tasks.find(item => item.key === selected);
  if (!task) return;
  const form = formFor(task);
  form.value = {manualStatus:$('manual').value, note:$('note').value, emailDraft:{to:$('draftTo').value, subject:$('draftSubject').value, body:$('draftBody').value}};
  form.changedAt = new Date().toISOString();
  $('manual').className = 'status-select tone-' + statusTone(form.value.manualStatus, task);
  rememberEdits();
  updateFormStatus();
  renderList();
}
function updateFormStatus() {
  const task = tasks.find(item => item.key === selected);
  if (!task || !$('saved')) return;
  const dirty = isDirty(task.key);
  $('saved').textContent = '';
  $('saved').hidden = true;
  $('savedIndicator').hidden = dirty;
  $('save').hidden = !dirty;
  $('save').disabled = !dirty || busy;
  $('saved').classList.toggle('unsaved', dirty);
  $('discard').hidden = !dirty;
  $('discard').disabled = !dirty || busy;
  if ($('staleNotice')) {
    $('staleNotice').hidden = !pendingDetail;
    $('staleNotice').textContent = 'Надійшли нові дані. Поточний текст залишається у формі; новий аналіз з’явиться після збереження правок. Якщо правок немає, достатньо вийти з поля.';
  }
}
function discardForm() {
  if (busy || !isDirty(selected)) return;
  if (!confirm('Скинути незбережені зміни статусу, нотаток і чернетки цієї задачі?')) return;
  forms.delete(selected);
  delete recoveredForms[selected];
  rememberEdits();
  renderList();
  renderDetail();
}
function setBusy(value) {
  busy = value;
  ['manual', 'note', 'draftTo', 'draftSubject', 'draftBody', 'save', 'done', 'email', 'discard'].forEach(id => { if ($(id)) $(id).disabled = value; });
  $('import').disabled = value;
  if (!value) updateFormStatus();
}
async function saveStatus(status) {
  if (busy || !STATUS_LABELS[status]) return;
  const task = tasks.find(item => item.key === selected);
  if (!task || task.manualStatus === status) return;
  captureForm();
  const scroll = $('detail').scrollTop;
  setBusy(true);
  try {
    // Only persist the status; keep typed note/draft buffers separate.
    await api('/api/tasks/' + encodeURIComponent(task.key), {manualStatus:status, note:task.note || ''});
    task.manualStatus = status;
    task.modifiedAt = new Date().toISOString();
    const form = formFor(task);
    form.value.manualStatus = status;
    form.base = JSON.stringify(savedForm(task));
    rememberEdits();
    signature = '';
    renderList();
    renderDetail();
    $('detail').scrollTop = scroll;
    $('manual')?.focus({preventScroll:true});
    message('Мій статус збережено автоматично.');
  } catch (error) { message(error.message, true); }
  finally { setBusy(false); }
}
async function saveTask(done = false) {
  if (busy) return false;
  const task = tasks.find(item => item.key === selected);
  if (!task) return false;
  captureForm();
  const value = structuredClone(formFor(task).value);
  if (done) value.manualStatus = 'DONE';
  setBusy(true);
  try {
    await api('/api/tasks/' + encodeURIComponent(task.key), value);
    Object.assign(task, {manualStatus:value.manualStatus, note:value.note, savedEmailDraft:value.emailDraft, modifiedAt:new Date().toISOString()});
    forms.delete(task.key);
    delete recoveredForms[task.key];
    rememberEdits();
    signature = '';
    if (done) selected = visibleTasks().find(item => item.key !== task.key)?.key || null;
    renderList();
    renderDetail();
    message(cloudMode ? 'Статус, нотатки та чернетку збережено у приватній базі.' : 'Статус, нотатки та чернетку збережено в локальній базі.');
    return true;
  } catch (error) {
    message(error.message, true);
    return false;
  } finally { setBusy(false); }
}
async function copyText(text, notice) {
  try { await navigator.clipboard.writeText(text); message(notice); }
  catch { message('Копіювання недоступне. Виділи видимий текст і скопіюй вручну.', true); }
}
let bulkItems = [];
let bulkPreviewRequest = 0;
async function previewBulkEmails() {
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
function editorFocused() { return ['manual', 'note', 'draftTo', 'draftSubject', 'draftBody'].includes(document.activeElement?.id); }
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
    if (changed) {
      tasks = data.tasks;
      signature = nextSignature;
      // A new snapshot must never overwrite a typed note or email draft.
      forms.forEach((form, key) => { if (!isDirty(key)) forms.delete(key); });
      if (!selected || !tasks.some(task => task.key === selected)) selected = visibleTasks()[0]?.key || null;
      renderList();
      updateSnapshotInfo();
    }
    const selectedTask = tasks.find(task => task.key === selected);
    const detailChanged = selectedTask ? taskVersion(selectedTask) !== renderedTaskVersion : renderedTaskVersion !== '';
    if (detailChanged || pendingDetail || !$('detail').hasChildNodes()) {
      if (isDirty(selected) || editorFocused()) { pendingDetail = true; updateFormStatus(); }
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
  renderList();
  if (!visibleTasks().some(task => task.key === selected)) {
    selected = visibleTasks()[0]?.key || null;
    renderList();
    renderDetail();
  }
}
document.addEventListener('click', event => { if (!$('dataMenu').contains(event.target)) $('dataMenu').open = false; });
document.addEventListener('keydown', event => { if (event.key === 'Escape') { $('dataMenu').open = false; document.querySelectorAll('.status-help[open]').forEach(help => help.open = false); } });
$('search').addEventListener('input', applyFilters);
$('filter').addEventListener('change', applyFilters);
$('signalFilter').addEventListener('change', applyFilters);
$('sprintFilter').addEventListener('change', applyFilters);
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
window.addEventListener('beforeunload', event => { if (hasUnsaved()) { event.preventDefault(); event.returnValue = ''; } });
let lastCloudAttemptState = null;
async function loadCloudCapabilities() {
  try {
    const health = await api('/api/health');
    cloudMode = health.cloud === true;
    if (cloudMode) {
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
setInterval(() => { load(); loadLogs(); loadDeltaStrip(); loadCloudCapabilities(); }, 5000);

function rankedTasks() { return rankTasks(tasks); }
function visibleTasks() {
  return filterTasks(rankedTasks(), {search: $('search').value.trim().toLocaleLowerCase('uk-UA'), filter: $('filter').value, signal: $('signalFilter').value, sprint: $('sprintFilter').value});
}
