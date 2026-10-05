/*
 * Pure logic for the manual pin tool (SU11A-19): CSV parsing, guards, picks state,
 * export. No DOM, no network - so it can be unit-tested with Node:
 *     node tests/pin_tool/test_pinlib.js
 * Loaded by index.html as a plain <script>; exposes window.PinLib.
 */
(function (root) {
  'use strict';

  var ISRAEL_BBOX = { latMin: 29.45, latMax: 33.35, lonMin: 34.2, lonMax: 35.95 };
  var WARN_CENTROID_KM = 3;
  var SAME_CHAIN_NEAR_KM = 0.03;
  var METHODS = ['candidate_osm', 'candidate_overture', 'clicked', 'confirmed_existing'];

  /** RFC 4180 CSV -> array of objects keyed by the header row. Handles a UTF-8 BOM,
   *  quoted fields, doubled quotes and newlines inside quotes. */
  function parseCSV(text) {
    if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
    var rows = [], row = [], field = '', i = 0, q = false;
    while (i < text.length) {
      var c = text[i];
      if (q) {
        if (c === '"') {
          if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
          q = false; i++; continue;
        }
        field += c; i++; continue;
      }
      if (c === '"') { q = true; i++; continue; }
      if (c === ',') { row.push(field); field = ''; i++; continue; }
      if (c === '\r') { i++; continue; }
      if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; i++; continue; }
      field += c; i++;
    }
    if (field !== '' || row.length) { row.push(field); rows.push(row); }
    if (!rows.length) return [];
    var head = rows[0];
    return rows.slice(1).filter(function (r) { return r.length > 1 || r[0] !== ''; }).map(function (r) {
      var o = {};
      head.forEach(function (h, k) { o[h] = r[k] === undefined ? '' : r[k]; });
      return o;
    });
  }

  function num(v) {
    if (v === null || v === undefined || v === '') return null;
    var n = Number(v);
    return isFinite(n) ? n : null;
  }

  /** queue.csv rows -> store objects, sorted city, chain, store_id (nearby stores together). */
  function loadQueue(rows) {
    var stores = rows.map(function (r) {
      return {
        fk: Number(r.store_fk), chainId: r.chain_id, chain: r.chain, storeId: r.store_id,
        name: r.store_name, city: r.city_canonical, address: r.address,
        lat: num(r.lat), lon: num(r.lon), precision: r.geo_precision, source: r.geo_source,
        tier: r.tier, flags: r.flags ? r.flags.split(';').filter(Boolean) : [],
        cLat: num(r.centroid_lat), cLon: num(r.centroid_lon),
        suggested: r.suggested || null
      };
    });
    stores.sort(function (a, b) {
      return (a.city || '￿').localeCompare(b.city || '￿', 'he') ||
        (a.chain || '').localeCompare(b.chain || '', 'he') ||
        String(a.storeId).localeCompare(String(b.storeId), 'he', { numeric: true });
    });
    return stores;
  }

  function haversineKm(lat1, lon1, lat2, lon2) {
    var r = Math.PI / 180, dp = (lat2 - lat1) * r, dl = (lon2 - lon1) * r;
    var h = Math.sin(dp / 2) * Math.sin(dp / 2) +
      Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(dl / 2) * Math.sin(dl / 2);
    return 2 * 6371 * Math.asin(Math.sqrt(h));
  }

  function inIsrael(lat, lon) {
    return lat >= ISRAEL_BBOX.latMin && lat <= ISRAEL_BBOX.latMax &&
      lon >= ISRAEL_BBOX.lonMin && lon <= ISRAEL_BBOX.lonMax;
  }

  /** The position a store currently stands at for the same-chain check: its pick if
   *  done, else its existing pin when that pin is a real one (house or street level). */
  function effectivePosition(store, picks) {
    var p = picks[store.fk];
    if (p && p.status === 'done') return { lat: p.lat, lon: p.lon };
    if (store.lat !== null && (store.precision === 'address' || store.precision === 'street')) {
      return { lat: store.lat, lon: store.lon };
    }
    return null;
  }

  /** Guard results for a proposed pin. warnings need a yes/no; none of them blocks. */
  function checkPin(store, lat, lon, stores, picks) {
    var w = [];
    if (!inIsrael(lat, lon)) w.push({ code: 'outside_israel', text: 'הנקודה מחוץ לתחום ישראל' });
    if (store.cLat !== null && store.cLon !== null) {
      var d = haversineKm(lat, lon, store.cLat, store.cLon);
      if (d > WARN_CENTROID_KM) {
        w.push({ code: 'far_from_city', text: 'הנקודה במרחק ' + d.toFixed(1) + ' ק"מ ממרכז ' + (store.city || 'העיר') });
      }
    }
    stores.forEach(function (o) {
      if (o.fk === store.fk || o.chainId !== store.chainId) return;
      var pos = effectivePosition(o, picks);
      if (!pos) return;
      var dd = haversineKm(lat, lon, pos.lat, pos.lon);
      if (dd <= SAME_CHAIN_NEAR_KM) {
        w.push({ code: 'near_same_chain', text: 'בטווח ' + Math.round(dd * 1000) + ' מ\' מסניף אחר של אותה רשת: ' + (o.name || o.storeId) });
      }
    });
    return w;
  }

  function round6(x) { return Math.round(x * 1e6) / 1e6; }

  /** Record a decision; returns the new picks and pushes an undo entry onto history. */
  function applyPick(picks, history, fk, pick) {
    if (pick.status === 'done' && METHODS.indexOf(pick.method) < 0) throw new Error('bad method ' + pick.method);
    var next = Object.assign({}, picks);
    history.push({ fk: fk, prev: picks[fk] || null });
    next[fk] = Object.assign({}, pick, pick.status === 'done' ? { lat: round6(pick.lat), lon: round6(pick.lon) } : {});
    return next;
  }

  /** Undo the last decision. Returns {picks, fk} or null when there is nothing to undo. */
  function undo(picks, history) {
    var h = history.pop();
    if (!h) return null;
    var next = Object.assign({}, picks);
    if (h.prev) next[h.fk] = h.prev; else delete next[h.fk];
    return { picks: next, fk: h.fk };
  }

  function statusOf(store, picks) {
    var p = picks[store.fk];
    return p ? p.status : 'todo';
  }

  function filterStores(stores, picks, f) {
    return stores.filter(function (s) {
      return (!f.tier || s.tier === f.tier) && (!f.chain || s.chain === f.chain) &&
        (!f.city || s.city === f.city) && (!f.status || statusOf(s, picks) === f.status);
    });
  }

  function pad(n) { return (n < 10 ? '0' : '') + n; }

  function exportFilename(d) {
    return 'picks_' + d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()) + '_' +
      pad(d.getHours()) + pad(d.getMinutes()) + '.csv';
  }

  /** picks -> CSV text (done picks only; skips are not pins). */
  function exportCSV(picks) {
    var lines = ['store_fk,lat,lon,method,candidate_id,timestamp'];
    Object.keys(picks).map(Number).sort(function (a, b) { return a - b; }).forEach(function (fk) {
      var p = picks[fk];
      if (p.status !== 'done') return;
      var cid = String(p.candidateId || '');
      if (/[",\n]/.test(cid)) cid = '"' + cid.replace(/"/g, '""') + '"';
      lines.push([fk, p.lat.toFixed(6), p.lon.toFixed(6), p.method, cid, p.timestamp].join(','));
    });
    return lines.join('\n') + '\n';
  }

  function methodForCandidate(point) {
    return point.source === 'overture' ? 'candidate_overture' : 'candidate_osm';
  }

  var api = {
    ISRAEL_BBOX: ISRAEL_BBOX, METHODS: METHODS, parseCSV: parseCSV, loadQueue: loadQueue,
    haversineKm: haversineKm, inIsrael: inIsrael, checkPin: checkPin, applyPick: applyPick,
    undo: undo, statusOf: statusOf, filterStores: filterStores, exportCSV: exportCSV,
    exportFilename: exportFilename, methodForCandidate: methodForCandidate,
    effectivePosition: effectivePosition
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PinLib = api;
})(this);
