/**
 * SU11A-72: the list / comparison-table logic (lazy chunks only): page
 * requests, the per-row cheapest cell, default table columns and the
 * per-chain totals. Preferences: resultViewPrefs.ts.
 */
import type { PriceQuote, ProductWithPrices } from '../api/client';
import { TABLE_DEFAULT_COLUMNS, TABLE_MAX_COLUMNS, type PageSize } from './resultViewPrefs';

export * from './resultViewPrefs';

/** limit / offset of one page; 0 ("הכל") = the endpoint's max in one request. */
export function pageRequest(size: PageSize, page: number, maxLimit: number): { limit: number; offset: number } {
  if (size === 0) return { limit: maxLimit, offset: 0 };
  const limit = Math.min(size, maxLimit);
  return { limit, offset: Math.max(0, page) * limit };
}

/** One quote per chain: the chain's cheapest. */
export function quoteByChain(item: ProductWithPrices): Map<string, PriceQuote> {
  const m = new Map<string, PriceQuote>();
  for (const q of item.quotes) {
    const cur = m.get(q.chain_id);
    if (!cur || q.price < cur.price) m.set(q.chain_id, q);
  }
  return m;
}

/**
 * The chains (among `chains`) holding the row's lowest price; ties all win.
 * Empty when fewer than two of those chains sell it - one price is not a comparison.
 */
export function rowCheapest(item: ProductWithPrices, chains: string[]): Set<string> {
  const by = quoteByChain(item);
  let best = Infinity;
  let sold = 0;
  for (const c of chains) {
    const q = by.get(c);
    if (!q) continue;
    sold += 1;
    if (q.price < best - 1e-9) best = q.price;
  }
  const out = new Set<string>();
  if (sold < 2) return out;
  for (const c of chains) {
    const q = by.get(c);
    if (q && Math.abs(q.price - best) < 1e-9) out.add(c);
  }
  return out;
}

export interface ChainInfo { chain_id: string; name: string; carried: number }

/** Every chain on the page with how many of the page's products it carries, most first, then by name. */
export function pageChains(items: ProductWithPrices[]): ChainInfo[] {
  const m = new Map<string, ChainInfo>();
  for (const it of items) {
    for (const [id, q] of quoteByChain(it)) {
      const cur = m.get(id) ?? { chain_id: id, name: q.chain_name ?? id, carried: 0 };
      cur.carried += 1;
      m.set(id, cur);
    }
  }
  return [...m.values()].sort((a, b) => b.carried - a.carried || a.name.localeCompare(b.name, 'he'));
}

/** The table's columns: the remembered choice (kept in its order) else the top 5 by products carried. */
export function tableColumns(items: ProductWithPrices[], remembered: string[]): string[] {
  if (remembered.length) return remembered.slice(0, TABLE_MAX_COLUMNS);
  return pageChains(items).slice(0, TABLE_DEFAULT_COLUMNS).map(c => c.chain_id);
}

/** Add or remove a chain column; never more than 8, never fewer than 1. */
export function toggleColumn(cols: string[], id: string): string[] {
  if (cols.includes(id)) return cols.length > 1 ? cols.filter(c => c !== id) : cols;
  return cols.length >= TABLE_MAX_COLUMNS ? cols : [...cols, id];
}

export interface ChainTotal { chain_id: string; total: number; missing: number; winner: boolean }

/**
 * Per-chain totals of the listed products. A chain missing any product shows
 * "חסר N" and is never the winner: the cheapest total is marked ONLY among the
 * chains that carry every listed product (ties all win).
 */
export function chainTotals(items: ProductWithPrices[], chains: string[]): ChainTotal[] {
  const maps = items.map(quoteByChain);
  const rows = chains.map(c => {
    let total = 0, missing = 0;
    for (const m of maps) {
      const q = m.get(c);
      if (q) total += q.price; else missing += 1;
    }
    return { chain_id: c, total: Math.round(total * 100) / 100, missing, winner: false };
  });
  const complete = rows.filter(r => r.missing === 0 && items.length > 0);
  if (complete.length) {
    const best = Math.min(...complete.map(r => r.total));
    for (const r of complete) if (Math.abs(r.total - best) < 0.005) r.winner = true;
  }
  return rows;
}
