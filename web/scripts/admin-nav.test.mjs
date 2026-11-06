// SU11A-59: the dashboard card titles link to their tabs (#queue,
// #categories[/suggestions], #promos/pins); the hash helpers pick the tab and
// sub-view. Bundles src/admin/nav.ts and the admin Card with esbuild and renders
// with react-dom/server. Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';

const web = join(dirname(fileURLToPath(import.meta.url)), '..');

async function load() {
  const out = await build({
    stdin: {
      contents: `
        import { createElement } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { Card } from './src/admin/ui.tsx';
        export * from './src/admin/nav.ts';
        export const card = (props) => renderToStaticMarkup(createElement(Card, props, 'x'));`,
      resolveDir: web, loader: 'tsx',
    },
    bundle: true, platform: 'node', format: 'esm', write: false, jsx: 'automatic', logLevel: 'silent',
    define: { 'import.meta.env': JSON.stringify({ VITE_SUPABASE_URL: 'https://test.invalid', VITE_SUPABASE_ANON_KEY: 'x' }) },
    banner: { js: "import { createRequire } from 'module'; const require = createRequire(import.meta.url);" },
  });
  const dir = mkdtempSync(join(tmpdir(), 'xxl-admin-nav-'));
  const file = join(dir, 'bundle.mjs');
  writeFileSync(file, out.outputFiles[0].text);
  try {
    return await import(pathToFileURL(file).href);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const m = await load();
const at = (hash) => { globalThis.window = { location: { hash } }; };

test('hash parts and sub-views', () => {
  at('#categories/suggestions');
  assert.deepEqual(m.hashParts(), ['categories', 'suggestions']);
  assert.equal(m.viewFromHash(['search', 'suggestions'], 'search'), 'suggestions');
  at('#promos/nope');
  assert.equal(m.viewFromHash(['search', 'pins'], 'search'), 'search');
  at('#queue');
  assert.deepEqual(m.hashParts(), ['queue', undefined]);
  at('');
  assert.equal(m.hashParts()[0], '');
  assert.equal(m.tabHref('promos', 'pins'), '#promos/pins');
  assert.equal(m.tabHref('queue'), '#queue');
});

test('a card with href has a real link in its heading, with the hint for screen readers', () => {
  const html = m.card({ title: 'ביקורות', href: '#queue', linkLabel: 'מעבר ללשונית ביקורות לטיפול' });
  assert.match(html, /<h2[^>]*><a href="#queue"[^>]*>ביקורות/);
  assert.match(html, /focus-visible:outline/);
  assert.match(html, /class="sr-only"> \(מעבר ללשונית ביקורות לטיפול\)/);
  assert.doesNotMatch(m.card({ title: 'בניית החיפוש' }), /<a /);
});

test('the dashboard links reviews, categories, promos and (SU11A-69) stats only', () => {
  const src = readFileSync(join(web, 'src/admin/screens/StatusScreen.tsx'), 'utf8');
  const hrefs = [...src.matchAll(/href=\{tabHref\(([^)]*\))/g)].map(x => x[1]);
  assert.equal(hrefs.length, 4);
  assert.ok(hrefs.some(h => h.startsWith("'stats'")));
  assert.ok(hrefs.some(h => h.startsWith("'queue'")));
  assert.ok(src.includes("href={tabHref('categories', (s.category_suggestions?.pending ?? 0) > 0 ? 'suggestions' : undefined)}"));
  assert.ok(hrefs.some(h => h.startsWith("'promos', 'pins'")));
  assert.match(src, /<Card title=\{t\('admin\.status\.chains'\)\}>/);
  assert.match(src, /<Card title=\{t\('admin\.status\.search'\)\}>/);
});
