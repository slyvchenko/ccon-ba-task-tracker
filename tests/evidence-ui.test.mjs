import test from 'node:test';
import assert from 'node:assert/strict';
import {valueMappingMarkup, investigationMarkup} from '../assets/evidence-ui.mjs';

const escape = x => String(x).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

test('comparison preview shows candidates without exposing actual scalar values', () => {
  const html = valueMappingMarkup({valueReview:{comparisons:[{
    direction:'REST_REQUEST_TO_SUPPLIER_REQUEST',
    exactValueCandidates:[{restField:'Price',supplierField:'RQ.Amount'}],
    sameNamedDifferentValues:[{restField:'StatusCode',supplierField:'RS.StatusCode'}]
  }]}}, escape);
  assert.match(html, /REST request → supplier request/);
  assert.match(html, /Однакове значення/);
  assert.match(html, /Різні значення/);
  assert.doesNotMatch(html, /139\.95|CONFIDENTIAL/);
});

test('no paired exchange does not pretend mapping is confirmed', () => {
  const html = valueMappingMarkup({valueReview:{comparisons:[]}}, escape);
  assert.match(html, /Немає однозначно спарених/);
  assert.doesNotMatch(html, /підтверджено/);
});

test('field names are escaped before display', () => {
  const html = valueMappingMarkup({valueReview:{comparisons:[{
    direction:'SUPPLIER_RESPONSE_TO_REST_RESPONSE',
    exactValueCandidates:[{restField:'<script>',supplierField:'RS.Value'}]
  }]}}, escape);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
});

test('Kibana multi-case preview shows unconfirmed RCA and exact coverage', () => {
  const html = investigationMarkup({
    analyzedCases: 3, availableUniqueFlows: 8, coverage: {
      withRest: 3, withSupplier: 2, withErrorLayer: 1},
    groups: [{errorCode:'AF_REJECTED', supplierMethod:'doRetrieve', caseCount:3}],
    hypotheses: [{titleUk:'Проблема mapping', alternativeUk:'Коректне правило',
       verificationUk:'Порівняти контракт та успішний flow'}],
    questionsUk: ['Бракує supplier RQ/RS']
  }, escape);
  assert.match(html, /3 із 8/);
  assert.match(html, /Supplier 2\/3/);
  assert.match(html, /RCA не підтверджено/);
  assert.match(html, /Коректне правило/);
  assert.match(html, /AF_REJECTED/);
});
test('No evidence does not display a fabricated root cause', () => {
  assert.equal(investigationMarkup(null, escape), '');
  assert.equal(investigationMarkup({analyzedCases:0}, escape), '');
});
test('Kibana labels and hypotheses are escaped', () => {
  const html = investigationMarkup({
    analyzedCases:1, availableUniqueFlows:1, coverage:{},
    groups:[{errorCode:'<img src=x>',supplierMethod:'read',caseCount:1}],
    hypotheses:[{titleUk:'<script>alert(1)</script>',alternativeUk:'Other',verificationUk:'Check'}]
  }, escape);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
  assert.doesNotMatch(html, /<img/);
});
