// SU11A-65: gift coupons ("קופון … 1 יח' מתנה") on the promos page and in the
// admin card: "מתנה בקופון", the free quantity and the condition; never a %,
// never a struck-through price. Renders the real PromoRow (esbuild +
// react-dom/server, as sponsored-label.test.mjs). Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { GIFT_COUPON_LABEL, giftCouponView, giftQtyText } from '../src/utils/giftCoupon.ts';

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
        import PromosPage, { PromoRow } from './src/pages/PromosPage.tsx';
        import PromoCard from './src/admin/screens/promos/PromoCard.tsx';
        import i18n from 'i18next';
        import he from './src/admin/i18n/promos.he.json';
        i18n.addResourceBundle('he', 'translation', { admin: { promos: he } }, true, true);
        export const row = (item) => renderToStaticMarkup(h(PromoRow, { item }));
        export const card = (p) => renderToStaticMarkup(h(PromoCard, { p }));
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
  const dir = mkdtempSync(join(tmpdir(), 'xxl-gift-'));
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

const GIFT = {
  chain_id: 'R', chain_name: 'רמי לוי', city: 'חיפה', branch: 'סניף', store_fk: 1, promo_kind: 'unit',
  promo_type: 'discount', savings: 6.9, min_purchase_amount: null, item_code: '7290000000040',
  product_name: 'שמנת חמוצה 15% טרה', shelf_price: 6.9, min_qty: 1, discount_price: null, reward_type: null,
  unit_price: 0, discount_pct: 100, promo_description: "קופון שמנת חמוצה 15% טרה 1 יח' מתנה",
  promo_start: null, promo_end: null, gift_coupon: true,
};

test('the card text: free quantity and condition', () => {
  assert.deepEqual(giftCouponView(GIFT), { qty: 1, condition: null });
  assert.deepEqual(giftCouponView({ promo_description: "קופון 2 יח' מתנה מעל 100 ש\"ח", min_qty: 1 }),
    { qty: 2, condition: 'מעל ₪100' });
  assert.deepEqual(giftCouponView({ promo_description: 'קופון חלב', min_qty: 1, min_purchase_amount: 149.9 }),
    { qty: 1, condition: 'מעל ₪149.90' });
  assert.deepEqual(giftCouponView({ promo_description: 'קופון קנה 2', min_qty: 2 }),
    { qty: null, condition: "בקניית 2 יח' לפחות" });   // not stated: no made-up quantity
  assert.equal(giftQtyText(1), "1 יח' מתנה");
  assert.equal(giftQtyText(null), null);
});

test('promos page: "מתנה בקופון", the quantity, the shelf price plain; no %, no struck price', () => {
  const html = m.row(GIFT);
  assert.ok(html.includes(GIFT_COUPON_LABEL));
  assert.ok(html.includes("1 יח&#x27; מתנה") || html.includes("1 יח' מתנה"));
  assert.ok(html.includes('מחיר מדף'));
  const shown = html.replace(/<[^>]*>/g, '');   // the visible text
  assert.ok(!shown.includes('100') && !html.includes('line-through'), html);
  const cond = m.row({ ...GIFT, min_purchase_amount: 100 });
  assert.ok(cond.includes('מעל ₪100'));
  // an ordinary row is unchanged: struck shelf price and the %
  const plain = m.row({ ...GIFT, gift_coupon: false, promo_type: 'fixed', discount_price: 4, unit_price: 4,
    discount_pct: 42, savings: 2.9, promo_description: 'ב-4' });
  assert.ok(/-(<!-- -->)?42(<!-- -->)?%/.test(plain) && plain.includes('line-through') && !plain.includes(GIFT_COUPON_LABEL));
});

test('admin card: "מתנה בקופון", never "100% הנחה"', () => {
  const p = { chain_id: 'R', chain_name: 'רמי לוי', promo_id: '123', promo_description: GIFT.promo_description,
    stores: 3, items: 1, promo_start: null, promo_end: null, live: true,
    sample: { item_code: GIFT.item_code, item_name: GIFT.product_name, min_qty: 1, discount_price: null,
      discount_rate: 100, gift_coupon: true } };
  const html = m.card(p);
  assert.ok(html.includes('מתנה בקופון') && !html.includes('100%'), html);
  const old = m.card({ ...p, sample: { ...p.sample, gift_coupon: undefined } });   // an older API: as before
  assert.ok(old.includes('100%'));
});

test('admin card: a compensation coupon says it is hidden from the lists (SU11A-66)', () => {
  const p = { chain_id: 'R', chain_name: 'רמי לוי', promo_id: '9', promo_description: 'קופון פיצוי לקוח 20שח מוצרי שסטוביץ',
    stores: 3, items: 797, promo_start: null, promo_end: null, live: true, cities: [], compensation: true,
    sample: { item_code: '7290000000001', item_name: 'וופל', min_qty: 1, discount_price: null, discount_rate: 100,
      gift_coupon: true } };
  const html = m.card(p);
  assert.ok(html.includes('פיצוי ללקוח — מוסתר מהרשימות') && html.includes('role="note"'), html);
  assert.ok(!html.includes('לא מוצג באף עיר'));   // the note replaces the "shown nowhere" warning
  const plain = m.card({ ...p, compensation: false });
  assert.ok(!plain.includes('פיצוי ללקוח') && plain.includes('לא מוצג באף עיר'));
});

test('the type chip is on the page and reads the URL', () => {
  const seed = [[['cities'], [{ city: 'חיפה', chain_count: 1, store_count: 1, chain_ids: ['R'] }]],
    [['category-tree'], { version: 'v1', nodes: [] }]];
  const html = m.page('/promos?city=' + encodeURIComponent('חיפה') + '&types=gift_coupon', seed);
  assert.ok(html.includes(`>${GIFT_COUPON_LABEL}</button>`), 'chip rendered');
  assert.match(html, new RegExp(`aria-pressed="true"[^>]*>${GIFT_COUPON_LABEL}</button>`));
});
