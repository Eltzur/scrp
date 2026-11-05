// SU11A-64: /promos/bulk request planning (server caps 300 stores / 1000
// barcodes per call) and the saved-baskets filter. Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BULK_MAX_ITEMS, BULK_MAX_STORES, mergePromoMaps, planPromosBulk } from '../src/utils/promoBulk.ts';
import { APP_BASKET_NAME, listedBaskets } from '../src/utils/savedBaskets.ts';

const stores = n => Array.from({ length: n }, (_, i) => ({ chain_id: 'C', store_id: String(i) }));
const codes = n => Array.from({ length: n }, (_, i) => `729${String(i).padStart(10, '0')}`);

test('a normal page is one call with its stores and barcodes', () => {
  const plan = planPromosBulk(stores(280), codes(20));
  assert.equal(plan.length, 1);
  assert.equal(plan[0].stores.length, 280);
  assert.equal(plan[0].item_codes.length, 20);
});

test('no call goes over the server caps; every store and barcode pair is covered once', () => {
  const plan = planPromosBulk(stores(700), [...codes(1500), ...codes(10)]);   // duplicates collapse
  assert.equal(plan.length, 3 * 2);
  assert.ok(plan.every(b => b.stores.length <= BULK_MAX_STORES && b.item_codes.length <= BULK_MAX_ITEMS));
  const pairs = new Set(plan.flatMap(b => b.stores.flatMap(s => b.item_codes.map(c => `${s.store_id}:${c}`))));
  assert.equal(pairs.size, 700 * 1500);
  assert.deepEqual(planPromosBulk([], codes(3)), []);
  assert.deepEqual(planPromosBulk(stores(3), []), []);
});

test('answers merge per store, also across barcode chunks', () => {
  const merged = mergePromoMaps([{ 'C/1': [{ item_code: 'a' }] }, { 'C/1': [{ item_code: 'b' }], 'C/2': [] }, {}]);
  assert.deepEqual(merged, { 'C/1': [{ item_code: 'a' }, { item_code: 'b' }], 'C/2': [] });
});

test('the app basket is not listed on the website', () => {
  const all = [{ id: 1, name: 'שבועי' }, { id: 2, name: APP_BASKET_NAME }, { id: 3, name: 'ערב חג' }];
  assert.deepEqual(listedBaskets(all).map(b => b.id), [1, 3]);
});