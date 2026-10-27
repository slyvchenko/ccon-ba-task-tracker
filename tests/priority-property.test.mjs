import test from 'node:test';
import assert from 'node:assert/strict';
import {rankTasks, priorityLane, actionRank, priorityEmail} from '../assets/task-rules.mjs';

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
test('seeded synthetic queue generator is reproducible',()=>{
  const a=seeded(2026),b=seeded(2026);
  assert.deepEqual(Array.from({length:25},()=>a()),
                   Array.from({length:25},()=>b()));
  assert.notEqual(a(),seeded(2027)());
});

test('fixed independent expected lane and WRITE order, with extreme priority scores',()=>{
  const create=(key,{sprint=false,signal='READY',manual='AUTO',active=true,score=50})=>({
    key,active,activeSprintStatus:'VERIFIED',activeSprint:sprint,
    manualStatus:manual,contextFingerprint:'same',blocking:false,
    analysis:{contextFingerprint:'same',signal,
      reasonUk:'Synthetic',nextActionUk:'Review',
      needsEmail:signal==='WRITE',queueScore:score}
  });
  const input=[
    create('CCON-16',{sprint:true,active:false,signal:'WRITE',score:100}),
    create('CCON-15',{sprint:false,signal:'READY',score:100}),
    create('CCON-13',{sprint:true,manual:'DONE',signal:'WRITE',score:100}),
    create('CCON-11',{sprint:true,signal:'READY',score:100}),
    create('CCON-14',{sprint:false,signal:'WRITE',score:0}),
    create('CCON-12',{sprint:true,signal:'WRITE',score:0})
  ];
  assert.deepEqual(rankTasks(input).map(x=>x.key),
    ['CCON-12','CCON-11','CCON-14','CCON-15','CCON-13','CCON-16']);
});

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

test('P0 exhaustive manual status × source freshness × email × sprint invariants',()=>{
  const statuses=['AUTO','IN PROGRESS','WAITING INPUT','WAITING DEPENDENCY','NEEDS DECISION','DONE'];
  const signals=['WRITE','READY','WAIT','REVIEW','DECIDE','DONE'];
  let checked=0;
  for(const manualStatus of statuses) for(const signal of signals)
    for(const needsEmail of [false,true]) for(const stale of [false,true])
      for(const confirmedSprint of [false,true]) {
        const item={
          key:'CCON-501',active:true,manualStatus,activeSprint:confirmedSprint,
          activeSprintStatus:'VERIFIED',contextFingerprint:'present',
          analysis:{signal,needsEmail,queueScore:100,
            contextFingerprint:stale?'previous':'present',reasonUk:'Synthetic',
            nextActionUk:'Review safely'}
        };
        const actualSignal={
          'IN PROGRESS':'READY','WAITING INPUT':'WAIT',
          'WAITING DEPENDENCY':'WAIT','NEEDS DECISION':'DECIDE','DONE':'DONE'
        }[manualStatus] || (stale?'REVIEW':signal);
        const shouldPrioritizeEmail=
          !['WAIT','DONE'].includes(actualSignal) &&
          manualStatus!=='NEEDS DECISION' &&
          (actualSignal==='WRITE' || (!stale && needsEmail));
        assert.equal(priorityEmail(item),shouldPrioritizeEmail,
          JSON.stringify({manualStatus,signal,needsEmail,stale,confirmedSprint}));
        const expectedRank=shouldPrioritizeEmail?0:
          ['READY','DECIDE'].includes(actualSignal)?1:
          actualSignal==='REVIEW'?2:actualSignal==='WAIT'?3:4;
        assert.equal(actionRank(item),expectedRank);
        assert.equal(priorityLane(item),
          manualStatus==='DONE'||actualSignal==='DONE' ? 2 : confirmedSprint?0:1);
        checked++;
      }
  assert.equal(checked,288);
});
