// SU11A-60: the promos page opens on filters + מבצעים מקודמים, with no list;
// a chain, a category or search text asks for results, a city alone does not;
// the view round-trips through the URL. Bundles the real page and
// src/utils/promosView.ts with esbuild and renders with react-dom/server inside
// a MemoryRouter and a pre-filled QueryClient (no network: effects do not run
// on the server, so "asks for results" shows as the results spinner). The
// 2026-11 follow-up: nothing waits on the city or on the promoted section.
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
        import { MemoryRouter } from 'react-router-dom';
        import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
        import './src/i18n/config.ts';
        import PromosPage from './src/pages/PromosPage.tsx';
        export * from './src/utils/promosView.ts';
        export function page(url, seed) {
          const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
          for (const [key, data] of seed) qc.setQueryData(key, data);
          return renderToStaticMarkup(h(QueryClientProvider, { client: qc },
            h(MemoryRouter, { initialEntries: [url] }, h(PromosPage))));
        }`,
      resolveDir: web, loader: 'tsx',
    },
    bundle: true, platform: 'node', format: 'esm', write: false, jsx: 'automatic', logLevel: 'silent',
    loader: { '.json': 'json' },
    define: { 'import.meta.env': JSON.stringify({ VITE_SUPABASE_URL: 'https://test.invalid', VITE_SUPABASE_ANON_KEY: 'x' }) },
    banner: { js: "import { createRequire } from 'module'; const require = createRequire(import.meta.url);" },
  });
  const dir = mkdtempSync(join(tmpdir(), 'xxl-promos-page-'));
  const file = join(dir, 'bundle.mjs');
  writeFileSync(file, out.outputFiles[0].text);
  globalThis.document = { documentElement: {} };
  try {
    return await import(pathToFileURL(file).href);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const m = await load();
const CITY = 'חיפה';
const TREE = { version: 'v1', nodes: [
  { id: 'D01', parent_id: null, level: 1, name_he: 'מוצרי חלב', name_en: 'Dairy' },
  { id: 'D01.C01', parent_id: 'D01', level: 2, name_he: 'גבינות', name_en: 'Cheese' },
  { id: 'D02', parent_id: null, level: 1, name_he: 'ניקיון', name_en: 'Cleaning' },
] };
const PIN = {
  chain_id: 'A', chain_name: 'רשת אלף', city: CITY, branch: 'סניף מרכז', store_fk: 1, item_code: '7290000000011',
  product_name: 'חלב 3%', shelf_price: 6, min_qty: 1, promo_kind: 'unit', promo_type: 'fixed', savings: 2,
  min_purchase_amount: null, discount_price: 4, reward_type: null, unit_price: 4, discount_pct: 33,
  promo_description: 'ב-4', promo_start: null, promo_end: null, pinned: true, sponsored: true, branch_count: 3, item_count: 1,
};
const seed = (promoted = [], extra = {}) => [
  [['cities'], [{ city: CITY, chain_count: 1, store_count: 1, chain_ids: ['A'] }]],
  [['category-tree'], TREE],
  [['promos-promoted', { city: CITY, ...extra }], promoted],
];
const START = 'איזה מבצעים מעניינים אתכם?';
const SPINNER = 'aria-label="טוען מבצעים"';

test('fresh visit: filters, department chips, no list', () => {
  const html = m.page(`/promos?city=${encodeURIComponent(CITY)}`, seed());
  assert.ok(html.includes(START));
  assert.ok(html.includes('>מוצרי חלב</button>') && html.includes('>ניקיון</button>'));
  assert.ok(!html.includes('>גבינות</button>'), 'chips are departments only');
  assert.ok(html.includes('aria-label="קטגוריה"') && html.includes('aria-label="רשת"'));
  assert.ok(!html.includes(SPINNER) && !html.includes('מבצעים מקודמים'));
});

test('promoted section on the start page: chain, branches, ממומן', () => {
  const html = m.page(`/promos?city=${encodeURIComponent(CITY)}`, seed([PIN]));
  assert.ok(html.includes('מבצעים מקודמים') && html.includes(START));
  assert.ok(html.indexOf('מבצעים מקודמים') < html.indexOf(START));
  assert.ok(html.includes('רשת אלף') && html.includes('סניף מרכז') && html.includes('ועוד 2 סניפים'));
  assert.ok(html.includes('ממומן'));
  const unsponsored = m.page(`/promos?city=${encodeURIComponent(CITY)}`, seed([{ ...PIN, sponsored: false, branch_count: 2 }]));
  assert.ok(!unsponsored.includes('ממומן') && unsponsored.includes('ועוד סניף אחד'));
});

for (const [what, qs, extra] of [
  ['a category', '&cat=D01', { category: 'D01' }],
  ['a chain', '&chain=A', { chainId: 'A' }],
  ['search text', `&q=${encodeURIComponent('חלב')}`, { q: 'חלב' }],
]) {
  test(`${what} asks for results`, () => {
    const html = m.page(`/promos?city=${encodeURIComponent(CITY)}${qs}`, seed([PIN], extra));
    assert.ok(html.includes('מבצעים מקודמים'), `${what}: the page is ready (promoted section shown)`);
    assert.ok(html.includes(SPINNER), `${what}: the results are requested`);
    assert.ok(!html.includes(START), what);
  });
}

test('the URL restores the filters', () => {
  const html = m.page(`/promos?city=${encodeURIComponent(CITY)}&cat=D01.C01&sort=savings&bands=26-50&types=gift`,
    seed([PIN], { category: 'D01.C01', bands: ['26-50'], promoTypes: ['gift'] }));
  assert.ok(html.includes('מבצעים מקודמים'));
  assert.match(html, /<option value="D01.C01" selected="">/);
  assert.match(html, /<option value="savings" selected="">/);
  assert.match(html, /aria-pressed="true"[^>]*>26–50%/);
  assert.match(html, /aria-pressed="true"[^>]*>1\+1 \/ מתנה/);
});

test('no city in the URL: renders at once, nothing gates on the city', () => {
  // A remembered city / "all cities" is used synchronously; the select is never disabled.
  const html = m.page('/promos', [[['cities'], []], [['category-tree'], TREE], [['promos-promoted', {}], []]]);
  assert.ok(html.includes(START) && html.includes('>מוצרי חלב</button>'));
  assert.match(html, /<select[^>]*aria-label="עיר"[^>]*>/);
  assert.doesNotMatch(html.match(/<select[^>]*aria-label="עיר"[^>]*>/)[0], /\sdisabled(=|\s|>)/);
});

test('promoted still loading: filters and chips are already there', () => {
  const html = m.page(`/promos?city=${encodeURIComponent(CITY)}`, seed().slice(0, 2));   // no promoted data
  assert.ok(html.includes(START) && html.includes('>מוצרי חלב</button>'));
  assert.ok(html.includes('טוען מבצעים מקודמים'));
  assert.ok(!html.includes(SPINNER), 'no page-wide spinner');
});

test('view: mode, read and write round-trip', () => {
  assert.equal(m.promosMode({ chain: '', cat: '', q: '' }), 'start');
  assert.equal(m.promosMode({ chain: '', cat: 'D01', q: '' }), 'flat');
  assert.equal(m.promosMode({ chain: '', cat: '', q: 'חלב' }), 'flat');
  assert.equal(m.promosMode({ chain: 'A', cat: 'D01', q: '' }), 'grouped');
  const allowed = { sorts: ['discount', 'savings', 'ending'], bands: ['0-10', '26-50'], types: ['gift', 'basket'] };
  let p = new URLSearchParams();
  p = m.withChanges(p, { city: '', cat: 'D01', bands: '26-50,bogus', types: 'gift', sort: 'nope', branch: 'x1' });
  const v = m.readView(new URLSearchParams(p.toString()), allowed);
  assert.deepEqual(v, { city: '', chain: '', branch: null, cat: 'D01', q: '', sort: 'discount',
    bands: ['26-50'], types: ['gift'], ending: false });
  assert.equal(m.readView(new URLSearchParams(), allowed).city, null);
  p = m.withChanges(p, { cat: '', q: 'זירו', ending: '1' });
  assert.equal(p.get('cat'), null);
  assert.deepEqual([p.get('q'), p.get('ending'), p.get('city')], ['זירו', '1', '']);
});
