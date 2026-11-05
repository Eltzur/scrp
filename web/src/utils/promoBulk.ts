/**
 * SU11A-64 (SU11A-63 H1): POST /promos/bulk takes at most BULK_MAX_STORES
 * stores and BULK_MAX_ITEMS barcodes per call (api/routers/promos.py; 422
 * above). The results list asks for the stores of every quote on screen (up to
 * 20 products x 14 chains = 280 a page, more after טען עוד), so a longer list
 * goes in several calls and the answers are merged. item_codes = the barcodes
 * on screen, the only ones ProductCard reads: same badges, far smaller answers.
 */
export const BULK_MAX_STORES = 300;
export const BULK_MAX_ITEMS = 1000;

export type StoreRef = { chain_id: string; store_id: string };
export type BulkBody = { stores: StoreRef[]; item_codes: string[] };

function chunks<T>(a: T[], n: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < a.length; i += n) out.push(a.slice(i, i + n));
  return out;
}

/** The request bodies for these stores and barcodes (none when either is empty). */
export function planPromosBulk(stores: StoreRef[], itemCodes: string[]): BulkBody[] {
  const codes = Array.from(new Set(itemCodes));
  return chunks(stores, BULK_MAX_STORES).flatMap(s =>
    chunks(codes, BULK_MAX_ITEMS).map(c => ({ stores: s, item_codes: c })));
}

/** Merge per-call answers keyed "chain_id/store_id" (a store split across
 *  barcode chunks gets both parts). */
export function mergePromoMaps<T>(parts: Record<string, T[]>[]): Record<string, T[]> {
  const out: Record<string, T[]> = {};
  for (const part of parts) {
    for (const [k, rows] of Object.entries(part)) out[k] = (out[k] ?? []).concat(rows);
  }
  return out;
}
