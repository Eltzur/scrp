/*
 * Manual pin tool (SU11A-19) - UI wiring. Logic lives in pinlib.js.
 *
 * Runs locally only:  python -m http.server 8765   ->  http://localhost:8765
 * Files are read with file pickers; nothing is uploaded. Picks autosave to this
 * browser's localStorage and are exported as a CSV.
 *
 * OSM tile usage policy (operations.osmfoundation.org/policies/tiles): the exact tile
 * URL, visible attribution, the browser's own User-Agent / Referer / cache (no
 * no-cache headers, no Referrer-Policy override), interactive use only - tiles are
 * fetched for the visible map, never prefetched, never downloaded for offline use.
 *
 * Pins come from OSM / Overture candidate points, a click on the map, or a Google Maps point
 * (since 2026-10-08 the Google results are the coordinate source - CLAUDE.md "Store positions").
 */
(function () {
  'use strict';
  var L_ = window.L, P = window.PinLib;
  var STORE_KEY = 'xxl_pin_tool_v1';

  var state = { stores: [], points: {}, cand: {}, picks: {}, history: [], view: [], idx: 0,
                selection: null, actionTimes: [] };
  var $ = function (id) { return document.getElementById(id); };

  // ---------------------------------------------------------------- map
  var map = L_.map('map', { zoomControl: true }).setView([31.9, 34.9], 8);
  L_.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    updateWhenIdle: true,        // load tiles when panning stops: no extra requests mid-drag
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' +
      ' | נקודות: OSM (ODbL), Overture (CDLA-Permissive-2.0)'
  }).addTo(map);
  var layer = L_.layerGroup().addTo(map);
  var pickMarker = null;

  map.on('click', function (e) {
    var s = current();
    if (!s) return;
    select({ lat: e.latlng.lat, lon: e.latlng.lng, method: 'clicked', candidateId: '' });
  });

  // ---------------------------------------------------------------- persistence
  function save() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({ picks: state.picks, history: state.history }));
    } catch (e) { setStatus('שמירה מקומית נכשלה – ייצאו את הבחירות עכשיו'); }
  }
  function restore() {
    try {
      var raw = localStorage.getItem(STORE_KEY);
      if (raw) { var o = JSON.parse(raw); state.picks = o.picks || {}; state.history = o.history || []; }
    } catch (e) { state.picks = {}; state.history = []; }
  }

  // ---------------------------------------------------------------- loading
  function readFile(input, cb) {
    var f = input.files && input.files[0];
    if (!f) return;
    var r = new FileReader();
    r.onload = function () { cb(String(r.result)); };
    r.readAsText(f, 'utf-8');
  }
  $('fQueue').addEventListener('change', function () {
    readFile(this, function (txt) {
      state.stores = P.loadQueue(P.parseCSV(txt));
      fillFilters(); refresh(0); info();
    });
  });
  $('fCand').addEventListener('change', function () {
    readFile(this, function (txt) {
      var o = JSON.parse(txt);
      state.points = o.points || {}; state.cand = o.stores || {};
      refresh(state.idx); info();
    });
  });
  function info() {
    $('loadInfo').textContent = state.stores.length + ' סניפים · ' + Object.keys(state.points).length + ' נקודות מועמדות';
  }

  function fillFilters() {
    var uniq = function (k) {
      return Array.from(new Set(state.stores.map(function (s) { return s[k]; }).filter(Boolean)))
        .sort(function (a, b) { return a.localeCompare(b, 'he'); });
    };
    [['fChain', 'chain'], ['fCity', 'city']].forEach(function (p) {
      var sel = $(p[0]);
      sel.length = 1;
      uniq(p[1]).forEach(function (v) { var o = document.createElement('option'); o.value = o.textContent = v; sel.appendChild(o); });
    });
  }
  ['fTier', 'fStatus', 'fChain', 'fCity'].forEach(function (id) {
    $(id).addEventListener('change', function () { refresh(0); });
  });

  // ---------------------------------------------------------------- view
  function filters() {
    return { tier: $('fTier').value, status: $('fStatus').value, chain: $('fChain').value, city: $('fCity').value };
  }
  function current() { return state.view[state.idx] || null; }

  function refresh(idx) {
    state.view = P.filterStores(state.stores, state.picks, filters());
    state.idx = Math.max(0, Math.min(idx, state.view.length - 1));
    renderList(); renderCounts(); renderStore();
  }

  function renderCounts() {
    var c = { todo: 0, done: 0, skipped: 0 };
    state.stores.forEach(function (s) { c[P.statusOf(s, state.picks)]++; });
    var t = state.actionTimes, per = t.length > 3 ? (t[t.length - 1] - t[0]) / (t.length - 1) / 1000 : 40;
    var left = Math.round(c.todo * per / 60);
    $('counts').textContent = 'לטיפול ' + c.todo + ' · בוצע ' + c.done + ' · דולג ' + c.skipped +
      ' · נותרו כ-' + left + ' דק\' (' + Math.round(per) + ' שנ\' לסניף)' + ' · בתצוגה ' + state.view.length;
  }

  function renderList() {
    var ul = $('list');
    ul.innerHTML = '';
    state.view.forEach(function (s, i) {
      var li = document.createElement('li'), b = document.createElement('button');
      var st = P.statusOf(s, state.picks);
      b.type = 'button';
      b.className = 'st-' + st;
      b.textContent = (st === 'done' ? '✓ ' : st === 'skipped' ? '↷ ' : '') + (s.city || '—') + ' · ' + s.chain + ' · ' + (s.name || s.storeId);
      if (i === state.idx) b.setAttribute('aria-current', 'true');
      b.addEventListener('click', function () { state.idx = i; renderList(); renderStore(); });
      li.appendChild(b); ul.appendChild(li);
    });
    var cur = ul.querySelector('[aria-current="true"]');
    if (cur) cur.scrollIntoView({ block: 'nearest' });
  }

  function popupHtml(p) {
    var esc = function (x) { return String(x === null || x === undefined ? '' : x).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
    var addr = Object.keys(p.addr || {}).filter(function (k) { return p.addr[k]; })
      .map(function (k) { return esc(k) + ': ' + esc(p.addr[k]); }).join('<br>');
    return '<div dir="rtl"><b>' + esc(p.name) + '</b><br>' + (p.brand ? 'מותג: ' + esc(p.brand) + '<br>' : '') +
      addr + '<br><small>' + esc(p.source) + ' ' + esc(p.id) + '</small></div>';
  }

  function renderStore() {
    layer.clearLayers(); pickMarker = null; state.selection = null;
    var s = current();
    if (!s) { $('addr').textContent = ''; $('meta').textContent = 'אין סניפים בתצוגה.'; $('links').innerHTML = ''; return; }
    var pick = state.picks[s.fk];
    $('addr').textContent = s.address || '(אין כתובת בפיד)';
    $('meta').textContent = s.chain + ' · ' + (s.name || '') + ' · סניף ' + s.storeId + ' · ' + (s.city || 'ללא עיר') +
      ' · שכבה: ' + s.tier + ' · מקור: ' + (s.source || '—') + (pick ? ' · סטטוס: ' + pick.status : '');
    $('flags').innerHTML = '';
    s.flags.forEach(function (f) { var sp = document.createElement('span'); sp.className = 'flag'; sp.textContent = f; $('flags').appendChild(sp); });
    var q = encodeURIComponent([s.chain, s.name, s.address, s.city].filter(Boolean).join(' '));
    $('links').innerHTML =
      '<a target="_blank" rel="noopener" href="https://www.openstreetmap.org/search?query=' + q + '">חיפוש ב-OSM</a>' +
      '<a target="_blank" rel="noopener" href="https://www.google.com/maps/search/?api=1&query=' + q + '">' +
      'פתיחה בגוגל מפות</a>';
    $('bExisting').disabled = !(s.lat !== null && (s.tier === 'house_unconfirmed' || s.tier === 'house_confirmed'));

    var bounds = [];
    if (s.lat !== null) {
      L_.circleMarker([s.lat, s.lon], { radius: 8, color: '#555', fillColor: '#888', fillOpacity: 0.9, weight: 2 })
        .bindTooltip('מיקום נוכחי (' + (s.precision || 'none') + ')').addTo(layer);
      bounds.push([s.lat, s.lon]);
    }
    var c = state.cand[String(s.fk)];
    (c ? c.candidates : []).forEach(function (id) {
      var p = state.points[id];
      if (!p) return;
      var sug = c.suggested === id;
      var m = L_.circleMarker([p.lat, p.lon], {
        radius: sug ? 11 : 8, color: sug ? '#1e7d32' : '#fff', weight: sug ? 4 : 2,
        fillColor: p.source === 'overture' ? '#c4560c' : '#1f5fbf', fillOpacity: 0.95
      }).bindPopup(popupHtml(p)).addTo(layer);
      m.on('click', function (e) {
        L_.DomEvent.stopPropagation(e);
        select({ lat: p.lat, lon: p.lon, method: P.methodForCandidate(p), candidateId: p.source + ':' + p.id });
        m.openPopup();
      });
      bounds.push([p.lat, p.lon]);
      if (sug && !pick) select({ lat: p.lat, lon: p.lon, method: P.methodForCandidate(p), candidateId: p.source + ':' + p.id });
    });
    if (pick && pick.status === 'done') {
      L_.circleMarker([pick.lat, pick.lon], { radius: 9, color: '#fff', weight: 2, fillColor: '#2e7d32', fillOpacity: 1 })
        .bindTooltip('נבחר: ' + pick.method).addTo(layer);
      bounds.push([pick.lat, pick.lon]);
    }
    if (bounds.length > 1) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 17 });
    else if (bounds.length === 1) map.setView(bounds[0], 17);
    else if (s.cLat !== null) map.setView([s.cLat, s.cLon], 14);
    setStatus(state.selection ? 'נבחרה נקודה מוצעת – Enter לאישור' : 'לחצו על מועמד או על המפה');
  }

  function select(sel) {
    state.selection = sel;
    if (pickMarker) layer.removeLayer(pickMarker);
    pickMarker = L_.circleMarker([sel.lat, sel.lon], { radius: 7, color: '#fff', weight: 2, fillColor: '#c62828', fillOpacity: 1 })
      .addTo(layer);
    setStatus('בחירה: ' + sel.method + ' ' + sel.lat.toFixed(6) + ', ' + sel.lon.toFixed(6) + ' – Enter לאישור');
  }

  function setStatus(t) { $('status').textContent = t; }

  // ---------------------------------------------------------------- actions
  function record(pick) {
    var s = current();
    state.picks = P.applyPick(state.picks, state.history, s.fk, Object.assign({ timestamp: new Date().toISOString() }, pick));
    state.actionTimes.push(Date.now());
    if (state.actionTimes.length > 30) state.actionTimes.shift();
    save();
    var keepIdx = state.idx;
    refresh(keepIdx);
    // With a status filter the done store drops out of the view, so keepIdx is already the next one.
    if (!filters().status && state.idx < state.view.length - 1) { state.idx++; renderList(); renderStore(); }
  }

  function guardsOk(s, lat, lon) {
    var w = P.checkPin(s, lat, lon, state.stores, state.picks);
    if (!w.length) return true;
    return window.confirm(w.map(function (x) { return '• ' + x.text; }).join('\n') + '\n\nלאשר בכל זאת?');
  }

  function confirmSelection() {
    var s = current(), sel = state.selection;
    if (!s) return;
    if (!sel) { setStatus('אין בחירה: לחצו על מועמד או על המפה'); return; }
    if (!guardsOk(s, sel.lat, sel.lon)) return;
    record({ status: 'done', lat: sel.lat, lon: sel.lon, method: sel.method, candidateId: sel.candidateId });
  }
  function confirmExisting() {
    var s = current();
    if (!s || $('bExisting').disabled) return;
    if (!guardsOk(s, s.lat, s.lon)) return;
    record({ status: 'done', lat: s.lat, lon: s.lon, method: 'confirmed_existing', candidateId: '' });
  }
  function skip() { if (current()) record({ status: 'skipped' }); }
  function move(d) { if (!state.view.length) return; state.idx = Math.max(0, Math.min(state.view.length - 1, state.idx + d)); renderList(); renderStore(); }
  function doUndo() {
    var u = P.undo(state.picks, state.history);
    if (!u) { setStatus('אין מה לבטל'); return; }
    state.picks = u.picks; save();
    refresh(state.idx);
    var i = state.view.findIndex(function (s) { return s.fk === u.fk; });
    if (i >= 0) { state.idx = i; renderList(); renderStore(); }
    setStatus('בוטלה הפעולה האחרונה');
  }
  function exportPicks() {
    var blob = new Blob([P.exportCSV(state.picks)], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = P.exportFilename(new Date());
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }

  $('bConfirm').addEventListener('click', confirmSelection);
  $('bExisting').addEventListener('click', confirmExisting);
  $('bSkip').addEventListener('click', skip);
  $('bBack').addEventListener('click', function () { move(-1); });
  $('bNext').addEventListener('click', function () { move(1); });
  $('bUndo').addEventListener('click', doUndo);
  $('bExport').addEventListener('click', exportPicks);
  $('bCopy').addEventListener('click', function () {
    var s = current();
    if (s && s.address && navigator.clipboard) navigator.clipboard.writeText(s.address).then(function () { setStatus('הכתובת הועתקה'); });
  });

  document.addEventListener('keydown', function (e) {
    var t = e.target.tagName;
    if (t === 'INPUT' || t === 'SELECT' || t === 'TEXTAREA' || e.ctrlKey || e.metaKey || e.altKey) return;
    var k = e.key.toLowerCase();
    if (e.key === 'Enter') { e.preventDefault(); confirmSelection(); }
    else if (k === 'c') confirmExisting();
    else if (k === 's') skip();
    else if (k === 'b') move(-1);
    else if (k === 'n') move(1);
    else if (k === 'u') doUndo();
    else if (e.key === 'Escape') { state.selection = null; if (pickMarker) layer.removeLayer(pickMarker); setStatus('הבחירה נוקתה'); }
  });

  restore();
})();
