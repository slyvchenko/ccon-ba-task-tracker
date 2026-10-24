/* Human-owned decision register. No Jira edits, no automatic approvals. */
export function decisionsMarkup(data, escape) {
  const entries = (data.decisions || []).slice(-75).reverse();
  const states = {PROPOSED:'Пропозиція',CONFIRMED:'Підтверджено аналітиком',
    SUPERSEDED:'Замінено',DISPUTED:'Оскаржено'};
  const list = entries.map(d =>
    '<div class="question-record"><b>' + escape(states[d.status] || d.status) +
      '</b> · ' + escape(d.id) +
      '<p>' + escape(d.text) + '</p>' +
      (d.impact ? '<p><b>Вплив на задачу:</b> ' + escape(d.impact) + '</p>' : '') +
      (d.supersedes ? '<p>Замінює ' + escape(d.supersedes) + '</p>' : '') +
      (d.supersededBy ? '<p>Замінене рішенням ' + escape(d.supersededBy) + '</p>' : '') +
      '<p><a href="' + escape(d.sourceUrl) + '" rel="noopener noreferrer" target="_blank">Джерело / контекст</a>' +
      ' · ' + escape(d.origin || 'HUMAN') + '</p></div>').join('');
  return '<p class="muted">AI може лише запропонувати рішення. Підтвердження, оскарження і заміна виконуються тільки вручну. ' +
    'Посилання на джерело не означає автоматичної перевірки його змісту. ' +
    'Зміни не переписують Jira та готовий опис.</p>' +
    (list || '<p>Історія рішень поки порожня.</p>') +
    '<div class="question-record"><div class="section-label">Керування рішенням</div>' +
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
    '</ol></details>';
}
export async function loadTaskDecisions(key, api, escape, notify, current) {
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
        if (current() === key) loadTaskDecisions(key, api, escape, notify, current);
      } catch (error) {
        notify('Рішення не збережено: ' + error.message, true);
        button.disabled = false;
      }
    });
  } catch (error) {
    if (current() === key) node.textContent = 'Рішення недоступні: ' + error.message;
  }
}
