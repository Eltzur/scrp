import { Star } from 'lucide-react';
import clsx from 'clsx';
import { useTranslation } from 'react-i18next';
import type { ProductWithPrices, PriceQuote } from '../api/client';
import BasketButton from './BasketButton';

interface Props {
  item: ProductWithPrices;
}

function cheapestPerChain(quotes: PriceQuote[]): PriceQuote[] {
  const byChain = new Map<string, PriceQuote>();
  for (const q of quotes) {
    const existing = byChain.get(q.chain_id);
    if (!existing || q.price < existing.price) byChain.set(q.chain_id, q);
  }
  return Array.from(byChain.values()).sort((a, b) => a.price - b.price);
}

export default function ProductCard({ item }: Props) {
  const { t, i18n } = useTranslation();
  const { product, cheapest_price, most_expensive_price, chains_count } = item;
  const quotes = cheapestPerChain(item.quotes);
  const isComparable = chains_count >= 2;

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

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 flex flex-col gap-3 shadow-sm hover:shadow-md transition-shadow">
      {/* Badge */}
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
                  <Star size={12} className="text-emerald-600 shrink-0 fill-emerald-600" />
                )}
                <span className={clsx('font-medium truncate', isCheapest ? 'text-emerald-800' : 'text-gray-700')}>
                  {q.chain_name ?? q.chain_id}
                </span>
                {q.city && (
                  <span className="text-gray-400 text-xs truncate hidden sm:inline" dir="auto">· {q.city}</span>
                )}
              </div>

              {/* Price + delta — always LTR for numerals */}
              <div className="flex items-center gap-2 shrink-0 ms-2" dir="ltr">
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
