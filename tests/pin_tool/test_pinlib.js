// Tests for tools/pin_tool/pinlib.js (SU11A-19). Run: node tests/pin_tool/test_pinlib.js
'use strict';
const assert = require('node:assert/strict');
const path = require('node:path');
const P = require(path.join(__dirname, '..', '..', 'tools', 'pin_tool', 'pinlib.js'));

let passed = 0;
function test(name, fn) { fn(); passed++; console.log('ok -', name); }

const CSV = '﻿store_fk,chain_id,chain,store_id,store_name,city_canonical,address,lat,lon,geo_precision,geo_source,tier,flags,centroid_lat,centroid_lon,n_candidates,suggested\n' +
  '2,C1,רשת א,002,"סניף ""ב""",תל אביב-יפו,"הרצל 5, קומה 2",32.06,34.77,street,nominatim,street,,32.08,34.78,1,\n' +
  '1,C1,רשת א,001,סניף א,חיפה,הנשיא 124,,,,,unplaced,no_house_number,32.79,34.99,0,\n' +
  '3,C2,רשת ב,010,"שורה\nשנייה",חיפה,רחוב 1,32.80,34.99,address,nominatim,house_unconfirmed,ambiguous_pin;shares_pin_30m,32.79,34.99,2,osm:node/7\n';

test('parseCSV: BOM, quotes, doubled quotes, embedded comma and newline', () => {
  const rows = P.parseCSV(CSV);
  assert.equal(rows.length, 3);
  assert.equal(rows[0].store_name, 'סניף "ב"');
  assert.equal(rows[0].address, 'הרצל 5, קומה 2');
  assert.equal(rows[2].store_name, 'שורה\nשנייה');
  assert.ok('store_fk' in rows[0]);
});

test('loadQueue: types, flags, sort by city then chain', () => {
  const s = P.loadQueue(P.parseCSV(CSV));
  assert.deepEqual(s.map(x => x.city), ['חיפה', 'חיפה', 'תל אביב-יפו']);
  assert.equal(s[0].lat, null);
  assert.deepEqual(s.find(x => x.fk === 3).flags, ['ambiguous_pin', 'shares_pin_30m']);
  assert.equal(s.find(x => x.fk === 3).suggested, 'osm:node/7');
});

const stores = P.loadQueue(P.parseCSV(CSV));
const st = fk => stores.find(x => x.fk === fk);

test('checkPin: outside Israel bbox', () => {
  const w = P.checkPin(st(1), 31.0, 32.0, stores, {});
  assert.ok(w.some(x => x.code === 'outside_israel'));
});

test('checkPin: more than 3 km from the city centroid', () => {
  assert.ok(P.checkPin(st(1), 32.83, 34.99, stores, {}).some(x => x.code === 'far_from_city'));
  assert.ok(!P.checkPin(st(1), 32.80, 34.99, stores, {}).some(x => x.code === 'far_from_city'));
});

test('checkPin: within 30 m of another same-chain store (existing pin or pick)', () => {
  // store 2 (chain C1) has a street pin at 32.06,34.77; store 1 is chain C1 too
  assert.ok(P.checkPin(st(1), 32.0601, 34.7701, stores, {}).some(x => x.code === 'near_same_chain'));
  // a different chain at the same spot does not trigger
  assert.ok(!P.checkPin(st(3), 32.0601, 34.7701, stores, {}).some(x => x.code === 'near_same_chain'));
  // a done pick counts as the other store's position
  const picks = { 2: { status: 'done', lat: 32.79, lon: 34.99, method: 'clicked' } };
  assert.ok(P.checkPin(st(1), 32.79001, 34.99001, stores, picks).some(x => x.code === 'near_same_chain'));
  // an unplaced store (no real pin) never triggers
  assert.ok(!P.checkPin(st(2), 32.79, 34.99, stores, {}).some(x => x.code === 'near_same_chain'));
});

test('applyPick rounds to 6 decimals, rejects bad methods; undo restores', () => {
  const h = [];
  let picks = P.applyPick({}, h, 1, { status: 'done', lat: 32.123456789, lon: 34.987654321, method: 'clicked', timestamp: 't' });
  assert.equal(picks[1].lat, 32.123457);
  picks = P.applyPick(picks, h, 1, { status: 'done', lat: 32.2, lon: 34.9, method: 'candidate_osm', candidateId: 'osm:node/1', timestamp: 't2' });
  assert.throws(() => P.applyPick(picks, h, 1, { status: 'done', lat: 1, lon: 1, method: 'google' }));
  assert.equal(h.length, 2, 'a rejected pick must not leave an undo entry');
  let u = P.undo(picks, h);
  assert.equal(u.picks[1].method, 'clicked');
  u = P.undo(u.picks, h);
  assert.equal(u.picks[1], undefined);
  assert.equal(P.undo(u.picks, h), null);
});

test('filterStores by tier, city and status', () => {
  const picks = { 1: { status: 'skipped' } };
  assert.equal(P.filterStores(stores, picks, { tier: 'unplaced' }).length, 1);
  assert.equal(P.filterStores(stores, picks, { city: 'חיפה' }).length, 2);
  assert.equal(P.filterStores(stores, picks, { status: 'todo' }).length, 2);
  assert.equal(P.filterStores(stores, picks, { status: 'skipped' })[0].fk, 1);
});

test('exportCSV: done only, 6 decimals, quoted candidate id, header', () => {
  const picks = {
    3: { status: 'done', lat: 32.8, lon: 34.99, method: 'candidate_overture', candidateId: 'overture:a,b', timestamp: '2026-10-05T10:00:00Z' },
    1: { status: 'skipped' },
    2: { status: 'done', lat: 32.06, lon: 34.77, method: 'confirmed_existing', candidateId: '', timestamp: '2026-10-05T10:01:00Z' },
  };
  const lines = P.exportCSV(picks).trim().split('\n');
  assert.equal(lines[0], 'store_fk,lat,lon,method,candidate_id,timestamp');
  assert.equal(lines.length, 3);
  assert.equal(lines[1], '2,32.060000,34.770000,confirmed_existing,,2026-10-05T10:01:00Z');
  assert.equal(lines[2], '3,32.800000,34.990000,candidate_overture,"overture:a,b",2026-10-05T10:00:00Z');
});

test('exportFilename: picks_YYYYMMDD_HHMM.csv', () => {
  assert.equal(P.exportFilename(new Date(2026, 9, 5, 9, 7)), 'picks_20261005_0907.csv');
});

test('methodForCandidate', () => {
  assert.equal(P.methodForCandidate({ source: 'osm' }), 'candidate_osm');
  assert.equal(P.methodForCandidate({ source: 'overture' }), 'candidate_overture');
});

// Optional: the real 5-store sample, when a local export is present (never committed).
const fs = require('node:fs');
const sample = process.env.PIN_SAMPLE_DIR;
if (sample && fs.existsSync(path.join(sample, 'queue.csv'))) {
  test('5-store sample from a real export loads and its candidates resolve', () => {
    const s = P.loadQueue(P.parseCSV(fs.readFileSync(path.join(sample, 'queue.csv'), 'utf8')));
    const c = JSON.parse(fs.readFileSync(path.join(sample, 'candidates.json'), 'utf8'));
    assert.equal(s.length, 5);
    s.forEach(x => {
      const e = c.stores[String(x.fk)];
      assert.ok(e, 'candidates entry for ' + x.fk);
      e.candidates.forEach(id => assert.ok(c.points[id], 'point ' + id));
      if (x.cLat !== null) assert.ok(P.inIsrael(x.cLat, x.cLon));
    });
  });
}

console.log(`\n${passed} passed`);
