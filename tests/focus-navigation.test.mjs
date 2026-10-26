import test from 'node:test';
import assert from 'node:assert/strict';
import {shortcutAction, adjacentTaskKey, isTextEditingTarget, captureTaskView,
  restoreTaskView, captureEditorFocus, restoreEditorFocus, sanitizeSessionFocus, focusAfterAction}
  from '../assets/focus-navigation.mjs';

const event=(key,options={})=>({key,altKey:false,ctrlKey:false,metaKey:false,
  shiftKey:false,isComposing:false,repeat:false,...options});

test('shortcuts are deterministic and do not hijack typed fields or dialogs',()=>{
  assert.equal(shortcutAction(event('ArrowDown',{altKey:true})), 'NEXT');
  assert.equal(shortcutAction(event('ArrowUp',{altKey:true})), 'PREVIOUS');
  assert.equal(shortcutAction(event('c',{altKey:true})), 'COPY_ACTION');
  assert.equal(shortcutAction(event('/')), 'SEARCH');
  assert.equal(shortcutAction(event('Enter',{ctrlKey:true}),{editing:true}), 'SAVE');
  assert.equal(shortcutAction(event('Enter',{metaKey:true}),{editing:true}), 'SAVE');
  for(const key of ['ArrowDown','ArrowUp','c','/']){
    const modified=key==='/'?{}:{altKey:true};
    assert.equal(shortcutAction(event(key,modified),{editing:true}),null);
  }
  assert.equal(shortcutAction(event('Enter',{ctrlKey:true}),{editing:false}),null);
  assert.equal(shortcutAction(event('ArrowDown',{altKey:true}),{dialogOpen:true}),null);
  assert.equal(shortcutAction(event('ArrowDown',{altKey:true,isComposing:true})),null);
  assert.equal(shortcutAction(event('ArrowDown',{altKey:true,repeat:true})),null);
  assert.equal(shortcutAction(event('ArrowDown',{altKey:true,shiftKey:true})),null);
  assert.equal(shortcutAction(event('ArrowDown',{altKey:true,ctrlKey:true})),null);
  assert.equal(shortcutAction(event('Escape')),null);
});

test('editor detection handles text field, select, rich text, role textbox and keyboard button',()=>{
  for(const tagName of ['INPUT','TEXTAREA','SELECT'])
    assert.equal(isTextEditingTarget({tagName}),true);
  assert.equal(isTextEditingTarget({tagName:'DIV',isContentEditable:true}),true);
  assert.equal(isTextEditingTarget({tagName:'DIV',getAttribute:()=> 'textbox'}),true);
  assert.equal(isTextEditingTarget({tagName:'BUTTON'}),false);
  assert.equal(isTextEditingTarget(null),false);
});

test('navigation stays in the *currently filtered* queue and wraps; never reorders',()=>{
  const keys=['CCON-900','CCON-4','CCON-33'];
  assert.equal(adjacentTaskKey(keys,'CCON-900',1),'CCON-4');
  assert.equal(adjacentTaskKey(keys,'CCON-4',-1),'CCON-900');
  assert.equal(adjacentTaskKey(keys,'CCON-33',1),'CCON-900');
  assert.equal(adjacentTaskKey(keys,'unknown',1),'CCON-900');
  assert.equal(adjacentTaskKey(keys,'unknown',-1),'CCON-33');
  assert.equal(adjacentTaskKey([],null,1),null);
  assert.deepEqual(keys,['CCON-900','CCON-4','CCON-33']);
});

function fakeDetail(defs, scroll=0) {
  const nodes=defs.map(([id,label,open])=>({
    id,open,getAttribute:()=>null,closest:()=>({getAttribute:()=> 'Контекст'}),
    querySelector:()=>({textContent:label})
  }));
  return {scrollTop:scroll,nodes,querySelectorAll:()=>nodes};
}

test('expanded state restored by semantic heading even if sections shift order',()=>{
  const before=fakeDetail([['','Правила IF / THEN',true],['','Джерела',false],
                           ['custom-id','QA',true]],320);
  const captured=captureTaskView(before);
  const changed=fakeDetail([['','Новий пункт',true],['custom-id','QA',false],
                            ['','Джерела',true],['','Правила IF / THEN',false]],0);
  restoreTaskView(changed,captured);
  assert.equal(changed.scrollTop,320);
  assert.deepEqual(changed.nodes.map(x=>x.open),[true,true,false,true]);
});

test('caret restoration does not overwrite text, tracks textarea only',()=>{
  const old={id:'note',tagName:'TEXTAREA',selectionStart:6,selectionEnd:11,
    selectionDirection:'forward',scrollTop:24};
  const root={contains:node=>node===old};
  const saved=captureEditorFocus(old,root);
  let focusCount=0,range=null;
  const fresh={id:'note',value:'This is my private unsaved note',scrollTop:0,
    focus:()=>focusCount++,setSelectionRange:(...a)=>range=a};
  const newRoot={querySelector:selector=>selector==='#note'?fresh:null};
  assert.equal(restoreEditorFocus(newRoot,saved),true);
  assert.equal(focusCount,1);
  assert.deepEqual(range,[6,11,'forward']);
  assert.equal(fresh.scrollTop,24);
  assert.equal(fresh.value,'This is my private unsaved note');
  assert.equal(captureEditorFocus({id:'save'},root),null);
});

test('per-tab persisted view excludes note contents, PNR and invalid arbitrary keys',()=>{
  const dirtyNote='PRIVATE DO NOT PERSIST';
  const candidate={selected:'CCON-100',note:dirtyNote,
    views:{'CCON-100':{scroll:120,sections:[['QA',true]],note:dirtyNote},
           'malformed_key':{scroll:500,sections:[['H',true]]},
           'CCON-200':{scroll:-10,sections:[['Email',false]]}}};
  const safe=sanitizeSessionFocus(candidate);
  assert.deepEqual(Object.keys(safe.views),['CCON-100','CCON-200']);
  assert.equal(safe.views['CCON-200'].scroll,0);
  assert.equal(safe.selected,'CCON-100');
  assert.ok(!JSON.stringify(safe).includes(dirtyNote));
  assert.deepEqual(sanitizeSessionFocus({selected:'not-an-issue',views:null}),
    {selected:null,views:{}});
});

test('async handoff restores focus only to live, enabled and visible explicit action',()=>{
  let focused='';
  const nodes={
    bulkOpen:{disabled:true,isConnected:true,focus:()=>{focused='bulkOpen';}},
    bulkClose:{disabled:false,isConnected:true,focus:()=>{focused='bulkClose';}},
    email:{disabled:false,isConnected:false,focus:()=>{focused='email';}},
    draftBody:{disabled:false,isConnected:true,hidden:true,
      focus:()=>{focused='draftBody';}}
  };
  const root={getElementById:id=>nodes[id] || null};
  assert.equal(focusAfterAction(root,['bulkOpen','bulkClose']),true);
  assert.equal(focused,'bulkClose');
  nodes.bulkOpen.disabled=false;
  assert.equal(focusAfterAction(root,['bulkOpen','bulkClose']),true);
  assert.equal(focused,'bulkOpen');
  focused='';
  assert.equal(focusAfterAction(root,['email','draftBody']),false);
  assert.equal(focused,'');
  assert.equal(focusAfterAction(root,['../bad']),false);
  assert.equal(focusAfterAction(null,['bulkOpen']),false);
});
