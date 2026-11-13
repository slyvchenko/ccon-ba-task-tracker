/* Human-owned decision register. No Jira edits, no automatic approvals. */
export function decisionsMarkup(data, escape) {
  const entries = (data.decisions || []).slice(-75).reverse();
  const states = {PROPOSED:'Пропозиція',CONFIRMED:'Підтверджено аналітиком',
    SUPERSEDED:'Замінено',DISPUTED:'Оскаржено'};
  const tones = {PROPOSED:'tone-amber',CONFIRMED:'tone-green',SUPERSEDED:'tone-gray',DISPUTED:'tone-red'};
  const link = d => d.sourceUrl ? ' <a href="' + escape(d.sourceUrl) + '" rel="noopener noreferrer" target="_blank">джерело ↗</a>' : '';
  const line = d => '<li class="decision-line"><span class="badge ' + (tones[d.status] || 'tone-gray') + '">' +
    escape(states[d.status] || d.status) + '</span><span>' + escape(d.text) +
    (d.impact ? ' <span class="muted">· Вплив на задачу: ' + escape(d.impact) + '</span>' : '') + link(d) + '</span></li>';
  const current = entries.filter(d => d.status !== 'SUPERSEDED');
  const replaced = entries.filter(d => d.status === 'SUPERSEDED');
  const confirmed = current.filter(d => d.status === 'CONFIRMED').length;
  const status = current.length
    ? '<p class="focus-status"><span class="badge ' + (confirmed === current.length ? 'tone-green' : 'tone-amber') + '">' +
      escape(confirmed) + ' з ' + escape(current.length) + ' підтверджено</span> ' +
      (confirmed === current.length ? 'Усі рішення підтверджені' : 'Пропозиції AI чекають на твоє рішення') + '</p>'
    : '';
  const compact = current.length
    ? status + '<ul class="decision-list">' + current.map(line).join('') + '</ul>'
    : '<p class="focus-status"><span class="badge tone-gray">Немає</span> Історія рішень поки порожня.</p>';
  return compact +
    '<details class="decision-manage"><summary>Керувати рішеннями та історія</summary>' +
    '<p class="muted">AI може лише запропонувати рішення. Підтвердження, оскарження і заміна виконуються тільки вручну. ' +
    'Зміни не переписують Jira та готовий опис.</p>' +
    (replaced.length ? '<div class="section-label">Замінені рішення</div><ul class="decision-list">' +
      replaced.map(d => line(d).replace('</li>', (d.supersededBy ? ' <span class="muted">→ ' + escape(d.supersededBy) + '</span>' : '') + '</li>')).join('') + '</ul>' : '') +
    (entries.length ? '<div class="section-label">ID рішень</div><p class="muted">' + entries.map(d => escape(d.id) + ' — ' + escape(states[d.status] || d.status)).join('<br>') + '</p>' : '') +
    '<div class="question-record">' +
    '<label>Дія<select id="decisionAction"><option value="propose">Нова пропозиція</option>' +
    '<option value="confirm">Підтвердити пропозицію</option>' +
    '<option value="dispute">Оскаржити рішення</option><option value="supersede">Замінити рішення</option></select></label>' +
    '<label>ID рішення (для confirm/dispute/supersede)<input id="decisionId" maxlength="16" placeholder="D-..."></label>' +
    '<label>Нове рішення / текст<input id="decisionText" maxlength="1500" placeholder="Для propose/supersede"></label>' +
    '<label>URL підтвердження / контексту<input id="decisionSource" maxlength="2000"></label>' +
    '<label>Вплив на опис / QA<input id="decisionImpact" maxlength="1500"></label>' +
    '<label>Причина зміни<input id="decisionReason" maxlength="1000"></label>' +
    '<button id="saveDecision" class="quiet">Зберегти вручну</button></div>' +
    '<details><summary>Журнал подій (' + escape((data.events || []).length) + ')</summary><ol>' +
    (data.events || []).slice(-40).reverse().map(e =>
       '<li>' + escape(e.at) + ' · ' + escape(e.id) + ': ' +
        escape(e.from || 'NEW') + ' → ' + escape(e.to) +
        ' (' + escape(e.actor) + '), ' + escape(e.reason) + '</li>').join('') +
    '</ol></details></details>';
}
export async function loadTaskDecisions(key, api, escape, notify, current, getActiveScope=()=>current) {
  const node = document.getElementById('decisionTracker');
  if (!node) return;
  try {
    const data = await api('/api/decisions/' + encodeURIComponent(key));
    if (current() !== key) return;
    node.innerHTML = decisionsMarkup(data, escape);
    const button = node.querySelector('#saveDecision');
    button?.addEventListener('click', async () => {
      const value = id => node.querySelector(id).value;
      button.disabled = true;
      try {
        await api('/api/decisions/' + encodeURIComponent(key), {
          action: value('#decisionAction'), id: value('#decisionId'),
          text: value('#decisionText'), sourceUrl: value('#decisionSource'),
          impact: value('#decisionImpact'), reason: value('#decisionReason')
        });
        notify('Рішення додано в локальну історію. Jira не змінена.');
        const live = getActiveScope();
        if (live() === key) loadTaskDecisions(key, api, escape, notify, live, getActiveScope);
      } catch (error) {
        notify('Рішення не збережено: ' + error.message, true);
        button.disabled = false;
      }
    });
  } catch (error) {
    if (current() === key) node.innerHTML = '<p class="focus-status"><span class="badge tone-red">Помилка</span> Рішення недоступні: ' + escape(error.message) + '</p>';
  }
}
