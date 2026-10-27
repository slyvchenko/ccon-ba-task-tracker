// Short-lived, in-memory undo for exactly one *successful* local BA DONE.
// Never reverses Jira, email, or a revision changed by another tab.
export function makeUndoToken(task, priorStatus, revision) {
  if (!task || !/^CCON-\d+$/.test(task.key) ||
      typeof priorStatus!=='string' || priorStatus==='DONE' ||
      !Number.isSafeInteger(revision) || revision < 0) return null;
  return {key:task.key,priorStatus,revision};
}
export function canUndoLocalDone(token,task) {
  return !!token && !!task && token.key===task.key &&
    task.manualStatus==='DONE' && task.manualRevision===token.revision &&
    task.active!==false;
}
export function undoLocalDonePayload(token,task) {
  if(!canUndoLocalDone(token,task))return null;
  // Status-only edit. The preserved saved note is sent exactly as in
  // existing saveStatus; the backend's expectedManualRevision is required.
  return {manualStatus:token.priorStatus,note:task.note||'',
    expectedManualRevision:token.revision,requireActiveTask:true};
}

export function rebaseUndoForm(form,savedSnapshot,revision) {
  if(!form) return null;
  if(JSON.stringify(form.value)===form.base) return null;
  // Preserve unsaved notes/email while rebasing the now-restored status.
  form.value.manualStatus=savedSnapshot.manualStatus;
  form.base=JSON.stringify(savedSnapshot);
  form.baseRevision=revision;
  return form;
}
