import test from 'node:test';import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const css=readFileSync(new URL('../assets/dashboard.css',import.meta.url),'utf8');
const js=readFileSync(new URL('../assets/dashboard.mjs',import.meta.url),'utf8');
const html=readFileSync(new URL('../dashboard.html',import.meta.url),'utf8');
test('legacy CSS signal/status helpers are absent and no longer referenced in markup',()=>{
 for(const cls of ['signal-strip','signal-text','task-badges']){
  assert.ok(!css.includes('.'+cls),'orphan CSS '+cls);
  assert.ok(!(js+'\n'+html).includes('class="'+cls+'"'));
 }
});
test('visible status domains, focus affordances and progressive filtering stay styled',()=>{
 for(const classname of ['.task-meta-compact','.task-status-provenance','.task-status-alerts',
  '.advanced-filters','.data-menu-group','.quick-handoff','.row.selected',
  '.keyboard-guide',':focus-visible']){
  assert.ok(css.includes(classname),'missing important CSS '+classname);
 }
 for(const name of ['#advancedFilters','#countDetails','#dataMenu','#list','#detail']){
  assert.ok((js+'\n'+html).includes(name)||html.includes('id="'+name.slice(1)+'"'));
 }
});
test('responsive/accessibility guardrails remain represented in CSS',()=>{
 for(const fragment of ['max-width:380px','forced-colors:active','prefers-reduced-motion:reduce',
  'overflow-wrap:anywhere']){
  assert.ok(css.includes(fragment));
 }
});

test('technical REST/PNR snippets can wrap without ellipsis or text truncation',()=>{
 const rule=css.match(/\.technical-token\s*\{([^}]+)\}/)?.[1] || '';
 assert.match(rule,/overflow-wrap:\s*anywhere/);
 assert.match(rule,/white-space:\s*pre-wrap/);
 assert.doesNotMatch(rule,/text-overflow:\s*ellipsis|overflow:\s*hidden/);
 assert.match(js,/code class="technical-token"/);
 const evidence=css.match(/\.evidence-scroll td,\.evidence-scroll th\s*\{([^}]+)\}/)?.[1] || '';
 assert.match(evidence,/overflow-wrap:anywhere/);
 for(const fragment of ['#contextPreview','#evidenceSummary','#approvedReview'])
   assert.ok(css.includes(fragment),'missing technical overflow scope '+fragment);
});
test('legacy overridden row density rules stay consolidated',()=>{
 assert.equal((css.match(/\.row-title\s*\{\s*margin:/g)||[]).length,0);
 assert.ok(css.includes('margin:3px 0 4px;'));
 assert.ok(!css.includes('font-size:11px;\n  font-weight:400;\n  padding:3px 6px;'));
});
