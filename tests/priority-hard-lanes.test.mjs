import test from 'node:test';
import assert from 'node:assert/strict';
import {rankTasks,priorityLane,actionRank} from '../assets/task-rules.mjs';
import {quickWinCandidate} from '../assets/effort-planning.mjs';

const make=(key,sprint,signal,score,extra={})=>({
  key,summary:'Synthetic '+key,active:true,manualStatus:'AUTO',
  activeSprintStatus:'VERIFIED',activeSprint:sprint,
  contextFingerprint:'fresh',
  analysis:{signal,queueScore:score,reasonUk:'Synthetic test',
    nextActionUk:'Check documented condition',contextFingerprint:'fresh'},
  ...extra
});

test('P0 contract: every verified active-sprint item precedes every backlog task across scores',()=>{
 for(let score=0;score<=100;score+=5) {
  const input=[make('CCON-1',false,'WRITE',100),
               make('CCON-2',true,'WAIT',score)];
  assert.deepEqual(rankTasks(input).map(x=>x.key),['CCON-2','CCON-1']);
 }
});
test('P0 contract: WRITE always outranks READY within the same verified lane',()=>{
 for(let score=0;score<=100;score+=10) {
  const input=[make('CCON-1',true,'READY',100),
               make('CCON-2',true,'WRITE',score)];
  assert.deepEqual(rankTasks(input).map(x=>x.key),['CCON-2','CCON-1']);
 }
});
test('manual DONE never outranks any open backlog and unverified is never sprint',()=>{
 const input=[make('CCON-1',true,'READY',100,{manualStatus:'DONE'}),
              make('CCON-2',false,'READY',0),
              make('CCON-3',true,'WRITE',100,{activeSprintStatus:'NOT_CONFIGURED'})];
 const keys=rankTasks(input).map(x=>x.key);
 assert.equal(keys.at(-1),'CCON-1');
 assert.equal(keys[0],'CCON-3'); // WRITE within outside-sprint lane still precedes READY
 assert.equal(priorityLane(input[2]),1);
});
test('quick-task heuristic cannot change queue order, task state or source score',()=>{
 const input=[make('CCON-1',true,'READY',75),make('CCON-2',false,'WRITE',100)];
 const before=structuredClone(input);
 const ranks=rankTasks(input).map(x=>x.key);
 input.forEach(x=>quickWinCandidate(x));
 assert.deepEqual(rankTasks(input).map(x=>x.key),ranks);
 assert.deepEqual(input,before);
});
