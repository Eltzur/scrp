// SU11A-70: the header logo goes to Super's home on super.xxl.co.il and to
// xxl.co.il on the portal; Super's footer links to all XXL services; the App
// Store badge (Apple's official artwork, he / en) comes first, next to the
// Play badge, both focusable links; the iPhone banner links to the App Store;
// no "coming soon for iPhone" string is left. Bundles the real components with
// esbuild and renders them with react-dom/server. Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { createHash } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';

const web = join(dirname(fileURLToPath(import.meta.url)), '..');
const IOS = 'https://apps.apple.com/il/app/super-xxl/id6829450422';

async function load() {
  const out = await build({
    stdin: {
      contents: `
        import { createElement as h } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { MemoryRouter } from 'react-router-dom';
        import i18n from './src/i18n/config.ts';
        import HeaderLogo from './src/components/HeaderLogo.tsx';
        import Footer from './src/components/Footer.tsx';
        import AppBadges from './src/components/AppBadges.tsx';
        import AppBanner from './src/components/AppBanner.tsx';
        export * as apps from './src/config/apps.ts';
        const r = (el) => renderToStaticMarkup(h(MemoryRouter, null, el));
        export const lang = (l) => i18n.changeLanguage(l);
        export const logo = () => r(h(HeaderLogo));
        export const footer = () => r(h(Footer));
        export const badges = () => r(h(AppBadges));
        export const banner = () => r(h(AppBanner));`,
      resolveDir: web, loader: 'tsx',
    },
    bundle: true, platform: 'node', format: 'esm', write: false, jsx: 'automatic', logLevel: 'silent',
    loader: { '.json': 'json' },
    define: { 'import.meta.env': JSON.stringify({ VITE_SUPABASE_URL: 'https://test.invalid', VITE_SUPABASE_ANON_KEY: 'x' }) },
    banner: { js: "import { createRequire } from 'module'; const require = createRequire(import.meta.url);" },
  });
  const dir = mkdtempSync(join(tmpdir(), 'xxl-su70-'));
  const file = join(dir, 'bundle.mjs');
  writeFileSync(file, out.outputFiles[0].text);
  const noop = new Proxy(function () {}, { get: () => noop, apply: () => noop });
  globalThis.document = new Proxy({ documentElement: {} }, { get: (t, k) => (k in t ? t[k] : noop) });
  try {
    return await import(pathToFileURL(file).href);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const m = await load();
const at = (hostname, search = '') => {
  globalThis.window = { location: { hostname, search, hash: '' } };
};
const ua = (userAgent, maxTouchPoints = 5) =>
  Object.defineProperty(globalThis, 'navigator', { value: { userAgent, maxTouchPoints }, configurable: true });
globalThis.localStorage = { getItem: () => null, setItem: () => {} };

test('header logo: Super home on super.xxl.co.il, xxl.co.il on the portal', async () => {
  await m.lang('he');
  at('super.xxl.co.il');
  let html = m.logo();
  assert.match(html, /^<a [^>]*href="\/"/);
  assert.match(html, /aria-label="SUPER XXL — דף הבית"/);
  assert.match(html, /focus-visible:outline/);
  assert.doesNotMatch(html, /https:\/\/xxl\.co\.il/);
  for (const host of ['xxl.co.il', 'www.xxl.co.il']) {
    at(host);
    html = m.logo();
    assert.match(html, /^<a [^>]*href="https:\/\/xxl\.co\.il"/, host);
    assert.doesNotMatch(html, /דף הבית/);
  }
  at('localhost', '?portal=1');
  assert.match(m.logo(), /href="https:\/\/xxl\.co\.il"/);
});

test('footer: "כל שירותי XXL" on Super only', async () => {
  await m.lang('he');
  at('super.xxl.co.il');
  assert.match(m.footer(), /<a href="https:\/\/xxl\.co\.il"[^>]*>כל שירותי XXL<\/a>/);
  at('xxl.co.il');
  assert.doesNotMatch(m.footer(), /כל שירותי XXL/);
  await m.lang('en');
  at('super.xxl.co.il');
  assert.match(m.footer(), />All XXL services<\/a>/);
  await m.lang('he');
});

test('badges: App Store first, official artwork per language, both focusable links', async () => {
  assert.equal(m.apps.IOS_APP_URL, IOS);
  await m.lang('he');
  let html = m.badges();
  const links = [...html.matchAll(/<a href="([^"]+)"[^>]*class="([^"]+)"[^>]*><img src="([^"]+)" alt="([^"]+)"/g)];
  assert.equal(links.length, 2);
  assert.deepEqual(links.map(l => l[1].replace(/&amp;/g, '&')), [IOS, m.apps.PLAY_STORE_URL]);
  assert.equal(links[0][3], '/badges/app-store-he.svg');
  assert.equal(links[0][4], 'הורידו מה-App Store');
  for (const l of links) assert.match(l[2], /focus-visible:outline-2/);
  // Apple: 40 px tall + clear space of 1/4 of the height (10 px) on every side, inside the link.
  assert.match(links[0][2], /p-\[10px\]/);
  assert.match(html, /app-store-he\.svg"[^>]*class="h-10 w-auto"/);
  // Play: 60 px image whose visible badge (168/250) is ~40 px.
  assert.match(html, /google-play-he\.png"[^>]*class="h-\[60px\] w-auto"/);
  await m.lang('en');
  html = m.badges();
  assert.match(html, /<img src="\/badges\/app-store-en\.svg" alt="Download on the App Store"/);
  await m.lang('he');
});

test('the badge files are the downloaded artwork, untouched', () => {
  const sha = (f) => createHash('sha256').update(readFileSync(join(web, 'public/badges', f))).digest('hex');
  const src = readFileSync(join(web, 'public/badges/SOURCE.txt'), 'utf8');
  for (const f of ['app-store-he.svg', 'app-store-en.svg']) {
    assert.ok(src.includes(`sha256 ${sha(f)}`), f);
    const svg = readFileSync(join(web, 'public/badges', f), 'utf8');
    assert.doesNotMatch(svg, /<script|href=|\r/);
  }
  assert.match(src, /toolbox\.marketingtools\.apple\.com\/api\/v2\/badges\/download-on-the-app-store\/black\/he-il/);
  assert.match(src, /Apple, the Apple logo and App Store are trademarks of Apple Inc\./);
});

test('iPhone banner links to the App Store; Android to Play; desktop none', async () => {
  await m.lang('he');
  ua('Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1');
  let html = m.banner();
  assert.match(html, new RegExp(`<a href="${IOS.replace(/[./]/g, '\\$&')}"[^>]*>הורידו מ-App Store</a>`));
  ua('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36');
  html = m.banner();
  assert.match(html, /href="https:\/\/play\.google\.com\/store\/apps\/details\?id=il\.co\.xxl\.supermarket/);
  ua('Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0', 0);
  assert.equal(m.banner(), '');
});

test('no "coming soon for iPhone" text is left in the web', () => {
  const files = [];
  const walk = (d) => {
    for (const f of readdirSync(d)) {
      const p = join(d, f);
      if (statSync(p).isDirectory()) walk(p);
      else if (/\.(tsx?|json)$/.test(f)) files.push(p);
    }
  };
  walk(join(web, 'src'));
  for (const p of files) {
    const s = readFileSync(p, 'utf8');
    assert.doesNotMatch(s, /בקרוב גם ל-iPhone|תגיע בקרוב|Coming soon for iPhone|ios_soon|banner_ios_sub/i, p);
  }
});
