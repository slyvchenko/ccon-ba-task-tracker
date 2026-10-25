import {analysisOf, hasAnalysis, effectiveSignal, actionRank, priorityLane, queueScore} from './task-rules.mjs';

export const EFFORT_LABELS = Object.freeze({
  UNKNOWN:'Не оцінено', XS:'XS · до 2 хв', S:'S · 2–5 хв',
  M:'M · 5–20 хв', L:'L · 20–60 хв', XL:'XL · понад 60 хв'
});
const VALID = new Set(Object.keys(EFFORT_LABELS));

function validBand(value) {
  return typeof value === 'string' && VALID.has(value) ? value : 'UNKNOWN';
}

// Shortcuts are explicitly marked low-confidence hypotheses. Never promise
// completion time, never derive a task's final scope from free-form text.
export function effortSuggestion(task) {
  if (!task || task.active === false || !hasAnalysis(task)) return {band:'UNKNOWN',reason:'Немає актуального підтвердженого аналізу.'};
  const analysis = analysisOf(task);
  const signal = effectiveSignal(task);
  if (signal === 'DONE' || signal === 'WAIT') return {band:'UNKNOWN',reason:'Очікування або завершення не є активною роботою.'};
  const brief = analysis.briefing || {};
  const unknown = (Array.isArray(analysis.missingInfo) ? analysis.missingInfo.length : 0) +
    (Array.isArray(brief.unknownsUk) ? brief.unknownsUk.length : 0);
  const rules = Array.isArray(brief.rules) ? brief.rules.length : 0;
  const evidence = Array.isArray(analysis.evidence) ? analysis.evidence.length : 0;
  const gate = analysis.qualityGate?.state || 'UNVERIFIED';
  if (rules >= 8 || unknown >= 6)
    return {band:'XL',reason:'Багато правил або відкритих питань. Потрібна оцінка BA.'};
  if (signal === 'REVIEW' || signal === 'DECIDE' || gate === 'BLOCKED' || unknown >= 3 || rules >= 4)
    return {band:'L',reason:'Є аналіз, рішення або суттєві відкриті умови.'};
  if (gate !== 'STRUCTURALLY_VERIFIED')
    return {band:'UNKNOWN',reason:'Немає достатньої перевірки для оцінки короткої роботи.'};
  if (unknown > 0 || rules >= 2 || evidence >= 6)
    return {band:'M',reason:'Є умови, джерела або уточнення для перевірки.'};
  if (signal === 'WRITE') {
    const draft = task.savedEmailDraft || analysis.emailDraft || {};
    const prepared = typeof draft.to === 'string' && draft.to.trim() &&
      typeof draft.subject === 'string' && draft.subject.trim() &&
      typeof draft.body === 'string' && draft.body.trim();
    return prepared ? {band:'S',reason:'Є текст листа, але його та адресатів треба перевірити вручну.'}
      : {band:'M',reason:'Лист ще потребує підготовки або перевірки полів.'};
  }
  if (signal === 'READY' && analysis.standardDescription?.trim())
    return {band:'S',reason:'Є структурно перевірена чернетка, її потрібно звірити з фактами.'};
  return {band:'M',reason:'Оцінка невизначена без ручного аналізу обсягу.'};
}

export function effortInfo(task) {
  const manual = validBand(task?.manualEffort);
  if (manual !== 'UNKNOWN') {
    return {band:manual,label:EFFORT_LABELS[manual],source:'MANUAL',
      confidence:'USER_SELECTED',reason:'Оцінку часу встановлено вручну. Не змінює Jira-пріоритет.'};
  }
  const suggestion = effortSuggestion(task);
  return {band:suggestion.band,label:EFFORT_LABELS[suggestion.band],source:'HEURISTIC',
    confidence:'LOW',reason:suggestion.reason};
}

export function quickWinCandidate(task) {
  const info = effortInfo(task);
  if (info.band !== 'XS' && info.band !== 'S') return false;
  if (!task || task.active === false || !hasAnalysis(task)) return false;
  if (effectiveSignal(task) !== 'READY' && effectiveSignal(task) !== 'WRITE') return false;
  if (analysisOf(task).qualityGate?.state !== 'STRUCTURALLY_VERIFIED') return false;
  if (Array.isArray(analysisOf(task).missingInfo) && analysisOf(task).missingInfo.length) return false;
  if (Array.isArray(analysisOf(task).briefing?.unknownsUk) &&
      analysisOf(task).briefing.unknownsUk.length) return false;
  // A quick-win hint is NEVER a new priority group.
  return true;
}

export function quickWinExplanation(task) {
  if (!quickWinCandidate(task)) return '';
  const estimate = effortInfo(task);
  return estimate.source === 'MANUAL' ?
    'Можлива коротка дія · час оцінено вручну, факти перевіряє BA' :
    'Можлива коротка дія · автоматична гіпотеза, час не підтверджений';
}

export function safeQuickWinGroups(rankedTasks) {
  // Returns display-only candidates without sorting or mutating the main queue.
  // Group key deliberately includes every priority discriminator. A shortcut
  // cannot move one issue in front of another, even inside a sprint.
  if (!Array.isArray(rankedTasks)) return [];
  const result = [];
  rankedTasks.forEach((task,index) => {
    if (!quickWinCandidate(task)) return;
    result.push({
      key:task.key,index,lane:priorityLane(task),actionRank:actionRank(task),
      queueScore:queueScore(task),blocking:task.blocking===true,
      effort:effortInfo(task).band
    });
  });
  return result;
}
