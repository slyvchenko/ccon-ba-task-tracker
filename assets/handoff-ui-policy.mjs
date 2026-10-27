// Presentation only. Distinguishes copying an artifact, reviewing it and
// locally approving BA wording from any actual external Jira/email action.
export function handoffCopyPolicy({description='',readyForCopy=false,qualityState='UNVERIFIED'}={}) {
  const exists=typeof description==='string'&&!!description.trim();
  return {
    showFastCopy:exists,
    fastLabel:'Скопіювати структурно перевірену чернетку',
    fastEnabled:exists&&readyForCopy,
    showFallbackCopy:exists&&!readyForCopy,
    fallbackLabel:'Скопіювати для доопрацювання (неперевірено)',
    approvalLabel:'Схвалити BA-опис локально',
    warning:qualityState==='BLOCKED'?
      'Quality Gate блокує чернетку. Копія лише для ручного доопрацювання, не для передачі.':
      'Чернетка не підтверджена Quality Gate. Перевір зміст перед будь-якою передачею.'
  };
}
// The quick-copy button can outlive a background snapshot while a form is in
// use. Revalidate against the task currently selected AND the latest revision.
export function readyToCopyCurrentHandoff({selectedKey,displayedKey,taskKey,
  renderedVersion,latestVersion,shown,latest}={}) {
  return typeof taskKey==='string' && selectedKey===taskKey &&
    displayedKey===taskKey && Boolean(renderedVersion) &&
    renderedVersion===latestVersion && shown?.readyForCopy===true &&
    latest?.readyForCopy===true && Boolean(latest.description) &&
    latest.description===shown.description;
}

export function mailActionLabels(cloudMode=false) {
  return {
    copy:'Скопіювати текст листа',
    open:cloudMode?'Зберегти й скопіювати лист':'Відкрити в пошті (без надсилання)',
    batch:'Пакет листів'
  };
}
