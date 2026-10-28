import test from 'node:test';
import assert from 'node:assert/strict';
import {dashboardBuckets, safeCount, RELEASE_CATEGORIES,
        TASK_CATEGORIES, MANUAL_CATEGORIES} from '../assets/stats.mjs';

test('stats use fixed, human-readable labels and never reveal input keys', () => {
  const buckets = dashboardBuckets({
    WRITE: 3, READY: 2, 'CCON-999/SECRET': 100
  }, TASK_CATEGORIES, {includeEmpty:false});
  assert.deepEqual(buckets.map(x => [x.key, x.count]),
                   [['WRITE', 3], ['READY', 2]]);
  assert.equal(buckets.reduce((s, x) => s + x.count, 0), 5);
  assert.doesNotMatch(JSON.stringify(buckets), /SECRET|CCON-999/);
});

test('counters reject booleans, negative, string and non-integer values', () => {
  for (const value of [false, true, null, undefined, '5', -5, 1.2, NaN, Infinity]) {
    assert.equal(safeCount(value), 0);
  }
  assert.equal(safeCount(8), 8);
  const buckets = dashboardBuckets({IMPLEMENTED:40, PARTIAL:82, GATE:3,
    DEFERRED:4}, RELEASE_CATEGORIES);
  assert.equal(buckets.reduce((s, x) => s + x.count, 0), 129);
  assert.equal(buckets.find(x => x.key === 'GATE').label, 'Очікує приймання');
});

test('manual status bars cannot be confused with Jira status', () => {
  const rows = dashboardBuckets({DONE:2, 'IN PROGRESS':5}, MANUAL_CATEGORIES,
                                {includeEmpty:false});
  assert.equal(rows.find(x => x.key === 'DONE').label, 'Локально завершено');
  assert.equal(rows.find(x => x.key === 'IN PROGRESS').count, 5);
});
