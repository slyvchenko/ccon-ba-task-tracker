import test from 'node:test';
import assert from 'node:assert/strict';
import {effectiveSignal, filterTasks, priorityLane, signalInfo} from '../assets/task-rules.mjs';

const issue = (extra={}) => ({key:'CCON-1', active:true, manualStatus:'AUTO',
  localCompletionEnabled:false, statusCategory:'new',
  activeSprint:true, activeSprintStatus:'VERIFIED',
  analysis:{signal:'READY', reasonUk:'Перевірено', nextActionUk:'Звірити mapping'}, ...extra});

test('disabled local completion cannot hide a Jira-open sprint task or suppress its action', () => {
  const task=issue({manualStatus:'DONE'});
  assert.equal(effectiveSignal(task),'READY');
  assert.equal(signalInfo(task).label,'Можна працювати');
  assert.equal(priorityLane(task),0);
  assert.deepEqual(filterTasks([task]),[task]);
});
test('AI completion is not Jira completion; actual Jira done is excluded', () => {
  const aiDone=issue({analysis:{signal:'DONE', reasonUk:'Старе', nextActionUk:'Перевірити'}});
  assert.equal(effectiveSignal(aiDone),'REVIEW');
  assert.deepEqual(filterTasks([aiDone]),[aiDone]);
  const jiraDone=issue({statusCategory:'done',manualStatus:'IN PROGRESS'});
  assert.equal(effectiveSignal(jiraDone),'DONE');
  assert.deepEqual(filterTasks([jiraDone]),[]);
});
