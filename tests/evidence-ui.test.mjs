import test from 'node:test';
import assert from 'node:assert/strict';
import {valueMappingMarkup, investigationMarkup, flowDiagnosticsMarkup, evidenceHealthMarkup, questionProvenanceNotice} from '../assets/evidence-ui.mjs';

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

test('flow diagnostics show explicit timestamp coverage without claiming inferred retries', () => {
  const report = {flowDiagnostics: {
    entriesExamined: 3, timestampedEntries: 2,
    contractCandidates: [{direction:'REST_REQUEST_TO_SUPPLIER_REQUEST',
      supplierMethod:'doOrder',exactValueCandidates:[{restField:'A',supplierField:'RQ.B'}],
      differentValueCandidates:[],restNullFields:['Extra'],
      supplierNullFields:[],restRepeatedFields:[],supplierRepeatedFields:['RQ.Items']}],
    timeline: [{layer:'rest',direction:'request',eventTimeUtc:'2026-10-24T08:00:00+00:00'},
      {layer:'supplier',direction:'request',method:'doOrder',eventTimeUtc:null}],
    repeatedMethodCandidates:[{supplierMethod:'doOrder',requestCount:2}]
  }};
  const html = flowDiagnosticsMarkup(report, escape);
  assert.match(html, /2\/3/);
  assert.match(html, /REST request → Supplier request/);
  assert.match(html, /Час невідомий/);
  assert.match(html, /не доведений retry/);
  assert.match(html, /null REST\/supplier: 1\/0/);
});
test('flow diagnostics never expose unsafe method names as HTML', () => {
  const html = flowDiagnosticsMarkup({flowDiagnostics:{
    entriesExamined:1,timestampedEntries:0,contractCandidates:[],
    timeline:[{layer:'supplier',direction:'request',method:'<img src=x>',eventTimeUtc:null}]
  }},escape);
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img/);
});

test('evidence coverage keeps missing source and candidate error categories explicit', () => {
  const html = evidenceHealthMarkup({
    expectedFlowCount: 3, restSupplierCoverage: 0.333,
    taxonomy: [{code:'AF_TIMEOUT',category:'TIMEOUT_OR_CONNECTIVITY_CANDIDATE',caseCount:2}],
    recurrence:[{code:'AF_TIMEOUT',caseCount:2}],
    flows:[{flowId:'12345678-1234-4234-8234-123456789012',gaps:['REST_MISSING']}]
  }, escape);
  assert.match(html, /33% REST \+ supplier із 3/);
  assert.match(html, /TIMEOUT_OR_CONNECTIVITY_CANDIDATE/);
  assert.match(html, /REST_MISSING/);
  assert.match(html, /класифікація попередня/);
});
test('taxonomy HTML escapes arbitrary codes and does not fabricate coverage', () => {
  const html = evidenceHealthMarkup({restSupplierCoverage:null,
    taxonomy:[{code:'<script>',category:'UNCLASSIFIED',caseCount:1}],
    flows:[],recurrence:[]}, escape);
  assert.match(html, /Немає підтвердженого списку/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
});

test('ANSWERED with only a source URL must never imply verified semantics', () => {
  const withLink = questionProvenanceNotice({
    status: 'ANSWERED', evidenceUrl: 'https://unverified.example.invalid/any',
    answerVerified: true, sourceLinkProvided: true
  });
  assert.match(withLink, /Посилання на джерело є/);
  assert.match(withLink, /не перевірено незалежно/);
  const noLink = questionProvenanceNotice({
    status: 'ANSWERED', answerVerified: true, evidenceUrl: ''
  });
  assert.match(noLink, /Немає посилання на джерело/);
  assert.match(noLink, /не перевірено незалежно/);
  const open = questionProvenanceNotice({status: 'OPEN', presentInLatestAnalysis: false});
  assert.match(open, /не закрито автоматично/);
});
