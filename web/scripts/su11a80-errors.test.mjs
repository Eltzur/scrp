// SU11A-80 (SU11A-79 batch A): customer error text with no developer hint (H1),
// the top-level error boundary fallback (H6), the catch-all "not found" page
// and its route meta (M1), the 20 s axios timeout mapped to the customer error
// with a retry (M2), the quiet /cities retry (L4) and the /stats staleTime (C1).
// Bundles the real modules with esbuild and renders them with react-dom/server.
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { createServer } from 'node:http';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';

const web = join(dirname(fileURLToPath(import.meta.url)), '..');

async function load() {
  const out = await build({
    stdin: {
      contents: `
        import { createElement as h } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { MemoryRouter, Routes, Route } from 'react-router-dom';
        import i18n from './src/i18n/config.ts';
        import ErrorState from './src/components/ErrorState.tsx';
        import AppErrorBoundary from './src/components/AppErrorBoundary.tsx';
        import NotFoundPage from './src/pages/NotFoundPage.tsx';
        export * as boundary from './src/components/AppErrorBoundary.tsx';
        export { http, isBusyError, API_TIMEOUT_MS } from './src/api/client.ts';
        export { loadWithRetry } from './src/utils/retry.ts';
        export { resolveRouteMeta, NOT_FOUND_TITLE } from './src/utils/seoMeta.ts';
        export { STATS_STALE_MS } from './src/api/hooks.ts';
        export const lang = (l) => i18n.changeLanguage(l);
        export const errorState = (props) => renderToStaticMarkup(h(ErrorState, props));
        export const notFound = (path) => renderToStaticMarkup(
          h(MemoryRouter, { initialEntries: [path] },
            h(Routes, null,
              h(Route, { path: '/', element: h('p', null, 'HOME') }),
              h(Route, { path: '*', element: h(NotFoundPage) }))));
        export function fallback(onReload) {
          const b = new AppErrorBoundary({ children: h('p', null, 'CHILD'), onReload });
          b.state = AppErrorBoundary.getDerivedStateFromError(new Error('boom secret stack'));
          return { html: renderToStaticMarkup(b.render()), boundary: b };
        }
        export function healthy() {
          return renderToStaticMarkup(h(AppErrorBoundary, null, h('p', null, 'CHILD')));
        }`,
      resolveDir: web, loader: 'tsx',
    },
    bundle: true, platform: 'node', format: 'esm', write: false, jsx: 'automatic', logLevel: 'silent',
    loader: { '.json': 'json' },
    define: { 'import.meta.env': JSON.stringify({
      VITE_SUPABASE_URL: 'https://test.invalid', VITE_SUPABASE_ANON_KEY: 'x', VITE_API_URL: 'http://127.0.0.1:9' }) },
    banner: { js: "import { createRequire } from 'module'; const require = createRequire(import.meta.url);" },
  });
  const dir = mkdtempSync(join(tmpdir(), 'xxl-su80-'));
  const file = join(dir, 'bundle.mjs');
  writeFileSync(file, out.outputFiles[0].text);
  const noop = new Proxy(function () {}, { get: () => noop, apply: () => noop });
  globalThis.document = new Proxy({ documentElement: {} }, { get: (t, k) => (k in t ? t[k] : noop) });
  globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
  try {
    return await import(pathToFileURL(file).href);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const m = await load();
const DEV_TEXT = /uvicorn|--reload|localhost|api\.main|<code/i;

// ------------------------------------------------------------------ H1
test('H1: the error screen shows customer text only, in Hebrew and English', async () => {
  await m.lang('he');
  const he = m.errorState({ onRetry: () => {} });
  assert.match(he, /לא ניתן לגשת לשרת/);
  assert.match(he, /השירות אינו זמין כרגע\. נסו שוב בעוד כמה דקות\./);
  assert.match(he, /<button[^>]*>.*נסה שוב/);
  assert.doesNotMatch(he, DEV_TEXT);
  assert.match(m.errorState({ busy: true }), /השרת עמוס כרגע/);
  await m.lang('en');
  assert.doesNotMatch(m.errorState({}), DEV_TEXT);
  await m.lang('he');
});

test('H1: no developer text anywhere in the web locales', () => {
  for (const f of ['he.json', 'en.json']) {
    const s = readFileSync(join(web, 'src', 'i18n', 'locales', f), 'utf8');
    assert.doesNotMatch(s, /uvicorn|--reload|api\.main:app|npm run|localhost/i, f);
  }
});

// ------------------------------------------------------------------ H6
test('H6: the boundary renders its children while healthy', () => {
  assert.equal(m.healthy(), '<p>CHILD</p>');
});

test('H6: the fallback is Hebrew RTL with a reload button and no error text', () => {
  let reloads = 0;
  const { html } = m.fallback(() => { reloads += 1; });
  assert.match(html, /dir="rtl"/);
  assert.match(html, /lang="he"/);
  assert.match(html, new RegExp(m.boundary.FALLBACK_TITLE));
  assert.match(html, new RegExp(m.boundary.FALLBACK_TEXT.replace(/\./g, '\\.')));
  assert.match(html, /<button type="button"[^>]*>רענון הדף<\/button>/);
  assert.doesNotMatch(html, /boom|secret|stack|CHILD/);
});

test('H6: the button reloads; the error goes to the console only', () => {
  let reloads = 0;
  const { boundary } = m.fallback(() => { reloads += 1; });
  boundary.reload();
  assert.equal(reloads, 1);
  const logged = [];
  const orig = console.error;
  console.error = (...a) => logged.push(a);
  try { boundary.componentDidCatch(new Error('x'), { componentStack: 'at Foo' }); }
  finally { console.error = orig; }
  assert.equal(logged.length, 1);
  assert.equal(logged[0][0], '[AppErrorBoundary]');
});

test('H6: main.tsx wraps the whole tree in the boundary', () => {
  const s = readFileSync(join(web, 'src', 'main.tsx'), 'utf8');
  const a = s.indexOf('<AppErrorBoundary>'), b = s.indexOf('<App />'), c = s.indexOf('</AppErrorBoundary>');
  assert.ok(a > 0 && a < b && b < c, 'AppErrorBoundary must enclose <App />');
});

// ------------------------------------------------------------------ M1
test('M1: an unknown path renders the Hebrew not-found page with a link home', () => {
  const html = m.notFound('/no-such-page-xyz');
  assert.match(html, /<h1[^>]*>הדף לא נמצא<\/h1>/);
  assert.match(html, /<a [^>]*href="\/"[^>]*>חזרה לדף הבית<\/a>/);
  assert.equal(m.notFound('/'), '<p>HOME</p>');
});

test('M1: the catch-all route is last in the Super shell', () => {
  const s = readFileSync(join(web, 'src', 'App.tsx'), 'utf8');
  assert.match(s, /<Route path="\/account\/delete"[^\n]*\n\s*<Route path="\*" element=\{<NotFoundPage \/>\} \/>\n\s*<\/Routes>/);
});

test('M1: an unknown path gets the not-found title, noindex and no canonical', () => {
  for (const portal of [false, true]) {
    const r = m.resolveRouteMeta('/no-such-page-xyz', portal);
    assert.equal(r.title, `${m.NOT_FOUND_TITLE} | ${portal ? 'XXL' : 'SUPER XXL'}`);
    assert.equal(r.noindex, true);
    assert.equal(r.canonical, null);
  }
  assert.notEqual(m.resolveRouteMeta('/promos', false).title, `${m.NOT_FOUND_TITLE} | SUPER XXL`);
});

// ------------------------------------------------------------------ M2
test('M2: the API client gives up after 20 s', () => {
  assert.equal(m.API_TIMEOUT_MS, 20000);
  assert.equal(m.http.defaults.timeout, 20000);
});

test('M2: a timed-out request is not "busy", so the customer error with retry shows', async () => {
  const server = createServer(() => { /* never answers */ });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const { port } = server.address();
  try {
    await assert.rejects(
      m.http.get(`http://127.0.0.1:${port}/search`, { timeout: 150 }),
      (err) => {
        assert.equal(err.code, 'ECONNABORTED');
        assert.equal(m.isBusyError(err), false);
        return true;
      },
    );
  } finally {
    server.closeAllConnections?.();
    server.close();
  }
  await m.lang('he');
  const html = m.errorState({ onRetry: () => {}, busy: false });
  assert.match(html, /השירות אינו זמין כרגע/);
  assert.match(html, /נסה שוב/);
});

// ------------------------------------------------------------------ L4
function fakeTimers() {
  const q = [];
  return { q, schedule: (cb, ms) => { q.push({ cb, ms }); return q.length; }, cancel: (h) => { q[h - 1].cancelled = true; } };
}
const tick = () => new Promise((r) => setImmediate(r));

test('L4: a failed /cities call is retried quietly and the late value is used', async () => {
  const t = fakeTimers();
  let calls = 0; const got = [];
  m.loadWithRetry(() => (++calls < 3 ? Promise.reject(new Error('down')) : Promise.resolve(['תל אביב'])),
    (v) => got.push(v), [5, 10, 20], t.schedule, t.cancel);
  await tick();
  assert.deepEqual(t.q.map((x) => x.ms), [5]);
  t.q[0].cb(); await tick();
  assert.deepEqual(t.q.map((x) => x.ms), [5, 10]);
  t.q[1].cb(); await tick();
  assert.equal(calls, 3);
  assert.deepEqual(got, [['תל אביב']]);
  assert.equal(t.q.length, 2);
});

test('L4: gives up silently after the last delay, and cleanup cancels a pending retry', async () => {
  const t = fakeTimers();
  let calls = 0;
  m.loadWithRetry(() => { calls += 1; return Promise.reject(new Error('down')); }, () => assert.fail('no value'),
    [1], t.schedule, t.cancel);
  await tick(); t.q[0].cb(); await tick();
  assert.equal(calls, 2); assert.equal(t.q.length, 1);

  const t2 = fakeTimers();
  const stop = m.loadWithRetry(() => Promise.reject(new Error('down')), () => assert.fail('no value'), [1], t2.schedule, t2.cancel);
  await tick(); stop();
  assert.equal(t2.q[0].cancelled, true);
});

test('L4: App.tsx no longer pings /health and retries /cities', () => {
  const s = readFileSync(join(web, 'src', 'App.tsx'), 'utf8');
  assert.doesNotMatch(s, /fetch\(['"]https:\/\/api-super\.xxl\.co\.il\/health/);
  assert.match(s, /loadWithRetry\(getCities, setCities\)/);
});

// ------------------------------------------------------------------ C1 (web side)
test('C1: StatsBar data stays fresh for 10 minutes (no refetch per route change)', () => {
  assert.equal(m.STATS_STALE_MS, 10 * 60 * 1000);
  const s = readFileSync(join(web, 'src', 'api', 'hooks.ts'), 'utf8');
  assert.match(s, /queryKey: \['stats'\],\s*queryFn: getStats,\s*staleTime: STATS_STALE_MS,\s*refetchOnWindowFocus: false/);
});

