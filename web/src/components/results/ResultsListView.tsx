import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CheckCircle2, ChevronDown, ImageOff } from 'lucide-react';
import clsx from 'clsx';
import type { PriceQuote, ProductWithPrices } from '../../api/client';
import { productImageUrl } from '../../api/client';
import BasketButton from '../BasketButton';
import ProductDetailModal from '../ProductDetailModal';
import { K } from './strings';
import {
  bundleCondition, cheapestPerChain, formatIls, productDisplayName, productSavings,
} from '../../utils/priceDisplay';
import { rowCheapest } from '../../utils/resultViews';

/** Price + its promo condition, as the grid shows it (a bundle never as a bare unit price). */
export function QuotePrice({ q, cheapest, lang }: { q: PriceQuote; cheapest: boolean; lang: string }) {
  const { t } = useTranslation();
  const cond = q.is_promo ? bundleCondition(q) : null;
  return (
    <span className="inline-flex flex-wrap items-center justify-end gap-1.5">
      {q.is_promo && (
        <span className="text-[11px] font-bold px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-800">{t(`${K}.promo`)}</span>
      )}
      {cond && (
        <span className="text-[11px] font-medium px-1.5 py-0.5 rounded bg-amber-50 text-amber-900 border border-amber-300">
          {t(`${K}.bundle`, { qty: cond.qty, total: cond.total })}
        </span>
      )}
      <span dir="ltr" className={clsx('font-semibold tabular-nums', cheapest ? 'text-emerald-800' : 'text-gray-900')}>
        {formatIls(q.price, lang)}
      </span>
    </span>
  );
}

function Thumb({ item }: { item: ProductWithPrices }) {
  const [failed, setFailed] = useState(false);
  // The search payload has no has_image, so the image is asked for lazily (visible rows
  // only, the nginx image zone) and a 404 falls back to the icon.
  if (failed) {
    return (
      <span className="shrink-0 w-10 h-10 rounded-md bg-gray-100 flex items-center justify-center" aria-hidden="true">
        <ImageOff size={16} className="text-gray-500" />
      </span>
    );
  }
  return (
    <img
      src={productImageUrl(item.product.item_code)}
      alt=""
      loading="lazy"
      decoding="async"
      width={40}
      height={40}
      onError={() => setFailed(true)}
      className="shrink-0 w-10 h-10 rounded-md object-contain bg-white border border-gray-200"
    />
  );
}

function Row({ item }: { item: ProductWithPrices }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const [open, setOpen] = useState(false);
  const [details, setDetails] = useState(false);
  const panelId = useId();
  const name = productDisplayName(item.product);
  const quotes = cheapestPerChain(item.quotes);
  const winners = rowCheapest(item, quotes.map(q => q.chain_id));
  const top = quotes[0];
  const { amount: saving } = productSavings(item);

  return (
    <li className="bg-white">
      <h3 className="m-0">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen(o => !o)}
          className="w-full flex items-center gap-3 px-3 py-2.5 text-start hover:bg-gray-50
                     focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-emerald-700"
        >
          <Thumb item={item} />
          <span className="flex-1 min-w-0">
            <span className="block text-sm font-semibold text-gray-900 leading-snug" dir="auto">{name}</span>
            <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-gray-700">
              {top && <span>{t(`${K}.cheapest_at`, { chain: top.chain_name ?? top.chain_id })}</span>}
              <span>{t(`${K}.chains_count`, { count: item.chains_count })}</span>
              {saving > 0.005 && (
                <span className="font-medium px-1.5 py-0.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-300">
                  {t(`${K}.save`, { amount: formatIls(saving, lang) })}
                </span>
              )}
            </span>
          </span>
          {item.cheapest_price != null && (
            <span dir="ltr" className="shrink-0 text-sm font-bold text-gray-900 tabular-nums">{formatIls(item.cheapest_price, lang)}</span>
          )}
          <ChevronDown
            size={18}
            aria-hidden="true"
            className={clsx('shrink-0 text-gray-700 transition-transform', open && 'rotate-180')}
          />
        </button>
      </h3>
      <div id={panelId} role="region" aria-label={t(`${K}.prices_of`, { name })} hidden={!open} className="px-3 pb-3">
        {open && (
          <>
            <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200 overflow-hidden">
              {quotes.map(q => {
                const best = winners.has(q.chain_id);
                return (
                  <li
                    key={`${q.chain_id}-${q.store_id}`}
                    className={clsx('flex items-center justify-between gap-3 px-3 py-2 text-sm', best ? 'bg-emerald-50' : 'bg-white')}
                  >
                    <span className="min-w-0">
                      <span className={clsx('font-medium', best ? 'text-emerald-900' : 'text-gray-800')}>{q.chain_name ?? q.chain_id}</span>
                      {(q.store_name || q.city) && (
                        <span className="block text-[11px] text-gray-700" dir="auto">{q.store_name ?? q.city}</span>
                      )}
                    </span>
                    <span className="flex items-center gap-2 shrink-0">
                      {best && (
                        <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-800">
                          <CheckCircle2 size={12} aria-hidden="true" />
                          {t(`${K}.cheapest`)}
                        </span>
                      )}
                      <QuotePrice q={q} cheapest={best} lang={lang} />
                    </span>
                  </li>
                );
              })}
            </ul>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <BasketButton item_code={item.product.item_code} item_name={name} is_weighted={item.product.is_weighted} />
              <button
                type="button"
                onClick={() => setDetails(true)}
                className="text-sm font-medium text-emerald-800 underline underline-offset-2 hover:text-emerald-900
                           focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 rounded"
              >
                {t(`${K}.all_chains_link`, { count: item.chains_count })}
              </button>
            </div>
          </>
        )}
      </div>
      {details && <ProductDetailModal item={item} initialTab="prices" onClose={() => setDetails(false)} />}
    </li>
  );
}

/** SU11A-72: the list view - a vertical accordion, every row closed by default. */
export default function ResultsListView({ items }: { items: ProductWithPrices[] }) {
  return (
    <ul className="divide-y divide-gray-200 rounded-xl border border-gray-200 overflow-hidden">
      {items.map(it => <Row key={it.product.item_code} item={it} />)}
    </ul>
  );
}
