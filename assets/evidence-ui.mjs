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
export function investigationMarkup(investigation, escape) {
  if (!investigation || !investigation.analyzedCases) return '';
  const total = Number(investigation.analyzedCases) || 0;
  const available = Number(investigation.availableUniqueFlows) || 0;
  const coverage = investigation.coverage || {};
  const groups = (investigation.groups || []).slice(0, 12).map(g =>
    '<li><b>' + escape(g.errorCode) + '</b> · ' + escape(g.supplierMethod) +
    ': ' + escape(g.caseCount) + ' flow(s)</li>').join('');
  const guesses = (investigation.hypotheses || []).slice(0, 8).map(h =>
    '<li><b>Гіпотеза (не підтверджено):</b> ' + escape(h.titleUk) +
    '. <span>Альтернатива: ' + escape(h.alternativeUk) +
    '</span> <span>Перевірити: ' + escape(h.verificationUk) + '</span></li>').join('');
  const questions = (investigation.questionsUk || []).slice(0, 12).map(q =>
    '<li>' + escape(q) + '</li>').join('');
  return '<details><summary>Серія помилок · ' + escape(total) + ' із ' + escape(available) +
    ' локальних flow (RCA не підтверджено)</summary>' +
    '<p class="muted">Лише локально завантажені ZIP. Вибірка не є статистично репрезентативною. ' +
    'Причину треба довести повними payload, часовою послідовністю та контрактом.</p>' +
    '<p>Покриття: REST ' + escape(coverage.withRest || 0) + '/' + escape(total) +
    ', Supplier ' + escape(coverage.withSupplier || 0) + '/' + escape(total) +
    ', Errors ' + escape(coverage.withErrorLayer || 0) + '/' + escape(total) + '</p>' +
    (groups ? '<div class="section-label">Коди й методи</div><ul>' + groups + '</ul>' : '') +
    (guesses ? '<div class="section-label">Що може бути причиною</div><ul>' + guesses + '</ul>' : '') +
    (questions ? '<div class="section-label">Недостатні докази / питання</div><ul>' + questions + '</ul>' : '') +
    '</details>';
}
export function flowDiagnosticsMarkup(report, escape) {
  const flow = report?.flowDiagnostics;
  if (!flow) return '';
  const contracts = (flow.contractCandidates || []).slice(0, 12);
  const methods = contracts.map(item =>
    '<li><b>' + escape(item.direction === 'REST_REQUEST_TO_SUPPLIER_REQUEST' ?
      'REST request → Supplier request' : 'Supplier response → REST response') +
    '</b> · supplier ' + escape(item.supplierMethod || 'Метод невідомий') +
    ', REST endpoint не підтверджено; точні збіги: ' +
    escape((item.exactValueCandidates || []).length) + ', різні значення: ' +
    escape((item.differentValueCandidates || []).length) +
    ', null REST/supplier: ' + escape((item.restNullFields || []).length) + '/' +
    escape((item.supplierNullFields || []).length) +
    ', повторювані поля: ' + escape((item.restRepeatedFields || []).length) + '/' +
    escape((item.supplierRepeatedFields || []).length) + '</li>').join('');
  const timeline = (flow.timeline || []).slice(0, 40).map(item =>
    '<li>' + escape(item.eventTimeUtc || 'Час невідомий') + ' · ' +
    escape(item.layer) + ' / ' + escape(item.direction) +
    (item.method ? ' · ' + escape(item.method) : '') +
    (!item.eventTimeUtc ? ' (порядок не підтверджений)' : '') + '</li>').join('');
  const repeat = (flow.repeatedMethodCandidates || []).slice(0, 10).map(item =>
    '<li>' + escape(item.supplierMethod) + ': ' + escape(item.requestCount) +
    ' запити, можливий повторний виклик (не доведений retry)</li>').join('');
  return '<details><summary>Контракт і хронологія · ' +
    escape(flow.timestampedEntries || 0) + '/' + escape(flow.entriesExamined || 0) +
    ' подій з достовірною часовою міткою</summary>' +
    '<p class="muted">Відповідності лише кандидатні. Порядок файлів і sequence не доводять час, причину чи retry.</p>' +
    (methods ? '<div class="section-label">REST ↔ Supplier</div><ul>' + methods + '</ul>' : '') +
    (timeline ? '<div class="section-label">Події</div><ol>' + timeline + '</ol>' : '') +
    (repeat ? '<div class="section-label">Повторні виклики</div><ul>' + repeat + '</ul>' : '') +
    '</details>';
}

