/**
 * SU11A-81 (SU11A-79 H5): one static HTML file per host, so crawlers that do not
 * run JS (WhatsApp, Facebook, X, Telegram, LinkedIn) see the right site.
 *
 * The build (vite.config.ts, plugin `xxl-host-html`) rewrites the head of the
 * built index.html twice:
 *   index.html        - the portal (xxl.co.il / www; admin.xxl.co.il, noindex, also uses it)
 *   index.super.html  - super.xxl.co.il (nginx: `try_files $uri /index.super.html`,
 *                       deploy/nginx/xxl-spa-super.conf)
 *
 * The values come from utils/seoMeta.ts (resolveRouteMeta for "/"), the same
 * source the app uses at runtime, so the wording never drifts. Only attribute
 * values and the <title> text change: the inline first-paint script is left
 * byte-for-byte alone (its CSP sha256 stays valid) and still refines canonical /
 * og:url to the current path for JS clients.
 *
 * Static tags are those of the host's home page. A deep link (e.g. /promos)
 * shared to a non-JS crawler previews as that site's home - the right site,
 * not yet the right page (per-path tags need pre-rendering, a later step).
 */
import { resolveRouteMeta } from './seoMeta';

export type HostKind = 'portal' | 'super';

export const HOST_HTML_FILES: Record<HostKind, string> = {
  portal: 'index.html',
  super: 'index.super.html',
};

export const SITE_NAMES: Record<HostKind, string> = {
  portal: 'XXL',
  super: 'SUPER XXL',
};

export interface HostHead {
  title: string;
  description: string;
  canonical: string;
  image: string;
  siteName: string;
}

export function hostHead(kind: HostKind): HostHead {
  const m = resolveRouteMeta('/', kind === 'portal');
  if (!m.canonical) throw new Error(`no canonical for the ${kind} home`);
  return { title: m.title, description: m.description, canonical: m.canonical, image: m.image, siteName: SITE_NAMES[kind] };
}

const escAttr = (v: string): string =>
  v.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const escText = (v: string): string => v.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/** Replace the value attribute of exactly one tag; throw if it is not there once. */
function setAttr(html: string, tag: RegExp, attr: 'content' | 'href', value: string, what: string): string {
  const hits = html.match(new RegExp(tag.source, 'g')) ?? [];
  if (hits.length !== 1) throw new Error(`hostHtml: expected one ${what}, found ${hits.length}`);
  const old = hits[0];
  const re = new RegExp(`${attr}="[^"]*"`);
  if (!re.test(old)) throw new Error(`hostHtml: ${what} has no ${attr}`);
  return html.replace(old, old.replace(re, `${attr}="${escAttr(value)}"`));
}

const metaName = (n: string) => new RegExp(`<meta\\s+name="${n}"[^>]*>`);
const metaProp = (p: string) => new RegExp(`<meta\\s+property="${p}"[^>]*>`);

/** The built index.html with the head values of `kind`. Pure; throws when a tag is missing. */
export function renderHostHtml(html: string, kind: HostKind): string {
  const h = hostHead(kind);
  const titles = html.match(/<title>[^<]*<\/title>/g) ?? [];
  if (titles.length !== 1) throw new Error(`hostHtml: expected one <title>, found ${titles.length}`);
  let out = html.replace(titles[0], `<title>${escText(h.title)}</title>`);
  out = setAttr(out, metaName('description'), 'content', h.description, 'meta description');
  out = setAttr(out, /<link\s+rel="canonical"[^>]*>/, 'href', h.canonical, 'canonical');
  out = setAttr(out, metaProp('og:type'), 'content', 'website', 'og:type');
  out = setAttr(out, metaProp('og:site_name'), 'content', h.siteName, 'og:site_name');
  out = setAttr(out, metaProp('og:title'), 'content', h.title, 'og:title');
  out = setAttr(out, metaProp('og:description'), 'content', h.description, 'og:description');
  out = setAttr(out, metaProp('og:url'), 'content', h.canonical, 'og:url');
  out = setAttr(out, metaProp('og:image'), 'content', h.image, 'og:image');
  out = setAttr(out, metaProp('og:image:width'), 'content', '1200', 'og:image:width');
  out = setAttr(out, metaProp('og:image:height'), 'content', '630', 'og:image:height');
  out = setAttr(out, metaProp('og:locale'), 'content', 'he_IL', 'og:locale');
  out = setAttr(out, metaName('twitter:card'), 'content', 'summary_large_image', 'twitter:card');
  out = setAttr(out, metaName('twitter:title'), 'content', h.title, 'twitter:title');
  out = setAttr(out, metaName('twitter:description'), 'content', h.description, 'twitter:description');
  out = setAttr(out, metaName('twitter:image'), 'content', h.image, 'twitter:image');
  if (kind !== 'portal') {
    // The portal's keywords name vacations and fashion; the super page has no
    // keywords tag (search engines ignore it) rather than invented ones.
    out = out.replace(/[ \t]*<meta\s+name="keywords"[^>]*>\r?\n?/, '');
  }
  return out;
}
