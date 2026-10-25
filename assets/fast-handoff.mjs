import {analysisOf, hasAnalysis, effectiveSignal, actionRank, priorityLane, queueTier} from './task-rules.mjs';

// A structurally checked draft remains a DRAFT: the analyst must verify the
// source and perform any Jira/email action manually before marking Done.
export function quickHandoff(task) {
  const current = hasAnalysis(task);
  const analysis = analysisOf(task);
  const description = current && typeof analysis.standardDescription === 'string'
    ? analysis.standardDescription.trim() : '';
  const state = analysis.qualityGate?.state || 'UNVERIFIED';
  const readyForCopy = Boolean(description) && state === 'STRUCTURALLY_VERIFIED' &&
    effectiveSignal(task) !== 'DONE' && task.active !== false;
  const nextAction = current && typeof analysis.nextActionUk === 'string'
    ? analysis.nextActionUk.trim() : '';
  let evidenceNote;
  if (!current) evidenceNote = 'Аналіз відсутній або застарів. Перевір джерела перед передачею.';
  else if (!description) evidenceNote = 'Готової Jira-чернетки немає. Визнач вимоги та критерії.';
  else if (state === 'BLOCKED') evidenceNote = 'Quality Gate блокує чернетку. Спочатку виправ зауваження.';
  else if (state === 'STRUCTURALLY_VERIFIED')
    evidenceNote = 'Структуру перевірено автоматично, але факти й передачу має підтвердити BA.';
  else evidenceNote = 'Чернетка потребує перевірки Quality Gate перед швидким копіюванням.';
  return {nextAction, description, readyForCopy, evidenceNote, state};
}

export function priorityExplanation(task) {
  const lane = priorityLane(task);
  const signal = effectiveSignal(task);
  const analysis = analysisOf(task);
  const activeSprint = lane === 0;
  const sprint = activeSprint ? 'Підтверджений активний спринт' :
    lane === 1 ? task.activeSprintStatus === 'VERIFIED'
      ? 'Поза активним спринтом' : 'Спринт не підтверджено' :
    lane === 2 ? 'Завершена вручну' : 'Задача поза поточним snapshot';
  const write = signal === 'WRITE' ||
    (hasAnalysis(task) && analysis.needsEmail === true);
  const score = hasAnalysis(task) && typeof analysis.queueScore === 'number' &&
    Number.isFinite(analysis.queueScore) && analysis.queueScore >= 0 && analysis.queueScore <= 100
    ? analysis.queueScore : null;
  const sourceOrder = [
    sprint,
    'Лист: ' + (write ? 'потрібен зараз (WRITE)' : 'без пріоритету листа'),
    'Сигнал: ' + signal,
    score === null ? 'Бал 0–100: ще не підтверджено' : 'Бал 0–100: ' + score,
    task.blocking === true ? 'Підтверджено, що блокує інших' : 'Ознака блокування відсутня'
  ];
  return {sourceOrder, lane, tier:queueTier(task), action:actionRank(task),
    score, activeSprint, write, signal};
}

export function completionPrompt(task) {
  const signal = effectiveSignal(task);
  const warning = signal === 'WRITE' ? 'Лист має бути відправлений вручну, не лише скопійований чи відкритий.\n'
    : 'Копіювання Jira-чернетки не означає її передачу.\n';
  return 'Підтверди фактичне завершення власної роботи над ' + task.key + '.\n\n' +
    warning + 'Якщо дія ще не виконана в Jira/пошті або рішення не зафіксоване, вибери Скасувати.\n\n' +
    'Позначити локальний статус DONE і перейти до наступної задачі?';
}
