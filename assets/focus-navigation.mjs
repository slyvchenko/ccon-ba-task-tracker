// Pure keyboard and view-state helpers. No content from Jira, notes or emails
// enters persisted UI state: only keys, scroll position and expanded sections.
const TASK_KEY = /^CCON-\d+$/;
const INPUT_TAGS = new Set(['INPUT','TEXTAREA','SELECT']);
const CURSOR_IDS = new Set(['note','draftTo','draftSubject','draftBody','manual','manualEffort']);
const MAIN_SAVE_IDS = new Set(['note','draftTo','draftSubject','draftBody','manual','manualEffort']);

// Ctrl/Cmd+Enter only persists the main status, note and email fields.
// Independent action/question/decision editors use separate POST handlers.
export function isMainFormSaveTarget(target) {
  return Boolean(target && MAIN_SAVE_IDS.has(target.id) &&
    INPUT_TAGS.has(String(target.tagName || '').toUpperCase()));
}

export function isTextEditingTarget(target) {
  if (!target) return false;
  const tag = String(target.tagName || '').toUpperCase();
  return INPUT_TAGS.has(tag) || target.isContentEditable === true ||
    target.getAttribute?.('role') === 'textbox';
}

export function shortcutAction(event, {dialogOpen=false, editing=false} = {}) {
  if (!event || event.isComposing || event.repeat || dialogOpen) return null;
  const key = String(event.key || '');
  if (event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
    if (editing) return null;
    if (key === 'ArrowDown') return 'NEXT';
    if (key === 'ArrowUp') return 'PREVIOUS';
    if (key.toLowerCase() === 'c') return 'COPY_ACTION';
  }
  if (!event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey &&
      !editing && key === '/') return 'SEARCH';
  if (!event.altKey && !event.shiftKey && (event.ctrlKey || event.metaKey) &&
      editing && key === 'Enter') return 'SAVE';
  return null;
}

export function adjacentTaskKey(keys, selected, direction) {
  const normalized = Array.isArray(keys) ? keys.filter(key => typeof key === 'string') : [];
  if (!normalized.length) return null;
  const index = normalized.indexOf(selected);
  if (index === -1) return direction < 0 ? normalized.at(-1) : normalized[0];
  return normalized[(index + (direction < 0 ? -1 : 1) + normalized.length) % normalized.length];
}

function viewSectionKey(node) {
  // Keep only an opaque deterministic key, NOT a source-summary/PNR/email
  // string in sessionStorage. FNV-1a is a compact UI identity, not encryption.
  const explicit = node.getAttribute?.('data-view-key') || node.id;
  const title = node.querySelector?.('summary')?.textContent?.trim().replace(/\s+/g,' ') || '';
  const region = node.closest?.('[aria-label]')?.getAttribute?.('aria-label') || '';
  // An evidence task can show several reports with identical disclosure
  // headings. Scope their keys to the *opaque* per-report identifier, not
  // report title/flow ID or the shared evidence region.
  const reportKey = node.parentElement?.closest?.('[data-view-key]')
    ?.getAttribute?.('data-view-key') || '';
  const source = String((reportKey ? reportKey + '::' : '') ||
                        '') + String(explicit || (region + '::' + title));
  let hash = 2166136261;
  for (let index=0; index<source.length; index++)
    hash = Math.imul(hash ^ source.charCodeAt(index), 16777619);
  return 'v_' + (hash>>>0).toString(16).padStart(8,'0');
}

export function captureTaskView(detail) {
  if (!detail) return {scroll:0,sections:[]};
  const sections = [...detail.querySelectorAll('details')].map(node =>
    [viewSectionKey(node), Boolean(node.open)]);
  return {scroll:Number.isFinite(detail.scrollTop) ? Math.max(0,detail.scrollTop) : 0,sections};
}

export function restoreTaskView(detail, state) {
  if (!detail) return;
  // A new task has no prior viewport; don't inherit the previous task's scroll.
  if (!state) { detail.scrollTop = 0; return; }
  const openByKey = new Map(Array.isArray(state.sections) ? state.sections : []);
  for (const node of detail.querySelectorAll('details')) {
    const key = viewSectionKey(node);
    if (openByKey.has(key)) node.open = openByKey.get(key) === true;
  }
  if (Number.isFinite(state.scroll)) detail.scrollTop = Math.max(0,state.scroll);
}

