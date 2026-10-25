// Pure, local-only optimistic-lock helpers for manual notes and mail drafts.
export function baseManualRevision(recovered, task) {
  if (recovered) return Number.isSafeInteger(recovered.baseRevision) &&
    recovered.baseRevision >= 0 ? recovered.baseRevision : null;
  return Number.isSafeInteger(task?.manualRevision) && task.manualRevision >= 0 ?
    task.manualRevision : null;
}

export function manualVersionChanged(baseRevision, serverRevision) {
  return !Number.isSafeInteger(baseRevision) || baseRevision < 0 ||
    !Number.isSafeInteger(serverRevision) || serverRevision < 0 ||
    baseRevision !== serverRevision;
}

export function withExpectedRevision(value, revision) {
  if (!Number.isSafeInteger(revision) || revision < 0)
    throw Error('Unknown local edit revision: compare the current saved version first.');
  return {...value, expectedManualRevision:revision};
}
