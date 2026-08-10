import { useState } from 'react';
import { Heart, CheckCircle2, Plus } from 'lucide-react';
import clsx from 'clsx';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import type { ProductWithPrices, PriceQuote, PromoItem } from '../api/client';
import type { PromoMap } from './ResultsList';
import BasketButton from './BasketButton';
import ProductDetailModal from './ProductDetailModal';
import { useAuth } from './AuthContext';
import { useFavorites } from './FavoritesContext';

interface Props {
  item: ProductWithPrices;
  promosByStore?: PromoMap;
}

function cheapestPerChain(quotes: PriceQuote[]): PriceQuote[] {
  const byChain = new Map<string, PriceQuote>();
  for (const q of quotes) {
    const existing = byChain.get(q.chain_id);
    if (!existing || q.price < existing.price) byChain.set(q.chain_id, q);
  }
  return Array.from(byChain.values()).sort((a, b) => a.price - b.price);
}

function getPromoBadges(
  q: PriceQuote,
  itemCode: string,
  promosByStore: PromoMap | undefined,
): { discountPct: number | null; bundleLabel: string | null; promoDesc: string | null } {
  const storePromos = promosByStore?.[`${q.chain_id}/${q.store_id}`] ?? [];
  const itemPromos = storePromos.filter((p: PromoItem) => p.item_code === itemCode);

  // Bundle deal (reward_type=10): "2 ב-60₪" — discount_price is the total for min_qty items.
  const bundlePromo = itemPromos.find(
    (p: PromoItem) =>
      p.reward_type === 10 &&
      p.min_qty != null && p.min_qty >= 2 &&
      p.discount_price != null,
  );
  const bundleLabel = bundlePromo
    ? `${Math.round(bundlePromo.min_qty!)} ב-${fmtBundlePrice(bundlePromo.discount_price!)}₪`
    : null;

  // Percentage discount — show any non-null discount_pct (no threshold).
  const discountPromo = bundleLabel == null
    ? itemPromos.find((p: PromoItem) => p.discount_pct != null)
    : null;
  const discountPct = discountPromo?.discount_pct != null
    ? Math.round(discountPromo.discount_pct)
    : null;

  // A "1+1" badge used to be inferred here from reward_type===1 && min_qty===2.
  // It was WRONG, and removed deliberately — do not reintroduce it. Across
  // 80,461 active rows in 13 chains that combination is an "N for ₪M" bundle
  // ("פיירי סבון 2 ב 18", "דובדבנים 250 גר 2 ב 35", "מרכך בדין 2 ב 30"), never
  // buy-one-get-one: discount_price is the bundle TOTAL for min_qty units, so
  // 2 × ₪9.00 = ₪18.00 against a ₪13.10 shelf price. reward_type is
  // chain-specific and must never be read as a quantity on its own — Victory
  // encodes 1+1 as reward_type=10, not 1. The honest signal is gift_count
  // (IsGiftItem, added in SU10A-7), which /promos/bulk does not return today.
  // Nothing is lost by dropping it: bundleCondition() below already states the
  // deal exactly, as "2 יח' ב-₪18.00 · ₪9.00 ליח'".

  // Fallback: show promo_description for any matched promo not covered above.
  const promoDesc =
    bundleLabel == null && discountPct == null && itemPromos.length > 0
      ? (itemPromos[0].promo_description ?? null)
      : null;

  return { discountPct, bundleLabel, promoDesc };
}

function fmtBundlePrice(price: number): string {
  return price % 1 === 0 ? price.toFixed(0) : price.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
}

/** Condition text for a promo quote.
 *
 *  A bundle must NEVER show a bare per-unit number: "₪3.75" alone reads as the
 *  shelf price of one unit, when in fact it only applies if you buy 8. The
 *  bundle total is COMPUTED (promo_price × promo_min_qty) rather than parsed out
 *  of promo_description, which is freeform chain text and not reliable.
 *  Returns null for single-unit promos, where no quantity condition exists.
 */
