/**
 * SU11A-65: what a gift-coupon card says ("קופון שמנת חמוצה … 1 יח' מתנה").
 * The server decides WHICH rows are gift coupons (db/query.py
 * _GIFT_COUPON_SQL: a free unit, i.e. no price and a 100% rate, whose
 * promotion description names a coupon) and sends gift_coupon; this only
 * reads the free quantity and the condition for the card. Used by the promos
 * page and the admin promotion card. Never a percentage, never a struck price.
 */
export const GIFT_COUPON_LABEL = 'מתנה בקופון';

export interface GiftCouponView {
  /** Free units: "N יח' מתנה" in the description, else 1 for a single-unit row; null = not stated. */
  qty: number | null;
  /** The condition, e.g. "מעל ₪100" or "בקניית 2 יח' לפחות"; null = none published. */
  condition: string | null;
}

const fmtShekel = (n: number) => `₪${Number.isInteger(n) ? n : n.toFixed(2)}`;

export function giftCouponView(p: {
  promo_description?: string | null;
  min_qty?: number | null;
  min_purchase_amount?: number | null;
}): GiftCouponView {
  const d = p.promo_description ?? '';
  const stated = d.match(/(\d+)\s*(?:יח(?:ידות|ידה)?['׳]?)\s*(?:ב)?מתנה/);
  const qty = stated ? Number(stated[1]) : /יחידה\s+מתנה/.test(d) ? 1
    : (p.min_qty == null || p.min_qty <= 1) ? 1 : null;
  const parts: string[] = [];
  const spend = p.min_purchase_amount != null && p.min_purchase_amount > 0 ? p.min_purchase_amount
    : (() => { const m = d.match(/מעל\s*₪?\s*(\d+(?:\.\d+)?)/); return m ? Number(m[1]) : null; })();
  if (spend != null) parts.push(`מעל ${fmtShekel(spend)}`);
  if (p.min_qty != null && p.min_qty >= 2 && p.min_qty <= 24) parts.push(`בקניית ${Math.round(p.min_qty)} יח' לפחות`);
  return { qty, condition: parts.length ? parts.join(' · ') : null };
}

/** "1 יח' מתנה" (null when the quantity is not stated). */
export function giftQtyText(qty: number | null): string | null {
  return qty == null ? null : `${qty} יח' מתנה`;
}
