// No DOM or network dependencies; testable revision polling policy.
export function needsFullTaskRefresh(lastRevision, lastError, response) {
  if (!response || !Number.isSafeInteger(response.revision) || response.revision < 0) return true;
  if (!Number.isSafeInteger(lastRevision) || lastRevision < 0) return true;
  return lastRevision !== response.revision || (lastError || '') !== (response.error || '');
}