function bundleCondition(q: PriceQuote): { total: string; perUnit: string; qty: number } | null {
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

export default function ProductCard({ item, promosByStore }: Props) {
  const { t, i18n }   = useTranslation();
  const navigate      = useNavigate();
  const { user }      = useAuth();
  const { isFavorited, toggleFavorite } = useFavorites();
  const [detailsOpen, setDetailsOpen] = useState(false);

  const { product, cheapest_price, most_expensive_price, chains_count } = item;
  const quotes       = cheapestPerChain(item.quotes);
  const isComparable = chains_count >= 2;
  const barcode      = product.item_code;
  const favorited    = isFavorited(barcode);

  const fmtPrice = (n: number) =>
    new Intl.NumberFormat(i18n.language, { style: 'currency', currency: 'ILS', minimumFractionDigits: 2 })
      .format(n);

  const savings =
    cheapest_price != null && most_expensive_price != null && isComparable
      ? most_expensive_price - cheapest_price
      : 0;
  const savingsPct =
    savings > 0 && most_expensive_price ? (savings / most_expensive_price) * 100 : 0;

  const displayName =
    product.canonical_name ||
    Object.values(product.names_per_chain ?? {})[0] ||
    product.item_code;

  const handleFavClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!user) {
      toast('התחברו כדי לסמן מועדפים', {
        duration: 3000,
        action: {
          label: 'להתחברות',
          onClick: () => navigate('/login'),
        },
      });
      return;
    }
    toggleFavorite(barcode);
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 flex flex-col gap-3 shadow-sm hover:shadow-md transition-shadow">
      {/* Badge row + favorite star */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          {isComparable ? (
            <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
              {t('product_card.chains_count', { count: chains_count })}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
              {t('product_card.only_at', { chain: quotes[0]?.chain_name ?? '' })}
            </span>
          )}
        </div>

        {/* Favorite star */}
        <button
          onClick={handleFavClick}
          className="shrink-0 p-0.5 -mt-0.5 -me-0.5 transition-transform hover:scale-110"
          aria-label={favorited ? 'הסר ממועדפים' : 'הוסף למועדפים'}
        >
          <Heart
            size={16}
            className={clsx(
              'transition-colors',
              favorited
                ? 'fill-orange-700 text-orange-700'
                : 'fill-none text-gray-500 hover:text-orange-700',
            )}
          />
        </button>
      </div>

      {/* Name + manufacturer */}
      <div>
        <h3 className="text-gray-900 font-semibold text-sm leading-snug" dir="auto">{displayName}</h3>
        {product.manufacturer && (
          <p className="text-gray-500 text-xs mt-0.5" dir="auto">{product.manufacturer}</p>
        )}
      </div>

      {/* More-info trigger. Two visual affordances, ONE control: the label and
          the + share a single <button>, so there is one tab stop and one
          accessible name rather than two buttons doing the same thing. */}
      <button
        onClick={() => setDetailsOpen(true)}
        className="self-start inline-flex items-center gap-1.5 text-xs font-medium text-orange-700
                   hover:text-orange-700 hover:bg-orange-50 rounded-lg px-2 py-1 -ms-2 transition-colors"
      >
        <span>{t('product_card.more_info')}</span>
        <Plus size={13} strokeWidth={2.5} className="rounded-full bg-orange-100 text-orange-700 p-[1px]" />
      </button>

      {/* Price rows */}
      <div className="divide-y divide-gray-100 rounded-lg border border-gray-100 overflow-hidden">
        {quotes.map((q, i) => {
          const isCheapest = i === 0 && isComparable;
          const { discountPct, bundleLabel, promoDesc } = getPromoBadges(q, product.item_code, promosByStore);
          const cond = q.is_promo ? bundleCondition(q) : null;
          // A row is promo-bearing if it carries ANY promo signal: the flag on the
          // quote, or a badge derived from promosByStore, which is fetched on a
          // separate path and can be populated while q.is_promo is false. Only
          // these rows get the 3-row treatment — plain cheapest rows are already
          // legible as a single line and are deliberately left alone.
          const hasPromo =
            q.is_promo || promoDesc != null || bundleLabel != null || discountPct != null;
          return (
            <div
              key={`${q.chain_id}-${q.store_id}`}
              className={clsx(
                'px-3 py-2 text-sm',
                isCheapest ? 'bg-emerald-50' : 'bg-white',
              )}
            >
            {hasPromo ? (
              <>
                {/* ROW 1 — chain + price ONLY. Everything else was moved out so
                    this line cannot be crowded at any card width. gap-2 stays
                    load-bearing and the chain stays shrink-0 with no truncate:
                    together those are what keep the name from being squeezed to
                    zero width, which is the bug this row originally had. */}
                <div className="flex items-center justify-between gap-2">
                  <span className={clsx('font-medium shrink-0', isCheapest ? 'text-emerald-800' : 'text-gray-700')}>
                    {q.chain_name ?? q.chain_id}
                  </span>
                  <div className="flex items-center gap-1.5 min-w-0" dir="ltr">
                    {/* Struck shelf price, so the promo price is never mistaken
                        for the ordinary one. */}
                    {q.is_promo && q.shelf_price != null && (
                      <span className="text-xs text-gray-500 line-through">{fmtPrice(q.shelf_price)}</span>
                    )}
                    <span className={clsx('font-semibold', isCheapest ? 'text-emerald-700' : 'text-gray-800')}>
                      {fmtPrice(q.price)}
                    </span>
                  </div>
                </div>

                {/* ROW 2 — promo detail. Wraps freely; this is the row that gives
                    way when content is long, by design. */}
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1" dir="auto">
                  {q.is_promo && (
                    <span className="text-xs font-bold px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700">
                      {t('product_card.promo')}
                    </span>
                  )}
                  {isCheapest && (
                    <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 uppercase tracking-wide">
                      <CheckCircle2 size={12} className="text-emerald-700 shrink-0" />
                      {t('product_card.cheapest')}
                    </span>
                  )}
                  {isComparable && !isCheapest && q.delta_from_cheapest > 0 && (
                    <span className="text-xs text-rose-600 font-medium" dir="ltr">
                      +{fmtPrice(q.delta_from_cheapest)}
                    </span>
                  )}
                  {bundleLabel != null && (
                    <span className="text-xs font-semibold px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700" dir="ltr">
                      {bundleLabel}
                    </span>
                  )}
                  {discountPct != null && (
                    <span className="text-xs font-semibold px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700" dir="ltr">
                      -{discountPct}%
                    </span>
                  )}
                  {cond && (
                    <span
                      className="text-[11px] font-medium px-1.5 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200"
                      title={q.promo_description ?? undefined}
                    >
                      {t('product_card.promo_bundle', { qty: cond.qty, total: cond.total })}
                      <span className="text-amber-700/70">
                        {' · '}{t('product_card.promo_per_unit', { price: cond.perUnit })}
                      </span>
                    </span>
                  )}
                  {/* Freeform chain text of any length — break-words rather than
                      a width cap, since it has a whole row to itself here. */}
                  {promoDesc != null && (
                    <span
                      className="text-[11px] font-semibold px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 max-w-full break-words"
                      title={promoDesc}
                    >
                      {promoDesc}
                    </span>
                  )}
                </div>

                {/* ROW 3 — location only. A promo is store-local, unlike the
                    chain-level shelf quotes, so the branch must be named or the
                    price is not actionable. */}
                {(q.store_name || q.city) && (() => {
                  // Several chains already bake the city into store_name
                  // ("23 כהנמן בני ברק"), so appending it unconditionally
                  // renders "… בני ברק · בני ברק". Only add it when it is
                  // genuinely absent.
                  const cityIsRedundant =
                    q.city != null && (q.store_name ?? '').includes(q.city);
                  const showCity = q.city != null && !cityIsRedundant;
                  return (
                    <div className="mt-1 text-[11px] text-gray-500 break-words" dir="auto">
                      {q.store_name && t('product_card.promo_at_branch', { branch: q.store_name })}
                      {q.store_name && showCity ? ' · ' : null}
                      {showCity ? q.city : null}
                    </div>
                  );
                })()}
              </>
            ) : (
              /* Plain, promo-free row — deliberately left as the single line it
                 already was. gap-2 + shrink-0 chain + min-w-0 price side are the
                 previously-fixed invariants; do not reintroduce truncate here. */
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 shrink-0">
                  {isCheapest && (
                    <CheckCircle2 size={12} className="text-emerald-700 shrink-0" />
                  )}
                  <span className={clsx('font-medium', isCheapest ? 'text-emerald-800' : 'text-gray-700')}>
                    {q.chain_name ?? q.chain_id}
                  </span>
                  {q.city && (
                    <span className="text-gray-500 text-xs hidden sm:inline" dir="auto">· {q.city}</span>
                  )}
                </div>

                <div className="flex flex-wrap items-center justify-end gap-1.5 min-w-0" dir="ltr">
                  <span className={clsx('font-semibold', isCheapest ? 'text-emerald-700' : 'text-gray-800')}>
                    {fmtPrice(q.price)}
                  </span>
                  {isComparable && !isCheapest && q.delta_from_cheapest > 0 && (
                    <span className="text-xs text-rose-600 font-medium">
                      +{fmtPrice(q.delta_from_cheapest)}
                    </span>
                  )}
                  {isCheapest && (
                    <span className="text-xs font-semibold text-emerald-700 uppercase tracking-wide hidden sm:inline">
                      {t('product_card.cheapest')}
                    </span>
                  )}
                </div>
              </div>
            )}
            </div>
          );
        })}
      </div>

      {/* Savings + barcode + basket */}
      <div className="flex items-end justify-between mt-auto gap-2">
        <div className="flex flex-col gap-1 min-w-0">
          {savings > 0.005 && (
            <p className="text-xs text-emerald-700 font-medium" dir="auto">
              {t('product_card.save', {
                amount: fmtPrice(savings),
                pct: savingsPct.toFixed(0),
              })}
            </p>
          )}
          <p className="text-xs text-gray-500 font-mono" dir="ltr">
            {t('product_card.barcode', { code: product.item_code })}
          </p>
        </div>
        <BasketButton
          item_code={product.item_code}
          item_name={displayName}
          is_weighted={product.is_weighted}
        />
      </div>

      {detailsOpen && (
        <ProductDetailModal item={item} onClose={() => setDetailsOpen(false)} />
      )}
    </div>
  );
}
