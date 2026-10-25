import test from 'node:test';
import assert from 'node:assert/strict';
import {createQueueModel, createSearchDebouncer, selectedAfterFilter} from '../assets/queue-performance.mjs';
import {rankTasks,filterTasks} from '../assets/task-rules.mjs';

function syntheticItems(count) {
  return Array.from({length:count},(_,index)=>{
    const key='CCON-'+(1000+index);
    const signal=['WRITE','READY','REVIEW','WAIT','DECIDE'][index%5];
    return {
      key,active:index%11!==0,summary:'Synthetic NDC flow '+index,
      manualStatus:index%17===0?'WAITING INPUT':'AUTO',
      activeSprintStatus:index%9===0?'UNVERIFIED':'VERIFIED',
      activeSprint:index%2===0,blocking:index%13===0,
      contextFingerprint:'current',
      jiraStatus:index%3===0?'In Progress':'Open',priority:'High',
      analysis:{
        contextFingerprint:'current',signal,reasonUk:'Synthetic only',
        nextActionUk:'Перевірити StatusCode і DeliveryStatusCode '+index,
        queueScore:(index*7)%101,needsEmail:signal==='WRITE',
        standardDescription:'IF StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED THEN omit SegmentRefID. '.repeat(18),
        briefing:{technicalScopeUk:'Reshop search multi-city',
          currentUk:'REST rules',targetUk:'Supplier response',
          rules:[{whenUk:'StatusCode=CANCELLED',thenUk:'Do not return segment'}]},
      },links:[{linkedKey:'CCON-'+(2000+index)}],blockedBy:[]
    };
  });
}

test('cached queue returns EXACT legacy rankings and search matches across 100/500/1000',()=>{
  for(const size of [100,500,1000]){
    const tasks=syntheticItems(size),cache=createQueueModel();
    const baseline=rankTasks(tasks);
    assert.deepEqual(cache.rankedTasks(tasks).map(x=>x.key),baseline.map(x=>x.key));
    const combinations=[];
    for(const search of ['', 'StatusCode', 'Delivery Status Code', 'CCON-10',
      'RESHOP', 'CANCELLED AND', 'Supplier response', 'a username not in corpus']){
      for(const filter of ['open','all','done','archive'])
        for(const sprint of ['all','active','outside','unverified'])
          combinations.push({search,filter,sprint,signal:'all'});
    }
    for(const options of combinations){
      const expected=filterTasks(baseline,options).map(x=>x.key);
      const actual=cache.visibleTasks(tasks,options).map(x=>x.key);
      assert.deepEqual(actual,expected,'size='+size+' '+JSON.stringify(options));
    }
    assert.equal(cache.stats.rankingBuilds,1);
    assert.equal(cache.rankedTasks(tasks),cache.rankedTasks(tasks));
  }
});

test('cache builds large normalized description once per task and only after real search',()=>{
  const model=createQueueModel(),items=syntheticItems(1000);
  model.visibleTasks(items,{search:''});
  assert.equal(model.stats.indexBuilds,0);
  model.visibleTasks(items,{search:'StatusCode'});
  const built=model.stats.indexBuilds;
  assert.ok(built>0 && built<=1000);
  model.visibleTasks(items,{search:'DeliveryStatusCode'});
  model.visibleTasks(items,{search:'SegmentRefID'});
  assert.equal(model.stats.indexBuilds,built);
  const first=model.visibleTasks(items,{search:'SegmentRefID'});
  assert.strictEqual(first,model.visibleTasks(items,{search:'SegmentRefID'}));
  model.invalidate();
  model.visibleTasks(items,{search:'SegmentRefID'});
  assert.equal(model.stats.rankingBuilds,2);
  assert.ok(model.stats.indexBuilds>built);
});

test('task manual status edit invalidates rank only on explicit mutation',()=>{
  const tasks=syntheticItems(10);
  const cache=createQueueModel();
  const initial=cache.rankedTasks(tasks).map(x=>x.key);
  // Change the CURRENT highest-priority active task, not an already archived
  // row at the bottom: the mutation must have an observable rank effect.
  const edited=tasks.find(item=>item.key===initial[0]);
  assert.ok(edited.active);
  edited.manualStatus='DONE';
  // Caller must invalidate on persisted manual write before rebuilding.
  cache.invalidate();
  const expected=rankTasks(tasks).map(x=>x.key);
  assert.deepEqual(cache.rankedTasks(tasks).map(x=>x.key),expected);
  assert.notDeepEqual(initial,expected);
});

test('new snapshot object identities invalidate all previous search tokens',()=>{
  const model=createQueueModel(),first=syntheticItems(100);
  const before=model.visibleTasks(first,{search:'original'}).length;
  const changed=structuredClone(first);
  changed[1].summary='original';
  assert.equal(before,0);
  assert.ok(model.visibleTasks(changed,{search:'original'}).length>0);
  assert.equal(model.stats.rankingBuilds,2);
});

test('pending text search plus new snapshot selects a visible row unless dirty editor is protected',()=>{
  const source=[{key:'CCON-1'},{key:'CCON-2'}];
  const matched=[source[1]];
  assert.equal(selectedAfterFilter(matched,'CCON-1'),'CCON-2');
  assert.equal(selectedAfterFilter(matched,'CCON-1',{protectEditor:true}),'CCON-1');
  assert.equal(selectedAfterFilter([], 'CCON-1'),null);
  assert.equal(selectedAfterFilter(source,'CCON-1'),'CCON-1');
  assert.equal(selectedAfterFilter(source,null),'CCON-1');
});
test('debouncer combines rapid search edits, flushes on navigation, and can cancel',()=>{
  let next=0,callbacks=new Map(),processed=0;
  const schedule=fn=>{const id=++next;callbacks.set(id,fn);return id};
  const cancel=id=>callbacks.delete(id);
  const debounce=createSearchDebouncer(()=>processed++,130,schedule,cancel);
  debounce.schedule();debounce.schedule();debounce.schedule();
  assert.equal(callbacks.size,1);
  assert.equal(debounce.pending(),true);
  assert.equal(debounce.flush(),true);
  assert.equal(processed,1);
  assert.equal(callbacks.size,0);
  assert.equal(debounce.flush(),false);
  debounce.schedule();
  debounce.cancel();
  assert.equal(callbacks.size,0);
  debounce.schedule();
  const id=[...callbacks.keys()][0];const tick=callbacks.get(id);
  callbacks.delete(id);tick();
  assert.equal(processed,2);
  assert.equal(debounce.pending(),false);
});
