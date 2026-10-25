import test from 'node:test';import assert from 'node:assert/strict';
import {advancedFilterSummary,evidenceSectionLabel} from '../assets/progressive-layout.mjs';
import {filterTasks,rankTasks} from '../assets/task-rules.mjs';
test('active filters are never silently hidden behind collapsed control',()=>{
 assert.equal(advancedFilterSummary({signal:'all',sprint:'all'}),'');
 assert.match(advancedFilterSummary({signal:'WRITE',sprint:'all'}),/1 активний/);
 assert.match(advancedFilterSummary({signal:'WRITE',sprint:'active'}),/2 активні/);
});
test('source evidence count stays discoverable in a native disclosure',()=>{
 assert.match(evidenceSectionLabel(0),/не додані/);
 assert.match(evidenceSectionLabel(5),/\(5\)/);
});
test('visual grouping never changes canonical active-sprint priority sorting or signal filter semantics',()=>{
 const input=[{key:'CCON-1',active:true,activeSprint:true,activeSprintStatus:'VERIFIED',manualStatus:'AUTO',
  contextFingerprint:'same',analysis:{contextFingerprint:'same',signal:'WRITE',reasonUk:'why',nextActionUk:'write',queueScore:1}},
  {key:'CCON-2',active:true,activeSprint:false,activeSprintStatus:'VERIFIED',manualStatus:'AUTO',
  contextFingerprint:'same',analysis:{contextFingerprint:'same',signal:'READY',reasonUk:'why',nextActionUk:'check',queueScore:99}}];
 assert.deepEqual(rankTasks(input).map(x=>x.key),['CCON-1','CCON-2']);
 assert.deepEqual(filterTasks(rankTasks(input),{search:'',filter:'open',signal:'WRITE',sprint:'active'}).map(x=>x.key),['CCON-1']);
});
