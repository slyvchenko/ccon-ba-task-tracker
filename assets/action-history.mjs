/* Two collapsed panels in the EXISTING task detail. No extra view/modes. */
const STATES = ['OPEN', 'WAITING', 'DONE'];
const LABELS = {OPEN:'Відкрита',WAITING:'Очікуємо',DONE:'Виконана'};

export function actionPlanMarkup(data, escape, suggestion='') {
  const items = (data?.actions || []).slice(0, 40);
  const newText = escape(suggestion || '');
  const rows = items.map(item => {
    const options = STATES.map(x => '<option value="' + x + '"' +
      (x === item.status ? ' selected' : '') + '>' + LABELS[x] + '</option>').join('');
    const due = item.overdue ? ' · Прострочено' : item.dueToday ? ' · На сьогодні' : '';
    return '<section class="question-record action-item" data-action="' + escape(item.id) + '">' +
      '<b>' + escape(item.description) + '</b><span class="muted">' +
      escape(LABELS[item.status] || item.status) + due + '</span>' +
      '<label>Опис<input class="action-text" maxlength="2000" value="' + escape(item.description) + '"></label>' +
      '<label>Виконавець<input class="action-owner" maxlength="160" value="' + escape(item.owner || '') + '"></label>' +
      '<label>Хто блокує<input class="action-wait" maxlength="160" value="' + escape(item.waitingOn || '') + '"></label>' +
      '<label>Дедлайн<input class="action-due" type="date" value="' + escape(item.dueDate || '') + '"></label>' +
      '<label>Перевірити знову<input class="action-review" type="date" value="' + escape(item.nextReviewDate || '') + '"></label>' +
      '<label>Стан<select class="action-status">' + options + '</select></label>' +
      '<button class="save-action quiet">Зберегти дію</button></section>';
  }).join('');
  return '<p class="muted">' + items.length + ' дій · прострочених ' +
    escape(data?.overdueCount || 0) + '. AI-пропозиція не стає задачею автоматично.</p>' +
    '<div class="question-record action-new">' +
    '<label>Нова дія<input class="action-text" maxlength="2000" value="' + newText + '"></label>' +
    '<label>Виконавець<input class="action-owner" maxlength="160"></label>' +
    '<label>Хто блокує<input class="action-wait" maxlength="160"></label>' +
    '<label>Дедлайн<input class="action-due" type="date"></label>' +
    '<label>Перевірити знову<input class="action-review" type="date"></label>' +
    '<button class="add-action">Додати до плану</button></div>' + rows;
}

function actionPayload(node) {
  return {
    description: node.querySelector('.action-text').value,
    owner: node.querySelector('.action-owner').value,
    waitingOn: node.querySelector('.action-wait').value,
    dueDate: node.querySelector('.action-due').value,
    nextReviewDate: node.querySelector('.action-review').value,
    status: node.querySelector('.action-status')?.value || 'OPEN'
  };
}

export async function loadTaskActions(key, api, escape, notify, current, suggestion='') {
  const target = document.getElementById('actionPlan');
  if (!target) return;
  try {
    const data = await api('/api/actions/' + encodeURIComponent(key));
    if (current() !== key || !document.getElementById('actionPlan')) return;
    target.innerHTML = actionPlanMarkup(data, escape, suggestion);
    for (const button of target.querySelectorAll('.add-action, .save-action')) {
      button.addEventListener('click', async () => {
        const node = button.closest('.question-record');
        const payload = actionPayload(node);
        if (button.classList.contains('save-action')) {
          payload.action = 'update';
          payload.id = node.dataset.action;
        } else payload.action = 'add';
        button.disabled = true;
        try {
          await api('/api/actions/' + encodeURIComponent(key), payload);
          notify('Дію збережено локально. Jira не змінено.');
          if (current() === key) loadTaskActions(key, api, escape, notify, current, '');
        } catch (error) {
          notify('Не збережено: ' + error.message, true);
          button.disabled = false;
        }
      });
    }
  } catch (error) {
    if (current() === key && document.getElementById('actionPlan'))
      target.textContent = 'План дій недоступний: ' + error.message;
  }
}

export function taskHistoryMarkup(data, escape) {
  const entries = (data?.revisions || []).slice(0, 40).map(revision => {
    const state = revision.state || {};
    const changed = (revision.changed || []).join(', ');
    const content = [
      ['Jira', state.jiraStatus], ['BA-сигнал', state.signal],
      ['Ручний статус', state.manualStatus],
      ['Наступна дія', state.nextActionUk],
      ['Опис Jira', state.standardDescription],
      ['Нотатка', state.note], ['Збережений лист', state.savedEmailDraft?.body || state.emailBody]
    ].filter(pair => pair[1]).map(([label, value]) =>
      '<p><b>' + escape(label) + ':</b> ' + escape(value) + '</p>').join('');
    return '<details class="description"><summary>' + escape(revision.at) + ' · ' +
      escape(revision.origin === 'MANUAL' ? 'Ручна зміна' : 'Jira/AI імпорт') +
      ' · ' + escape(changed || 'Без змін') + '</summary>' + content + '</details>';
  }).join('');
  return (entries || '<p class="muted">Збережених ревізій ще немає.</p>') +
    (data?.hasMore ? '<button class="history-more quiet">Показати попередні зміни</button>' : '') +
    '<p class="muted">Локальна історія: ' + escape(data?.total || 0) +
    ' ревізій. Дані не надсилаються в Jira.</p>';
}

export async function loadTaskHistory(key, api, escape, current) {
  const target = document.getElementById('taskHistory');
  if (!target) return;
  let offset = 0;
  let total = 0;
  async function page() {
    try {
      const result = await api('/api/history/' + encodeURIComponent(key) + '?limit=20&offset=' + offset);
      if (current() !== key || !document.getElementById('taskHistory')) return;
      const previous = offset ? target.querySelector('.history-records')?.innerHTML || '' : '';
      const fresh = taskHistoryMarkup({...result,hasMore:false}, escape);
      const content = fresh.replace(/<p class="muted">Локальна історія:[\s\S]*?<\/p>$/, '');
      total = result.total;
      offset += (result.revisions || []).length;
      target.innerHTML = '<div class="history-records">' + previous + content + '</div>' +
        (result.hasMore ? '<button class="history-more quiet">Показати попередні зміни</button>' : '') +
        '<p class="muted">Історія: ' + escape(offset) + ' з ' + escape(total) + ' ревізій.</p>';
      target.querySelector('.history-more')?.addEventListener('click', page);
    } catch (error) {
      if (current() === key && document.getElementById('taskHistory'))
        target.textContent = 'Історія недоступна: ' + error.message;
    }
  }
  await page();
}
