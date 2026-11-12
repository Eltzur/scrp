// SU11A-81 (SU11A-79 H5): each host's raw HTML (no JS) carries its own head.
// Runs a real production build (vite, the repo config) into a temp folder and
// checks index.html (portal) and index.super.html (super.xxl.co.il): title,
// description, canonical, og:* / twitter:* values, the OG image files, no portal
// value left in the super file, the inline script unchanged (CSP hash), and the
// nginx snippet. Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build as esbuild } from 'esbuild';
import { createHash } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';

const web = join(dirname(fileURLToPath(import.meta.url)), '..');
const repo = join(web, '..');

// ---------------------------------------------------------------- the build
const outDir = mkdtempSync(join(tmpdir(), 'xxl-su81-dist-'));
const { build } = await import('vite');
await build({ root: web, configFile: join(web, 'vite.config.ts'), logLevel: 'silent',
  build: { outDir, emptyOutDir: true } });
const files = {
  portal: readFileSync(join(outDir, 'index.html'), 'utf8'),
  super: readFileSync(join(outDir, 'index.super.html'), 'utf8'),
};
rmSync(outDir, { recursive: true, force: true });

// the pure module, for the expected values and the error path
const bundled = await esbuild({
  entryPoints: [join(web, 'src', 'utils', 'hostHtml.ts')], bundle: true, platform: 'node', format: 'esm',
  write: false, logLevel: 'silent', define: { 'import.meta.env': '{}' },
});
const tmp = mkdtempSync(join(tmpdir(), 'xxl-su81-'));
writeFileSync(join(tmp, 'm.mjs'), bundled.outputFiles[0].text);
const m = await import(pathToFileURL(join(tmp, 'm.mjs')).href);
rmSync(tmp, { recursive: true, force: true });

const attr = (html, re) => {
  const all = [...html.matchAll(new RegExp(re.source, 'g'))];
  assert.equal(all.length, 1, `expected exactly one ${re}`);
  return all[0][1];
};
const head = (html) => ({
  title: attr(html, /<title>([^<]*)<\/title>/),
  description: attr(html, /<meta\s+name="description"\s+content="([^"]*)"/),
  canonical: attr(html, /<link\s+rel="canonical"\s+href="([^"]*)"/),
  ogType: attr(html, /<meta\s+property="og:type"\s+content="([^"]*)"/),
  ogSite: attr(html, /<meta\s+property="og:site_name"\s+content="([^"]*)"/),
  ogTitle: attr(html, /<meta\s+property="og:title"\s+content="([^"]*)"/),
  ogDesc: attr(html, /<meta\s+property="og:description"\s+content="([^"]*)"/),
  ogUrl: attr(html, /<meta\s+property="og:url"\s+content="([^"]*)"/),
  ogImage: attr(html, /<meta\s+property="og:image"\s+content="([^"]*)"/),
  ogW: attr(html, /<meta\s+property="og:image:width"\s+content="([^"]*)"/),
  ogH: attr(html, /<meta\s+property="og:image:height"\s+content="([^"]*)"/),
  ogLocale: attr(html, /<meta\s+property="og:locale"\s+content="([^"]*)"/),
  twCard: attr(html, /<meta\s+name="twitter:card"\s+content="([^"]*)"/),
  twTitle: attr(html, /<meta\s+name="twitter:title"\s+content="([^"]*)"/),
  twDesc: attr(html, /<meta\s+name="twitter:description"\s+content="([^"]*)"/),
  twImage: attr(html, /<meta\s+name="twitter:image"\s+content="([^"]*)"/),
});

const EXPECT = {
  portal: { origin: 'https://xxl.co.il', site: 'XXL', image: 'https://xxl.co.il/og-portal.png',
    title: 'XXL — הפורטל שהופך כסף רגיל לכסף חכם' },
  super: { origin: 'https://super.xxl.co.il', site: 'SUPER XXL', image: 'https://super.xxl.co.il/og-super.png',
    title: 'XXL — השוואת מחירים בסופרמרקט · חוסכים בענקקק' },
};

