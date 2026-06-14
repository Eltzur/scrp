import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import type { HotPromoItem } from '../api/client';
import { getTodayPromos } from '../api/client';

function fmtPrice(n: number): string {
  return new Intl.NumberFormat('he-IL', { style: 'currency', currency: 'ILS', minimumFractionDigits: 2 }).format(n);
}

function fmtDate(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return `עד ${d.getDate()}.${d.getMonth() + 1}.${d.getFullYear()}`;
}

function PromoBadge({ item }: { item: HotPromoItem }) {
  const isOneForOne = item.reward_type === 1 && item.min_qty != null && Math.round(item.min_qty) === 2;
  if (isOneForOne) {
    return (
      <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">
        1+1
      </span>
    );
  }
  if (item.discount_pct != null) {
    return (
      <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">
        -{Math.round(item.discount_pct)}%
      </span>
    );
  }
  return null;
}

function PromoCard({ item }: { item: HotPromoItem }) {
  const isBundle = item.min_qty != null && item.min_qty > 1;
  const discountedLabel = item.discount_price != null
    ? isBundle
      ? `${Math.round(item.min_qty!)} ב-${fmtPrice(item.discount_price)}`
      : fmtPrice(item.discount_price)
    : null;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 flex flex-col gap-3 shadow-sm hover:shadow-md transition-shadow" dir="rtl">
      {/* Description + badge */}
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-semibold text-gray-900 leading-snug line-clamp-2 flex-1">
          {item.promo_description ?? item.item_code}
        </p>
        <PromoBadge item={item} />
      </div>

      {/* Store info */}
      <div className="flex flex-col gap-0.5">
        <span className="text-xs font-medium text-emerald-700">{item.chain_name}</span>
        <span className="text-xs text-gray-500 truncate">
          {[item.store_name, item.city].filter(Boolean).join(' · ')}
        </span>
      </div>

      {/* Price */}
      <div className="flex items-baseline gap-2 mt-auto">
        {item.item_price != null && (
          <span className="text-sm text-gray-400 line-through">{fmtPrice(item.item_price)}</span>
        )}
        {discountedLabel && (
          <span className="text-base font-bold text-emerald-700">{discountedLabel}</span>
        )}
      </div>

      {/* Expiry */}
      {item.promo_end && (
        <p className="text-[11px] text-gray-300">{fmtDate(item.promo_end)}</p>
      )}
    </div>
  );
}

export default function PromosPage() {
  const [promos, setPromos] = useState<HotPromoItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getTodayPromos().then(data => {
      setPromos(data);
      setLoading(false);
    });
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <main className="max-w-6xl mx-auto px-4 pt-8 pb-24" dir="rtl">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">🔥 מבצעים חמים היום</h1>

        {loading ? (
          <div className="flex justify-center items-center py-24">
            <Loader2 size={32} className="animate-spin text-emerald-500" />
          </div>
        ) : promos.length === 0 ? (
          <p className="text-center text-gray-400 py-24">אין מבצעים זמינים כרגע</p>
        ) : (
          <>
            <p className="text-xs text-gray-400 mb-4">{promos.length} מבצעים פעילים</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {promos.map((item, i) => (
                <PromoCard key={`${item.item_code}-${item.chain_name}-${i}`} item={item} />
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
