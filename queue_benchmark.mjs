/* Synthetic-only frontend queue benchmark (Node, not browser DOM).
   Usage: node queue_benchmark.mjs --sizes 100 500 1000 --iterations 15
   No corporate data, network calls or runtime dependencies. */
import {performance} from 'node:perf_hooks';
import {createQueueModel} from './assets/queue-performance.mjs';
import {rankTasks,filterTasks} from './assets/task-rules.mjs';

function percentile(values,fraction) {
  const sorted=[...values].sort((a,b)=>a-b);
  return sorted[Math.min(sorted.length-1,Math.round((sorted.length-1)*fraction))];
}
function synthesize(count) {
  if (!Number.isInteger(count)||count<1||count>3000) throw Error('Invalid count 1..3000');
  return Array.from({length:count},(_,n)=>({
    key:'CCON-'+(n+1),active:true,activeSprintStatus:'VERIFIED',
    activeSprint:n%2===0,manualStatus:'AUTO',jiraStatus:'In Progress',
    priority:n%3===0?'High':'Medium',summary:'Synthetic supplier integration '+n,
    contextFingerprint:'current',
    analysis:{signal:['WRITE','READY','REVIEW'][n%3],
      reasonUk:'Synthetic description',nextActionUk:'Verify REST segment field',
      contextFingerprint:'current',needsEmail:n%3===0,queueScore:n%100,
      standardDescription:('IF StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED THEN omit SegmentRefID. ').repeat(15),
      briefing:{rules:[{whenUk:'StatusCode=CANCELLED',thenUk:'Do not return segment'}],
        currentUk:'REST reshop search',targetUk:'Supplier response'}}
  }));
}
function sample(fn,iterations) {
  const times=[];
  for(let n=0;n<iterations;n++){
    const started=performance.now();
    fn();
    times.push(performance.now()-started);
  }
  return {p50Ms:+percentile(times,0.5).toFixed(3),p95Ms:+percentile(times,0.95).toFixed(3)};
}
export function benchmark(size,iterations=15) {
  if(!Number.isInteger(iterations)||iterations<3||iterations>200)throw Error('Iterations must be 3..200');
  const source=synthesize(size);
  const original=rankTasks(source);
  const uncached=sample(()=>filterTasks(original,{search:'StatusCode'}),iterations);
  const model=createQueueModel();
  const cold=sample(()=>{
    model.invalidate();
    model.visibleTasks(source,{search:'StatusCode'});
  },iterations);
  model.invalidate();
  model.visibleTasks(source,{search:'StatusCode'});
  const warm=sample(()=>{
    model.visibleTasks(source,{search:'REST'});
    model.visibleTasks(source,{search:'StatusCode'});
  },iterations);
  const sameMatches=filterTasks(original,{search:'StatusCode'}).map(x=>x.key).join(',')===
    model.visibleTasks(source,{search:'StatusCode'}).map(x=>x.key).join(',');
  if(!sameMatches)throw Error('Cached and uncached query mismatch');
  return {
    syntheticTasks:size,iterations,uncachedSearch:uncached,
    cachedColdSearch:cold,cachedWarmAlternatingSearch:warm,
    matchedSearch: sameMatches,
    note:'Node data/search only; NO DOM render, Windows latency, browser startup or human work.'
  };
}
function main(){
  const args=process.argv.slice(2);
  const sizesAt=args.indexOf('--sizes');
  const iterationsAt=args.indexOf('--iterations');
  const iterations=iterationsAt===-1?15:Number(args[iterationsAt+1]);
  const sizes=sizesAt===-1?[100,500,1000]:
    args.slice(sizesAt+1,iterationsAt===-1?undefined:iterationsAt).map(Number);
  const output=sizes.map(size=>benchmark(size,iterations));
  process.stdout.write(JSON.stringify({node:process.version,syntheticOnly:true,results:output},null,2)+'\n');
}
if(process.argv[1] && /queue_benchmark\.mjs$/.test(process.argv[1])) main();
