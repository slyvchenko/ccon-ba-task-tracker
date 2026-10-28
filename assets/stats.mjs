/* One-page local-only statistics. Never render Jira strings or send telemetry. */
export const RELEASE_CATEGORIES = {
  IMPLEMENTED: 'Реалізовано (код)',
  PARTIAL: 'Частково',
  GATE: 'Очікує приймання',
  DEFERRED: 'Відкладено',
  PLANNED: 'Заплановано',
  NEXT: 'Наступне'
};
export const TASK_CATEGORIES = {
  WRITE: 'Написати листа',
  READY: 'Готові до дії',
  DECIDE: 'Потрібне рішення',
  REVIEW: 'Перевірити',
  WAIT: 'Очікуємо',
  OTHER: 'Без класифікації'
};
export const MANUAL_CATEGORIES = {
  AUTO: 'Без ручного статусу',
  'IN PROGRESS': 'У роботі',
  'WAITING INPUT': 'Очікуємо дані',
  'WAITING DEPENDENCY': 'Очікуємо залежність',
  'NEEDS DECISION': 'Потрібне рішення',
  DONE: 'Локально завершено'
};

export function safeCount(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : 0;
}

export function dashboardBuckets(counts, labels, {includeEmpty = true} = {}) {
  // An explicit vocabulary prevents untrusted keys becoming text or HTML.
  return Object.entries(labels).filter(([key]) =>
    includeEmpty || safeCount(counts?.[key]) > 0
  ).map(([key, label]) => ({key, label, count: safeCount(counts?.[key])}));
}

const el = id => document.getElementById(id);
const number = n => safeCount(n).toLocaleString('uk-UA');

function metric(id, value, available = true) {
  el(id).textContent = available ? number(value) : '—';
}

function renderBars(id, counts, labels, {includeEmpty = true} = {}) {
  const root = el(id);
  const rows = dashboardBuckets(counts, labels, {includeEmpty});
  const total = rows.reduce((sum, item) => sum + item.count, 0);
  if (!rows.length) {
    const empty = document.createElement('p');
    empty.className = 'placeholder';
    empty.textContent = 'Поки немає задач цієї категорії.';
    root.replaceChildren(empty);
    return;
  }
  const elements = rows.map(({key, label, count}) => {
    const row = document.createElement('div');
    row.className = 'bar';
    row.dataset.kind = key;
    const caption = document.createElement('span');
    caption.className = 'bar-label';
    caption.title = label;
    caption.textContent = label;
    const bar = document.createElement('progress');
    bar.max = Math.max(1, total);
    bar.value = count;
    bar.setAttribute('aria-label', label + ': ' + count + ' з ' + total);
    const value = document.createElement('span');
    value.className = 'bar-value';
    value.textContent = number(count);
    row.append(caption, bar, value);
    return row;
  });
  root.replaceChildren(...elements);
}

function render(data) {
  if (!data || data.schemaVersion !== 1 ||
      data.privacy !== 'AGGREGATE_ONLY_NO_ISSUE_CONTENT' ||
      !data.tasks || !data.project) throw Error('Unexpected statistics format');
  const task = data.tasks, project = data.project;
  const present = task.snapshotAvailable === true;
  metric('taskActive', task.active, present);
  metric('taskOpen', task.unfinished, present);
  metric('taskDone', task.done, present);
  metric('taskSprint', task.activeVerifiedSprint, present);
  if (present) {
    renderBars('taskSignals', task.signalCounts, TASK_CATEGORIES, {includeEmpty:false});
    renderBars('manualStatuses', task.manualStatusCounts, MANUAL_CATEGORIES, {includeEmpty:false});
  } else {
    for (const id of ['taskSignals', 'manualStatuses']) {
      const p = document.createElement('p');
      p.className = 'placeholder';
      p.textContent = 'Імпортуйте snapshot, щоб побачити статистику задач.';
      el(id).replaceChildren(p);
    }
  }
  const note = present ?
    'Всього в базі: ' + number(task.loaded) + ' · Архів: ' + number(task.archived) +
    ' · Без аналізу: ' + number(task.withoutAnalysis) +
    ' · Застарілий аналіз: ' + number(task.staleAnalysis) +
    '. WAIT і ручні статуси можуть перетинатися з іншими показниками.' :
    'Snapshot відсутній. Нулі не видаються за статистику роботи.';
  el('taskFootnote').textContent = note;
  if (present && task.snapshotGeneratedAt) {
    const d = new Date(task.snapshotGeneratedAt);
    el('snapshotAge').textContent = Number.isFinite(d.getTime()) ?
      'Джерело задач: ' + d.toLocaleString('uk-UA') : 'Дата snapshot недоступна';
  } else {
    el('snapshotAge').textContent = '';
  }

  metric('requirements', project.requirements);
  metric('implemented', project.reportedStatuses?.IMPLEMENTED);
  el('pointers').textContent = number(project.codeAndTestPointers) +
    '/' + number(project.requirements);
  el('goldProgress').textContent = number(project.goldCasesVerifiedHere) +
    '/' + number(project.goldCaseTarget);
  renderBars('backlogBars', project.reportedStatuses, RELEASE_CATEGORIES);
  renderBars('p0Bars', project.p0ReportedStatuses, RELEASE_CATEGORIES);
  el('releaseState').textContent = project.releaseApproved === false ?
    'BLOCKED · незалежний UAT' : 'Перевірити рішення вручну';
}

async function refresh() {
  const button = el('refresh');
  button.disabled = true;
  el('loadState').textContent = 'Оновлення локальної статистики…';
  try {
    const response = await fetch('/api/stats', {cache:'no-store', credentials:'same-origin'});
    if (!response.ok) throw Error('Statistics unavailable');
    render(await response.json());
    el('loadState').textContent = 'Оновлено локально · ' +
      new Date().toLocaleTimeString('uk-UA', {hour:'2-digit',minute:'2-digit'});
  } catch {
    el('loadState').textContent =
      'Не вдалося завантажити статистику. Перевірте, чи запущений CCON BA Desk.';
  } finally {
    button.disabled = false;
  }
}

if (typeof document !== 'undefined') {
  el('refresh')?.addEventListener('click', refresh);
  refresh();
}
