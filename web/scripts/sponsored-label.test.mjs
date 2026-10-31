// SU11A-58: a sponsored promo card shows "ממומן"; an unsponsored one does not.
// Renders the real PromosPage cards (unit and basket) to static HTML with esbuild
// (Vite's own) and react-dom/server. Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';

const web = join(dirname(fileURLToPath(import.meta.url)), '..');

async function render() {
  const out = await build({
    stdin: {
      contents: `
        import { createElement } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { PromoRow } from './src/pages/PromosPage.tsx';
        export const html = (item) => renderToStaticMarkup(createElement(PromoRow, { item }));`,
      resolveDir: web, loader: 'tsx',
    },
    bundle: true, platform: 'node', format: 'esm', write: false, jsx: 'automatic', logLevel: 'silent',
    // placeholders: the Supabase client refuses an empty URL at import time
    define: { 'import.meta.env': JSON.stringify({ VITE_SUPABASE_URL: 'https://test.invalid', VITE_SUPABASE_ANON_KEY: 'x' }) },
    // node: the bundle's own require() calls for node builtins
    banner: { js: "import { createRequire } from 'module'; const require = createRequire(import.meta.url);" },
  });
  const dir = mkdtempSync(join(tmpdir(), 'xxl-sponsored-'));
  const file = join(dir, 'bundle.mjs');
  writeFileSync(file, out.outputFiles[0].text);
  try {
    return (await import(pathToFileURL(file).href)).html;
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const unit = {
  chain_id: 'A', chain_name: 'רשת', city: 'עיר', branch: 'סניף', store_fk: 1, promo_kind: 'unit',
  promo_type: 'fixed', savings: 2, min_purchase_amount: null, item_code: '7290000000011', product_name: 'חלב',
  shelf_price: 6, min_qty: 1, discount_price: 4, reward_type: null, unit_price: 4, discount_pct: 33,
  promo_description: 'ב-4', promo_start: null, promo_end: null,
};
const basket = { ...unit, promo_kind: 'basket', promo_type: 'basket', unit_price: null, discount_pct: null,
  savings: null, min_purchase_amount: 100 };

test('sponsored cards carry the label, others do not', async () => {
  const html = await render();
  for (const item of [unit, basket]) {
    assert.ok(html({ ...item, sponsored: true, pinned: true }).includes('ממומן'), item.promo_kind);
    assert.ok(!html({ ...item, sponsored: false, pinned: true }).includes('ממומן'), item.promo_kind);
    assert.ok(!html(item).includes('ממומן'), `${item.promo_kind} without the field (older API)`);
  }
});
