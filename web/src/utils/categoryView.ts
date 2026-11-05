/**
 * SU11A-67: the category page view, kept in the URL (shareable, Back works).
 * Keys: city ('' = all cities; absent = the remembered city), chain,
 * sort (absent = popular), promo=1, q (SU11A-68: search inside the category).
 * Pure, so it is unit-tested
 * (scripts/categories-page.test.mjs).
 */
import type { BrowseNode, BrowseTree, CategoryItemsParams } from '../api/categoryBrowse';

export const CATEGORY_SORTS = ['popular', 'cheapest', 'name'] as const;
export type CategorySort = (typeof CATEGORY_SORTS)[number];
export const CATEGORY_PAGE_SIZE = 30;
/** The API's offset cap (db/category_browse.py OFFSET_MAX): no "load more" past it. */
export const CATEGORY_OFFSET_MAX = 2000;

const NODE_ID = /^D\d{2}(\.C\d{2}(\.S\d{2})?)?$/;

export function isNodeId(id: string | undefined): id is string {
  return !!id && NODE_ID.test(id);
}

export interface CategoryView {
  city: string | null;
  chain: string;
  sort: CategorySort;
  promo: boolean;
  q: string;
}

/** Search text the server would use: whitespace collapsed; '' when under 2 characters besides %, _, \
 *  and spaces (the same rule as promosView.promoSearchText and db/query.py clean_promo_q). */
export function categorySearchText(q: string): string {
  const t = q.split(/\s+/).filter(Boolean).join(' ');
  return t.replace(/[%_\\\s]/g, '').length >= 2 ? t : '';
}
/** The API's cap on q (api/routers/categories.py Q_MAX). */
export const CATEGORY_Q_MAX = 100;

export function readCategoryView(p: URLSearchParams): CategoryView {
  const sort = p.get('sort') ?? '';
  return {
    city: p.has('city') ? p.get('city')! : null,
    chain: p.get('chain') ?? '',
    sort: (CATEGORY_SORTS as readonly string[]).includes(sort) ? (sort as CategorySort) : 'popular',
    promo: p.get('promo') === '1',
    q: (p.get('q') ?? '').slice(0, CATEGORY_Q_MAX),
  };
}

/** The URL after a filter change: defaults are left out (popular, no promo, no chain). */
export function categoryParams(prev: URLSearchParams, changes: Partial<CategoryView>): URLSearchParams {
  const v = { ...readCategoryView(prev), ...changes };
  const next = new URLSearchParams();
  if (v.city !== null) next.set('city', v.city);
  if (v.chain) next.set('chain', v.chain);
  if (v.sort !== 'popular') next.set('sort', v.sort);
  if (v.promo) next.set('promo', '1');
  const q = v.q.trim();
  if (q) next.set('q', q.slice(0, CATEGORY_Q_MAX));
  return next;
}

/** The request for a page: the URL city, else the remembered one ('' = all cities). */
export function itemsRequest(v: CategoryView, remembered: string, offset = 0): CategoryItemsParams {
  const city = v.city ?? remembered;
  const q = categorySearchText(v.q);
  return {
    ...(city ? { city } : {}),
    ...(q ? { q } : {}),
    ...(v.chain ? { chain: v.chain } : {}),
    ...(v.sort !== 'popular' ? { sort: v.sort } : {}),
    ...(v.promo ? { on_promo: true } : {}),
    limit: CATEGORY_PAGE_SIZE,
    offset,
  };
}

/** react-query getNextPageParam: the next offset, or undefined at the end / at the API cap. */
export function nextOffset(last: { has_more: boolean; items: unknown[] }, all: { items: unknown[] }[]): number | undefined {
  if (!last.has_more) return undefined;
  const n = all.reduce((acc, pg) => acc + pg.items.length, 0);
  return n <= CATEGORY_OFFSET_MAX ? n : undefined;
}

/** The node in the browse tree (null when it is not listed: unlinked or unknown). */
export function findNode(tree: BrowseTree | undefined, id: string): BrowseNode | null {
  const walk = (ns: BrowseNode[]): BrowseNode | null => {
    for (const n of ns) {
      if (n.id === id) return n;
      if (id.startsWith(n.id + '.')) {
        const hit = walk(n.children);
        if (hit) return hit;
      }
    }
    return null;
  };
  return tree ? walk(tree.departments) : null;
}

/** Display name in the current language (English falls back to Hebrew). */
export function nodeName(n: { name_he: string; name_en: string }, en: boolean): string {
  return en && n.name_en ? n.name_en : n.name_he;
}

/** The filters' URL part, or '' (SEO: a filtered view is noindex, canonical to the clean URL). */
export function hasViewFilters(p: URLSearchParams): boolean {
  return ['city', 'chain', 'sort', 'promo', 'q', 'offset'].some(k => p.has(k));
}

/** SU11A-68 carry-over: the search page with the text and the category preselected. */
export function searchPageUrl(q: string, category?: string): string {
  const p = new URLSearchParams();
  const t = q.trim();
  if (t) p.set('q', t);
  if (category) p.set('category', category);
  const s = p.toString();
  return s ? `/?${s}` : '/';
}

/** The category page for a search text (the search page's "הצג רק ב..." keeps q on the search page instead). */
export function categoryPageUrl(id: string, q = ''): string {
  const t = q.trim();
  return `/categories/${id}` + (t ? `?q=${encodeURIComponent(t)}` : '');
}
