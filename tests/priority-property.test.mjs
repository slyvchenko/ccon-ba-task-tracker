import test from 'node:test';
import assert from 'node:assert/strict';
import {rankTasks, priorityLane, actionRank} from '../assets/task-rules.mjs';

// PRIOR-03: deterministic property-style synthetic queue invariants, no real Jira.
function seeded(seed=0x5f3759df) {
  let state=seed>>>0;
  return ()=>{state=(Math.imul(1664525,state)+1013904223)>>>0;return state/4294967296;};
}
function task(n,rng) {
  const signal=['WRITE','READY','WAIT','REVIEW','DECIDE','DONE'][Math.floor(rng()*6)];
  const active=rng()>.1;
  const manualStatus=['AUTO','AUTO','AUTO','WAITING INPUT','DONE'][Math.floor(rng()*5)];
  return {
    key:'CCON-'+(n+1),summary:'Synthetic NDC '+n,active,manualStatus,
    activeSprintStatus:rng()>.2?'VERIFIED':'UNVERIFIED',
    activeSprint:rng()>.5,blocking:rng()>.8,manualEffort:['XS','M','XL'][Math.floor(rng()*3)],
    contextFingerprint:'current',analysis:{
      signal,contextFingerprint:'current',reasonUk:'Known synthetic evidence',
      nextActionUk:'Manual review',needsEmail:signal==='WRITE'&&rng()>.5,
      queueScore:Math.floor(rng()*101)
    }
  };
}
test('verified sprint, WRITE, Done, archive are ordered for 300 seeded randomized queues',()=>{
  const rng=seeded(), lanes=new Set();
  for(let run=0;run<300;run++) {
    const inputs=Array.from({length:10+Math.floor(rng()*45)},(_,i)=>task(i,rng));
    const ranked=rankTasks(inputs);
    assert.deepEqual([...ranked].map(x=>x.key).sort(),inputs.map(x=>x.key).sort());
    for(let i=1;i<ranked.length;i++) {
      const before=ranked[i-1],after=ranked[i],laneBefore=priorityLane(before),laneAfter=priorityLane(after);
      assert.ok(laneBefore<=laneAfter,'active sprint/Done/archive lane must not be crossed');
      if(laneBefore===laneAfter)
        assert.ok(actionRank(before)<=actionRank(after),'WRITE/action tier invariant');
      lanes.add(laneBefore);
    }
    const effortChanged=inputs.map(x=>({...x,manualEffort:x.manualEffort==='XS'?'XL':'XS'}));
    assert.deepEqual(rankTasks(effortChanged).map(x=>x.key),ranked.map(x=>x.key),
      'subjective effort must never silently reorder the primary queue');
  }
  assert.deepEqual([...lanes].sort(),[0,1,2,3]);
});
