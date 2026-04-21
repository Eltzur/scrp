import { Star } from 'lucide-react';
import clsx from 'clsx';
import type { ProductWithPrices, PriceQuote } from '../api/client';

interface Props {
  item: ProductWithPrices;
}

// Group quotes by chain_id, keep cheapest store per chain
function cheapestPerChain(quotes: PriceQuote[]): PriceQuote[] {
  const byChain = new Map<string, PriceQuote>();
  for (const q of quotes) {
    const existing = byChain.get(q.chain_id);
    if (!existing || q.price < existing.price) byChain.set(q.chain_id, q);
  }
  return Array.from(byChain.values()).sort((a, b) => a.price - b.price);
}

function formatPrice(n: number) {
  return `₪${n.toFixed(2)}`;
}

export default function ProductCard({ item }: Props) {
  const { product, cheapest_price, most_expensive_price, chains_count } = item;
  const quotes = cheapestPerChain(item.quotes);
  const isComparable = chains_count >= 2;

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
      {/* Top badges */}
      <div className="flex items-center gap-2 flex-wrap">
        {isComparable ? (
          <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
            {chains_count} chains
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
            Only at {quotes[0]?.chain_name ?? 'one chain'}
          </span>
        )}
      </div>

      {/* Product name + manufacturer */}
      <div>
        <h3 className="text-gray-900 font-semibold text-sm leading-snug">{displayName}</h3>
        {product.manufacturer && (
          <p className="text-gray-400 text-xs mt-0.5">{product.manufacturer}</p>
        )}
      </div>

      {/* Price rows */}
      <div className="divide-y divide-gray-100 rounded-lg border border-gray-100 overflow-hidden">
        {quotes.map((q, i) => {
          const isCheapest = i === 0 && isComparable;
          const chainName = product.names_per_chain?.[q.chain_id]
            ? undefined
            : q.chain_name;
          const rowName = chainName ?? q.chain_name ?? q.chain_id;

          return (
            <div
              key={`${q.chain_id}-${q.store_id}`}
              className={clsx(
                'flex items-center justify-between px-3 py-2 text-sm',
                isCheapest ? 'bg-emerald-50' : 'bg-white',
              )}
            >
              {/* Left: chain + store + city */}
              <div className="flex items-center gap-1.5 min-w-0">
                {isCheapest && (
                  <Star size={12} className="text-emerald-600 shrink-0 fill-emerald-600" />
                )}
                <span className={clsx('font-medium truncate', isCheapest ? 'text-emerald-800' : 'text-gray-700')}>
                  {rowName}
                </span>
                {q.city && (
                  <span className="text-gray-400 text-xs truncate hidden sm:inline">· {q.city}</span>
                )}
              </div>

              {/* Right: price + delta */}
              <div className="flex items-center gap-2 shrink-0 ml-2">
                <span className={clsx('font-semibold', isCheapest ? 'text-emerald-700' : 'text-gray-800')}>
                  {formatPrice(q.price)}
                </span>
                {isComparable && !isCheapest && q.delta_from_cheapest > 0 && (
                  <span className="text-xs text-rose-500 font-medium">
                    +{formatPrice(q.delta_from_cheapest)}
                  </span>
                )}
                {isCheapest && (
                  <span className="text-xs font-semibold text-emerald-600 uppercase tracking-wide hidden sm:inline">
                    cheapest
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Savings + barcode footer */}
      <div className="flex items-end justify-between mt-auto">
        {savings > 0.005 ? (
          <p className="text-xs text-emerald-600 font-medium">
            Save {formatPrice(savings)} ({savingsPct.toFixed(0)}%) vs most expensive
          </p>
        ) : (
          <span />
        )}
        <p className="text-xs text-gray-300 font-mono">{product.item_code}</p>
      </div>
    </div>
  );
}
