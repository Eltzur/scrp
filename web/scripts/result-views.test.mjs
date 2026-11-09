// SU11A-72: result view modes. Pure logic (persistence incl. storage that
// throws, page-size clamp, page requests, row cheapest, default columns, the
// complete-only total winner and "חסר N") plus server renders of the list and
// the comparison table (aria, caption / th scope, never colour alone).
// Bundles the real modules with esbuild. Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';

const web = join(dirname(fileURLToPath(import.meta.url)), '..');

// The basket (and, behind it, auth + the Supabase client) is stubbed: the views
// only render BasketButton, and a real Supabase client keeps node alive.
const stubs = {
  name: 'stubs',
  setup(b) {
    b.onResolve({ filter: /(^|\/)BasketContext$/ }, () => ({ path: 'basket', namespace: 'stub' }));
    b.onResolve({ filter: /(^|\/)lib\/supabase$/ }, () => ({ path: 'supabase', namespace: 'stub' }));
    b.onLoad({ filter: /^basket$/, namespace: 'stub' }, () => ({
      contents: `export const useBasket = () => ({ items: [], addItem() {}, removeItem() {} });
                 export const BasketProvider = ({ children }) => children;`, loader: 'js' }));
    b.onLoad({ filter: /^supabase$/, namespace: 'stub' }, () => ({
      contents: `export const supabase = { auth: { getSession: async () => ({ data: { session: null } }),
                 onAuthStateChange: () => ({ data: { subscription: { unsubscribe() {} } } }) } };`, loader: 'js' }));
  },
};

const out = await build({
  stdin: {
    contents: `
      import { createElement as h } from 'react';
      import { renderToStaticMarkup } from 'react-dom/server';
      import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
      import i18n from './src/i18n/config.ts';
      import './src/components/results/strings.ts';
      import ResultsListView from './src/components/results/ResultsListView.tsx';
      import CompareTable from './src/components/results/CompareTable.tsx';
      import ViewSwitcher from './src/components/results/ViewSwitcher.tsx';
      export * as V from './src/utils/resultViews.ts';
      const qc = new QueryClient({ defaultOptions: { queries: { gcTime: Infinity, retry: false } } });
      const wrap = (el) => renderToStaticMarkup(h(QueryClientProvider, { client: qc }, el));
      export const lang = (l) => i18n.changeLanguage(l);
      export const list = (items) => wrap(h(ResultsListView, { items }));
      export const table = (items, city) => wrap(h(CompareTable, { items, city }));
      export const switcher = (p) => wrap(h(ViewSwitcher, p));`,
    resolveDir: web, loader: 'tsx',
  },
  bundle: true, platform: 'node', format: 'esm', write: false, jsx: 'automatic', logLevel: 'silent',
  loader: { '.json': 'json' }, plugins: [stubs],
  define: { 'import.meta.env': JSON.stringify({ VITE_SUPABASE_URL: 'https://test.invalid', VITE_SUPABASE_ANON_KEY: 'x' }) },
  banner: { js: "import { createRequire } from 'module'; const require = createRequire(import.meta.url);" },
});
const dir = mkdtempSync(join(tmpdir(), 'xxl-su72-'));
const file = join(dir, 'bundle.mjs');
writeFileSync(file, out.outputFiles[0].text);
const noop = new Proxy(function () {}, { get: () => noop, apply: () => noop });
globalThis.document = new Proxy({ documentElement: {} }, { get: (t, k) => (k in t ? t[k] : noop) });
globalThis.window = { location: { hostname: 'super.xxl.co.il', search: '', hash: '' }, addEventListener() {}, removeEventListener() {} };
const m = await import(pathToFileURL(file).href);
rmSync(dir, { recursive: true, force: true });
const { V } = m;
await m.lang('he');