for (const kind of ['portal', 'super']) {
  test(`${kind}: title, canonical, og:url and og:image are the ${kind} values`, () => {
    const h = head(files[kind]);
    const e = EXPECT[kind];
    const want = m.hostHead(kind);
    assert.equal(h.title, e.title);
    assert.equal(h.title, want.title);
    assert.equal(h.description, want.description);
    assert.equal(h.canonical, `${e.origin}/`);
    assert.equal(h.ogUrl, `${e.origin}/`);
    assert.equal(h.ogImage, e.image);
    assert.equal(h.twImage, e.image);
    assert.equal(h.ogSite, e.site);
    assert.deepEqual([h.ogTitle, h.twTitle], [h.title, h.title]);
    assert.deepEqual([h.ogDesc, h.twDesc], [h.description, h.description]);
    assert.deepEqual([h.ogType, h.ogW, h.ogH, h.ogLocale, h.twCard],
      ['website', '1200', '630', 'he_IL', 'summary_large_image']);
  });
}

const PNG_SIZE = (file) => {
  const b = readFileSync(file);
  assert.equal(b.subarray(1, 4).toString('latin1'), 'PNG');
  return [b.readUInt32BE(16), b.readUInt32BE(20)];
};

test('both OG images exist in web/public at 1200x630', () => {
  assert.deepEqual(PNG_SIZE(join(web, 'public', 'og-portal.png')), [1200, 630]);
  assert.deepEqual(PNG_SIZE(join(web, 'public', 'og-super.png')), [1200, 630]);
});

const withoutScripts = (html) => html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, '');

test('no portal value is left in the super file (outside the inline script)', () => {
  const s = withoutScripts(files.super);
  const portal = head(files.portal);
  for (const v of [portal.title, portal.description, 'og-portal.png', 'https://xxl.co.il/', '"https://xxl.co.il"',
    'חופשות', 'אופנה', 'name="keywords"']) {
    assert.ok(!s.includes(v), `super file still has portal value: ${v}`);
  }
  assert.ok(!withoutScripts(files.portal).includes('og-super.png'));
});

const inlineScript = (html) => {
  const all = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  assert.equal(all.length, 1, 'one inline (non-module) script');
  return all[0][1];
};

test('the inline first-paint script is unchanged and still matches the CSP hash', () => {
  const src = inlineScript(readFileSync(join(web, 'index.html'), 'utf8'));
  const csp = readFileSync(join(repo, 'deploy', 'nginx', 'xxl-csp-web.conf'), 'utf8');
  const hash = `'sha256-${createHash('sha256').update(src, 'utf8').digest('base64')}'`;
  for (const kind of ['portal', 'super']) {
    assert.equal(inlineScript(files[kind]), src, `${kind}: inline script changed`);
  }
  assert.ok(csp.includes(hash), `CSP must list ${hash}`);
});

test('both files load the same hashed assets', () => {
  const assets = (html) => [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((x) => x[1]).sort();
  assert.ok(assets(files.portal).some((a) => /\/assets\/index-[\w-]+\.js$/.test(a)));
  assert.deepEqual(assets(files.super), assets(files.portal));
});

test('renderHostHtml refuses an HTML file without the expected tags', () => {
  assert.throws(() => m.renderHostHtml('<html><head><title>x</title></head></html>', 'super'), /meta description/);
  assert.throws(() => m.renderHostHtml('<html></html>', 'portal'), /<title>/);
});

test('nginx: the super snippet falls back to index.super.html, without $uri/', () => {
  const s = readFileSync(join(repo, 'deploy', 'nginx', 'xxl-spa-super.conf'), 'utf8');
  const directives = s.split(/\r?\n/).map((l) => l.trim()).filter((l) => l && !l.startsWith('#'));
  assert.deepEqual(directives, ['try_files $uri /index.super.html;']);
});
