import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {describeMetrics} from '../assets/error-budget.mjs';

test('dashboard displays only opt-in fixed-key aggregates',()=>{
 const result=describeMetrics({
   localOnly:true,remoteTelemetry:false,sampledApiResponses:140,
   server5xx:1,client4xx:2,successPercent:99.29,
   errorBudgetRemaining:.4,responseLatencyP95Ms:50,
   insufficientSamples:false,sampleTruncated:false,
 });
 assert.equal(result.rate,'99.29%');
 assert.equal(result.remaining,'0.4');
 assert.equal(result.latency,'50 ms');
 assert.ok(!JSON.stringify(result).includes('CCON-'));
 assert.throws(()=>describeMetrics({localOnly:false,remoteTelemetry:false}));
});
test('local dashboard never polls or contacts an external endpoint',()=>{
 const module=readFileSync(new URL('../assets/error-budget.mjs',import.meta.url),'utf8');
 const html=readFileSync(new URL('../error_budget.html',import.meta.url),'utf8');
 assert.match(module,/fetcher\('\/api\/error-budget'/);
 for (const bad of [/setInterval\(/,/setTimeout\(/,/sendBeacon\(/,/localStorage\./,/https?:\/\//]) {
   assert.doesNotMatch(module,bad);
 }
 assert.match(html,/refreshBudget/);
});
