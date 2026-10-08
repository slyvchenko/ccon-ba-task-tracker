import test from 'node:test';
import assert from 'node:assert/strict';
import {createLogsController} from '../assets/logs.mjs';

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return {promise, resolve};
}

test('a late response for the previous task cannot overwrite the selected attachments', async () => {
  const first = deferred(), second = deferred();
  let selected = 'CCON-1', calls = 0;
  const panel = {innerHTML: ''};
  const controller = createLogsController({
    api: () => (++calls === 1 ? first.promise : second.promise),
    escapeHtml: value => String(value ?? ''), message: () => {},
    getSelected: () => selected, getElement: id => id === 'emailLogs' ? panel : null,
  });
  const oldRequest = controller.loadLogs();
  selected = 'CCON-2';
  const currentRequest = controller.loadLogs();
  second.resolve({items: [], emptyMessage: 'Current task', folder: 'CCON-2'});
  await currentRequest;
  first.resolve({items: [], emptyMessage: 'Previous task', folder: 'CCON-1'});
  await oldRequest;
  assert.match(panel.innerHTML, /Current task/);
  assert.doesNotMatch(panel.innerHTML, /Previous task/);
});

test('unchanged attachment metadata does not replace panel content or editor buffers', async () => {
  const nodes = {emailLogs: {innerHTML: ''}, draftBody: {value: 'My unsaved draft'}};
  const controller = createLogsController({api: async () => ({items: [], emptyMessage: 'Pending', folder: 'CCON-1'}),
    escapeHtml: value => String(value ?? ''), message: () => {}, getSelected: () => 'CCON-1',
    getElement: id => nodes[id] ?? null});
  await controller.loadLogs();
  nodes.emailLogs.innerHTML = 'Existing panel with focus';
  await controller.loadLogs();
  assert.equal(nodes.emailLogs.innerHTML, 'Existing panel with focus');
  assert.equal(nodes.draftBody.value, 'My unsaved draft');
});
