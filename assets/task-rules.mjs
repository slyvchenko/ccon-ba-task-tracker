// Pure task classification and queue rules; independent of the DOM.
const STATUS_LABELS = {'AUTO':'Автоматично','IN PROGRESS':'Аналітика','WAITING INPUT':'Очікую відповідь','WAITING DEPENDENCY':'Очікую залежність','NEEDS DECISION':'Потрібне рішення','DONE':'Завершено'};
const STATUS_TONES = {'AUTO':'gray','IN PROGRESS':'amber','WAITING INPUT':'red','WAITING DEPENDENCY':'red','NEEDS DECISION':'blue','DONE':'green'};
const MANUAL_SIGNALS = {'IN PROGRESS':'READY','WAITING INPUT':'WAIT','WAITING DEPENDENCY':'WAIT','NEEDS DECISION':'DECIDE','DONE':'DONE'};
const SIGNALS = {
  READY:{label:'Можна працювати',group:'Можна працювати зараз',tone:'green',order:0},
  WRITE:{label:'Написати листа',group:'Підготувати й надіслати лист',tone:'blue',order:0},
  DECIDE:{label:'Потрібне рішення',group:'Ухвалити рішення',tone:'blue',order:1},
  REVIEW:{label:'Потрібна перевірка',group:'Проаналізувати',tone:'gray',order:2},
  WAIT:{label:'Очікуємо',group:'Очікуємо відповідь або залежність',tone:'red',order:3},
  DONE:{label:'Завершено',group:'Завершені',tone:'green',order:4}
};

function defaultRecipients(task) {
  const title = task.summary || '';
  if (/^airtuerk\b/i.test(title)) return 'systems_airtuerk <systems@airtuerk.de>, Oruc Demir - airtuerk Service GmbH <odemir@airtuerk.de>';
  if (/^(?:AF\s*\/\s*KL|AFKL)\b/i.test(title)) return 'mail.afkl.ndc.production <mail.afkl.ndc.production@airfrance.fr>, mail.afkl.ndc.team@airfrance.fr';
  if (/^SQ213\b/i.test(title)) return 'Leon Woon <leon_woon@singaporeair.com.sg>, NDC Support <NDC_Support@singaporeair.com.sg>';
  return '';
}

function analysisOf(task) { return task.analysis && typeof task.analysis === 'object' ? task.analysis : {}; }

function analysisIsStale(task) {
  const analysis = analysisOf(task);
  return !!analysis.stale || !!(analysis.contextFingerprint && task.contextFingerprint && analysis.contextFingerprint !== task.contextFingerprint);
}

function hasAnalysis(task) { const a = analysisOf(task); return !analysisIsStale(task) && !!SIGNALS[a.signal] && !!a.reasonUk && !!a.nextActionUk; }

function effectiveSignal(task) {
  if (task.manualStatus && task.manualStatus !== 'AUTO') return MANUAL_SIGNALS[task.manualStatus] || 'REVIEW';
  return hasAnalysis(task) ? task.analysis.signal : 'REVIEW';
}

function signalInfo(task) {
  const info = SIGNALS[effectiveSignal(task)];
  return task.manualStatus && task.manualStatus !== 'AUTO' ? {...info, label:STATUS_LABELS[task.manualStatus], tone:statusTone(task.manualStatus)} : info;
}

function statusTone(status) { return STATUS_TONES[status] || 'gray'; }

function queueScore(task) {
  if (!hasAnalysis(task)) return 0;
  const score = Number(analysisOf(task).queueScore);
  return Number.isFinite(score) ? score : 0;
}

function queueTier(task) {
  if (!task.active) return 3;
  const signal = effectiveSignal(task);
  return signal === 'WAIT' ? 1 : signal === 'DONE' ? 2 : 0;
}

function priorityLane(task) {
  if (!task.active) return 3;
  if (effectiveSignal(task) === 'DONE') return 2;
  // A confirmed member of the configured active sprint outranks every backlog item.
  // Unverified membership is never treated as sprint work.
  return task.activeSprintStatus === 'VERIFIED' && task.activeSprint === true ? 0 : 1;
}

function actionRank(task) {
  const signal = effectiveSignal(task);
  if (signal === 'WRITE' || (hasAnalysis(task) && analysisOf(task).needsEmail === true)) return 0;
  if (signal === 'READY' || signal === 'DECIDE') return 1;
  if (signal === 'REVIEW') return 2;
  if (signal === 'WAIT') return 3;
  return 4;
}

function rankTasks(tasks) {
  return tasks.map((task, index) => ({task, index})).sort((left, right) => {
    const lane = priorityLane(left.task) - priorityLane(right.task);
    const group = actionRank(left.task) - actionRank(right.task);
    return lane || group || queueScore(right.task) - queueScore(left.task) || Number(right.task.blocking) - Number(left.task.blocking) || left.index - right.index;
  }).map(item => item.task);
}

function filterTasks(items, {search = '', filter = 'open', signal = 'all', sprint = 'all'} = {}, indexedText = null) {
  // Avoid rebuilding potentially long Jira descriptions for every task on
  // each no-search render; check cheap predicates before reading full text.
  const queryTerms = String(search).toLocaleLowerCase('uk-UA').trim().split(/\s+/).filter(Boolean);
  const cleanTerms = queryTerms.map(term => term.replace(/[^\p{L}\p{N}]/gu, ''));
  return items.filter(task => {
    const done = effectiveSignal(task) === 'DONE';
    const inList = filter === 'archive' ? !task.active : task.active &&
      (filter === 'all' || (filter === 'done' ? done : !done));
    if (!inList) return false;
    const sprintMatch = sprint === 'all' ||
      (sprint === 'active' && task.activeSprintStatus === 'VERIFIED' && task.activeSprint === true) ||
      (sprint === 'outside' && task.activeSprintStatus === 'VERIFIED' && task.activeSprint === false) ||
      (sprint === 'unverified' && task.activeSprintStatus !== 'VERIFIED');
    if (!sprintMatch || (signal !== 'all' && effectiveSignal(task) !== signal)) return false;
    if (!queryTerms.length) return true;
    const cached = indexedText?.(task);
    let text, folded;
    if (cached) ({text, folded} = cached);
    else {
      const analysis = analysisOf(task), brief = analysis.briefing || {};
      const references = (task.links || task.linkedIssues || [])
        .map(item => typeof item === 'string' ? item : (item.linkedKey || item.key || ''));
      text = [
        task.key, task.summary, task.jiraStatus, task.priority,
        analysis.nextActionUk, analysis.standardDescription,
        brief.technicalScopeUk, brief.currentUk, brief.targetUk,
        ...(brief.rules || []).slice(0, 30).flatMap(rule => [rule.whenUk, rule.thenUk]),
        ...references, ...(task.blockedBy || [])
      ].filter(x => typeof x === 'string').join(' ').toLocaleLowerCase('uk-UA');
      folded = text.replace(/[^\p{L}\p{N}]/gu, '');
    }
    // Punctuation-only tokens fold to an empty string, which matches every
    // task. Keep exact punctuation searches possible, but never treat an
    // empty folded candidate as a universal match.
    return queryTerms.every((term, index) => text.includes(term) ||
      (cleanTerms[index].length > 0 && folded.includes(cleanTerms[index])));
  });
}

export {STATUS_LABELS, STATUS_TONES, MANUAL_SIGNALS, SIGNALS, defaultRecipients, analysisOf, analysisIsStale, hasAnalysis, effectiveSignal, signalInfo, statusTone, queueScore, queueTier, actionRank, priorityLane, rankTasks, filterTasks};
