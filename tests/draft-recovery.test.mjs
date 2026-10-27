import test from 'node:test';
import assert from 'node:assert/strict';
import {createDraftRecoveryStore,sanitizeDraftMap,TAB_ID_KEY,RECORD_PREFIX,
  LEGACY_DRAFT_KEY,RETENTION_DAYS} from '../assets/draft-recovery.mjs';

class FakeStorage {
  constructor() {this.items=new Map();this.failWrites=false;}
  get length(){return this.items.size;}
  key(n){return [...this.items.keys()][n]??null;}
  getItem(k){return this.items.get(k)??null;}
  setItem(k,v){if(this.failWrites)throw Error('quota/private-mode');this.items.set(k,String(v));}
  removeItem(k){if(this.failWrites)throw Error('quota/private-mode');this.items.delete(k);}
}
const ids=[
  '00000000-0000-4000-8000-000000000001',
  '00000000-0000-4000-8000-000000000002',
  '00000000-0000-4000-8000-000000000003'
];
const record=(value='important text',revision=3)=>({
  manualStatus:'IN PROGRESS',manualEffort:'S',note:value,
  emailDraft:{to:'fake@example.invalid',subject:'Synthetic',body:'Test body'},
  baseRevision:revision,changedAt:'2026-10-25T10:00:00Z'
});
const clock={time:Date.parse('2026-10-25T13:00:00Z')};
const store=(local,session,id)=>createDraftRecoveryStore({
  local,session,newId:()=>id,now:()=>clock.time
});

test('two independent tabs cannot overwrite one shared unsaved forms key',()=>{
  const local=new FakeStorage(),a=store(local,new FakeStorage(),ids[0]);
  const b=store(local,new FakeStorage(),ids[1]);
  assert.deepEqual(a.load(),{});
  assert.deepEqual(b.load(),{});
  assert.equal(a.persist({'CCON-1':record('draft A')}),true);
  assert.equal(b.persist({'CCON-1':record('draft B')}),true);
  assert.notEqual(a.ownKey(),b.ownKey());
  assert.deepEqual(store(local,new FakeStorage(),ids[0]).load()['CCON-1'].note,'draft A');
  assert.deepEqual(store(local,new FakeStorage(),ids[1]).load()['CCON-1'].note,'draft B');
  b.persist({});
  assert.equal(a.load()['CCON-1'].note,'draft A');
  assert.equal(local.getItem(LEGACY_DRAFT_KEY),null);
});

test('a reload in the same tab preserves its ID, fields and original CAS token',()=>{
  const local=new FakeStorage(),session=new FakeStorage();
  const a=store(local,session,ids[0]);
  const payload={'CCON-2':record('do not lose',17)};
  assert.equal(a.persist(payload),true);
  const b=store(local,session,ids[1]);
  assert.equal(b.id,ids[0]);
  assert.deepEqual(b.load(),payload);
  assert.equal(b.load()['CCON-2'].baseRevision,17);
});

test('cloned session ID rotation creates a separate copy and leaves original intact',()=>{
  const local=new FakeStorage(),session=new FakeStorage();
  const original=store(local,session,ids[0]);
  original.persist({'CCON-9':record('first tab')});
  const duplicated=new FakeStorage();
  duplicated.setItem(TAB_ID_KEY,ids[0]);
  const copy=store(local,duplicated,ids[1]);
  assert.equal(copy.load()['CCON-9'].note,'first tab');
  assert.equal(copy.rotateTabId(),true);
  assert.equal(copy.id,ids[1]);
  assert.equal(duplicated.getItem(TAB_ID_KEY),ids[1]);
  copy.persist({'CCON-9':record('second tab')});
  assert.equal(original.load()['CCON-9'].note,'first tab');
  assert.equal(copy.load()['CCON-9'].note,'second tab');
});

test('legacy v2 drafts migrated only after successful v3 tab storage',()=>{
  const local=new FakeStorage(),old={'CCON-4':record('legacy notes',11)};
  local.setItem(LEGACY_DRAFT_KEY,JSON.stringify(old));
  const a=store(local,new FakeStorage(),ids[0]);
  assert.deepEqual(a.load(),old);
  assert.equal(local.getItem(LEGACY_DRAFT_KEY),null);
  assert.deepEqual(a.load(),old);
});

test('quota and denied storage must never claim durable recovery',()=>{
  const local=new FakeStorage(),session=new FakeStorage();
  const a=store(local,session,ids[0]);
  local.failWrites=true;
  assert.equal(a.persist({'CCON-1':record()}),false);
  assert.equal(a.error,'WRITE_FAILED');
  local.failWrites=false;
  assert.equal(a.persist({'CCON-1':record()}),true);
  const denied=new FakeStorage();
  denied.failWrites=true;
  const x=store(local,denied,ids[1]);
  assert.equal(x.id,null);
  assert.equal(x.persist({'CCON-5':record()}),false);
  assert.equal(x.error,'STORAGE_DENIED');
});

