import test from 'node:test';import assert from 'node:assert/strict';
import {handoffCopyPolicy,mailActionLabels} from '../assets/handoff-ui-policy.mjs';
test('one primary copy when structural QA passes, local approval remains separate',()=>{
 const info=handoffCopyPolicy({description:'Synthetic document',readyForCopy:true,
  qualityState:'STRUCTURALLY_VERIFIED'});
 assert.equal(info.showFastCopy,true);
 assert.equal(info.fastEnabled,true);
 assert.equal(info.showFallbackCopy,false);
 assert.match(info.approvalLabel,/локально/);
});
test('unverified and BLOCKED source still visible for manual internal rework only',()=>{
 for(const state of ['UNVERIFIED','NEEDS_REVIEW','BLOCKED']){
  const info=handoffCopyPolicy({description:'Synthetic',readyForCopy:false,qualityState:state});
  assert.equal(info.showFastCopy,true);
  assert.equal(info.fastEnabled,false);
  assert.equal(info.showFallbackCopy,true);
  assert.match(info.fallbackLabel,/неперевірено/);
  assert.match(info.warning, state==='BLOCKED'?/блокує/:/не підтверджена/);
 }
});
test('missing description never exposes a copy action',()=>{
 const info=handoffCopyPolicy({description:' ',readyForCopy:true});
 assert.equal(info.showFastCopy,false);
 assert.equal(info.fastEnabled,false);
 assert.equal(info.showFallbackCopy,false);
});
test('mail verbs distinguish copy and open, never imply sent',()=>{
 const local=mailActionLabels(false);
 assert.match(local.copy,/Скопіювати/);
 assert.match(local.open,/без надсилання/);
 assert.ok(!local.open.includes('Надіслати'));
 assert.match(mailActionLabels(true).open,/Зберегти й скопіювати/);
 assert.match(local.batch,/Пакет/);
});
