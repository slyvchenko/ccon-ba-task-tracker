// A queue import may update 999 OTHER tasks without changing the open detail.
// The detail template does not read snapshot-level metadata, so key its DOM,
// evidence, questions, decisions and history to the selected task's content.
export function detailContentFingerprint(task) {
  if (!task) return '';
  // Every imported Jira snapshot rewrites importedAt for ALL rows in SQLite,
  // even when the selected issue is byte-identical. This is presentation-only
  // metadata, not a reason to refetch its evidence/questions/history.
  const {importedAt: _lastImport, ...content} = task;
  return JSON.stringify(content);
}

// Stale responses for the SAME key must not write into a newer render.
// Every render gets a new generation, and a closure used by its async GETs.
// No storage, timers, business network writes or global mutable state.
export function createDetailRequestScope(getSelected) {
  let generation = 0;
  let current = () => null;
  return {
    begin(key) {
      const currentGeneration = ++generation;
      current = () => currentGeneration === generation && getSelected() === key ? key : null;
      return current;
    },
    current() { return current; }
  };
}