test('over-100 draft maps fail rather than silently dropping the last task',()=>{
  const local=new FakeStorage(),a=store(local,new FakeStorage(),ids[0]);
  assert.equal(a.persist({'CCON-1':record('original durable draft')}),true);
  const before=local.getItem(a.ownKey());
  const oversized=Object.fromEntries(
    Array.from({length:101},(_,i)=>['CCON-'+(i+1),record('draft '+i)]));
  assert.equal(a.persist(oversized),false);
  assert.equal(a.error,'CAPACITY_EXCEEDED');
  assert.equal(local.getItem(a.ownKey()),before);
});

test('legacy migration never deletes a record exceeding the task limit',()=>{
  const local=new FakeStorage();
  const oversized=Object.fromEntries(
    Array.from({length:101},(_,i)=>['CCON-'+(i+1),record('legacy '+i)]));
  const original=JSON.stringify(oversized);
  local.setItem(LEGACY_DRAFT_KEY,original);
  const a=store(local,new FakeStorage(),ids[0]);
  assert.deepEqual(a.load(),{});
  assert.equal(a.error,'CAPACITY_EXCEEDED');
  assert.equal(local.getItem(LEGACY_DRAFT_KEY),original);
  assert.equal(local.getItem(a.ownKey()),null);
});

test('manually recovering another tab skips existing/dirty task keys without deleting source',()=>{
  const local=new FakeStorage(),a=store(local,new FakeStorage(),ids[0]);
  const b=store(local,new FakeStorage(),ids[1]);
  a.persist({'CCON-1':record('external'), 'CCON-2':record('other')});
  b.persist({'CCON-1':record('current')});
  const result=b.adopt(a.id,b.load(),['CCON-4']);
  assert.deepEqual(Object.keys(result.added),['CCON-2']);
  assert.deepEqual(result.skipped,['CCON-1']);
  assert.equal(b.load()['CCON-1'].note,'current');
  assert.equal(b.load()['CCON-2'].note,'other');
  assert.equal(a.load()['CCON-2'].note,'other');
});

test('30-day retention never deletes drafts automatically; manual cleanup only removes other tab',()=>{
  const local=new FakeStorage(),a=store(local,new FakeStorage(),ids[0]);
  const b=store(local,new FakeStorage(),ids[1]);
  a.persist({'CCON-1':record('aged')});
  clock.time += (RETENTION_DAYS+1)*86400000;
  b.persist({'CCON-2':record('new')});
  assert.equal(b.others().length,1);
  assert.equal(b.others()[0].stale,true);
  assert.equal(a.load()['CCON-1'].note,'aged');
  const done=b.clearExpired();
  assert.deepEqual(done,{cleared:1,remaining:0});
  assert.equal(a.load()['CCON-1'],undefined);
  assert.equal(b.load()['CCON-2'].note,'new');
  clock.time=Date.parse('2026-10-25T13:00:00Z');
});

test('private payload validation forbids arbitrary identifiers, oversized inputs and invalid schema',()=>{
  const sample={
    'CCON-1':record('normal'),
    'ES8SQX':record('unsafe unknown key'),
    '__proto__':record('fake'),
    'CCON-2':{...record(),note:'n'.repeat(20001)},
    'CCON-3':{...record(),emailDraft:{...record().emailDraft,body:'x'.repeat(50001)}},
    'CCON-4':{...record(),manualStatus:'SENT'},
    'CCON-5':{...record(),baseRevision:Infinity}
  };
  const sanitized=sanitizeDraftMap(sample);
  assert.deepEqual(Object.keys(sanitized),['CCON-1','CCON-5']);
  assert.equal(sanitized['CCON-5'].baseRevision,null);
  const local=new FakeStorage(),a=store(local,new FakeStorage(),ids[0]);
  assert.equal(a.persist(sample),true);
  assert.ok(local.getItem(a.ownKey()).includes('normal'));
  assert.ok(!local.getItem(a.ownKey()).includes('unsafe unknown key'));
});

test('invalid/wrong format or malformed record does not crash a second tab recovery listing',()=>{
  const local=new FakeStorage(),a=store(local,new FakeStorage(),ids[0]);
  local.setItem(RECORD_PREFIX+ids[1],'{bad json');
  local.setItem(RECORD_PREFIX+ids[2],JSON.stringify({version:1,forms:{'CCON-1':record()}}));
  assert.deepEqual(a.others(),[]);
  assert.deepEqual(a.adopt(ids[1]),{added:{},skipped:[]});
});

test('a failure writing merged recovery cannot claim restored items',()=>{
  const local=new FakeStorage(),a=store(local,new FakeStorage(),ids[0]);
  const b=store(local,new FakeStorage(),ids[1]);
  a.persist({'CCON-1':record('source')});
  local.failWrites=true;
  const result=b.adopt(a.id,{});
  assert.equal(result.failed,true);
  assert.deepEqual(result.added,{});
  local.failWrites=false;
  assert.equal(b.load()['CCON-1'],undefined);
  assert.equal(a.load()['CCON-1'].note,'source');
});
