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
        import { InternalSwitch, StatsView } from './src/admin/screens/StatsScreen.tsx';
        export * as cookie from './src/admin/screens/stats/internalCookie.ts';
        export * from './src/admin/screens/stats/statsView.ts';
        export const view = (b) => renderToStaticMarkup(h(StatsView, { b }));
        export const switchHtml = () => renderToStaticMarkup(h(InternalSwitch));`,
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
    { source: 'web', metric: 'rejected_requests', dimension: 'super.xxl.co.il', points: [['2026-11-05', 333]] },
    { source: 'web', metric: 'internal_page_views', dimension: 'super.xxl.co.il', points: [['2026-11-05', 12]] },
    { source: 'web', metric: 'visitors', dimension: 'super.xxl.co.il', points: [['2026-11-04', 30], ['2026-11-05', 40]] },
    { source: 'api', metric: 'calls', dimension: 'android', points: [['2026-11-04', 300], ['2026-11-05', 100]] },
    { source: 'api', metric: 'calls', dimension: 'ios', points: [['2026-11-05', 100]] },
    { source: 'api', metric: 'calls', dimension: 'web', points: [['2026-11-05', 500]] },
    { source: 'api', metric: 'errors_5xx', dimension: 'android', points: [['2026-11-05', 2]] },
    { source: 'api', metric: 'calls', dimension: 'admin', points: [['2026-11-05', 1000]] },
  ],
  top_paths: [{ dimension: 'super.xxl.co.il/promos', value: 70 }, { dimension: 'super.xxl.co.il/(other)', value: 5 }],
  top_referrers: [{ dimension: 'super.xxl.co.il|google.com', value: 12 }, { dimension: 'super.xxl.co.il|(direct)', value: 40 }],
};

const m = await load();

test('days, totals, daily series with gaps, shares', () => {
  assert.deepEqual(m.dayList('2026-10-30', '2026-11-02'), ['2026-10-30', '2026-10-31', '2026-11-01', '2026-11-02']);
  assert.deepEqual(m.totals(BODY.series, 'web', 'page_views'), { 'super.xxl.co.il': 200, 'xxl.co.il': 10 });
  assert.equal(m.total(BODY.series, 'api', 'calls'), 2000);
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
  // SU11A-70: + rejected and team (internal) columns.
  assert.match(html, /super\.xxl\.co\.il<\/th><td[^>]*><span dir="ltr">200<\/span><\/td><td[^>]*><span dir="ltr">70<\/span><\/td><td[^>]*><span dir="ltr">20%<\/span><\/td><td[^>]*><span dir="ltr">333<\/span><\/td><td[^>]*><span dir="ltr">12<\/span><\/td><\/tr>/);
  assert.match(html, />נדחו<\/th>/);
  assert.match(html, />מהצוות<\/th>/);
  assert.match(html, /צפייה בדף = דפדפן שטען דף באתר בהצלחה \(200 או 304\)/);
  assert.match(html, /סה״כ<\/th><td[^>]*><span dir="ltr">210<\/span><\/td>/);
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
  assert.match(html, /אנדרואיד<\/th><td[^>]*><span dir="ltr">400<\/span><\/td><td[^>]*><span dir="ltr">20%<\/span><\/td><td[^>]*><span dir="ltr">2<\/span><\/td>/);
  // SU11A-70: the admin console is its own row.
  assert.match(html, /קונסולת ניהול<\/th><td[^>]*><span dir="ltr">1,000<\/span><\/td><td[^>]*><span dir="ltr">50%<\/span><\/td>/);
  assert.match(html, /iPhone<\/th><td[^>]*><span dir="ltr">100<\/span><\/td><td[^>]*><span dir="ltr">5%<\/span><\/td>/);
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

test('SU11A-70: "don\'t count this browser" switch and its cookie', () => {
  assert.equal(m.cookie.internalCookie(true),
    'xxl_internal=1; Domain=.xxl.co.il; Path=/; Secure; SameSite=Lax; Max-Age=31536000');
  assert.equal(m.cookie.internalCookie(false),
    'xxl_internal=; Domain=.xxl.co.il; Path=/; Secure; SameSite=Lax; Max-Age=0');
  assert.equal(m.cookie.isInternal('a=b; xxl_internal=1; c=d'), true);
  assert.equal(m.cookie.isInternal('xxl_internal=10'), false);
  assert.equal(m.cookie.isInternal(''), false);
  // Default off; a real switch with its label and explanation, focus ring visible.
  globalThis.document = { cookie: '' };
  let html = m.switchHtml();
  assert.match(html, /<button type="button" role="switch" aria-checked="false"[^>]*aria-labelledby="[^"]+"[^>]*aria-describedby="[^"]+"/);
  assert.match(html, /focus-visible:outline-2/);
  assert.match(html, /לא לספור את הדפדפן הזה/);
  assert.match(html, /כבוי: הצפיות מהדפדפן הזה נספרות כרגיל\./);
  assert.match(html, /יש להפעיל אותה בכל דפדפן ובכל טלפון/);
  assert.match(html, /רק על צפיות בדפים באתר/);
  assert.match(html, /בקשות API מהדפדפן הזה .* עדיין נספרות/);
  globalThis.document = { cookie: 'xxl_internal=1' };
  html = m.switchHtml();
  assert.match(html, /aria-checked="true"/);
  assert.match(html, /פעיל: הצפיות מהדפדפן הזה לא נספרות\./);
  // Turning it on writes exactly the cookie above (a fake document.cookie records it).
  const writes = [];
  globalThis.document = { get cookie() { return writes.at(-1)?.startsWith('xxl_internal=1') ? 'xxl_internal=1' : ''; },
    set cookie(v) { writes.push(v); } };
  assert.equal(m.cookie.writeInternal(true), true);
  assert.equal(m.cookie.writeInternal(false), false);
  assert.deepEqual(writes, [m.cookie.internalCookie(true), m.cookie.internalCookie(false)]);
});
