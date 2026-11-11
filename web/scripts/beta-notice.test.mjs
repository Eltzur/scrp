// SU11A-75: the "בהרצה" notice (show / hide logic, the dialog's aria and the
// exact approved text, the header label) and the admin table alignment (one
// alignment per column, shared by <th> and <td>). Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';

const web = join(dirname(fileURLToPath(import.meta.url)), '..');
const he = JSON.parse(readFileSync(join(web, 'src/i18n/locales/he.json'), 'utf8'));

const out = await build({
  stdin: {
    contents: `
      import { createElement as h } from 'react';
      import { renderToStaticMarkup } from 'react-dom/server';
      import i18n from './src/i18n/config.ts';
      import { NoticeDialog, BetaLabel } from './src/components/BetaNotice.tsx';
      export * as N from './src/utils/betaNotice.ts';
      export * as A from './src/utils/analytics.ts';
      export const lang = (l) => i18n.changeLanguage(l);
      export const dialog = () => renderToStaticMarkup(h(NoticeDialog, { onClose() {} }));
      export const label = () => renderToStaticMarkup(h(BetaLabel));`,
    resolveDir: web, loader: 'tsx',
  },
  bundle: true, platform: 'node', format: 'esm', write: false, jsx: 'automatic', logLevel: 'silent',
  loader: { '.json': 'json' },
  define: { 'import.meta.env': JSON.stringify({}) },
  banner: { js: "import { createRequire } from 'module'; const require = createRequire(import.meta.url);" },
});
const dir = mkdtempSync(join(tmpdir(), 'xxl-su75-'));
const file = join(dir, 'bundle.mjs');
writeFileSync(file, out.outputFiles[0].text);
const noop = new Proxy(function () {}, { get: () => noop, apply: () => noop });
globalThis.document = new Proxy({ documentElement: {} }, { get: (t, k) => (k in t ? t[k] : noop) });
const events = [];
globalThis.window = { location: { hostname: 'super.xxl.co.il', pathname: '/', search: '' }, dispatchEvent: e => { events.push(e.type); return true; } };
const m = await import(pathToFileURL(file).href);
rmSync(dir, { recursive: true, force: true });
const { N, A } = m;
await m.lang('he');

const mem = (init = {}) => { const d = new Map(Object.entries(init)); return { getItem: k => (d.has(k) ? d.get(k) : null), setItem: (k, v) => d.set(k, String(v)), d }; };
const throwing = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
const answered = () => mem({ xxl_cookie_consent: 'true' });

test('shown on the portal and Super once the cookie choice exists; once per browser', () => {
  N._resetNoticeForTests();
  for (const host of ['xxl.co.il', 'www.xxl.co.il', 'super.xxl.co.il', 'SUPER.XXL.CO.IL']) {
    assert.equal(N.shouldAutoShow(host, '/', answered()), true, host);
  }
  assert.equal(N.shouldAutoShow('super.xxl.co.il', '/', mem({ xxl_cookie_consent: 'false' })), true);   // declined is a choice too
  const s = answered();
  N.markNoticeSeen(s);
  assert.equal(s.d.get('xxl_notice_beta_v1'), 'seen');
  N._resetNoticeForTests();
  assert.equal(N.shouldAutoShow('super.xxl.co.il', '/promos', s), false);
  assert.equal(N.NOTICE_KEY, 'xxl_notice_beta_v1');
});

test('not while the cookie banner waits for a choice', () => {
  N._resetNoticeForTests();
  assert.equal(N.cookieChoice(mem()), 'pending');
  assert.equal(N.shouldAutoShow('super.xxl.co.il', '/', mem()), false);
  assert.equal(N.shouldAutoShow('super.xxl.co.il', '/', mem({ xxl_cookie_consent: 'maybe' })), false);
});

test('storage that throws: shown, then once per page load only', () => {
  N._resetNoticeForTests();
  assert.equal(N.cookieChoice(throwing), 'unknown');             // the banner cannot show either
  assert.equal(N.shouldAutoShow('super.xxl.co.il', '/', throwing), true);
  assert.doesNotThrow(() => N.markNoticeSeen(throwing));
  assert.equal(N.shouldAutoShow('super.xxl.co.il', '/', throwing), false);
  assert.equal(N.shouldAutoShow('super.xxl.co.il', '/', null), false);
  N._resetNoticeForTests();
});

test('never on legal pages, admin or fly', () => {
  N._resetNoticeForTests();
  for (const p of ['/privacy', '/disclaimer', '/accessibility', '/account/delete', '/privacy/', '/Accessibility']) {
    assert.equal(N.shouldAutoShow('super.xxl.co.il', p, answered()), false, p);
    assert.equal(N.shouldAutoShow('xxl.co.il', p, answered()), false, p);
  }
  for (const h of ['admin.xxl.co.il', 'fly.xxl.co.il', 'api-super.xxl.co.il', 'example.com']) {
    assert.equal(N.shouldAutoShow(h, '/', answered()), false, h);
  }
  assert.equal(N.shouldAutoShow('localhost', '/', answered(), true), false);   // localhost?admin=1
  assert.equal(N.shouldAutoShow('super.xxl.co.il', '/promos', answered()), true);
});

