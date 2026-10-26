// View-only consolidation. Never merges Jira status with local manual status
// or the computed BA signal: these are independent provenance domains.
// UI-07: distinguish an unpopulated dashboard, an empty verified snapshot,
// a filter with zero matches, and an import warning without hiding old tasks.
export function queueEmptyState({visible=0,total=0,hasSnapshot=false,importError=false}={}) {
  if (visible > 0) return null;
  if (importError && !hasSnapshot) return {
    kind:'error', text:'Перший імпорт не вдався. Перевір файл, дозвіл доступу або налаштування Jira. Попереднього списку немає.'
  };
  if (importError) return {
    kind:'stale', text:'Оновлення даних не вдалося. Попередній список збережено. Перевір стан імпорту; фільтри можуть приховувати задачі.'
  };
  if (!hasSnapshot) return {
    kind:'unavailable', text:'Snapshot ще не імпортовано. Перевір файл inbox/CCON_BA_Snapshot.json або налаштування Jira.'
  };
  if (total === 0) return {
    kind:'empty', text:'Поточний snapshot не містить задач у твоїй області Jira. Перевір JQL та дату синхронізації.'
  };
  return {kind:'no-matches', text:'За поточним пошуком та фільтрами збігів немає. Очисть пошук або обери «Усі». Збережені задачі не видалено.'};
}
export function queueSummary({visible=0,sprint=0,write=0,active=0,analyzed=0,unverified=0,quick=0}={}) {
  return {
    primary:`${visible} у списку · спринт ${sprint} · листи ${write}`,
    diagnostics:`Поточних: ${active} · аналіз: ${analyzed}/${active} · короткі кандидати: ${quick} · спринт не підтверджено: ${unverified}`
  };
}
export function conciseSnapshotInfo(latest, dateLabel) {
  return latest ? 'Оновлено ' + dateLabel(latest.generated_at) : 'Очікую snapshot';
}
export function statusPresentation({jiraStatus='',manualStatus='AUTO',manualLabel='',
  activeSprintStatus='',activeSprint=false,activeSprintNames=[],blocking=false,
  active=true,email,waiting,waitingLabel='',isWrite=false}={}) {
  const provenance=[
    'Jira: '+(jiraStatus||'Не вказано'),
    'Мій стан: '+(manualStatus==='AUTO'?'Автоматично':manualLabel||manualStatus)
  ];
  if(activeSprintStatus==='VERIFIED') provenance.push(activeSprint ?
    'Активний спринт'+(activeSprintNames.length?': '+activeSprintNames.join(', '):'') :
    'Поза активним спринтом');
  else provenance.push('Спринт не підтверджено');
  const alerts=[];
  if(blocking) alerts.push('Блокує інших');
  if(!active) alerts.push('Поза поточним snapshot');
  if(isWrite&&email===true) alerts.push('Потрібен лист');
  if(waiting===true) alerts.push(waitingLabel||'Очікуємо відповідь');
  return {provenance,alerts};
}
export function shouldRenderBriefing(value) {
  return !!value && typeof value==='object' && !Array.isArray(value);
}
export function assessmentReason(value) {
  return typeof value==='string'?value.trim():'';
}
