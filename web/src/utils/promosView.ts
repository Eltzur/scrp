/**
 * SU11A-60: the promos page view, kept in the URL so a view is shareable and
 * Back works. Keys: city ('' = all cities; absent = not resolved yet), chain,
 * branch, cat, q, sort, bands, types, ending=1.
 */
export type PromosMode = 'start' | 'flat' | 'grouped';

export interface PromosView {
  city: string | null;
  chain: string;
  branch: number | null;
  cat: string;
  q: string;
  sort: string;
  bands: string[];
  types: string[];
  ending: boolean;
}

const csv = (v: string | null) => (v ? v.split(',').filter(Boolean) : []);

/** sorts / bands / types: the allowed values; anything else in the URL is dropped. */
export function readView(p: URLSearchParams, allowed: { sorts: string[]; bands: string[]; types: string[] }): PromosView {
  const branch = p.get('branch');
  const sort = p.get('sort') ?? '';
  return {
    city: p.has('city') ? p.get('city')! : null,
    chain: p.get('chain') ?? '',
    branch: branch && /^\d+$/.test(branch) ? Number(branch) : null,
    cat: p.get('cat') ?? '',
    q: p.get('q') ?? '',
    sort: allowed.sorts.includes(sort) ? sort : allowed.sorts[0],
    bands: csv(p.get('bands')).filter(b => allowed.bands.includes(b)),
    types: csv(p.get('types')).filter(t => allowed.types.includes(t)),
    ending: p.get('ending') === '1',
  };
}

/** Apply changes (null / '' = remove; city keeps '' = all cities). */
export function withChanges(prev: URLSearchParams, changes: Record<string, string | null>): URLSearchParams {
  const next = new URLSearchParams(prev);
  for (const [k, v] of Object.entries(changes)) {
    if (v == null || (v === '' && k !== 'city')) next.delete(k);
    else next.set(k, v);
  }
  return next;
}

/** SU11A-62: the search text as the server reads it (db/query.py
 *  clean_promo_q): whitespace collapsed; '' when under 2 characters besides
 *  %, _, \ and spaces, which is no search (SU11A-63 H2). */
export function promoSearchText(q: string): string {
  const t = q.split(/\s+/).filter(Boolean).join(' ');
  return t.replace(/[%_\\\s]/g, '').length >= 2 ? t : '';
}

/** No list until a chain, a category or search text is chosen; a city alone
 *  is only a scope. No chain: one cross-chain list; a chain: its branches. */
export function promosMode(v: Pick<PromosView, 'chain' | 'cat' | 'q'>): PromosMode {
  if (v.chain) return 'grouped';
  return v.cat || promoSearchText(v.q) ? 'flat' : 'start';
}