// Async evidence/question/decision/history panels insert nested <details> after
// the parent render. Restore only NEWLY inserted disclosures by semantic key;
// never re-toggle an existing section while the user is interacting with it.
export function restoreInsertedDisclosureStates(mutations, openByKey) {
  if (!(openByKey instanceof Map)) return 0;
  let restored=0;
  for (const mutation of mutations || []) for (const root of mutation.addedNodes || []) {
    if (root.nodeType !== 1) continue;
    const nodes=[...(root.matches?.('details') ? [root] : []),
      ...(root.querySelectorAll?.('details') || [])];
    for (const node of nodes) {
      const key=viewSectionKey(node);
      if (!openByKey.has(key)) continue;
      node.open=openByKey.get(key) === true;
      restored++;
    }
  }
  return restored;
}

export function captureEditorFocus(active, detail) {
  if (!active || !detail?.contains(active) || !CURSOR_IDS.has(active.id)) return null;
  const selection = {id:active.id, scroll:Number.isFinite(active.scrollTop) ? active.scrollTop : 0};
  if (typeof active.selectionStart === 'number' && typeof active.selectionEnd === 'number') {
    selection.start = active.selectionStart;
    selection.end = active.selectionEnd;
    selection.direction = active.selectionDirection || 'none';
  }
  return selection;
}

export function restoreEditorFocus(detail, focus, {focusElement=true} = {}) {
  if (!detail || !focus || !CURSOR_IDS.has(focus.id)) return false;
  const target = detail.querySelector('#' + focus.id);
  if (!target || target.disabled) return false;
  if (focusElement) target.focus({preventScroll:true});
  if (Number.isFinite(focus.start) && Number.isFinite(focus.end) &&
      typeof target.setSelectionRange === 'function') {
    try { target.setSelectionRange(focus.start, focus.end, focus.direction || 'none'); }
    catch { /* select elements cannot restore a text caret */ }
  }
  if (Number.isFinite(focus.scroll)) target.scrollTop = focus.scroll;
  return true;
}

// Explicit user-triggered handoffs only. After an async save/dialog rerender,
// focus a live enabled action instead of leaving keyboard users on <body>.
// Never use this from polling, background refresh or unrelated events.
export function focusAfterAction(root, candidateIds) {
  if (!root || !Array.isArray(candidateIds)) return false;
  for (const id of candidateIds) {
    if (typeof id !== 'string' || !/^[a-zA-Z][a-zA-Z0-9]*$/.test(id)) continue;
    const target = root.getElementById?.(id) || root.querySelector?.('#'+id);
    if (!target || target.isConnected === false || target.disabled ||
        target.hidden || target.closest?.('[hidden]')) continue;
    if (typeof target.focus !== 'function') continue;
    target.focus({preventScroll:true});
    return true;
  }
  return false;
}

export function sanitizeSessionFocus(candidate) {
  const selected = typeof candidate?.selected === 'string' &&
    TASK_KEY.test(candidate.selected) ? candidate.selected : null;
  const views = {};
  const raw = candidate?.views;
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    for (const [key,value] of Object.entries(raw).slice(-12)) {
      if (!TASK_KEY.test(key) || !value || typeof value !== 'object') continue;
      const scroll = Number.isFinite(value.scroll) && value.scroll >= 0 ?
        Math.min(2000000,Math.trunc(value.scroll)) : 0;
      const sections = Array.isArray(value.sections) ?
        value.sections.slice(0,50).filter(pair =>
          Array.isArray(pair) && pair.length === 2 && /^v_[a-f0-9]{8}$/.test(pair[0]) &&
          typeof pair[1] === 'boolean') : [];
      const rawFocus=value.focus;
      const focus=rawFocus && CURSOR_IDS.has(rawFocus.id) &&
        Number.isSafeInteger(rawFocus.start) && rawFocus.start >= 0 && rawFocus.start <= 50000 &&
        Number.isSafeInteger(rawFocus.end) && rawFocus.end >= 0 && rawFocus.end <= 50000 ?
        {id:rawFocus.id,start:rawFocus.start,end:rawFocus.end,
         direction:['forward','backward','none'].includes(rawFocus.direction) ?
           rawFocus.direction : 'none',
         scroll:Number.isFinite(rawFocus.scroll) ? Math.max(0,Math.min(2000000,rawFocus.scroll)) : 0} : undefined;
      views[key] = {scroll,sections,...(focus ? {focus} : {})};
    }
  }
  return {selected,views};
}
