import test from 'node:test';
import assert from 'node:assert/strict';
import {createReconnectPolicy} from '../assets/reconnect-policy.mjs';

test('reconnection GET backoff bounded 5s, 10s, 20s, 40s, 60s',()=>{
  let now=1000;
  const p=createReconnectPolicy({clock:()=>now});
  assert.equal(p.shouldPoll(),true);
  for(const [i,delay] of [5000,10000,20000,40000,60000,60000].entries()){
    const result=p.failed();
    assert.equal(result.firstFailure,i===0);
    assert.equal(result.delay,delay);
    assert.equal(p.shouldPoll(),false);
    now+=delay-1;
    assert.equal(p.shouldPoll(),false);
    now+=1;
    assert.equal(p.shouldPoll(),true);
  }
  assert.equal(p.failures,6);
  assert.equal(p.recovered(),true);
  assert.equal(p.recovered(),false);
  assert.equal(p.failures,0);
  assert.equal(p.offline,false);
});

test('manual user reconnection events are allowed without resetting failure history',()=>{
  let time=123;
  const p=createReconnectPolicy({clock:()=>time});
  p.failed();
  assert.equal(p.shouldPoll(),false);
  assert.equal(p.shouldPoll({force:true}),true);
  assert.equal(p.failures,1);
  time+=5000;
  assert.equal(p.shouldPoll(),true);
});

test('configuration and state are pure, no POST/replay behavior',()=>{
  assert.throws(()=>createReconnectPolicy({baseMs:0}),/Invalid/);
  assert.throws(()=>createReconnectPolicy({baseMs:10000,maxMs:5000}),/Invalid/);
  const policy=createReconnectPolicy();
  assert.equal(typeof policy.replay,'undefined');
  assert.equal(typeof policy.post,'undefined');
  assert.equal(policy.offline,false);
});
