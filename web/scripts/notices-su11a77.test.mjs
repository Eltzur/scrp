// SU11A-77: the admin "הודעות לאפליקציה" screen (server-rendered with seeded
// data: three scopes, switch semantics, labelled fields, the rules per scope)
// and has_image in the list view (false = no image request; true / missing =
// as before). Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';

const web = join(dirname(fileURLToPath(import.meta.url)), '..');
const stubs = {
  name: 'stubs',
  setup(b) {
    b.onResolve({ filter: /(^|\/)BasketContext$/ }, () => ({ path: 'basket', namespace: 'stub' }));
    b.onResolve({ filter: /(^|\/)lib\/supabase$/ }, () => ({ path: 'supabase', namespace: 'stub' }));
    b.onLoad({ filter: /^basket$/, namespace: 'stub' }, () => ({
      contents: 'export const useBasket = () => ({ items: [], addItem() {}, removeItem() {} });', loader: 'js' }));
    b.onLoad({ filter: /^supabase$/, namespace: 'stub' }, () => ({
      contents: 'export const supabase = { auth: { getSession: async () => ({ data: { session: null } }) } };', loader: 'js' }));
  },
};
const out = await build({
  stdin: {
    contents: `
      import { createElement as h } from 'react';
      import { renderToStaticMarkup } from 'react-dom/server';
      import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
      import i18n from './src/i18n/config.ts';
      import NoticesScreen from './src/admin/screens/NoticesScreen.tsx';
      import ResultsListView from './src/components/results/ResultsListView.tsx';
      export const lang = (l) => i18n.changeLanguage(l);
      export const screen = (data) => {
        const qc = new QueryClient({ defaultOptions: { queries: { gcTime: Infinity, staleTime: Infinity, retry: false } } });
        qc.setQueryData(['admin-announcements'], data);
        return renderToStaticMarkup(h(QueryClientProvider, { client: qc }, h(NoticesScreen)));
      };
      export const list = (items) => {
        const qc = new QueryClient({ defaultOptions: { queries: { gcTime: Infinity } } });
        return renderToStaticMarkup(h(QueryClientProvider, { client: qc }, h(ResultsListView, { items })));
      };`,
    resolveDir: web, loader: 'tsx',
  },
  bundle: true, platform: 'node', format: 'esm', write: false, jsx: 'automatic', logLevel: 'silent',
  loader: { '.json': 'json' }, plugins: [stubs],
  define: { 'import.meta.env': JSON.stringify({}) },
  banner: { js: "import { createRequire } from 'module'; const require = createRequire(import.meta.url);" },
});
const dir = mkdtempSync(join(tmpdir(), 'xxl-su77-'));
const file = join(dir, 'bundle.mjs');
writeFileSync(file, out.outputFiles[0].text);
const noop = new Proxy(function () {}, { get: () => noop, apply: () => noop });
globalThis.document = new Proxy({ documentElement: {} }, { get: (t, k) => (k in t ? t[k] : noop) });
globalThis.window = { location: { hostname: 'admin.xxl.co.il', hash: '#notices', search: '' } };
const m = await import(pathToFileURL(file).href);
rmSync(dir, { recursive: true, force: true });
await m.lang('he');

const row = (platform, extra = {}) => ({
  platform, title: '', body: '', active: false, version: 0, updated_at: '2026-11-11T10:00:00+00:00', ...extra,
});
const DATA = {
  items: [row('ios', { title: 'עדכון', body: 'המחירים מתעדכנים כל יום.', active: true, version: 3 }), row('android'), row('both')],
  rules: { title_max: 60, body_max: 600 },
};

test('notices screen: three scopes, a real switch, labelled fields, preview, rules per scope', () => {
  const html = m.screen(DATA);
  for (const s of ['iPhone', 'Android', 'שתי הפלטפורמות']) assert.ok(html.includes(`aria-label="${s}"`), s);
  const sw = html.match(/<button[^>]*role="switch"[^>]*>/g) ?? [];
  assert.equal(sw.length, 3);
  assert.match(sw[0], /aria-checked="true"/);
  assert.ok(sw.slice(1).every(b => b.includes('aria-checked="false"') && /aria-labelledby="[^"]+"/.test(b)));
  const ids = [...html.matchAll(/<label for="([^"]+)"/g)].map(x => x[1]);
  assert.equal(ids.length, 6);
  for (const id of ids) assert.ok(html.includes(`id="${id}"`), id);
  assert.match(html, /maxLength="60"/);
  assert.match(html, /maxLength="600"/);
  assert.match(html, /<p class="font-bold text-gray-900" dir="auto">עדכון<\/p>/);    // live preview
  assert.equal((html.match(/Apple 2\.2/g) ?? []).length, 2);                         // ios + both, not android
  assert.equal((html.match(/Apple 3\.1\.1/g) ?? []).length, 3);
  assert.match(html, /גרסה 3/);
  assert.match(html, /border-gray-500/);                                             // ≥ 3:1 field borders
});

test('the tab is registered, lazy, with its own strings; the client uses the admin endpoints', () => {
  const app = readFileSync(join(web, 'src/admin/AdminApp.tsx'), 'utf8');
  assert.match(app, /const NoticesScreen = lazy\(\(\) => import\('\.\/screens\/NoticesScreen'\)\);/);
  assert.match(app, /'promos', 'notices', 'history'/);
  const he = JSON.parse(readFileSync(join(web, 'src/i18n/locales/he.json'), 'utf8'));
  assert.equal(he.admin.nav.notices, 'הודעות לאפליקציה');
  assert.equal(he.admin.notices.title, 'הודעות לאפליקציה');
  const api = readFileSync(join(web, 'src/admin/api.ts'), 'utf8');
  assert.match(api, /http\.put<Announcement>\(`\/admin\/announcements\/\$\{platform\}`/);
  assert.match(api, /http\.post<Announcement>\(`\/admin\/announcements\/\$\{platform\}\/active`/);
});

const quote = (chain_id, price) => ({ chain_id, chain_name: 'רשת', store_id: '001', store_name: 'סניף', city: 'חיפה',
  price, unit_of_measure: null, delta_from_cheapest: 0, is_promo: false });
const item = (code, has_image) => ({
  product: { item_code: code, canonical_name: `מוצר ${code}`, manufacturer: '', unit_of_measure: '', is_weighted: false,
    ...(has_image === undefined ? {} : { has_image }) },
  quotes: [quote('7290000000001', 5), quote('7290000000002', 6)], cheapest_price: 5, most_expensive_price: 6, chains_count: 2,
});

test('list view: has_image false asks for nothing; true and missing (older API) ask as before', () => {
  const img = (html) => (html.match(/<img[^>]*\/image"/g) ?? []).length;
  assert.equal(img(m.list([item('7290000000017', false)])), 0);
  assert.equal(img(m.list([item('7290000000017', true)])), 1);
  assert.equal(img(m.list([item('7290000000017', undefined)])), 1);
  assert.equal(img(m.list([item('7290000000017', null)])), 1);
  assert.equal(img(m.list([item('1', false), item('2', true), item('3', false)])), 1);
});
