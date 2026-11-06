// SU11A-69: the סטטיסטיקות screen. Bundles the pure helpers
// (src/admin/screens/stats/statsView.ts) and the real StatsView with esbuild
// and renders it with react-dom/server: totals and daily series (a day not
// stored is null, never 0), the card states ("לא מחובר" with its hint for
// GA4 / Play / App Store), the nginx vs GA4 explanation, accessible charts
// (legend text + data table), and nothing personal in the markup.
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';

const web = join(dirname(fileURLToPath(import.meta.url)), '..');

async function load() {
  const out = await build({
    stdin: {
      contents: `
        import { createElement as h } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import './src/i18n/config.ts';
        import { StatsView } from './src/admin/screens/StatsScreen.tsx';
        export * from './src/admin/screens/stats/statsView.ts';
        export const view = (b) => renderToStaticMarkup(h(StatsView, { b }));`,
      resolveDir: web, loader: 'tsx',
    },
    bundle: true, platform: 'node', format: 'esm', write: false, jsx: 'automatic', logLevel: 'silent',
    loader: { '.json': 'json' },
    define: { 'import.meta.env': JSON.stringify({ VITE_SUPABASE_URL: 'https://test.invalid', VITE_SUPABASE_ANON_KEY: 'x' }) },
    banner: { js: "import { createRequire } from 'module'; const require = createRequire(import.meta.url);" },
  });
  const dir = mkdtempSync(join(tmpdir(), 'xxl-admin-stats-'));
  const file = join(dir, 'bundle.mjs');
  writeFileSync(file, out.outputFiles[0].text);
  // i18n sets documentElement.dir; supabase-js touches document after import
  // (same stub as categories-page.test.mjs).
  const noop = new Proxy(function () {}, { get: () => noop, apply: () => noop });
  globalThis.document = new Proxy({ documentElement: {} }, { get: (t, k) => (k in t ? t[k] : noop) });
  try {
    return await import(pathToFileURL(file).href);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const run = (status, extra = {}) => ({ status, last_run_at: null, last_success_at: null, last_error_at: null,
  error: null, as_of: null, note: null, ...extra });

const BODY = {
  from: '2026-11-03', to: '2026-11-05', days: 3,
  sources: {
    web: run('ok', { as_of: '2026-11-05' }), api: run('ok', { as_of: '2026-11-05' }),
    ga4: run('not_configured'), play: run('error', { error: 'play export: HTTP 403' }), appstore: run('never_run'),
  },
  series: [
    { source: 'web', metric: 'page_views', dimension: 'super.xxl.co.il', points: [['2026-11-04', 90], ['2026-11-05', 110]] },
    { source: 'web', metric: 'page_views', dimension: 'xxl.co.il', points: [['2026-11-05', 10]] },
    { source: 'web', metric: 'bot_page_views', dimension: 'super.xxl.co.il', points: [['2026-11-05', 50]] },
    { source: 'web', metric: 'visitors', dimension: 'super.xxl.co.il', points: [['2026-11-04', 30], ['2026-11-05', 40]] },
    { source: 'api', metric: 'calls', dimension: 'android', points: [['2026-11-04', 300], ['2026-11-05', 100]] },
    { source: 'api', metric: 'calls', dimension: 'ios', points: [['2026-11-05', 100]] },
    { source: 'api', metric: 'calls', dimension: 'web', points: [['2026-11-05', 500]] },
    { source: 'api', metric: 'errors_5xx', dimension: 'android', points: [['2026-11-05', 2]] },
  ],
  top_paths: [{ dimension: 'super.xxl.co.il/promos', value: 70 }, { dimension: 'super.xxl.co.il/(other)', value: 5 }],
  top_referrers: [{ dimension: 'super.xxl.co.il|google.com', value: 12 }, { dimension: 'super.xxl.co.il|(direct)', value: 40 }],
};

const m = await load();

test('days, totals, daily series with gaps, shares', () => {
  assert.deepEqual(m.dayList('2026-10-30', '2026-11-02'), ['2026-10-30', '2026-10-31', '2026-11-01', '2026-11-02']);
  assert.deepEqual(m.totals(BODY.series, 'web', 'page_views'), { 'super.xxl.co.il': 200, 'xxl.co.il': 10 });
  assert.equal(m.total(BODY.series, 'api', 'calls'), 1000);
  assert.equal(m.total(BODY.series, 'api', 'calls', ['ios', 'web']), 600);
  const d3 = m.dayList(BODY.from, BODY.to);
  assert.deepEqual(m.daily(BODY.series, 'web', 'page_views', d3), [null, 90, 120]);
  assert.deepEqual(m.daily(BODY.series, 'api', 'calls', d3, ['ios']), [null, null, 100]);
  assert.equal(m.latest(BODY.series, 'web', 'visitors'), 40);
  assert.equal(m.latest(BODY.series, 'play', 'active_devices'), null);
  assert.equal(m.share(1, 3), 33.3);
  assert.equal(m.share(1, 0), null);
  assert.deepEqual(m.splitDim('super.xxl.co.il/categories/D02', '/'), ['super.xxl.co.il', '/categories/D02']);
  assert.deepEqual(m.splitDim('xxl.co.il|google.com', '|'), ['xxl.co.il', 'google.com']);
});

test('card states', () => {
  assert.equal(m.cardState(BODY, 'web'), 'ok');
  assert.equal(m.cardState(BODY, 'ga4'), 'not_connected');
  assert.equal(m.cardState(BODY, 'play'), 'error');
  assert.equal(m.cardState(BODY, 'appstore'), 'never_run');
  assert.equal(m.cardState({ ...BODY, unavailable: true }, 'web'), 'unavailable');
  assert.equal(m.cardState(undefined, 'web'), 'unavailable');
});

test('a null day breaks the line; the points stay in the box', () => {
  const segs = m.linePaths([1, null, 2, 4], 4, 100, 50, 0);
  assert.equal(segs.length, 2);
  assert.equal(segs[0], '0.0,37.5');
  assert.equal(segs[1], '66.7,25.0 100.0,0.0');
  assert.deepEqual(m.linePaths([null, null], 0, 100, 50), []);
});

test('the screen: sources, states, explanation, charts, no personal data', () => {
  const html = m.view(BODY);
  // Website table: host rows + total, bots as a share, no GA4 columns while GA4 is not connected.
  assert.match(html, /super\.xxl\.co\.il<\/th><td[^>]*>200<\/td><td[^>]*>70<\/td><td[^>]*>20%<\/td><\/tr>/);
  assert.match(html, /סה״כ<\/th><td[^>]*>210<\/td>/);
  assert.doesNotMatch(html, /משתמשים ב־GA4/);
  // States and hints.
  assert.match(html, /לא מחובר/);
  assert.match(html, /חסר מפתח חשבון שירות של Google ומספר הנכס ב־GA4/);
  assert.match(html, /שגיאה אחרונה: play export: HTTP 403/);
  assert.match(html, /טרם נאסף/);
  assert.match(html, /מעודכן עד 2026-11-05/);
  // nginx vs GA4 and the cookie caveat.
  assert.match(html, /למה המספרים שונים\?/);
  assert.match(html, /GA4 סופר רק מבקרים שאישרו עוגיות/);
  // App activity per platform.
  assert.match(html, /אנדרואיד<\/th><td[^>]*>400<\/td><td[^>]*>40%<\/td><td[^>]*>2<\/td>/);
  assert.match(html, /iPhone<\/th><td[^>]*>100<\/td><td[^>]*>10%<\/td>/);
  // Top lists with readable labels.
  assert.match(html, /\(דפים אחרים\)/);
  assert.match(html, /\(כניסה ישירה\)/);
  // Charts: an SVG with a title + description, a text legend and a data table.
  assert.match(html, /<svg[^>]*role="img"[^>]*aria-labelledby="[^"]+"/);
  assert.match(html, /<desc[^>]*>03\.11–05\.11/);
  assert.match(html, /הצגת הנתונים כטבלה/);
  assert.match(html, /stroke-dasharray="6 4"/); // the second line differs by pattern, not only colour
  assert.doesNotMatch(html, /\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/); // no IP-like text anywhere
});

test('before the migration: every card says so, nothing breaks', () => {
  const html = m.view({ ...BODY, unavailable: true, series: [], top_paths: [], top_referrers: [],
    sources: Object.fromEntries(Object.keys(BODY.sources).map(k => [k, run('never_run')])) });
  assert.match(html, /טבלאות הסטטיסטיקה עדיין לא קיימות/);
  assert.match(html, /אין נתונים בטווח הזה\./);
});
