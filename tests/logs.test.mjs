import test from 'node:test';
import assert from 'node:assert/strict';
import {createLogsController, zipStatusText} from '../assets/logs.mjs';

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


test('ZIP readiness is rendered in the current email block without mode switching', () => {
  const escape = v => String(v ?? '').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
  const result = zipStatusText({state:'PARTIAL',reasonCode:'SOME_FLOWS_NOT_READY',
    flows:[{flowId:'11111111-2222-4333-8444-555555555555',state:'READY'},
           {flowId:'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',state:'PENDING'}]}, escape);
  assert.match(result, /Частково готово/);
  assert.match(result, /Готово/);
  assert.match(result, /Очікує ZIP/);
  assert.match(result, /Не всі приклади оброблені/);
});
test('damaged or sign-in HTML does not display READY, names get escaped', () => {
  const escape = v => String(v ?? '').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
  const text = zipStatusText({state:'FAILED',
    reasonCode:'NOT_ZIP_SIGNIN_OR_ERROR_PAGE',
    flows:[{flowId:'<script>alert(1)',state:'FAILED'}]}, escape);
  assert.match(text, /Помилка ZIP/);
  assert.match(text, /сторінку входу/);
  assert.doesNotMatch(text, /<script>/);
  assert.match(text, /&lt;script/);
});