export function evidenceHealthMarkup(health, escape) {
  if (!health) return '';
  const ratio = health.restSupplierCoverage;
  const coverage = ratio === null || ratio === undefined ?
    'Немає підтвердженого списку cconFlowId з Jira' :
    Math.round(ratio * 100) + '% REST + supplier із ' + Number(health.expectedFlowCount || 0) + ' очікуваних flows';
  const codes = (health.taxonomy || []).slice(0, 12).map(x =>
    '<li><b>' + escape(x.code) + '</b>: ' + escape(x.category) +
    ' · ' + escape(x.caseCount) + ' незалежних flow(s) · класифікація попередня</li>').join('');
  const gaps = (health.flows || []).slice(0, 20).filter(x => x.gaps?.length).map(x =>
    '<li>' + escape(x.flowId) + ': ' + escape(x.gaps.join(', ')) + '</li>').join('');
  const repeat = (health.recurrence || []).slice(0, 10).map(x =>
    '<li>' + escape(x.code) + ': ' + escape(x.caseCount) + ' локально завантажених flows</li>').join('');
  return '<details><summary>Покриття доказів · ' + escape(coverage) + '</summary>' +
    '<p class="muted">Помилка може спостерігатися у supplier, але мати причину в запиті CCON. ' +
    'Коди не підтверджують root cause; ця вибірка не репрезентативна.</p>' +
    (codes ? '<div class="section-label">Гіпотези категорій помилок</div><ul>' + codes + '</ul>' : '') +
    (repeat ? '<div class="section-label">Повторення у доступних flows</div><ul>' + repeat + '</ul>' : '') +
    (gaps ? '<div class="section-label">Прогалини в ZIP</div><ul>' + gaps + '</ul>' : '') +
    '</details>';
}

export async function loadTaskEvidence(key, api, escape, current) {
  const destination = document.getElementById('evidenceSummary');
  if (!destination) return;
  try {
    const data = await api('/api/evidence/' + encodeURIComponent(key));
    if (current() !== key) return;
    const reports = data.reports || [];
    if (!reports.length) {
      destination.innerHTML = '<p class="muted">Потрібні ZIP-логи. Запусти Evidence Flow у локальному Codex.</p>' +
        evidenceHealthMarkup(data.health, escape);
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
        flowDiagnosticsMarkup(report, escape) +
        (questions ? '<div class="section-label">Що уточнити</div><ul>' + questions + '</ul>' : '') +
        '</div>';
    }).join('') + investigationMarkup(data.investigation, escape) +
      evidenceHealthMarkup(data.health, escape);
  } catch (error) {
    if (current() === key) destination.textContent = 'Evidence недоступні: ' + error.message;
  }
}

export async function loadTaskQuestions(key, api, escape, notify, current, getActiveScope=()=>current) {
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
      (q.answerCandidates?.length ? '<details><summary>Можлива відповідь у нових коментарях (' +
        escape(q.answerCandidates.length) + '). Не підтверджено</summary><div class="question-candidates">' +
        q.answerCandidates.slice(0, 3).map(c => '<div class="question-candidate">' +
          '<p>' + escape(c.excerpt) + '</p><a target="_blank" rel="noopener noreferrer" href="' +
          escape(c.sourceUrl) + '">Джерело Jira</a> · <button class="suggest-answer quiet" ' +
          'data-comment="' + escape(c.commentId) + '">Підставити для перевірки</button>' +
          '</div>').join('') + '</div></details>' : '') +
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
    // Fill fields for review, never update OPEN status or persist without
    // the analyst explicitly choosing a status and clicking Save.
    destination.querySelectorAll('.suggest-answer').forEach(button => button.addEventListener('click', () => {
      const box = button.closest('.question-record');
      const question = data.questions.find(q => q.id === box.dataset.question);
      const match = question?.answerCandidates?.find(c => c.commentId === button.dataset.comment);
      if (!match) return;
      box.querySelector('.question-answer').value = match.excerpt;
      box.querySelector('.question-url').value = match.sourceUrl;
      notify('Коментар підставлено. Це лише кандидат: перевір зміст, обери стан і збережи вручну.');
    }));
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
        const live = getActiveScope();
        if (live() === key) loadTaskQuestions(key, api, escape, notify, live, getActiveScope);
      } catch (error) {
        notify('Питання не збережено: ' + error.message, true);
        button.disabled = false;
      }
    }));
  } catch (error) {
    if (current() === key) destination.textContent = 'Питання недоступні: ' + error.message;
  }
}