test('a cookie choice fires the event the notice waits for', () => {
  globalThis.localStorage = mem();
  events.length = 0;
  A.setCookieConsent(false);
  assert.ok(events.includes(A.COOKIE_CHOICE_EVENT));
  delete globalThis.localStorage;
});

test('dialog: role, aria-modal, labelled by its title, the approved text exactly, focusable close and OK', () => {
  const html = m.dialog();
  assert.match(html, /role="dialog"/);
  assert.match(html, /aria-modal="true"/);
  const id = html.match(/aria-labelledby="([^"]+)"/)[1];
  assert.match(html, new RegExp(`<h2 id="${id.replace(/[:]/g, '\\:')}"[^>]*>ברוכים הבאים ל-XXL</h2>`));
  const exact = {
    title: 'ברוכים הבאים ל-XXL',
    p1: 'האתר נמצא כעת בשלב הרצה. בתקופה זו כל המידע, ההשוואות והמבצעים זמינים לכם במלואם, ללא תשלום וללא הגבלה.',
    p2: 'בעתיד, חלק מהשירותים יוצעו במסגרת מנוי חודשי בתשלום. הסיבה פשוטה: כפי שנהוג לומר, אם אינכם משלמים על המוצר, ככל הנראה אתם המוצר.',
    p3: 'דמי המנוי יאפשרו לנו שלא להסתמך רק על הכנסות מרשתות השיווק ומהיצרנים, וכך לשמור על האינטרס של הציבור ולהמשיך להציג לכם מידע אובייקטיבי, שאינו מוטה משיקולים שיווקיים או מסחריים.',
    ok: 'הבנתי',
    label: 'בהרצה',
  };
  for (const [k, v] of Object.entries(exact)) assert.equal(he.beta_notice[k], v, k);
  for (const k of ['p1', 'p2', 'p3']) assert.ok(html.includes(`<p>${exact[k]}</p>`), k);
  assert.match(html, /<button[^>]*type="button"[^>]*>הבנתי<\/button>/);
  assert.match(html, /aria-label="סגירה"/);
  assert.match(html, /focus-visible:outline-emerald-700/);
  assert.match(html, /max-w-md/);                                   // fits 360 px with p-3 around it
});

test('label: a real button whose accessible name contains its visible text', () => {
  const html = m.label();
  assert.match(html, /^<button type="button" aria-label="האתר בהרצה – מידע נוסף"[^>]*>בהרצה<\/button>$/);
});

test('mounted in the site only, after the cookie banner; both headers carry the label', () => {
  const app = readFileSync(join(web, 'src/App.tsx'), 'utf8');
  assert.match(app, /<CookieBanner \/>\s*\{\/\*[^]*?\*\/\}\s*<BetaNotice \/>/);
  assert.equal((app.match(/<BetaNotice \/>/g) ?? []).length, 1);
  assert.doesNotMatch(readFileSync(join(web, 'src/admin/AdminApp.tsx'), 'utf8'), /BetaNotice|BetaLabel/);
  assert.match(readFileSync(join(web, 'src/components/Header.tsx'), 'utf8'), /<BetaLabel \/>/);
  assert.match(readFileSync(join(web, 'src/pages/PortalPage.tsx'), 'utf8'), /<BetaLabel \/>/);
  const src = readFileSync(join(web, 'src/components/BetaNotice.tsx'), 'utf8') + readFileSync(join(web, 'src/utils/betaNotice.ts'), 'utf8');
  assert.doesNotMatch(src, /gtag|trackPageview|navigate\(|history\.|useSearchParams/);
});

test('admin tables: one alignment per column, shared by th and td; no dir on a cell', () => {
  const ui = readFileSync(join(web, 'src/admin/ui.tsx'), 'utf8');
  assert.match(ui, /export const COL_TEXT = 'text-start';/);
  assert.match(ui, /export const COL_NUM = 'text-end tabular-nums';/);
  for (const f of ['src/admin/screens/StatsScreen.tsx', 'src/admin/screens/StatusScreen.tsx', 'src/admin/screens/stats/LineChart.tsx']) {
    const s = readFileSync(join(web, f), 'utf8');
    assert.doesNotMatch(s, /<t[dh][^>]*dir="ltr"/, f);             // a dir on the cell flips its alignment
    assert.doesNotMatch(s, /<tr className="text-right/, f);         // no row-level default for headers
    assert.ok((s.match(/COL_NUM/g) ?? []).length >= 2 && (s.match(/COL_TEXT/g) ?? []).length >= 2, f);
    assert.ok((s.match(/scope="col"/g) ?? []).length >= 1, f);
  }
  const stats = readFileSync(join(web, 'src/admin/screens/StatsScreen.tsx'), 'utf8');
  assert.match(stats, /className=\{`py-2 px-1 font-medium \$\{j === 0 \? COL_TEXT : COL_NUM\}`\}/);
  assert.match(stats, /<td key=\{j\} className=\{`py-2 px-1 \$\{COL_NUM\}`\}><span dir="ltr">\{c\}<\/span><\/td>/);
});
