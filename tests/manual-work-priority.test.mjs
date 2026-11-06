import test from 'node:test';
import assert from 'node:assert/strict';
import {rankTasks, workPriority, workPriorityRank, supportPriorityLabel, filterTasks} from '../assets/task-rules.mjs';

const make = (key, opts={}) => ({
  key, summary:'Synthetic '+key, active:true, manualStatus:'AUTO',
  activeSprintStatus:'VERIFIED', activeSprint:false, labels:[],
  contextFingerprint:'fresh', analysis:{
    signal:'READY', queueScore:60, reasonUk:'Test evidence',
    nextActionUk:'Investigate', contextFingerprint:'fresh'
  }, ...opts
});

test('P1 business > P2 urgent > P3 tech support > unchanged sprint/AI lane', () => {
  const items = [
    make('CCON-10', {activeSprint:true,analysis:{signal:'WRITE',queueScore:100,reasonUk:'test',nextActionUk:'act'}}),
    make('CCON-20', {labels:['AIS_Prio_Bug']}),
    make('CCON-30', {manualPriority:'URGENT',activeSprint:false}),
    make('CCON-40', {manualPriority:'BUSINESS',activeSprint:false})
  ];
  assert.deepEqual(rankTasks(items).map(t=>t.key), ['CCON-40','CCON-30','CCON-20','CCON-10']);
  assert.deepEqual(items.map(workPriorityRank), [3,2,1,0]);
  assert.deepEqual(items.map(workPriority), ['STANDARD','SUPPORT','URGENT','BUSINESS']);
});

test('Jira support label is exact normalized token, not a loose substring', () => {
  for (const alias of ['AIS_Prio_Bug','AIS-PrioBug','ais prio bug','AIS_PRIOR_BUG','AIS Priority Bug'])
    assert.equal(supportPriorityLabel(make('CCON-1',{labels:[alias]})), alias);
  for (const other of ['prio-bug','Other_AIS_Prio_Bug','AIS_prio_bug_later','AIS',''])
    assert.equal(supportPriorityLabel(make('CCON-2',{labels:[other]})), '');
  assert.equal(supportPriorityLabel(make('CCON-3',{labels:'AIS_Prio_Bug'})), '');
});

test('manual priority overrides Jira label without changing Jira fields', () => {
  const task=make('CCON-1',{labels:['AIS_Prio_Bug'],manualPriority:'URGENT'});
  const snapshot=structuredClone(task);
  assert.equal(workPriority(task),'URGENT');
  rankTasks([task]);
  assert.deepEqual(task,snapshot);
});

test('manual DONE and archived work never promoted above active open tasks', () => {
  const ranked=rankTasks([
    make('CCON-1',{manualPriority:'BUSINESS',manualStatus:'DONE'}),
    make('CCON-2',{manualPriority:'BUSINESS',active:false}),
    make('CCON-3',{manualPriority:'URGENT'}),
    make('CCON-4',{labels:['AIS_Prio_Bug']}),
    make('CCON-5',{})
  ]);
  assert.deepEqual(ranked.map(t=>t.key),['CCON-3','CCON-4','CCON-5','CCON-1','CCON-2']);
});

test('existing score and verified-sprint lanes still rank standard work', () => {
  const tasks=[
    make('CCON-10',{activeSprint:false,analysis:{signal:'WRITE',queueScore:100,reasonUk:'r',nextActionUk:'a'}}),
    make('CCON-20',{activeSprint:true,analysis:{signal:'WAIT',queueScore:0,reasonUk:'r',nextActionUk:'a'}})
  ];
  assert.deepEqual(rankTasks(tasks).map(t=>t.key),['CCON-20','CCON-10']);
});

test('priority filter exposes four exclusive buckets', () => {
  const tasks=[
    make('CCON-1',{manualPriority:'BUSINESS'}),
    make('CCON-2',{manualPriority:'URGENT'}),
    make('CCON-3',{labels:['AIS_Prio_Bug']}),
    make('CCON-4',{})
  ];
  for(const [priority,key] of [['BUSINESS','CCON-1'],['URGENT','CCON-2'],
    ['SUPPORT','CCON-3'],['STANDARD','CCON-4']])
    assert.deepEqual(filterTasks(tasks,{priority}).map(t=>t.key),[key]);
  assert.equal(filterTasks(tasks,{priority:'all'}).length,4);
});
