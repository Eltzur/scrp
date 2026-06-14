import { Heart, CheckCircle2 } from 'lucide-react';
import clsx from 'clsx';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import type { ProductWithPrices, PriceQuote, PromoItem } from '../api/client';
import type { PromoMap } from './ResultsList';
import BasketButton from './BasketButton';
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
): { discountPct: number | null; bundleLabel: string | null; buyOneGetOne: boolean } {
  const storePromos = promosByStore?.get(`${q.chain_id}/${q.store_id}`) ?? [];
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

  // Percentage discount — only shown when there is no bundle label for this item.
  const discountPromo = bundleLabel == null
    ? itemPromos.find((p: PromoItem) => p.discount_pct != null && p.discount_pct >= 10)
    : null;
  const discountPct = discountPromo?.discount_pct != null
    ? Math.round(discountPromo.discount_pct)
    : null;

  // 1+1: buy-one-get-one (reward_type=1, min_qty=2).
  const buyOneGetOne = itemPromos.some(
    (p: PromoItem) => p.reward_type === 1 && p.min_qty != null && Math.round(p.min_qty) === 2,
  );

  return { discountPct, bundleLabel, buyOneGetOne };
}

function fmtBundlePrice(price: number): string {
  return price % 1 === 0 ? price.toFixed(0) : price.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
}

export default function ProductCard({ item, promosByStore }: Props) {
  const { t, i18n }   = useTranslation();
  const navigate      = useNavigate();
  const { user }      = useAuth();
  const { isFavorited, toggleFavorite } = useFavorites();

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
                ? 'fill-orange-600 text-orange-600'
                : 'fill-none text-gray-300 hover:text-orange-500',
            )}
          />
        </button>
      </div>

      {/* Name + manufacturer */}
      <div>
        <h3 className="text-gray-900 font-semibold text-sm leading-snug" dir="auto">{displayName}</h3>
        {product.manufacturer && (
          <p className="text-gray-400 text-xs mt-0.5" dir="auto">{product.manufacturer}</p>
        )}
      </div>

      {/* Price rows */}
      <div className="divide-y divide-gray-100 rounded-lg border border-gray-100 overflow-hidden">
        {quotes.map((q, i) => {
          const isCheapest = i === 0 && isComparable;
          const { discountPct, bundleLabel, buyOneGetOne } = getPromoBadges(q, product.item_code, promosByStore);
          return (
            <div
              key={`${q.chain_id}-${q.store_id}`}
              className={clsx(
                'flex items-center justify-between px-3 py-2 text-sm',
                isCheapest ? 'bg-emerald-50' : 'bg-white',
              )}
            >
              {/* Chain + city */}
              <div className="flex items-center gap-1.5 min-w-0">
                {isCheapest && (
                  <CheckCircle2 size={12} className="text-emerald-600 shrink-0" />
                )}
                <span className={clsx('font-medium truncate', isCheapest ? 'text-emerald-800' : 'text-gray-700')}>
                  {q.chain_name ?? q.chain_id}
                </span>
                {q.city && (
                  <span className="text-gray-400 text-xs truncate hidden sm:inline" dir="auto">· {q.city}</span>
                )}
              </div>

              {/* Price + delta + promo badges — always LTR for numerals */}
              <div className="flex items-center gap-1.5 shrink-0 ms-2" dir="ltr">
                <span className={clsx('font-semibold', isCheapest ? 'text-emerald-700' : 'text-gray-800')}>
                  {fmtPrice(q.price)}
                </span>
                {isComparable && !isCheapest && q.delta_from_cheapest > 0 && (
                  <span className="text-xs text-rose-500 font-medium">
                    +{fmtPrice(q.delta_from_cheapest)}
                  </span>
                )}
                {isCheapest && (
                  <span className="text-xs font-semibold text-emerald-600 uppercase tracking-wide hidden sm:inline">
                    {t('product_card.cheapest')}
                  </span>
                )}
                {bundleLabel != null && (
                  <span className="text-xs font-semibold px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700">
                    {bundleLabel}
                  </span>
                )}
                {discountPct != null && (
                  <span className="text-xs font-semibold px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700">
                    -{discountPct}%
                  </span>
                )}
                {buyOneGetOne && (
                  <span className="text-xs font-semibold px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">
                    1+1
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Savings + barcode + basket */}
      <div className="flex items-end justify-between mt-auto gap-2">
        <div className="flex flex-col gap-1 min-w-0">
          {savings > 0.005 && (
            <p className="text-xs text-emerald-600 font-medium" dir="auto">
              {t('product_card.save', {
                amount: fmtPrice(savings),
                pct: savingsPct.toFixed(0),
              })}
            </p>
          )}
          <p className="text-xs text-gray-300 font-mono" dir="ltr">
            {t('product_card.barcode', { code: product.item_code })}
          </p>
        </div>
        <BasketButton
          item_code={product.item_code}
          item_name={displayName}
          is_weighted={product.is_weighted}
        />
      </div>
    </div>
  );
}
