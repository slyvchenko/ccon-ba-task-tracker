// Refresh attachments without replacing the editable draft fields.
// Current state is derived on the server from verified supplier-only ZIPs.
export const zipStatusLabels = {
  READY: 'Готово', PARTIAL: 'Частково готово', PENDING: 'Очікує ZIP',
  STALE: 'Застаріло', NEEDS_REVIEW: 'Потрібна перевірка',
  FAILED: 'Помилка ZIP', BLOCKED: 'Немає даних'
};
export const zipReasonLabels = {
  ALL_SUPPLIER_ZIPS_READY: 'Усі архіви постачальника підготовлені.',
  SUPPLIER_ONLY_ZIP_READY: 'Архів постачальника готовий до завантаження.',
  SOME_FLOWS_NOT_READY: 'Не всі приклади оброблені.',
  ZIP_REQUIRES_REVIEW: 'У ZIP є зауваження щодо методу або цілісності обмінів.',
  BROWSER_ZIP_NOT_SAVED: 'Повний ZIP ще не збережено з авторизованого браузера.',
  NO_CCON_FLOW: 'Немає підтвердженого cconFlowId у Jira.',
  SUPPLIER_UNKNOWN: 'Постачальник не визначений.',
  JIRA_SOURCE_UNAVAILABLE: 'Актуальний Jira-контекст недоступний.',
  JIRA_CONTEXT_CHANGED: 'Контекст Jira змінився, архів потрібно перевірити.',
  ARCHIVE_INTEGRITY_FAILED: 'Готовий ZIP пошкоджено або змінено.',
  OLD_DOWNLOAD: 'Знайдений ZIP старіший за поточний план завантаження.',
  INVALID_DOWNLOAD_SIZE: 'Файл не схожий на допустимий ZIP за розміром.',
  NOT_ZIP_SIGNIN_OR_ERROR_PAGE: 'Завантажено не ZIP, а сторінку входу/помилки.',
  ZIP_INSPECTION_OR_CONTEXT_FAILED: 'ZIP не пройшов перевірку. Перевір локальний журнал.',
  SUPPLIER_ZIP_READY_WITH_WARNINGS: 'Архів є, але потрібно перевірити зауваження.',
  SUPPLIER_ZIP_READY_EVIDENCE_PARTIAL: 'Supplier ZIP готовий, аналіз REST/errors неповний.',
  VERIFIED_SUPPLIER_ARCHIVE_CACHED: 'Перевірений supplier ZIP доступний із кешу.',
  CHECK_DOWNLOAD: 'Потрібно повторити перевірку завантаження.',
  ZIP_UNAVAILABLE: 'Архів поки недоступний.'
};
export function zipStatusText(data, escapeHtml) {
  const state = zipStatusLabels[data?.state] || 'Стан невідомий';
  const reason = zipReasonLabels[data?.reasonCode] || '';
  const flows = (data?.flows || []).slice(0, 100).map(flow =>
    '<span class="muted" title="' + escapeHtml(flow.flowId || '') + '">' +
    escapeHtml((flow.flowId || '').slice(0, 8)) + '…: ' +
    escapeHtml(zipStatusLabels[flow.state] || 'Невідомо') + '</span>').join(' · ');
  return '<div class="logs-status" role="status"><b>ZIP: ' +
    escapeHtml(state) + '</b>' + (reason ? ' · ' + escapeHtml(reason) : '') +
    (flows ? '<div>' + flows + '</div>' : '') + '</div>';
}


export function createLogsController({api, escapeHtml, message, getSelected, getElement = id => document.getElementById(id)}) {
  const $ = getElement;
  let logRequest = 0;
  const logSignatures = new WeakMap();
  async function loadLogs(key = getSelected()) {
    if (!key || getSelected() !== key || !$('emailLogs')) return;
    const request = ++logRequest, target = $('emailLogs');
    try {
      const data = await api('/api/logs/' + encodeURIComponent(key));
      if (request !== logRequest || getSelected() !== key || target !== $('emailLogs')) return;
      const nextSignature = JSON.stringify(data);
      if (logSignatures.get(target) === nextSignature) return;
      logSignatures.set(target, nextSignature);
      const items = data.items || [];
      target.innerHTML = `<div class="logs-heading"><h4>Логи до листа</h4><span class="logs-count">${items.length ? items.length + ' ZIP' : ''}</span></div>` +
        zipStatusText(data, escapeHtml) +
        (items.length ? items.map(item => `<div class="log-file ${item.stale || item.needsReview ? 'log-review' : ''}"><div class="log-file-name">${escapeHtml(item.filename)}</div><p class="muted">${escapeHtml(item.method || item.supplier || 'Метод потребує перевірки')} · ${escapeHtml(item.fileCount ?? '?')} XML · <span title="${escapeHtml(item.flowId)}">flow ${escapeHtml(item.flowId.slice(0, 8))}…</span></p>${item.stale || item.needsReview ? `<div class="log-review-note">${item.stale ? 'З попереднього контексту — перевір актуальність перед відправленням.' : 'Є зауваження до логів — перевір перед відправленням.'}</div>` : ''}<div class="log-actions"><a class="file-button" href="${escapeHtml(item.downloadUrl)}" download>Завантажити ZIP</a></div></div>`).join('') : '<p class="muted">' + escapeHtml(data.emptyMessage) + '</p>') +
        (items.length && data.pendingCount ? `<p class="muted">Ще ${escapeHtml(data.pendingCount)} прикладів очікують підготовки.</p>` : '') +
        `<div class="logs-folder"><span class="muted" title="${escapeHtml(data.folder)}">CCON-Logs / ${escapeHtml(key)}</span>${data.folderAvailable ? '<button id="openLogsFolder" class="file-button">Відкрити папку</button>' : ''}</div>` +
        (items.length ? '<p class="footer-note">Прикріпи ZIP до цього листа в Outlook.</p>' : '');
      if ($('openLogsFolder')) $('openLogsFolder').addEventListener('click', async () => {
        const button = $('openLogsFolder'); button.disabled = true;
        try { const result = await api('/api/logs/' + encodeURIComponent(key) + '/folder', {}); message(result.message); }
        catch (error) { message(error.message, true); }
        finally { button.disabled = false; }
      });
    } catch (error) {
      if (request === logRequest && getSelected() === key && target === $('emailLogs')) {
        logSignatures.delete(target);
        target.innerHTML = '<div class="logs-heading"><h4>Логи до листа</h4></div><p class="muted" role="status">Не вдалося прочитати архіви. ' + escapeHtml(error.message) + '</p>';
      }
    }
  }
  return {loadLogs};
}
