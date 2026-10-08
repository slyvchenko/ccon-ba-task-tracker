// Refresh attachments without replacing the editable draft fields.
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