// ------------------------------------------------------------------ fixtures
const C = { a: '7290000000001', b: '7290000000002', c: '7290000000003' };
const quote = (chain_id, price, extra = {}) => ({
  chain_id, chain_name: `רשת ${chain_id.slice(-1)}`, store_id: '001', store_name: 'סניף', city: 'חיפה',
  price, unit_of_measure: null, delta_from_cheapest: 0, is_promo: false, ...extra,
});
const item = (code, quotes) => {
  const prices = quotes.map(q => q.price);
  return {
    product: { item_code: code, canonical_name: `מוצר ${code}`, manufacturer: '', unit_of_measure: '', is_weighted: false },
    quotes, cheapest_price: Math.min(...prices), most_expensive_price: Math.max(...prices),
    chains_count: new Set(quotes.map(q => q.chain_id)).size,
  };
};
const P1 = item('1', [quote(C.a, 5), quote(C.b, 4), quote(C.c, 6)]);
const P2 = item('2', [quote(C.a, 3), quote(C.b, 3.5)]);           // c does not sell it
const memStore = () => { const d = new Map(); return { getItem: k => (d.has(k) ? d.get(k) : null), setItem: (k, v) => d.set(k, String(v)), d }; };
const throwing = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('quota'); } };

// ------------------------------------------------------------------ persistence
test('persistence: defaults, round trip, xxl_ keys, junk ignored', () => {
  const s = memStore();
  assert.equal(V.loadView(s), 'grid');
  assert.equal(V.loadPageSize(s), 25);
  assert.deepEqual(V.loadChains(s), []);
  V.saveView('table', s); V.savePageSize(0, s); V.saveChains([C.b, C.a], s);
  assert.equal(V.loadView(s), 'table');
  assert.equal(V.loadPageSize(s), 0);
  assert.deepEqual(V.loadChains(s), [C.b, C.a]);
  assert.ok([...s.d.keys()].every(k => k.startsWith('xxl_')));
  s.setItem('xxl_result_view', 'carousel'); s.setItem('xxl_result_page_size', '7'); s.setItem('xxl_table_chains', '{"x":1}');
  assert.equal(V.loadView(s), 'grid');
  assert.equal(V.loadPageSize(s), 25);
  assert.deepEqual(V.loadChains(s), []);
  s.setItem('xxl_result_page_size', '');
  assert.equal(V.loadPageSize(s), 25);
  s.setItem('xxl_table_chains', JSON.stringify([C.a, C.a, 'nope', 5, ...Array.from({ length: 12 }, (_, i) => `72900000001${String(i).padStart(2, '0')}`)]));
  const ch = V.loadChains(s);
  assert.equal(ch.length, 8); assert.equal(ch[0], C.a); assert.equal(new Set(ch).size, 8);
});

test('persistence: storage that throws never breaks the page', () => {
  assert.equal(V.loadView(throwing), 'grid');
  assert.equal(V.loadPageSize(throwing), 25);
  assert.deepEqual(V.loadChains(throwing), []);
  assert.doesNotThrow(() => { V.saveView('list', throwing); V.savePageSize(50, throwing); V.saveChains([C.a], throwing); });
  assert.equal(V.loadView(null), 'grid');
});

// ------------------------------------------------------------------ page size / requests
test('page size: the table clamps 100 / הכל to 50 with a note; the list keeps them', () => {
  assert.deepEqual(V.effectivePageSize('table', 100), { size: 50, clamped: true });
  assert.deepEqual(V.effectivePageSize('table', 0), { size: 50, clamped: true });
  assert.deepEqual(V.effectivePageSize('table', 25), { size: 25, clamped: false });
  assert.deepEqual(V.effectivePageSize('list', 100), { size: 100, clamped: false });
  assert.deepEqual(V.effectivePageSize('list', 0), { size: 0, clamped: false });
});

test('page requests: one request per page, capped by the endpoint; הכל = the cap from 0', () => {
  assert.deepEqual(V.pageRequest(25, 0, 100), { limit: 25, offset: 0 });
  assert.deepEqual(V.pageRequest(25, 2, 100), { limit: 25, offset: 50 });
  assert.deepEqual(V.pageRequest(100, 1, 60), { limit: 60, offset: 60 });
  assert.deepEqual(V.pageRequest(0, 3, 100), { limit: 100, offset: 0 });
  assert.deepEqual(V.pageRequest(0, 0, 60), { limit: 60, offset: 0 });
});

