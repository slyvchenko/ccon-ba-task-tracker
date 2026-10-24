import test from 'node:test';
import assert from 'node:assert/strict';
import {decisionsMarkup} from '../assets/decisions-ui.mjs';

const escape = x => String(x ?? '').replaceAll('&', '&amp;').replaceAll('<','&lt;').replaceAll('>', '&gt;').replaceAll('"','&quot;');

test('decision history renders proposed, confirmed and superseded without hiding old record', () => {
  const html = decisionsMarkup({decisions:[
    {id:'D-11111111111111',status:'SUPERSEDED',text:'Old rule',sourceUrl:'https://jira.example/1',
     supersededBy:'D-22222222222222'},
    {id:'D-22222222222222',status:'CONFIRMED',text:'New rule',sourceUrl:'https://jira.example/2',
     supersedes:'D-11111111111111',impact:'Update QA'}
  ],events:[{id:'D-11111111111111',to:'PROPOSED',at:'2026-10-24',actor:'AI_PROPOSAL',reason:'New'}]}, escape);
  assert.match(html, /Old rule/);
  assert.match(html, /New rule/);
  assert.match(html, /Update QA/);
  assert.match(html, /Замінено/);
  assert.match(html, /підтверджен/i);
  assert.match(html, /журнал/i);
  assert.match(html, /id="saveDecision"/);
});
test('Jira decision content escaped in unchanged task layout', () => {
  const html = decisionsMarkup({decisions:[
    {id:'D-33333333333333',status:'PROPOSED',text:'<script>bad</script>',
     impact:'<img src=x>',sourceUrl:'https://jira.example/1'}]}, escape);
  assert.doesNotMatch(html, /<script>/);
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;script&gt;/);
});
test('empty register remains clear and human-controlled', () => {
  const html = decisionsMarkup({decisions:[],events:[]}, escape);
  assert.match(html, /Історія рішень поки порожня/);
  assert.match(html, /тільки вручну/);
});
