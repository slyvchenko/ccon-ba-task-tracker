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

test('global row/badge and technical wrapping cascade is consolidated',()=>{
 assert.equal((css.match(/\.row-title\s*\{/g)||[]).length,1);
 assert.equal((css.match(/\.row \.badge\s*\{/g)||[]).length,1);
 const title=css.match(/\.row-title\s*\{([^}]+)\}/)?.[1]||'';
 const badge=css.match(/\.row \.badge\s*\{([^}]+)\}/)?.[1]||'';
 const row=css.match(/\.row\s*\{[^}]*display:grid;([^}]+)\}/)?.[1]||'';
 assert.match(title,/overflow-wrap:anywhere/);
 assert.match(title,/-webkit-line-clamp:2/);
 assert.match(badge,/font-weight:400/);
 assert.match(badge,/font-size:10px/);
 assert.match(row,/min-width:0/);
 assert.ok(!css.includes('.row {\n  min-width:0\n}'));
});
test('email legibility and adaptive accessibility styles survive consolidation',()=>{
 const value=css.match(/\.email-panel textarea\s*\{[^}]*font-family:Aptos,Arial,sans-serif;[^}]*font-size:11pt;[^}]*color:#000[^}]*\}/);
 assert.ok(value,'full independent email readability contract');
 for(const fragment of ['@media(max-width:750px)','@media(max-width:380px)',
   '@media (forced-colors:active)','@media (prefers-reduced-motion:reduce)',
   'summary:focus-visible']) assert.ok(css.includes(fragment),'lost '+fragment);
});

test('PERF-09 brand cascade is single-source without changing final token values',()=>{
 const one=(pattern,label)=>(()=>{
   const matches=[...css.matchAll(pattern)];
   assert.equal(matches.length,1,'duplicate canonical '+label);
   return matches[0][1];
 })();
 const root=one(/:root\s*\{([^}]+)\}/g,':root');
 assert.match(root,/--blue:var\(--brand-blue\)/);
 assert.match(root,/--brand-blue:#0879b6/);
 assert.match(root,/--brand-canvas:#f4f7f9/);
 assert.match(root,/--line:#dbe3e9/);
 assert.match(root,/--muted:#64717b/);
 assert.match(root,/font-family:Aptos,"Segoe UI",Arial,sans-serif/);
 const header=css.match(/header\s*\{([^}]+)\}/)?.[1]||'';
 assert.match(header,/border-bottom:2px solid var\(--brand-blue\)/);
 const primary=one(/\.primary\s*\{([^}]+)\}/g,'.primary');
 assert.match(primary,/background:var\(--brand-blue\)/);
 assert.match(primary,/border-color:var\(--brand-blue\)/);
 const hover=one(/\.primary:hover\s*\{([^}]+)\}/g,'.primary:hover');
 assert.match(hover,/background:#09628f/);
 const selected=css.match(/\.row\.selected\s*\{([^}]+)\}/)?.[1]||'';
 assert.match(selected,/background:var\(--brand-blue-light\)/);
 assert.match(selected,/border-left-color:var\(--brand-blue\)/);
 for(const query of ['max-width:1150px','max-width:750px','max-width:380px',
  'forced-colors:active','prefers-reduced-motion:reduce'])
   assert.ok(css.includes(query),'lost adaptive CSS '+query);
});


test('stale supplier ZIP warnings retain an emphasized amber helper',()=>{
 const rule=css.match(/\.text-amber\s*\{([^}]+)\}/)?.[1] || '';
 assert.match(rule,/color:\s*var\(--amber\)/);
 assert.match(rule,/font-weight:\s*700/);
 assert.ok(js.includes("text-amber"));
});

test('recovery source and narrow-view sticky action preserve accessible controls',()=>{
 assert.match(html,/<select id="recoverySource"[^>]+disabled/);
 assert.match(js,/others\.find\(item=>item\.id===\$\('recoverySource'\)\.value\)/);
 assert.match(css,/@media \(max-width:750px\)\s*\{\s*\/\*[^]*?\.sticky-next-action\s*\{top:var\(--task-toolbar-height/);
 assert.match(js,/toolbar\?\.getBoundingClientRect\(\)\.height/);
 assert.match(js,/sticky\.style\.setProperty\('--task-toolbar-height'/);
 assert.match(js,/restoreInsertedDisclosureStates\(changes,disclosureState\)/);
});
