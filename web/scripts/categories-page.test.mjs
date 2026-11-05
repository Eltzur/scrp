// SU11A-67: category browse pages. The URL state (utils/categoryView.ts) and
// the rendered page (esbuild + react-dom/server, as gift-coupon.test.mjs):
// breadcrumbs, chips, labelled filters, the card grid with add-to-basket,
// "טען עוד", the department grid. Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import {
  CATEGORY_OFFSET_MAX, categoryParams, findNode, isNodeId, itemsRequest, nextOffset, readCategoryView,
} from '../src/utils/categoryView.ts';

const web = join(dirname(fileURLToPath(import.meta.url)), '..');

async function load() {
  const out = await build({
    stdin: {
      contents: `
        import { createElement as h } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { MemoryRouter, Routes, Route } from 'react-router-dom';
        import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
        import './src/i18n/config.ts';
        import { AuthProvider } from './src/components/AuthContext.tsx';
        import { BasketProvider } from './src/components/BasketContext.tsx';
        import { FavoritesProvider } from './src/components/FavoritesContext.tsx';
        import CategoriesPage from './src/pages/categories/CategoriesPage.tsx';
        export function page(url, seed) {
          const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
          for (const [key, data] of seed) qc.setQueryData(key, data);
          return renderToStaticMarkup(h(QueryClientProvider, { client: qc },
            h(MemoryRouter, { initialEntries: [url] },
              h(AuthProvider, null, h(BasketProvider, null, h(FavoritesProvider, null,
                h(Routes, null,
                  h(Route, { path: '/categories', element: h(CategoriesPage) }),
                  h(Route, { path: '/categories/:id', element: h(CategoriesPage) }))))))));
        }`,
      resolveDir: web, loader: 'tsx',
    },
    bundle: true, platform: 'node', format: 'esm', write: false, jsx: 'automatic', logLevel: 'silent',
    loader: { '.json': 'json' },
    define: { 'import.meta.env': JSON.stringify({ VITE_SUPABASE_URL: 'https://test.invalid', VITE_SUPABASE_ANON_KEY: 'x' }) },
    banner: { js: "import { createRequire } from 'module'; const require = createRequire(import.meta.url);" },
  });
  const dir = mkdtempSync(join(tmpdir(), 'xxl-cat-'));
  const file = join(dir, 'bundle.mjs');
  writeFileSync(file, out.outputFiles[0].text);
  // i18n sets documentElement.dir; sonner / supabase-js touch document after
  // import. A stub whose every other member is a no-op is enough here.
  const noop = new Proxy(function () {}, { get: () => noop, apply: () => noop });
  globalThis.document = new Proxy({ documentElement: {} }, { get: (t, k) => (k in t ? t[k] : noop) });
  try {
    return await import(pathToFileURL(file).href);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const TREE = {
  min_linked: 5, total: 40, built_at: null,
  departments: [
    { id: 'D02', level: 1, name_he: 'מוצרי חלב', name_en: 'Dairy', count: 40, children: [
      { id: 'D02.C01', level: 2, name_he: 'חלב', name_en: 'Milk', count: 30, linked: true, children: [
        { id: 'D02.C01.S01', level: 3, name_he: 'חלב טרי', name_en: 'Fresh milk', count: 12, linked: true, children: [] }] },
      { id: 'D02.C02', level: 2, name_he: 'גבינות', name_en: 'Cheese', count: 10, linked: true, children: [] }] },
    { id: 'D16', level: 1, name_he: 'ריק', name_en: 'Empty', count: 0, children: [] },
  ],
};

const ITEM = {
  product: { item_code: '7290000000001', canonical_name: 'חלב 3% תנובה 1 ליטר', manufacturer: 'תנובה',
    unit_of_measure: 'ליטר', is_weighted: false, names_per_chain: {} },
  quotes: [{ chain_id: 'A', chain_name: 'רשת א', store_id: '1', store_name: 'סניף', city: 'חיפה', price: 6.9,
    unit_price: 6.9, unit_of_measure: 'ליטר', updated_at: null, delta_from_cheapest: 0, is_promo: false,
    promo_kind: 'shelf', shelf_price: 6.9, promo_price: null, promo_min_qty: null, promo_description: null,
    promo_end: null, store_fk: 1 }],
  cheapest_price: 6.9, most_expensive_price: 6.9, chains_count: 1, category_id: 'D02.C01.S01',
};

const PAGE = {
  category: { id: 'D02.C01', level: 2, name_he: 'חלב', name_en: 'Milk' },
  path: [{ id: 'D02', level: 1, name_he: 'מוצרי חלב', name_en: 'Dairy' }, { id: 'D02.C01', level: 2, name_he: 'חלב', name_en: 'Milk' }],
  children: [{ id: 'D02.C01.S01', level: 3, name_he: 'חלב טרי', name_en: 'Fresh milk', count: 12 }],
  count: 30, total: 30, total_exact: true, has_more: true, sort: 'popular', items: [ITEM],
};

// ------------------------------------------------------------------ URL state

test('readCategoryView: defaults, allowed sorts only, city absent vs all cities', () => {
  assert.deepEqual(readCategoryView(new URLSearchParams('')), { city: null, chain: '', sort: 'popular', promo: false });
  const v = readCategoryView(new URLSearchParams('city=&chain=A&sort=cheapest&promo=1'));
  assert.deepEqual(v, { city: '', chain: 'A', sort: 'cheapest', promo: true });
  assert.equal(readCategoryView(new URLSearchParams('sort=price')).sort, 'popular');
  assert.equal(readCategoryView(new URLSearchParams('promo=yes')).promo, false);
});

test('categoryParams: defaults are left out of the URL, other keys dropped', () => {
  const p = categoryParams(new URLSearchParams('city=חיפה&junk=1'), { sort: 'name', promo: true });
  assert.equal(p.toString(), new URLSearchParams({ city: 'חיפה', sort: 'name', promo: '1' }).toString());
  const back = categoryParams(p, { sort: 'popular', promo: false, chain: '' });
  assert.equal(back.toString(), new URLSearchParams({ city: 'חיפה' }).toString());
  assert.equal(categoryParams(new URLSearchParams(''), { city: '' }).toString(), 'city=');   // all cities
});

test('itemsRequest: the URL city, else the remembered one; on_promo / sort only when set', () => {
  const v = readCategoryView(new URLSearchParams(''));
  assert.deepEqual(itemsRequest(v, 'חיפה'), { city: 'חיפה', limit: 30, offset: 0 });
  assert.deepEqual(itemsRequest({ ...v, city: '' }, 'חיפה', 60), { limit: 30, offset: 60 });
  assert.deepEqual(itemsRequest({ city: null, chain: 'A', sort: 'cheapest', promo: true }, '', 30),
    { chain: 'A', sort: 'cheapest', on_promo: true, limit: 30, offset: 30 });
});

test('nextOffset: the loaded count, none at the end or past the API cap', () => {
  const pg = n => ({ has_more: true, items: Array(n).fill(0) });
  assert.equal(nextOffset(pg(30), [pg(30)]), 30);
  assert.equal(nextOffset({ has_more: false, items: [] }, [pg(30)]), undefined);
  const many = Array(Math.ceil((CATEGORY_OFFSET_MAX + 30) / 30)).fill(pg(30));
  assert.equal(nextOffset(pg(30), many), undefined);
});

test('isNodeId and findNode', () => {
  for (const ok of ['D02', 'D02.C01', 'D02.C01.S01']) assert.ok(isNodeId(ok), ok);
  for (const bad of ['', 'd02', 'D2', 'D02.C1', 'D02.C01.S01.X', '../x']) assert.ok(!isNodeId(bad), bad);
  assert.equal(findNode(TREE, 'D02.C01.S01').name_he, 'חלב טרי');
  assert.equal(findNode(TREE, 'D02.C09'), null);
  assert.equal(findNode(undefined, 'D02'), null);
});

// ------------------------------------------------------------------ rendering

const m = await load();
const key = (id, city = '', chain = '', sort = 'popular', promo = false) => ['category-items', id, city, chain, sort, promo];
const seed = (extra = []) => [[['cities'], [{ city: 'חיפה', chain_count: 1, store_count: 1, chain_ids: ['A'] }]],
  [['chains'], [{ chain_id: 'A', name: 'רשת א', total_barcodes: 1, total_stores_loaded: 1 }]],
  [['browse-tree'], TREE], ...extra];

test('department grid: links with counts, empty departments left out', () => {
  const html = m.page('/categories', seed());
  assert.match(html, /<h1[^>]*>קטגוריות<\/h1>/);
  assert.ok(html.includes('href="/categories/D02"') && html.includes('40 מוצרים'));
  assert.ok(!html.includes('href="/categories/D16"'));
  assert.ok(html.includes('חלב · גבינות'));
});

test('category page: breadcrumbs, chips, labelled filters, cards with add-to-basket, load more', () => {
  const html = m.page('/categories/D02.C01?city=' + encodeURIComponent('חיפה'),
    seed([[key('D02.C01', 'חיפה'), { pages: [PAGE], pageParams: [0] }]]));
  assert.match(html, /<nav aria-label="פירורי לחם"/);
  assert.ok(html.includes('href="/categories/D02"') && html.includes('aria-current="page"'));
  assert.match(html, /<h1[^>]*>חלב<\/h1>/);
  assert.ok(html.includes('href="/categories/D02.C01.S01"') && html.includes('12 מוצרים'));
  for (const label of ['עיר', 'רשת', 'מיון', 'רק במבצע']) assert.ok(html.includes(label), label);
  assert.match(html, /<option value="חיפה" selected="">/);
  assert.ok(html.includes('type="checkbox"'));
  assert.ok(html.includes('חלב 3% תנובה 1 ליטר'), 'the product card');
  assert.ok(html.includes('הוסף לסל'), 'add-to-basket on the card');
  assert.ok(html.includes('30 מוצרים'), 'the count line');
  assert.ok(html.includes('טעינת עוד'), 'load more (has_more)');
  const done = m.page('/categories/D02.C01?city=' + encodeURIComponent('חיפה'),
    seed([[key('D02.C01', 'חיפה'), { pages: [{ ...PAGE, has_more: false }], pageParams: [0] }]]));
  assert.ok(!done.includes('טעינת עוד'), 'no load more at the end');
});

test('an estimated total reads "כ-N"; an empty result has its own state', () => {
  const est = m.page('/categories/D02.C01?city=' + encodeURIComponent('חיפה'),
    seed([[key('D02.C01', 'חיפה'), { pages: [{ ...PAGE, total: 30, total_exact: false }], pageParams: [0] }]]));
  assert.ok(est.includes('כ-30 מוצרים'));
  const empty = m.page('/categories/D02.C01?city=&promo=1',
    seed([[key('D02.C01', '', '', 'popular', true), { pages: [{ ...PAGE, items: [], total: 0, has_more: false }], pageParams: [0] }]]));
  assert.ok(empty.includes('אין מוצרים בקטגוריה הזו') && empty.includes('נקה סינון'));
});

test('a malformed id is "not found" without a request', () => {
  const html = m.page('/categories/xyz', seed());
  assert.ok(html.includes('הקטגוריה לא נמצאה') && html.includes('href="/categories"'));
});