// ------------------------------------------------------------------ cheapest / columns / totals
test('row cheapest: among the shown chains, ties all win, one seller is no comparison', () => {
  assert.deepEqual([...V.rowCheapest(P1, [C.a, C.b, C.c])], [C.b]);
  assert.deepEqual([...V.rowCheapest(P1, [C.a, C.c])], [C.a]);
  assert.deepEqual([...V.rowCheapest(P2, [C.a, C.c])], []);            // only a sells it among these
  const tie = item('3', [quote(C.a, 2), quote(C.b, 2), quote(C.c, 9)]);
  assert.deepEqual([...V.rowCheapest(tie, [C.a, C.b, C.c])].sort(), [C.a, C.b].sort());
  const branches = item('4', [quote(C.a, 7), quote(C.a, 4, { store_id: '002' }), quote(C.b, 5)]);
  assert.equal(V.quoteByChain(branches).get(C.a).price, 4);            // the chain's cheapest branch
});

test('default columns: top 5 by products carried, else the remembered choice; 1..8 columns', () => {
  const many = Array.from({ length: 7 }, (_, i) => `72900000000${String(10 + i)}`);
  const items = [item('a', many.map((c, i) => quote(c, 1 + i))), item('b', many.slice(0, 3).map(c => quote(c, 2)))];
  const cols = V.tableColumns(items, []);
  assert.equal(cols.length, 5);
  assert.deepEqual(cols.slice(0, 3), many.slice(0, 3));
  assert.deepEqual(V.tableColumns(items, [C.c, C.a]), [C.c, C.a]);
  let c8 = many.concat([C.a]);
  assert.equal(V.toggleColumn(c8, C.b), c8);                           // already 8: unchanged
  assert.deepEqual(V.toggleColumn([C.a], C.a), [C.a]);                 // never fewer than 1
  assert.deepEqual(V.toggleColumn([C.a, C.b], C.a), [C.b]);
  assert.deepEqual(V.toggleColumn([C.a], C.b), [C.a, C.b]);
});

test('totals: the cheapest total is marked only among chains carrying every product; others say חסר N', () => {
  const t = V.chainTotals([P1, P2], [C.a, C.b, C.c]);
  const by = Object.fromEntries(t.map(x => [x.chain_id, x]));
  assert.deepEqual([by[C.a].total, by[C.a].missing], [8, 0]);
  assert.deepEqual([by[C.b].total, by[C.b].missing], [7.5, 0]);
  assert.deepEqual([by[C.c].total, by[C.c].missing], [6, 1]);         // cheapest sum, but incomplete
  assert.deepEqual(t.filter(x => x.winner).map(x => x.chain_id), [C.b]);
  assert.equal(by[C.c].winner, false);
  const none = V.chainTotals([P1, P2], [C.c]);
  assert.equal(none.some(x => x.winner), false);
  const tie = V.chainTotals([item('5', [quote(C.a, 2), quote(C.b, 2)])], [C.a, C.b]);
  assert.equal(tie.filter(x => x.winner).length, 2);
  assert.equal(V.chainTotals([], [C.a]).some(x => x.winner), false);
});

