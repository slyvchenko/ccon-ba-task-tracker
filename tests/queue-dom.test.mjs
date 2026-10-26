import test from 'node:test';
import assert from 'node:assert/strict';
import {queuePatchIndexes} from '../assets/queue-dom.mjs';

function entries(size) {
  const nodes=[{id:'group:0:active',html:'<div class="queue-group">Active sprint</div>'}];
  for(let i=0;i<size;i++) nodes.push({id:'task:CCON-'+i,
    html:'<button data-key="CCON-'+i+'">Synthetic '+i+'</button>'});
  return nodes;
}
test('100/500/1000 rows patch only modified content without replacing other accessible buttons',()=>{
  for(const size of [100,500,1000]) {
    const before=entries(size),after=before.map(x=>({...x}));
    after[Math.floor(size/2)].html+='<span class="badge">Reviewed</span>';
    assert.deepEqual(queuePatchIndexes(before,after),[Math.floor(size/2)]);
    assert.deepEqual(queuePatchIndexes(after,after),[]);
  }
});
test('rank/order, group boundaries, item insertion and empty state force full safe rebuild',()=>{
  const before=entries(100);
  assert.equal(queuePatchIndexes(null,before),null);
  assert.equal(queuePatchIndexes(before,before.slice(1)),null);
  const swapped=before.map(x=>({...x}));
  [swapped[1],swapped[2]]=[swapped[2],swapped[1]];
  assert.equal(queuePatchIndexes(before,swapped),null);
  const changedGroup=before.map(x=>({...x}));
  changedGroup[0].id='group:0:out-of-sprint';
  assert.equal(queuePatchIndexes(before,changedGroup),null);
});
