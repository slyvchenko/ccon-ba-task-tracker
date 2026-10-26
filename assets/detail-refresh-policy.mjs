// A queue import may update 999 OTHER tasks without changing the open detail.
// The detail template does not read snapshot-level metadata, so key its DOM,
// evidence, questions, decisions and history to the selected task's content.
export function detailContentFingerprint(task) {
  return task ? JSON.stringify(task) : '';
}

// Stale responses for the SAME key must not write into a newer render.
// Every render gets a new generation, and a closure used by its async GETs.
// No storage, timers, business network writes or global mutable state.
export function createDetailRequestScope(getSelected) {
  let generation = 0;
  return {
    begin(key) {
      const currentGeneration = ++generation;
      return () => currentGeneration === generation && getSelected() === key ? key : null;
    }
  };
}
