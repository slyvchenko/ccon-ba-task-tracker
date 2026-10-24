/* Optional evidence/questions within the original BA Desk task layout. */
const stateLabels = {OPEN:'Відкрите', ANSWERED:'Отримано відповідь',
  SUPERSEDED:'Замінене', NOT_APPLICABLE:'Не стосується'};

export function valueMappingMarkup(report, escape) {
  const comparisons = (report.valueReview?.comparisons || []).slice(0, 20);
  const rows = [];
  for (const comparison of comparisons) {
    const dir = comparison.direction === 'REST_REQUEST_TO_SUPPLIER_REQUEST'
      ? 'REST request → supplier request' : 'Supplier response → REST response';
    for (const matched of (comparison.exactValueCandidates || []).slice(0, 15)) {
      rows.push('<tr><td>' + escape(dir) + '</td><td>' + escape(matched.restField) +
        '</td><td>' + escape(matched.supplierField) + '</td><td>Однакове значення (кандидат)</td></tr>');
    }
    for (const diff of (comparison.sameNamedDifferentValues || []).slice(0, 15)) {
      rows.push('<tr><td>' + escape(dir) + '</td><td>' + escape(diff.restField) +
        '</td><td>' + escape(diff.supplierField) + '</td><td>Різні значення, перевірити трансформацію</td></tr>');
    }
  }
  if (!comparisons.length) return '<p class="muted">Немає однозначно спарених REST/supplier обмінів для перевірки значень.</p>';
  return '<details><summary>Порівняння значень REST ↔ supplier (' + rows.length + ' спостережень)</summary>' +
    '<p class="muted">Кандидати, не підтверджені mapping rules. Сирі значення не зберігаються.</p>' +
    '<div class="evidence-scroll"><table><thead><tr><th>Напрям</th><th>REST</th><th>Supplier</th><th>Висновок</th>' +
    '</tr></thead><tbody>' + rows.join('') + '</tbody></table></div></details>';
}
export async function loadTaskEvidence(key, api, escape, current) {
  const destination = document.getElementById('evidenceSummary');
  if (!destination) return;
  try {
    const data = await api('/api/evidence/' + encodeURIComponent(key));
    if (current() !== key) return;
    const reports = data.reports || [];
    if (!reports.length) {
      destination.textContent = 'Потрібні ZIP-логи. Запусти Evidence Flow у локальному Codex.';
      return;
    }
    destination.innerHTML = reports.map(report => {
      const counts = report.counts || {};
      const codes = (report.errorCodes || []).slice(0, 20)
        .map(x => escape(x.code) + ' (' + escape(x.count) + ')').join(', ');
      const rows = (report.samples || []).slice(0, 30).map(item =>
        '<tr><td>' + escape(item.id) + '</td><td>' + escape(item.layer) +
        '</td><td>' + escape(item.kind) + '</td><td>' +
        escape((item.fields || []).slice(0, 8).join(', ')) + '</td></tr>').join('');
      const questions = (report.questionsUk || []).slice(0, 12)
        .map(x => '<li>' + escape(x) + '</li>').join('');
      return '<div class="evidence-report"><b>' + escape(report.supplier) +
        ' · ' + escape(report.status || 'PARTIAL') + '</b><p>REST: ' + escape(counts.rest || 0) +
        ' · Supplier: ' + escape(counts.supplier || 0) + ' · Errors: ' + escape(counts.errors || 0) +
        '</p><p><b>Коди помилок:</b> ' + (codes || 'Не знайдено') + '</p>' +
        (rows ? '<details><summary>Приклади обмінів (до 30)</summary><div class="evidence-scroll">' +
          '<table><thead><tr><th>#</th><th>Рівень</th><th>Напрям</th><th>Поля</th>' +
          '</tr></thead><tbody>' + rows + '</tbody></table></div></details>' : '') +
        valueMappingMarkup(report, escape) +
        (questions ? '<div class="section-label">Що уточнити</div><ul>' + questions + '</ul>' : '') +
        '</div>';
    }).join('');
  } catch (error) {
    if (current() === key) destination.textContent = 'Evidence недоступні: ' + error.message;
  }
}

export async function loadTaskQuestions(key, api, escape, notify, current) {
  const destination = document.getElementById('questionTracker');
  if (!destination) return;
  try {
    const data = await api('/api/questions/' + encodeURIComponent(key));
    if (current() !== key) return;
    if (!data.questions?.length) {
      destination.textContent = 'Питання з’являться після наступного BA-аналізу.';
      return;
    }
    destination.innerHTML = data.questions.map(q =>
      '<section class="question-record" data-question="' + escape(q.id) + '">' +
      '<b>' + escape(q.text) + '</b>' +
      '<label>Стан <select class="question-state">' +
        Object.keys(stateLabels).map(s => '<option value="' + s + '"' +
          (q.status === s ? ' selected' : '') + '>' + stateLabels[s] + '</option>').join('') +
      '</select></label>' +
      '<label>Відповідає <input class="question-owner" maxlength="180" value="' + escape(q.owner || '') + '"></label>' +
      '<label>Відповідь / рішення<textarea class="question-answer" maxlength="8000" rows="2">' +
        escape(q.answer || '') + '</textarea></label>' +
      '<label>Джерело (URL)<input class="question-url" maxlength="2000" value="' + escape(q.evidenceUrl || '') + '"></label>' +
      '<div class="actions"><button class="save-question quiet" data-question="' + escape(q.id) +
        '">Зберегти</button><span class="muted">' +
        (q.status === 'ANSWERED' && !q.answerVerified ? 'Відповідь без підтвердженого джерела' :
        q.presentInLatestAnalysis === false ? 'Немає в аналізі, але не закрито автоматично' : '') +
      '</span></div></section>').join('');
    destination.querySelectorAll('.save-question').forEach(button => button.addEventListener('click', async () => {
      const box = button.closest('.question-record');
      button.disabled = true;
      try {
        await api('/api/questions/' + encodeURIComponent(key) + '/' +
          encodeURIComponent(button.dataset.question), {
          status: box.querySelector('.question-state').value,
          owner: box.querySelector('.question-owner').value,
          answer: box.querySelector('.question-answer').value,
          evidenceUrl: box.querySelector('.question-url').value
        });
        notify('Питання збережено локально. Jira не змінена.');
        if (current() === key) loadTaskQuestions(key, api, escape, notify, current);
      } catch (error) {
        notify('Питання не збережено: ' + error.message, true);
        button.disabled = false;
      }
    }));
  } catch (error) {
    if (current() === key) destination.textContent = 'Питання недоступні: ' + error.message;
  }
}
