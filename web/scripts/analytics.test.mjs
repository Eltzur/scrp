// SU11A-71: GA4 never received data because the gtag shim pushed Arrays
// (`(...args) => dataLayer.push(args)`), which gtag.js ignores; it only reads
// Arguments objects. These tests bundle the real src/utils/analytics.ts and
// check: the shim pushes Arguments; nothing is loaded or sent before consent;
// every value sent is path-only (no '?' or '#'); one page_view per route
// (a query-only change such as /promos -> /promos?city=... is not one);
// declining / withdrawing stops the tag. Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';

const web = join(dirname(fileURLToPath(import.meta.url)), '..');
const GA = 'G-TEST123';
const ORIGIN = 'https://super.xxl.co.il';

const out = await build({
  entryPoints: [join(web, 'src/utils/analytics.ts')],
  bundle: true, platform: 'node', format: 'esm', write: false, logLevel: 'silent',
  define: { 'import.meta.env': JSON.stringify({ VITE_GA_MEASUREMENT_ID: GA }) },
});
const dir = mkdtempSync(join(tmpdir(), 'xxl-su71-'));
const file = join(dir, 'analytics.mjs');
writeFileSync(file, out.outputFiles[0].text);
let n = 0;

/** A fresh module instance in a fresh fake browser. */
async function fresh({ path = '/promos', search = '', hash = '', referrer = '', consent = null } = {}) {
  const store = new Map(consent === null ? [] : [['xxl_cookie_consent', consent]]);
  const scripts = [];
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  };
  globalThis.document = {
    referrer,
    createElement: () => ({}),
    head: { appendChild: (el) => scripts.push(el) },
  };
  globalThis.window = {
    location: { origin: ORIGIN, pathname: path, search, hash, href: ORIGIN + path + search + hash },
    dispatchEvent: () => true,
  };
  const m = await import(`${pathToFileURL(file).href}?n=${n++}`);
  return { m, scripts, w: globalThis.window };
}

const pageViews = (w) => (w.dataLayer || []).filter((e) => e[0] === 'event' && e[1] === 'page_view');

test.after(() => rmSync(dir, { recursive: true, force: true }));

test('the gtag shim pushes Arguments objects, never Arrays', async () => {
  const { m, w, scripts } = await fresh({ consent: 'true' });
  m.initGA();
  assert.equal(scripts.length, 1);
  assert.equal(scripts[0].src, `https://www.googletagmanager.com/gtag/js?id=${GA}`);
  assert.ok(w.dataLayer.length >= 3);
  for (const e of w.dataLayer) {
    assert.equal(Object.prototype.toString.call(e), '[object Arguments]');
    assert.equal(Array.isArray(e), false);
  }
  assert.deepEqual([...w.dataLayer].map((e) => e[0]), ['js', 'config', 'set', 'event']);
  assert.equal(w.dataLayer[1][1], GA);
  assert.equal(w.dataLayer[1][2].send_page_view, false);
});

test('nothing loads or is sent before consent; accept starts it', async () => {
  const { m, w, scripts } = await fresh();
  m.initGA();
  m.trackPageview('/promos');
  assert.equal(scripts.length, 0);
  assert.equal(w.dataLayer, undefined);
  assert.equal(w.gtag, undefined);
  m.setCookieConsent(true);
  assert.equal(scripts.length, 1);
  assert.equal(pageViews(w).length, 1);
  assert.equal(w[`ga-disable-${GA}`], false);
});

test('declined: nothing loads', async () => {
  const { m, w, scripts } = await fresh({ consent: 'false' });
  m.initGA();
  m.trackPageview('/categories');
  assert.equal(scripts.length, 0);
  assert.equal(w.dataLayer, undefined);
});

test('every value sent is path-only: no query string, no hash, referrer origin only', async () => {
  const { m, w } = await fresh({
    consent: 'true', path: '/', search: '?q=SECRETTEXT&city=x', hash: '#top',
    referrer: 'https://www.google.com/search?q=SECRETTEXT',
  });
  m.initGA();
  m.trackPageview('/promos?city=x#a');
  m.trackPageview('/categories/D02?sort=price');
  const blob = JSON.stringify([...w.dataLayer].map((e) => [...e]));
  assert.doesNotMatch(blob, /[?#]/);
  assert.doesNotMatch(blob, /SECRETTEXT|city=|sort=/);
  const cfg = w.dataLayer[1][2];
  assert.equal(cfg.page_location, `${ORIGIN}/`);
  assert.equal(cfg.page_referrer, 'https://www.google.com/');
  const [first, second, third] = pageViews(w).map((e) => e[2]);
  assert.deepEqual(first, { page_path: '/', page_location: `${ORIGIN}/`, page_referrer: 'https://www.google.com/' });
  assert.deepEqual(second, { page_path: '/promos', page_location: `${ORIGIN}/promos`, page_referrer: `${ORIGIN}/` });
  assert.equal(third.page_path, '/categories/D02');
  assert.equal(third.page_referrer, `${ORIGIN}/promos`);
});

test('one page_view for /promos with the ?city= replace; real route changes still count', async () => {
  const { m, w } = await fresh({ consent: 'true', path: '/promos' });
  m.initGA();                          // the page the visitor is on
  m.trackPageview('/promos');          // App.tsx mount effect, same location
  m.trackPageview('/promos?city=x');   // PromosPage's history.replace with the city
  m.trackPageview('/promos?city=y#z'); // another replace
  assert.equal(pageViews(w).length, 1);
  m.trackPageview('/categories');
  m.trackPageview('/promos');          // A -> B -> A is a real navigation
  assert.deepEqual(pageViews(w).map((e) => e[2].page_path), ['/promos', '/categories', '/promos']);
});

test('withdrawing consent stops the loaded tag', async () => {
  const { m, w } = await fresh({ consent: 'true', path: '/' });
  m.initGA();
  m.openCookiePreferences();           // clears the choice
  assert.equal(w[`ga-disable-${GA}`], true);
  m.trackPageview('/promos');
  m.setCookieConsent(false);
  m.trackPageview('/categories');
  assert.equal(pageViews(w).length, 1);
  assert.equal(w[`ga-disable-${GA}`], true);
  m.setCookieConsent(true);            // accepted again
  assert.equal(w[`ga-disable-${GA}`], false);
  m.trackPageview('/categories');
  assert.equal(pageViews(w).length, 2);
});

test('App.tsx tracks the pathname only, once per route change; the portal uses the same module', () => {
  const app = readFileSync(join(web, 'src/App.tsx'), 'utf8');
  assert.match(app, /trackPageview\(location\.pathname\);\s*\}, \[location\.pathname\]\);/);
  assert.doesNotMatch(app, /trackPageview\([^)]*search/);
  // SiteApp serves super.xxl.co.il and the portal (xxl.co.il / www): one call site.
  assert.equal(app.match(/trackPageview\(/g).length, 1);
  assert.equal(app.match(/initGA\(\)/g).length, 1);
  const src = readFileSync(join(web, 'src/utils/analytics.ts'), 'utf8');
  assert.match(src, /window\.gtag = function gtag\(\) \{\s*\/\/ eslint-disable-next-line prefer-rest-params\s*window\.dataLayer\.push\(arguments\);/);
  assert.doesNotMatch(src, /gtag = function \(\.\.\.args\)/);
});
