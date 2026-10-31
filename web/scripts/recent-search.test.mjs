// SU11A-58: recent-search normalisation. Run: npm run test:unit
// (node --test; Node 22.18+ strips the TypeScript types itself.)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { cleanSearch, dedupeSearches, pushSearch, searchKey } from '../src/utils/recentSearch.ts';

test('clean: trim and collapse spaces', () => {
  assert.equal(cleanSearch('  חלב   תנובה \t 3% '), 'חלב תנובה 3%');
});

test('key: spacing between number and word does not matter', () => {
  const keys = ['זירו 1.5', 'זירו1.5', '1.5זירו', '  זירו   1.5 ', '1.5 זירו'].map(searchKey);
  assert.equal(new Set(keys).size, 1);
  assert.notEqual(searchKey('זירו 1.5'), searchKey('זירו 1,5 ליטר'));
  assert.notEqual(searchKey('זירו 1.5'), searchKey('זירו 15'));
  assert.equal(searchKey('Coca Cola'), searchKey('coca  COLA'));
});

test('push: newest spelling first, other spellings removed, max kept', () => {
  let list = [];
  for (const q of ['במבה', 'זירו1.5', 'חלב', '1.5זירו']) list = pushSearch(list, q, 10);
  assert.deepEqual(list, ['1.5זירו', 'חלב', 'במבה']);
  list = pushSearch(list, '  זירו   1.5 ', 10);
  assert.deepEqual(list, ['זירו 1.5', 'חלב', 'במבה']);
  assert.equal(pushSearch(Array.from({ length: 10 }, (_, i) => `מוצר${i}x`), 'חדש', 10).length, 10);
});

test('dedupe on load: old stored entries cleaned, first (newest) kept, junk dropped', () => {
  const stored = ['זירו 1.5', 'חלב  תנובה', 'זירו1.5', ' חלב תנובה', 'א', 42, null, '1.5זירו', 'במבה'];
  assert.deepEqual(dedupeSearches(stored, 10), ['זירו 1.5', 'חלב תנובה', 'במבה']);
  assert.deepEqual(dedupeSearches(['a1', 'b2', 'c3'], 2), ['a1', 'b2']);
});