// ------------------------------------------------------------------ renders
test('list: rows closed by default, accordion aria, cheapest in words, savings', () => {
  const bundle = item('6', [quote(C.a, 3.75, { is_promo: true, promo_price: 3.75, promo_min_qty: 8, shelf_price: 5 }), quote(C.b, 4.2)]);
  const html = m.list([P1, bundle]);
  const btns = html.match(/<button[^>]*aria-expanded="[^"]*"[^>]*>/g) ?? [];
  assert.equal(btns.length, 2);
  assert.ok(btns.every(b => b.includes('aria-expanded="false"') && /aria-controls="[^"]+"/.test(b)));
  assert.equal((html.match(/hidden=""/g) ?? []).length, 2);            // both panels closed
  assert.match(html, /הכי זול ברשת 2/);                                 // P1's cheapest chain, in words
  assert.match(html, /רשתות: 3/);
  assert.match(html, /חיסכון/);
  assert.doesNotMatch(html, /src="[^"]*\/image"[^>]*alt="[^"]+"/);     // decorative thumbnail (alt="")
});

test('table: caption, th scope, sticky product column, — for not sold, words for cheapest and totals', () => {
  globalThis.localStorage = memStore();
  localStorage.setItem('xxl_table_chains', JSON.stringify([C.a, C.b, C.c]));
  const html = m.table([P1, P2], 'חיפה');
  assert.match(html, /<caption class="sr-only">השוואת מחירים: 2 מוצרים לפי רשת<\/caption>/);
  assert.equal((html.match(/scope="col"/g) ?? []).length, 4);          // product + 3 chains
  assert.equal((html.match(/scope="row"/g) ?? []).length, 3);          // 2 products + total
  assert.match(html, /sticky start-0/);
  assert.match(html, /<span aria-hidden="true">—<\/span><span class="sr-only">לא נמכר<\/span>/);
  assert.match(html, /<span class="sr-only">, הכי זול<\/span>/);
  assert.match(html, /חסר 1/);
  assert.equal((html.match(/הסכום הזול ביותר/g) ?? []).length, 1);
  assert.match(html, /לכל רשת מוצג המחיר בסניף הזול שלה בחיפה/);
  assert.match(html, /aria-pressed="true"/);
  const bundle = item('6', [quote(C.a, 3.75, { is_promo: true, promo_price: 3.75, promo_min_qty: 8, shelf_price: 5 }), quote(C.b, 4.2)]);
  const promo = m.table([bundle], null);
  assert.match(promo, /8 יח(?:'|&#x27;) ב-₪30\.00/);                               // a bundle is never a bare unit price
  assert.match(promo, />מבצע</);
  // a chain selling none of the page's products shows no ₪0.00 total
  assert.match(promo, /<td class="px-3 py-2 text-center whitespace-nowrap"><span aria-hidden="true">—<\/span><span class="sr-only">לא נמכר<\/span><span class="block text-xs font-medium text-amber-900">חסר 1<\/span><\/td>/);
  assert.doesNotMatch(promo, />‏?0\.00/);                         // (the bundle's ₪30.00 is fine)
  const noCity = m.table([P1], null);
  assert.match(noCity, /לא נבחרה עיר: לכל רשת מוצג המחיר הזול שלה בכל הארץ/);
  delete globalThis.localStorage;
});

test('switcher: aria-pressed segmented control; page size only for list / table; table sizes 10/25/50', () => {
  const grid = m.switcher({ view: 'grid', size: 25, onView() {}, onSize() {}, pagedAvailable: true });
  assert.equal((grid.match(/aria-pressed="true"/g) ?? []).length, 1);
  assert.match(grid, /רשת/); assert.match(grid, /רשימה/); assert.match(grid, /טבלת השוואה/);
  assert.doesNotMatch(grid, /<select/);
  const tbl = m.switcher({ view: 'table', size: 100, onView() {}, onSize() {}, pagedAvailable: true });
  assert.deepEqual([...tbl.matchAll(/<option value="(\d+)"/g)].map(x => x[1]), ['10', '25', '50']);
  assert.match(tbl, /<option value="50" selected="">/);
  const lst = m.switcher({ view: 'list', size: 0, onView() {}, onSize() {}, pagedAvailable: true });
  assert.deepEqual([...lst.matchAll(/<option value="(\d+)"/g)].map(x => x[1]), ['10', '25', '50', '100', '0']);
  const store = m.switcher({ view: 'grid', wanted: 'list', size: 25, onView() {}, onSize() {}, pagedAvailable: false });
  assert.equal((store.match(/disabled=""/g) ?? []).length, 2);
  assert.match(store, /בקיבוץ לפי רשת/);
});

test('nothing in the views touches the URL or sends analytics', () => {
  const files = readdirSync(join(web, 'src/components/results')).filter(f => f.endsWith('.tsx') || f.endsWith('.ts'))
    .map(f => join(web, 'src/components/results', f))
    .concat([join(web, 'src/components/ResultViews.tsx'), join(web, 'src/utils/resultViews.ts'), join(web, 'src/utils/resultViewPrefs.ts')]);
  for (const f of files) {
    const src = readFileSync(f, 'utf8');
    assert.doesNotMatch(src, /useSearchParams|setParams|navigate\(|history\.|gtag|trackPageview/, f);
  }
});
