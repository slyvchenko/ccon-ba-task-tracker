import test from 'node:test';
import assert from 'node:assert/strict';
import {EFFORT_LABELS,effortSuggestion,effortInfo,quickWinCandidate,quickWinExplanation,safeQuickWinGroups}
  from '../assets/effort-planning.mjs';
import {rankTasks,priorityLane,actionRank} from '../assets/task-rules.mjs';

function task(key, options={}) {
  const defaults={
    key,active:true,activeSprintStatus:'VERIFIED',activeSprint:true,
    manualStatus:'AUTO',manualEffort:'UNKNOWN',blocking:false,contextFingerprint:'current',
    summary:'Synthetic issue '+key,
    analysis:{
      contextFingerprint:'current',signal:'READY',reasonUk:'Known synthetic source',
      nextActionUk:'Review conditional REST response.',queueScore:50,needsEmail:false,
      standardDescription:'#### To Do\nUse exact REST field names.\n#### QA\nCheck positive and negative.',
      missingInfo:[],briefing:{unknownsUk:[],rules:[]},
      qualityGate:{state:'STRUCTURALLY_VERIFIED'},
      emailDraft:{to:'',subject:'',body:''}
    }
  };
  return {...defaults,...options,analysis:{...defaults.analysis,...(options.analysis||{})}};
}

test('manual effort bands and provenance do not masquerade as Jira priority',()=>{
  for(const band of ['XS','S','M','L','XL']){
    const entry=task('CCON-1',{manualEffort:band});
    const info=effortInfo(entry);
    assert.equal(info.band,band);
    assert.equal(info.source,'MANUAL');
    assert.equal(info.confidence,'USER_SELECTED');
    assert.equal(info.label,EFFORT_LABELS[band]);
    assert.deepEqual(effortSuggestion(entry),{band:'S',
      reason:'Є структурно перевірена чернетка, її потрібно звірити з фактами.'});
  }
  assert.equal(effortInfo(task('CCON-1')).source,'HEURISTIC');
  assert.equal(effortInfo(task('CCON-1')).confidence,'LOW');
});

test('unknown, stale, waiting and done task effort does not invent completion time',()=>{
  const stale=task('CCON-10',{analysis:{contextFingerprint:'old'}});
  const wait=task('CCON-11',{manualStatus:'WAITING INPUT'});
  const done=task('CCON-12',{manualStatus:'DONE'});
  const archived=task('CCON-13',{active:false});
  for(const entry of [stale,wait,done,archived]){
    assert.equal(effortInfo(entry).band,'UNKNOWN');
    assert.equal(quickWinCandidate(entry),false);
  }
});

test('large/complex and uncertain tasks receive conservative, marked-low-confidence suggestion',()=>{
  const complex=task('CCON-50',{analysis:{briefing:{rules:Array.from({length:9},(_,i)=>({id:'R'+i})),unknownsUk:[]}}});
  const uncertain=task('CCON-51',{analysis:{missingInfo:['A','B','C'],qualityGate:{state:'BLOCKED'}}});
  const review=task('CCON-52',{analysis:{signal:'REVIEW'}});
  const noProof=task('CCON-53',{analysis:{qualityGate:{state:'NEEDS_REVIEW'}}});
  assert.equal(effortInfo(complex).band,'XL');
  assert.equal(effortInfo(uncertain).band,'L');
  assert.equal(effortInfo(review).band,'L');
  assert.equal(effortInfo(noProof).band,'UNKNOWN');
  for(const entry of [complex,uncertain,review,noProof]) assert.equal(quickWinCandidate(entry),false);
});

test('prepared email can be a small hypothetical task, unprepared or proof-missing cannot',()=>{
  const ready=task('CCON-80',{analysis:{signal:'WRITE',needsEmail:true,
    emailDraft:{to:'synthetic@example.invalid',subject:'Synthetic',body:'Ask test question'}}});
  assert.equal(effortInfo(ready).band,'S');
  assert.equal(quickWinCandidate(ready),true);
  assert.match(quickWinExplanation(ready),/гіпотеза/);
  const unprepared=task('CCON-81',{analysis:{signal:'WRITE',needsEmail:true}});
  assert.equal(effortInfo(unprepared).band,'M');
  assert.equal(quickWinCandidate(unprepared),false);
  assert.equal(quickWinExplanation(unprepared),'');
});

test('a manually short task is NOT automatically safe to copy or quick if sources are missing',()=>{
  const blocked=task('CCON-90',{manualEffort:'XS',analysis:{qualityGate:{state:'BLOCKED'}}});
  const unknown=task('CCON-91',{manualEffort:'XS',analysis:{missingInfo:['missing confirmation']}});
  const verified=task('CCON-92',{manualEffort:'XS'});
  assert.equal(quickWinCandidate(blocked),false);
  assert.equal(quickWinCandidate(unknown),false);
  assert.equal(quickWinCandidate(verified),true);
  assert.match(quickWinExplanation(verified),/вручну/);
});

test('400 combinatorial hard priorities remain unchanged when effort bands vary',()=>{
  const manualStatuses=['AUTO','IN PROGRESS','NEEDS DECISION','WAITING INPUT','WAITING DEPENDENCY','DONE'];
  const signals=['READY','WRITE','WAIT','DECIDE','REVIEW'];
  const bands=['UNKNOWN','XS','S','M','L','XL'];
  const original=[];
  let i=1;
  for(const activeSprint of [true,false]){
    for(const status of manualStatuses){
      for(const signal of signals){
        for(const score of [0,30,90]){
          const x=task('CCON-'+i++,{activeSprint,manualStatus:status,
            analysis:{signal,queueScore:score,needsEmail:signal==='WRITE'}});
          original.push(x);
        }
      }
    }
  }
  const canonical=rankTasks(original).map(x=>x.key);
  for(const band of bands){
    const changed=original.map((x,index)=>({...x,manualEffort:index%2?band:'UNKNOWN'}));
    assert.deepEqual(rankTasks(changed).map(x=>x.key),canonical);
    const hints=safeQuickWinGroups(rankTasks(changed));
    assert.ok(hints.every(x=>canonical[x.index]===x.key));
    assert.ok(hints.every(x=>x.lane===priorityLane(changed.find(e=>e.key===x.key))));
    assert.ok(hints.every(x=>x.actionRank===actionRank(changed.find(e=>e.key===x.key))));
  }
  assert.equal(original.length,180);
});

test('priority score, sprint and blocker outrank short manually estimated backlog',()=>{
  const low=task('CCON-101',{activeSprint:false,manualEffort:'XS',analysis:{queueScore:99}});
  const sprint=task('CCON-102',{activeSprint:true,manualEffort:'XL',analysis:{queueScore:0}});
  const high=task('CCON-103',{activeSprint:true,manualEffort:'S',analysis:{queueScore:90,signal:'WRITE',needsEmail:true}});
  const sorted=rankTasks([low,sprint,high]);
  assert.deepEqual(sorted.map(x=>x.key),['CCON-103','CCON-102','CCON-101']);
  assert.deepEqual(safeQuickWinGroups(sorted).map(x=>x.key),['CCON-103','CCON-101']);
});

test('estimate helper is pure and ignores invalid manually imported values',()=>{
  const x=task('CCON-200',{manualEffort:'SOME RANDOM VALUE'});
  const before=structuredClone(x);
  const info=effortInfo(x);
  assert.equal(info.source,'HEURISTIC');
  effortSuggestion(x);quickWinCandidate(x);safeQuickWinGroups([x]);
  assert.deepEqual(x,before);
});
