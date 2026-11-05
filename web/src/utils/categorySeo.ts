/**
 * SU11A-68: head tags of a category browse page, once its data has loaded
 * (utils/seoMeta.ts gives the generic ones on the route change). Imported only
 * by the lazy categories page.
 *
 *   title        "<קטגוריה> — השוואת מחירים בכל הרשתות | SUPER XXL"
 *   description  the path and the item count, in Hebrew
 *   canonical    the clean URL (https://super.xxl.co.il/categories/<id>), never
 *                with city / chain / sort / promo / q / offset
 *   robots       noindex on a filtered view (any of those parameters)
 *   JSON-LD      BreadcrumbList (קטגוריות › department › ... › the node),
 *                script#ld-breadcrumb, removed when the page unmounts
 *
 * categoryHead is pure (unit-tested in scripts/categories-seo.test.mjs).
 */
import { setMeta } from './seoMeta';

export const SUPER_ORIGIN = 'https://super.xxl.co.il';
const LD_ID = 'ld-breadcrumb';

export interface CrumbRef { id: string; name_he: string }

export interface CategoryHead {
  title: string;
  description: string;
  canonical: string;
  noindex: boolean;
  jsonLd: Record<string, unknown>;
}

/** path: department first, ending with the node. filtered: the URL has view parameters. */
export function categoryHead(path: CrumbRef[], count: number | null, filtered: boolean): CategoryHead {
  const node = path[path.length - 1];
  const canonical = node ? `${SUPER_ORIGIN}/categories/${node.id}` : `${SUPER_ORIGIN}/categories`;
  const name = node?.name_he ?? 'קטגוריות';
  const trail = path.map(p => p.name_he).join(' › ');
  const n = count != null && count > 0 ? ` ${count.toLocaleString('he-IL')} מוצרים,` : '';
  const items = [{ '@type': 'ListItem', position: 1, name: 'קטגוריות', item: `${SUPER_ORIGIN}/categories` },
    ...path.map((p, i) => ({ '@type': 'ListItem', position: i + 2, name: p.name_he, item: `${SUPER_ORIGIN}/categories/${p.id}` }))];
  return {
    title: `${name} — השוואת מחירים בכל הרשתות | SUPER XXL`,
    description: `${trail}:${n} המחיר הזול בכל רשת — שופרסל, רמי לוי, יוחננוף, ויקטורי ועוד. השוואה לפי עיר ומבצעים.`,
    canonical,
    noindex: filtered,
    jsonLd: { '@context': 'https://schema.org', '@type': 'BreadcrumbList', itemListElement: items },
  };
}

/** Writes the tags (runs after App's applyRouteMeta for the same path). */
export function applyCategoryHead(h: CategoryHead): void {
  document.title = h.title;
  setMeta('name', 'description', h.description);
  setMeta('property', 'og:title', h.title);
  setMeta('property', 'og:description', h.description);
  setMeta('name', 'twitter:title', h.title);
  setMeta('name', 'twitter:description', h.description);
  let link = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if (!link) {
    link = document.createElement('link');
    link.rel = 'canonical';
    document.head.appendChild(link);
  }
  link.href = h.canonical;
  setMeta('property', 'og:url', h.canonical);
  if (h.noindex) setMeta('name', 'robots', 'noindex');
  else document.head.querySelector('meta[name="robots"]')?.remove();
  let ld = document.head.querySelector<HTMLScriptElement>(`script#${LD_ID}`);
  if (!ld) {
    ld = document.createElement('script');
    ld.type = 'application/ld+json';
    ld.id = LD_ID;
    document.head.appendChild(ld);
  }
  ld.textContent = JSON.stringify(h.jsonLd);
}

export function removeCategoryHead(): void {
  document.head.querySelector(`script#${LD_ID}`)?.remove();
}
