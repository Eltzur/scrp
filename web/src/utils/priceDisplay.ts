import type { PriceQuote, Product } from '../api/client';

/**
 * Shared price-display helpers (moved out of ProductCard in SU11A-72 so the
 * grid, the list and the comparison table show prices the same way).
 */

/** One quote per chain (its cheapest), cheapest first. */
export function cheapestPerChain(quotes: PriceQuote[]): PriceQuote[] {
  const byChain = new Map<string, PriceQuote>();
  for (const q of quotes) {
    const existing = byChain.get(q.chain_id);
    if (!existing || q.price < existing.price) byChain.set(q.chain_id, q);
  }
  return Array.from(byChain.values()).sort((a, b) => a.price - b.price);
}

/** Condition text for a promo quote.
 *
 *  A bundle must NEVER show a bare per-unit number: "₪3.75" alone reads as the
 *  shelf price of one unit, when in fact it only applies if you buy 8. The
 *  bundle total is COMPUTED (promo_price × promo_min_qty) rather than parsed out
 *  of promo_description, which is freeform chain text and not reliable.
 *  Returns null for single-unit promos, where no quantity condition exists.
 */
export function bundleCondition(q: PriceQuote): { total: string; perUnit: string; qty: number } | null {
  const qty = q.promo_min_qty ?? 1;
  if (!(qty > 1) || q.promo_price == null) return null;
  // 2dp on both: these are money, and fmtBundlePrice strips trailing zeros
  // ("14.9"), which reads wrong next to the ₪14.90 shown elsewhere on the card.
  return {
    qty: Math.round(qty),
    total: (q.promo_price * qty).toFixed(2),
    perUnit: q.promo_price.toFixed(2),
  };
}

/** ₪ with two decimals in the UI language. */
export function formatIls(n: number, lang: string): string {
  return new Intl.NumberFormat(lang, { style: 'currency', currency: 'ILS', minimumFractionDigits: 2 }).format(n);
}

/** The product name the cards show. */
export function productDisplayName(product: Product): string {
  return product.canonical_name || Object.values(product.names_per_chain ?? {})[0] || product.item_code;
}

/** Savings vs the most expensive chain, only for products in 2+ chains. */
export function productSavings(item: { cheapest_price: number | null; most_expensive_price: number | null; chains_count: number }):
  { amount: number; pct: number } {
  const amount = item.cheapest_price != null && item.most_expensive_price != null && item.chains_count >= 2
    ? item.most_expensive_price - item.cheapest_price
    : 0;
  const pct = amount > 0 && item.most_expensive_price ? (amount / item.most_expensive_price) * 100 : 0;
  return { amount, pct };
}
