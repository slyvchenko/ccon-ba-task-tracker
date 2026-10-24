import test from 'node:test';
import assert from 'node:assert/strict';
import {valueMappingMarkup} from '../assets/evidence-ui.mjs';

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
