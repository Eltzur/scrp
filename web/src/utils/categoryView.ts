/**
 * SU11A-67: the category page view, kept in the URL (shareable, Back works).
 * Keys: city ('' = all cities; absent = the remembered city), chain,
 * sort (absent = popular), promo=1. Pure, so it is unit-tested
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
}

export function readCategoryView(p: URLSearchParams): CategoryView {
  const sort = p.get('sort') ?? '';
  return {
    city: p.has('city') ? p.get('city')! : null,
    chain: p.get('chain') ?? '',
    sort: (CATEGORY_SORTS as readonly string[]).includes(sort) ? (sort as CategorySort) : 'popular',
    promo: p.get('promo') === '1',
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
  return next;
}

/** The request for a page: the URL city, else the remembered one ('' = all cities). */
export function itemsRequest(v: CategoryView, remembered: string, offset = 0): CategoryItemsParams {
  const city = v.city ?? remembered;
  return {
    ...(city ? { city } : {}),
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
