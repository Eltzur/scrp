// SU11A-68: SEO of the category pages. The route rules (utils/seoMeta.ts:
// indexable, canonical of the clean URL), the node head (utils/categorySeo.ts:
// Hebrew title / description, noindex on a filtered view, BreadcrumbList) and
// the sitemap block (scripts/sitemap-categories.mjs). Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { categoryPaths, renderSitemap } from './sitemap-categories.mjs';

const web = join(dirname(fileURLToPath(import.meta.url)), '..');

async function load() {
  const out = await build({
    stdin: {
      contents: `export { resolveRouteMeta, CATEGORY_PATH } from './src/utils/seoMeta.ts';
                 export { categoryHead } from './src/utils/categorySeo.ts';`,
      resolveDir: web, loader: 'ts',
    },
    bundle: true, platform: 'node', format: 'esm', write: false, logLevel: 'silent',
  });
  const dir = mkdtempSync(join(tmpdir(), 'xxl-seo-'));
  const file = join(dir, 'bundle.mjs');
  writeFileSync(file, out.outputFiles[0].text);
  try {
    return await import(pathToFileURL(file).href);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const m = await load();
const PATH = [{ id: 'D02', name_he: 'מוצרי חלב' }, { id: 'D02.C01', name_he: 'חלב' }];

test('route rules: /categories and node paths are indexable with their clean canonical', () => {
  const root = m.resolveRouteMeta('/categories', false);
  assert.equal(root.noindex, false);
  assert.equal(root.canonical, 'https://super.xxl.co.il/categories');
  assert.match(root.title, /השוואת מחירים בכל הרשתות \| SUPER XXL$/);
  for (const p of ['/categories/D02', '/categories/D02.C01', '/categories/D02.C01.S01', '/categories/D02/']) {
    const r = m.resolveRouteMeta(p, false);
    assert.equal(r.noindex, false, p);
    assert.equal(r.canonical, 'https://super.xxl.co.il' + p.replace(/\/$/, ''), p);
  }
  // on the portal host the canonical still points at the super host
  assert.equal(m.resolveRouteMeta('/categories/D02', true).canonical, 'https://super.xxl.co.il/categories/D02');
  for (const bad of ['/categories/xyz', '/categories/D02.C1', '/categories/D02/items']) {
    const r = m.resolveRouteMeta(bad, false);
    assert.equal(r.noindex, true, bad);
    assert.equal(r.canonical, null, bad);
  }
});

test('node head: Hebrew title and description, canonical without parameters, noindex when filtered', () => {
  const h = m.categoryHead(PATH, 3597, false);
  assert.equal(h.title, 'חלב — השוואת מחירים בכל הרשתות | SUPER XXL');
  assert.ok(h.description.startsWith('מוצרי חלב › חלב:'), h.description);
  assert.ok(h.description.includes('3,597 מוצרים'), h.description);
  assert.equal(h.canonical, 'https://super.xxl.co.il/categories/D02.C01');
  assert.equal(h.noindex, false);
  const f = m.categoryHead(PATH, 3597, true);
  assert.equal(f.noindex, true);
  assert.equal(f.canonical, h.canonical);          // a filtered view canonicalises to the clean URL
});

test('node head: BreadcrumbList JSON-LD', () => {
  const ld = m.categoryHead(PATH, 10, false).jsonLd;
  assert.equal(ld['@type'], 'BreadcrumbList');
  assert.deepEqual(ld.itemListElement.map(x => [x.position, x.name, x.item]), [
    [1, 'קטגוריות', 'https://super.xxl.co.il/categories'],
    [2, 'מוצרי חלב', 'https://super.xxl.co.il/categories/D02'],
    [3, 'חלב', 'https://super.xxl.co.il/categories/D02.C01'],
  ]);
});

const TREE = {
  built_at: '2026-11-06T14:31:00+02:00',
  departments: [
    { id: 'D02', level: 1, count: 40, children: [
      { id: 'D02.C01', level: 2, count: 30, linked: true, children: [
        { id: 'D02.C01.S01', level: 3, count: 12, linked: true, children: [] },
        { id: 'D02.C01.S02', level: 3, count: 3, linked: false, children: [] }] },
      { id: 'D02.C02', level: 2, count: 4, linked: false, children: [] }] },
    { id: 'D10', level: 1, count: 9, children: [
      { id: 'D10.C05', level: 2, count: 50, linked: true, children: [] },
      { id: 'D10.C01', level: 2, count: 9, linked: true, children: [] }] },
    { id: 'D16', level: 1, count: 0, children: [] },
  ],
};

test('sitemap: /categories, departments with items and linked nodes only; never tobacco', () => {
  assert.deepEqual(categoryPaths(TREE), [
    '/categories', '/categories/D02', '/categories/D02.C01', '/categories/D02.C01.S01',
    '/categories/D10', '/categories/D10.C01',
  ]);
});

test('sitemap: the committed file has the block and every URL is indexable by the route rules', () => {
  const xml = readFileSync(join(web, 'public', 'sitemap-super.xml'), 'utf8');
  const out = renderSitemap(xml, categoryPaths(TREE), '2026-11-06');
  assert.ok(out.includes('<loc>https://super.xxl.co.il/categories/D02.C01.S01</loc><lastmod>2026-11-06</lastmod>'));
  assert.ok(!out.includes('D10.C05') && !out.includes('D02.C02'));
  assert.ok(out.includes('<loc>https://super.xxl.co.il/promos</loc>'), 'the rest is untouched');
  assert.equal(renderSitemap(out, categoryPaths(TREE), '2026-11-06'), out, 'idempotent');
  for (const loc of out.match(/<loc>[^<]+<\/loc>/g)) {
    const path = new URL(loc.slice(5, -6)).pathname;
    if (!path.startsWith('/categories')) continue;
    const r = m.resolveRouteMeta(path, false);
    assert.equal(r.noindex, false, path);
    assert.equal(r.canonical, 'https://super.xxl.co.il' + path, path);
  }
  // the committed block: /categories and the 16 departments
  const committed = xml.match(/categories\/D\d{2}</g);
  assert.equal(committed.length, 16);
  assert.throws(() => renderSitemap('<urlset></urlset>', [], 'x'), /markers/);
});
