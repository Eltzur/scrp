/**
 * Recent-search normalisation (SU11A-58). Pure; tested by
 * scripts/recent-search.test.mjs (node --test).
 *
 * cleanSearch: what is stored and shown — trimmed, inner whitespace collapsed.
 * searchKey:   when two entries are the same search. Lower case; the text is cut
 *   into words AND at every digit/letter boundary, and the pieces are sorted, so
 *   "זירו 1.5", "זירו1.5" and "1.5זירו" are one entry. Sorting is safe because
 *   search matches every word in any order.
 */
const SPLIT = /(\d+(?:[.,]\d+)*)/;

export function cleanSearch(query: string): string {
  return query.trim().replace(/\s+/g, ' ');
}

export function searchKey(query: string): string {
  return cleanSearch(query)
    .toLowerCase()
    .split(' ')
    .flatMap(w => w.split(SPLIT))
    .filter(Boolean)
    .sort()
    .join(' ');
}

/** Newest first in, newest first out: the first spelling of each key wins. */
export function dedupeSearches(list: unknown[], max: number): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of list) {
    if (typeof raw !== 'string') continue;
    const q = cleanSearch(raw);
    const k = searchKey(q);
    if (q.length < 2 || seen.has(k)) continue;
    seen.add(k);
    out.push(q);
    if (out.length >= max) break;
  }
  return out;
}

/** The list after searching for query: query first, its other spellings gone. */
export function pushSearch(prev: string[], query: string, max: number): string[] {
  return dedupeSearches([query, ...prev], max);
}
